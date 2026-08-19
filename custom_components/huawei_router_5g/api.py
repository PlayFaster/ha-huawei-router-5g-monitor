"""Huawei Router 5G API client."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from huawei_lte_api.enums.device import ControlModeEnum
from huawei_lte_api.enums.sms import BoxTypeEnum, SortTypeEnum
from huawei_lte_api.exceptions import (
    LoginErrorAlreadyLoginException,
    LoginErrorPasswordWrongException,
    LoginErrorUsernameWrongException,
    ResponseErrorException,
    ResponseErrorLoginRequiredException,
)

from .const import (
    FETCH_DEADLINE,
    LOCK_TIMEOUT,
    NET_MODE_SETTLE,
    PROBE_TIMEOUT,
    REQUEST_TIMEOUT,
    WRITE_TIMEOUT,
)
from .helpers import _safe_int, confirm_write

_LOGGER = logging.getLogger(__name__)


def _normalize_router_url(host: str) -> str:
    """Normalize a host/URL string to a clean http(s) URL for huawei-lte-api.

    Handles bare IP addresses, optional scheme, uppercase schemes, and trailing
    slashes.  Intentionally avoids the ``url_normalize`` / ``idna`` stack to
    eliminate the UTS46 import-race that can occur during HA startup.
    """
    host = host.strip()
    if "://" not in host:
        host = f"http://{host}"
    parsed = urlparse(host)
    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc, parsed.path.rstrip("/"), "", "", "")
    )


class HuaweiConnectionError(Exception):
    """Raised when the router cannot be reached."""


class HuaweiAuthError(Exception):
    """Raised when login credentials are rejected."""


READ_BACK_ENDPOINTS: dict[str, Callable[[Any], Any]] = {
    "mobile_dataswitch": lambda client: client.dial_up.mobile_dataswitch(),
    "monitoring_status": lambda client: client.monitoring.status(),
    "wlan_multi_basic_settings": lambda client: client.wlan.multi_basic_settings(),
    "net_mode": lambda client: client.net.net_mode(),
}
"""Endpoints a write path may re-read to confirm itself (Section 22).

An explicit map rather than a free-form endpoint name, so a write path cannot
reach an arbitrary part of the router and so the set is reviewable in one
place. Each entry is the **single** call that carries the key the matching
control writes — the point of a read-back is one round trip, not another full
poll.

Deliberately absent: anything a `NEVER`-confirmable write touches. Network
mode and Reconnect both re-establish the connection, so the router answers
abnormally *while succeeding* and a read-back would report a working command
as failed. Those declare their exclusion on the entity instead.
"""


class HuaweiRouter5GAPI:
    """Async wrapper for the huawei-lte-api library."""

    def __init__(
        self,
        host: str,
        username: str | None,
        password: str,
    ) -> None:
        """Initialize the API."""
        self.url = _normalize_router_url(host)
        self.username = username
        self.password = password
        self._connection: Connection | None = None
        self._client: Client | None = None
        self._lock = asyncio.Lock()
        # The task currently holding `_lock`, or None. Tracked so re-entry can
        # be told from ordinary contention: "held by anyone" is the normal
        # case and must keep waiting, "held by me" is a deadlock.
        self._lock_owner: asyncio.Task[Any] | None = None
        self._last_activity = datetime.now(UTC)

    @asynccontextmanager
    async def _write_deadline(self, operation: str) -> AsyncIterator[None]:
        """Stop waiting for a write that will not finish, and free the lock.

        The gap this closes: no write path had an outer timeout, and
        `asyncio.to_thread` cannot be cancelled, so a write whose worker never
        returned held `_lock` with nothing able to release it. Polls and other
        writes then failed at `LOCK_TIMEOUT` one after another while the
        integration stayed unusable until a reload. Cancelling the *await*
        unwinds through `_locked`, whose `finally` releases the lock, so the
        cost is one write rather than the session.

        **Expiry is not a failure, and this deliberately does not raise.** The
        command reached the router and may well have applied; only the waiting
        stopped. Raising here would report a successful write as broken and
        invite the user to repeat a command that already took effect — Section
        22's third outcome, and the same reasoning `confirm_write` uses for
        `None`. The next poll shows the router's actual state.
        """
        try:
            async with asyncio.timeout(WRITE_TIMEOUT):
                yield
        except TimeoutError:
            _LOGGER.warning(
                "%s did not complete within %ss. The command was sent and may "
                "have applied; the next poll will show the router's actual "
                "state. The connection has been released.",
                operation,
                WRITE_TIMEOUT,
            )

    @asynccontextmanager
    async def _locked(self, operation: str) -> AsyncIterator[None]:
        """Acquire the API lock, refusing to wait for ever or on ourselves.

        Two failure modes this replaces, both observed on 2026-08-17 when a
        single network-mode change took the integration offline until Home
        Assistant was restarted:

        **Re-entry.** `asyncio.Lock` is not reentrant, so a path that takes the
        lock and then calls a helper that takes it again waits on itself for
        ever. That is invisible from outside — no exception, no log, no
        recovery — and it survives every reload. Raising `RuntimeError` names
        the file and line the first time the control is used instead. It is
        deliberately an error and not a silent pass-through: this is a
        programming mistake, not a runtime condition.

        **Unbounded waiting.** Once one task was wedged, every later poll and
        button press queued behind it and died at the coordinator's timeout,
        each one reporting a router problem that did not exist. A bounded wait
        turns a permanent silent hang into a loud repeating error naming the
        operation that could not get the lock. See `LOCK_TIMEOUT` for the
        arithmetic behind the bound.
        """
        if self._lock_owner is not None and self._lock_owner is asyncio.current_task():
            raise RuntimeError(
                f"{operation}: the API lock is already held by this task. "
                "A write path must not call a helper that re-acquires the lock."
            )
        try:
            async with asyncio.timeout(LOCK_TIMEOUT):
                await self._lock.acquire()
        except TimeoutError as err:
            raise HuaweiConnectionError(
                f"{operation}: timed out after {LOCK_TIMEOUT}s waiting for the "
                "router API lock"
            ) from err
        self._lock_owner = asyncio.current_task()
        try:
            yield
        finally:
            self._lock_owner = None
            self._lock.release()

    def _create_connection_sync(self) -> tuple[Connection, Client]:
        """Create a new Connection and Client (blocking, runs in thread).

        The Connection constructor triggers login automatically when
        credentials are provided.
        """
        if self.url is None:
            raise ValueError("Router URL is not initialized")
        conn = Connection(
            self.url,
            username=self.username,
            password=self.password,
            timeout=REQUEST_TIMEOUT,
        )
        return conn, Client(conn)

    async def login(self) -> None:
        """Establish a fresh connection to the router."""
        async with self._locked("login"):
            self._reset_client()
            try:
                conn, client = await asyncio.to_thread(self._create_connection_sync)
                self._connection = conn
                self._client = client
                self._last_activity = datetime.now(UTC)
            except (
                LoginErrorPasswordWrongException,
                LoginErrorUsernameWrongException,
            ) as err:
                self._connection = None
                self._client = None
                raise HuaweiAuthError(f"Authentication failed: {err}") from err
            except Exception as err:
                self._connection = None
                self._client = None
                raise HuaweiConnectionError(f"Cannot connect to router: {err}") from err

    async def logout(self) -> None:
        """Log out of the router and release the connection.

        `Connection` has no `logout` method and never has — the previous call
        was `self._connection.logout` under a `# type: ignore[attr-defined]`,
        so it raised `AttributeError` into the debug-level handler below on
        every unload, reload and options change. The session was therefore
        never closed and simply expired on its own TTL, on a router whose
        concurrent-session limit is the reason this class holds a lock at all.
        The real method is `client.user.logout()`.

        Deliberately **not** routed through `_execute_with_retry`: re-logging
        in so a logout can be retried is self-defeating.

        The broad `except` is kept on purpose — a failed logout during teardown
        is not worth propagating, and the connection is discarded either way.
        What stops that swallow hiding a wrong method name again is the library
        contract test, not a narrower catch here.
        """
        async with self._locked("logout"):
            client = self._client
            if client is None:
                self._reset_client()
                return
            try:
                await asyncio.to_thread(client.user.logout)
            except Exception:
                _LOGGER.debug("Logout failed", exc_info=True)
            finally:
                self._reset_client()

    def _reset_client(self) -> None:
        """Close the underlying HTTP session, then clear connection and client.

        **Dropping the references is not enough, and that gap was measurable.**
        `huawei_lte_api` holds a `requests.Session` with a connection pool; a
        session that is only dereferenced leaves its sockets to the garbage
        collector. During a network-mode change the router closes its end while
        re-registering the radio, so those sockets sat in `CLOSE_WAIT` — three
        connections to the router were open while the integration was wedged,
        two of them already half-closed and still eligible to be handed back
        out of the pool.

        Kept synchronous: it is called from `except` blocks and from teardown,
        and `Session.close()` does not block on the network. The broad suppress
        is deliberate — a failed close must never stop the client being
        cleared, which is the part that matters.
        """
        connection = self._connection
        self._connection = None
        self._client = None
        if connection is not None:
            with contextlib.suppress(Exception):
                connection.requests_session.close()

    async def invalidate(self) -> None:
        """Discard the current connection so the next call builds a fresh one.

        For the layer that imposed a timeout to call after it fires.
        `asyncio.timeout` in the coordinator cancels the await from *outside*
        this module, so none of the `_reset_client()` calls in the `except`
        blocks below ever run — the API object keeps its wedged client for ever
        and every later poll reuses it. That is why the lockup survived until a
        Home Assistant restart, and it is not specific to any one bug: any hang
        inside `get_data` produced the same state.

        **Deliberately does not take the lock.** A jammed lock is precisely the
        condition this exists to clear, so waiting for it would be waiting for
        the fault to fix itself.
        """
        self._reset_client()

    async def probe_liveness(self) -> bool | None:
        """Say whether the router answers on a brand-new connection.

        The complaint this answers: the router was reachable from its web GUI,
        from the host and from inside the container, and the integration
        reported everything unavailable with nothing to say which end was at
        fault.

        Three outcomes, and the third exists because this router permits one
        login:

        | Return | Meaning |
        | :-- | :-- |
        | `True` | The router answered a fresh connection while the pooled path failed — **the fault is ours**, and rebuilding fixes it |
        | `False` | A fresh connection failed too — the router really is unreachable, and the existing messaging is right |
        | `None` | The router **refused a second session**. Inconclusive: it is plainly alive enough to refuse, but nothing here can say whether the pooled path is at fault |

        Without the third row a session-limit refusal reads as `False` and
        reports a working router as unreachable — inverting the verdict this
        exists to give. A fresh login was measured succeeding in 0.04 s during
        the 2026-08-17 lockup while three sockets were held, so the refusal
        path is a narrowing rather than the expected case.

        **Does not take the lock**, for the same reason as `invalidate`: the
        lock is one of the things being diagnosed. It logs out and closes the
        session it opens, because this router permits one login and a probe
        that leaked sessions would cause the outage it is investigating. Called
        once per exhausted strike budget, never per poll.
        """

        def _probe() -> None:
            conn, client = self._create_connection_sync()
            try:
                client.device.information()
            finally:
                with contextlib.suppress(Exception):
                    client.user.logout()
                with contextlib.suppress(Exception):
                    conn.requests_session.close()

        try:
            async with asyncio.timeout(PROBE_TIMEOUT):
                await asyncio.to_thread(_probe)
        except LoginErrorAlreadyLoginException:
            # A router with a session already open is answering, not down.
            _LOGGER.debug("Liveness probe refused: a session is already open")
            return None
        except Exception:
            _LOGGER.debug("Liveness probe failed", exc_info=True)
            return False
        return True

    async def _ensure_client(self) -> Client:
        """Create a client if one does not exist."""
        now = datetime.now(UTC)
        if (
            self._client is not None
            and (now - self._last_activity).total_seconds() > 100
        ):
            _LOGGER.debug("Session likely expired due to inactivity; resetting client")
            self._reset_client()

        if self._client is None:
            await self._login_internal()
        if self._client is None:
            raise HuaweiConnectionError("Failed to establish API client connection")
        return self._client

    async def _login_internal(self) -> None:
        """Perform internal login without locking."""
        self._reset_client()
        try:
            conn, client = await asyncio.to_thread(self._create_connection_sync)
            self._connection = conn
            self._client = client
            self._last_activity = datetime.now(UTC)
        except (
            LoginErrorPasswordWrongException,
            LoginErrorUsernameWrongException,
        ) as err:
            self._connection = None
            self._client = None
            raise HuaweiAuthError(f"Authentication failed: {err}") from err
        except Exception as err:
            self._connection = None
            self._client = None
            raise HuaweiConnectionError(f"Cannot connect to router: {err}") from err

    async def _execute_with_retry(self, func: Callable[[Client], Any]) -> Any:
        """Execute operation on client, retrying once on session expiry."""
        client = await self._ensure_client()
        res = None
        try:
            res = await asyncio.to_thread(lambda: func(client))
            self._last_activity = datetime.now(UTC)
        except (ResponseErrorLoginRequiredException, ResponseErrorException) as err:
            is_expired = isinstance(err, ResponseErrorLoginRequiredException)
            if not is_expired and isinstance(err, ResponseErrorException):
                is_expired = str(err.code) in ("125002", "125003", "100003")

            if is_expired:
                _LOGGER.debug(
                    "Session expired during operation. Retrying after re-login."
                )
                self._reset_client()
                client = await self._ensure_client()
                res = await asyncio.to_thread(lambda: func(client))
                self._last_activity = datetime.now(UTC)
            else:
                raise
        return res

    async def get_data(self) -> dict[str, Any]:
        """Fetch all available data from the router."""
        async with self._locked("get_data"):
            await self._ensure_client()

            def _fetch() -> dict[str, Any]:
                data: dict[str, Any] = {}
                client = self._client
                if client is None:
                    raise HuaweiConnectionError("API client not established")

                fetch_tasks: list[tuple[str, Callable[[], Any]]] = [
                    ("device_information", lambda: client.device.information()),
                    ("device_signal", lambda: client.device.signal()),
                    ("monitoring_status", lambda: client.monitoring.status()),
                    (
                        "monitoring_check_notifications",
                        lambda: client.monitoring.check_notifications(),
                    ),
                    (
                        "traffic_statistics",
                        lambda: client.monitoring.traffic_statistics(),
                    ),
                    ("month_statistics", lambda: client.monitoring.month_statistics()),
                    ("current_plmn", lambda: client.net.current_plmn()),
                    ("net_mode", lambda: client.net.net_mode()),
                    ("sms_count", lambda: client.sms.sms_count()),
                    (
                        "sms_list",
                        lambda: client.sms.get_sms_list(
                            page=1,
                            box_type=(
                                BoxTypeEnum.LOCAL_INBOX
                                if (
                                    _safe_int(
                                        data.get("sms_count", {}).get("LocalInbox")
                                    )
                                    or 0
                                )
                                > 0
                                or not _safe_int(
                                    data.get("sms_count", {}).get("SimInbox")
                                )
                                else BoxTypeEnum.SIM_INBOX
                            ),
                            read_count=20,
                            sort_type=SortTypeEnum.DATE,
                            ascending=False,
                            unread_preferred=True,
                        ),
                    ),
                    ("mobile_dataswitch", lambda: client.dial_up.mobile_dataswitch()),
                    ("lan_host_info", lambda: client.lan.host_info()),
                    ("wlan_host_list", lambda: client.wlan.host_list()),
                    (
                        "wlan_wifi_feature_switch",
                        lambda: client.wlan.wifi_feature_switch(),
                    ),
                    (
                        "wlan_multi_basic_settings",
                        lambda: client.wlan.multi_basic_settings(),
                    ),
                    # --- Added 2026-08-15 (status_plan §T-4) ----------------
                    #
                    # Eight endpoints the integration had never called. Each
                    # is non-critical by the rule below: only
                    # `device_information` raises, so a block that fails
                    # leaves its own entities unknown and disturbs nothing
                    # else. That is the whole strike-budget answer for these
                    # — they degrade individually and need no per-entity
                    # `source` declaration.
                    #
                    # `monitoring.daily_data_limit` is deliberately absent:
                    # it answers `100002: No support` on the reference B535,
                    # so calling it would spend a round trip per poll to
                    # collect the same error forever.
                    ("start_date", lambda: client.monitoring.start_date()),
                    ("converged_status", lambda: client.monitoring.converged_status()),
                    ("dial_up_profiles", lambda: client.dial_up.profiles()),
                    ("dial_up_connection", lambda: client.dial_up.connection()),
                    ("antenna_type", lambda: client.device.antenna_type()),
                    ("csps_state", lambda: client.net.csps_state()),
                    ("security_sip", lambda: client.security.sip()),
                    ("security_upnp", lambda: client.security.upnp()),
                    # `voice_busy` returns a bare string ("Idle"), not a dict -
                    # the only block in this payload that does. Anything walking
                    # the payload must tolerate that.
                    ("voice_busy", lambda: client.voice.voicebusy()),
                    ("voice_volte", lambda: client.voice.volte()),
                    ("onekey_diag", lambda: client.monitoring.onekey_diag()),
                ]
                started = time.monotonic()
                for index, (key, fetcher) in enumerate(fetch_tasks):
                    # The deadline is checked between endpoints, never inside
                    # one: a request already in flight cannot be interrupted.
                    # `index` guards the first entry, so `device_information`
                    # is always attempted and the caller always has its
                    # critical block.
                    if index and time.monotonic() - started > FETCH_DEADLINE:
                        skipped = [name for name, _ in fetch_tasks[index:]]
                        _LOGGER.warning(
                            "Fetch reached its %ss deadline after %d of %d "
                            "endpoints; returning what was collected. "
                            "Skipped: %s",
                            FETCH_DEADLINE,
                            index,
                            len(fetch_tasks),
                            ", ".join(skipped),
                        )
                        break

                    try:
                        data[key] = fetcher()
                    except ResponseErrorLoginRequiredException as err:
                        _LOGGER.debug(
                            "Session expired during fetch of %s (%s). Re-logging.",
                            key,
                            err,
                        )
                        raise HuaweiAuthError(f"Session expired: {err}") from err
                    except ResponseErrorException as err:
                        if str(err.code) in ("125002", "125003"):
                            _LOGGER.debug(
                                "Session expired during fetch of %s (%s). "
                                "Forcing re-login.",
                                key,
                                err,
                            )
                            raise HuaweiAuthError(f"Session expired: {err}") from err

                        if key == "device_information":
                            _LOGGER.warning("Critical fetch %s failed: %s", key, err)
                            raise HuaweiConnectionError(
                                f"Critical data fetch failed: {err}"
                            ) from err

                        if key == "sms_list":
                            _LOGGER.warning("Failed to fetch %s: %s", key, err)
                        else:
                            _LOGGER.debug("Failed to fetch %s: %s", key, err)
                    except Exception as err:
                        if key == "device_information":
                            _LOGGER.warning("Critical fetch %s failed: %s", key, err)
                            raise HuaweiConnectionError(
                                f"Critical data fetch failed: {err}"
                            ) from err
                        if key == "sms_list":
                            _LOGGER.warning("Failed to fetch %s: %s", key, err)
                        else:
                            _LOGGER.debug("Failed to fetch %s: %s", key, err)

                return data

            res = None
            try:
                res = await asyncio.to_thread(_fetch)
                self._last_activity = datetime.now(UTC)
            except HuaweiAuthError:
                self._reset_client()
                raise
            except Exception as err:
                _LOGGER.exception("Failed to fetch router data")
                self._reset_client()
                raise HuaweiConnectionError(f"Data fetch failed: {err}") from err
            return res

    async def reboot(self) -> None:
        """Reboot the router.

        Uses `set_control(ControlModeEnum.REBOOT)` rather than the older
        `device.reboot()`. Both exist in `huawei-lte-api` 1.11.0; **2.0.0
        removes `reboot()` and `control()`**, keeping only `set_control`. So
        this spelling is correct on both versions and the library bump needs no
        code change here.
        """
        async with self._write_deadline("reboot"), self._locked("reboot"):
            try:
                await self._execute_with_retry(
                    lambda client: client.device.set_control(ControlModeEnum.REBOOT)
                )
                self._reset_client()
            except Exception:
                _LOGGER.exception("Reboot failed")
                self._reset_client()
                raise

    async def reconnect(self) -> None:
        """Drop and re-establish the mobile data session.

        This is the router GUI's advanced-settings Reconnect, and it is not
        Reboot: the device stays up, only the data session cycles.

        **`net/reconnect` does not work on this hardware.** The library exposes
        `client.net.reconnect()` and the router advertises the feature
        (`net_feature_switch.reconnect_switch` is `1`), but the call is refused
        with `-1: Unknown`. Verified against a live B535 on 2026-08-15, both
        through Home Assistant and directly. The method existing in the library
        says nothing about the device accepting it.

        What the router does accept is `dialup/dial`, in two steps. Measured on
        the same device: `CurrentConnectTime` went 3893 -> 4 -> 10, so the
        session genuinely cycles, and it was back inside five seconds.

        `Action: 0` has no public wrapper - `DialUp.dial()` hardcodes
        `Action: 1` - so the disconnect reaches through `_session.post_set`
        under a reasoned `# noqa: SLF001`. The connect half uses the public
        method.
        """
        async with self._write_deadline("reconnect"), self._locked("reconnect"):
            try:
                await self._execute_with_retry(
                    lambda client: client.dial_up._session.post_set(  # noqa: SLF001
                        "dialup/dial", {"Action": 0}
                    )
                )
                await self._execute_with_retry(lambda client: client.dial_up.dial())
                self._reset_client()
            except Exception:
                _LOGGER.exception("Reconnect failed")
                self._reset_client()
                raise

    async def clear_traffic_statistics(self) -> None:
        """Clear the traffic statistics counters.

        The method is `set_clear_traffic()`. `Monitoring.clear_traffic()` does
        not exist in `huawei-lte-api` 1.11.0 or 2.0.0 and never has, so this
        button could not work: the call raised `AttributeError` under a
        `# type: ignore[attr-defined]`, and the test asserting it passed only
        because it ran against a bare `MagicMock`.
        """
        async with (
            self._write_deadline("clear_traffic_statistics"),
            self._locked("clear_traffic_statistics"),
        ):
            try:
                await self._execute_with_retry(
                    lambda client: client.monitoring.set_clear_traffic()
                )
            except Exception:
                _LOGGER.exception("Clear traffic failed")
                raise

    async def read_back(self, endpoint: str) -> dict[str, Any] | None:
        """Re-read one endpoint to confirm a write, or None if it cannot be read.

        Section 22's targeted read-back. The alternative is
        `coordinator.async_force_refresh()`, which is debounced by up to ten
        seconds and fetches all 26 endpoints to learn one key — during which
        the frontend's optimistic toggle springs back and then corrects
        itself.

        **Returns None rather than raising, and that distinction carries the
        whole design.** A write that succeeded followed by a read that failed
        is *unverified*, not failed. Raising here would collapse the two, and
        every transient blip would report a real write as an error and invite
        the user to repeat a command that has already taken effect.

        Only endpoints in `READ_BACK_ENDPOINTS` are permitted, so a caller
        cannot quietly reach an arbitrary part of the router from a write path.
        """
        reader = READ_BACK_ENDPOINTS.get(endpoint)
        if reader is None:
            raise ValueError(f"no read-back reader for endpoint {endpoint!r}")

        async with self._locked("read_back"):
            try:
                result = await self._execute_with_retry(reader)
            except Exception:
                # Debug, not exception: this is an expected outcome on a busy
                # router and is not a fault the user needs to see.
                _LOGGER.debug("Read-back of %s failed", endpoint, exc_info=True)
                return None

        return result if isinstance(result, dict) else None

    async def set_mobile_data(self, enable: bool) -> None:
        """Enable or disable the mobile data connection."""
        async with (
            self._write_deadline("set_mobile_data"),
            self._locked("set_mobile_data"),
        ):
            try:
                await self._execute_with_retry(
                    lambda client: client.dial_up.set_mobile_dataswitch(
                        1 if enable else 0
                    )
                )
            except Exception:
                _LOGGER.exception("Set mobile data failed")
                raise

    async def _band_arguments(self) -> tuple[str, str]:
        """Return the LTE and network band masks to send with a mode change.

        `net/net-mode` takes all three fields together, so a mode change must
        supply bands as well. This previously sent `LTEBandEnum.ALL` and
        `NetworkBandEnum.ALL` — **library constants, never checked against the
        device.** On the reference H165-383 that is harmless because the router
        clamps: after writing `ALL` it reported `LTEBand=7A0880800D5`, its own
        supported mask, and a `NetworkBand` matching neither the value sent nor
        anything in its published list.

        **That is one device's behaviour, not a guarantee.** A model that took
        the value literally would have every mode change silently widen or reset
        whatever band selection the user had made. So the router's *current*
        bands are read and sent back unchanged, which asks it to keep what it
        has rather than asserting a value from a table.

        Falls back to the library constants only when the read fails, since a
        mode change that cannot name any band is worse than one using the old
        assumption.
        """
        from huawei_lte_api.enums.net import LTEBandEnum, NetworkBandEnum

        fallback = (f"{LTEBandEnum.ALL.value:x}", f"{NetworkBandEnum.ALL.value:x}")
        try:
            current = await self._execute_with_retry(
                lambda client: client.net.net_mode()
            )
        except Exception:
            _LOGGER.debug("Could not read current bands; sending ALL", exc_info=True)
            return fallback

        lteband = str(current.get("LTEBand") or "") or fallback[0]
        networkband = str(current.get("NetworkBand") or "") or fallback[1]
        return lteband, networkband

    async def get_supported_net_modes(self) -> list[str] | None:
        """Return the mode codes this router accepts, or None if it will not say.

        `net.net_mode_list()` publishes `AccessList.Access` — on the reference
        H165-383, `["00", "08", "03"]`, exactly the three its web interface
        offers. The select previously offered eight modes taken from the
        library's enum, five of which **this router rejects**, and omitted the
        one it was actually in.

        Read once at setup rather than polled: it is static configuration, and
        a mode set only changes with a firmware update.
        """
        try:
            listing = await self._execute_with_retry(
                lambda client: client.net.net_mode_list()
            )
        except Exception:
            _LOGGER.debug("net_mode_list unavailable", exc_info=True)
            return None

        access = (listing or {}).get("AccessList", {}).get("Access")
        if isinstance(access, str):
            access = [access]
        if not isinstance(access, list) or not access:
            return None
        return [str(code) for code in access]

    async def set_net_mode(self, mode: str) -> None:
        """Set the preferred network mode.

        **The router sometimes applies the change and then answers the POST
        with `-1: Unknown`.** Verified on a live B535 / H165-383 on 2026-08-16:
        starting from `03` (4G Only), a write of `00` (Auto) raised, and the
        router's own web interface showed Auto immediately afterwards. The same
        error surfaces in Home Assistant when the Network Mode select is used.

        **It does not do this every time, and an earlier version of this
        docstring said it did.** On 2026-08-19 the hardware check wrote `03`
        from `00` and the router accepted it outright, with no `-1` at all.
        What decides it is not established — direction, starting mode and radio
        state are all candidates and none has been isolated. So the `-1` branch
        below is an occasional path, not the normal one, and a run that never
        enters it has not exercised it.

        The cause is the one already documented on that select: setting the mode
        drops and re-registers the radio, and the router answers abnormally
        while it does. That was known, but the conclusion drawn from it was that
        only a *read-back* would be unreliable. The POST response is unreliable
        for the same reason and cannot be trusted on its own.

        So `-1` is not treated as a refusal. It means **applied, response
        unverifiable** — the radio state is settled for and `net_mode` re-read,
        and that read decides the outcome. A genuine refusal also returns `-1`,
        and the read-back is what separates the two.
        """
        async with self._write_deadline("set_net_mode"):
            unverified: ResponseErrorException | None = None

            async with self._locked("set_net_mode"):
                lteband, networkband = await self._band_arguments()

                try:
                    await self._execute_with_retry(
                        lambda client: client.net.set_net_mode(
                            lteband=lteband,
                            networkband=networkband,
                            networkmode=mode,
                        )
                    )
                except ResponseErrorException as err:
                    if str(err.code) != "-1":
                        _LOGGER.exception("Set net mode failed")
                        raise
                    unverified = err
                except Exception:
                    _LOGGER.exception("Set net mode failed")
                    raise

            if unverified is None:
                return

            # Outside the lock, and that is the whole point. `confirm_write` calls
            # `read_back`, which acquires the same non-reentrant lock — doing this
            # inside the block above meant the task waited on itself for ever and
            # the integration never polled again. `switch.py` had it right all
            # along: confirm after the API call has returned and released.
            _LOGGER.debug(
                "Set net mode answered -1 while re-registering; confirming by read-back"
            )
            await asyncio.sleep(NET_MODE_SETTLE)
            confirmed = await confirm_write(
                self,
                "net_mode",
                lambda block: block.get("NetworkMode"),
                mode,
                label="set_net_mode",
            )
            if confirmed is False:
                _LOGGER.error("Set net mode was refused by the router")
                raise unverified
            if confirmed is None:
                _LOGGER.warning(
                    "Set net mode could not be confirmed; the router did "
                    "not answer the read-back. The change may have applied."
                )

    async def set_wifi(self, enable: bool) -> None:
        """Turn the WiFi radios on or off.

        **This is the master switch, and it is a different level from the guest
        network.** The router keeps radio state in `wlan/status-switch-settings`
        and per-SSID state in `wlan/multi-basic-settings`; the SSID flags are
        gated by the radio, so writing them while the radio is off changes
        nothing. An earlier attempt at this control worked at the SSID level
        and could not turn WiFi on, which is why.

        **The library's own helper does not work here.**
        `client.wlan.wifi_network_switch()` builds its payload from
        `find_wlan_settings`/`save_wlan_settings` and the router answers
        `100005: Request format error`. Verified on a live B535, 2026-08-15.

        What works is round-tripping the endpoint's own GET response with
        `wifienable` flipped - the same pattern as `set_guest_wifi`, and for the
        same reason: the response carries fields we neither understand nor need
        to, and a payload built from scratch drops them.

        Measured both directions on the same device: radios `0,0 -> 1,1` with
        `WifiStatus` `0 -> 1`, and back. The SSIDs follow the radio on their
        own - enabling brought up the two primaries and left the guest and
        secondary networks off, which is the router remembering their state
        rather than anything this write sets.
        """
        async with self._write_deadline("set_wifi"):

            def _write(client: Client) -> None:
                """Read the radio block, flip every radio, write it back whole."""
                settings = client.wlan.status_switch_settings()
                radios = settings.get("radios", {}).get("radio", [])
                if isinstance(radios, dict):
                    radios = [radios]
                if not radios:
                    # A router with no radios to switch is not a write failure to
                    # retry; it means this model does not expose the endpoint the
                    # way the reference B535 does.
                    raise HuaweiConnectionError(
                        "Router returned no WiFi radios to switch"
                    )
                for radio in radios:
                    radio["wifienable"] = "1" if enable else "0"
                settings["radios"] = {"radio": radios}
                client.wlan._session.post_set(  # noqa: SLF001
                    "wlan/status-switch-settings", settings
                )

            async with self._locked("set_wifi"):
                try:
                    await self._execute_with_retry(_write)
                except Exception:
                    _LOGGER.exception("Set WiFi failed")
                    raise

    async def set_guest_wifi(self, enable: bool) -> None:
        """Enable or disable the guest WiFi network."""
        async with (
            self._write_deadline("set_guest_wifi"),
            self._locked("set_guest_wifi"),
        ):

            def _set(client: Client) -> None:
                multi_settings = client.wlan.multi_basic_settings()
                ssids = multi_settings.get("Ssids", {}).get("Ssid", [])
                if isinstance(ssids, dict):
                    ssids = [ssids]

                found = False
                for ssid in ssids:
                    if str(ssid.get("wifiisguestnetwork")) == "1":
                        ssid["WifiEnable"] = "1" if enable else "0"
                        found = True
                        break

                if not found:
                    _LOGGER.warning(
                        "No guest SSID (wifiisguestnetwork=1) found; known SSIDs: %s",
                        [s.get("WifiSsid") for s in ssids],
                    )
                    raise RuntimeError("No guest SSID found in router response")

                # Send back the full original payload so no required fields are dropped.
                payload = dict(multi_settings)
                payload["WifiRestart"] = "1"

                _LOGGER.debug(
                    "Setting guest WiFi %s; payload keys: %s",
                    "enabled" if enable else "disabled",
                    list(payload.keys()),
                )
                try:
                    # SLF001, and deliberately NOT `wlan.set_multi_basic_settings()`.
                    #
                    # A public setter does exist — an earlier comment here claimed
                    # otherwise and was wrong. But it discards the payload:
                    #
                    #     post_set('wlan/multi-basic-settings',
                    #              {'Ssids': {'Ssid': clients}, 'WifiRestart': 1})
                    #
                    # It sends `Ssids` and nothing else. Probed against a live
                    # B535 on 2026-08-14, the GET returns three top-level keys —
                    # `Ssids`, `DbhoEnable` and `modify_guest_ssid` — so calling
                    # the public setter would drop band-steering and guest-SSID
                    # state on every guest-WiFi toggle, silently.
                    #
                    # Round-tripping the whole GET response is therefore the
                    # correct behavior, not a shortcut. The AttributeError
                    # handler below guards the library changing its internals.
                    client.wlan._session.post_set(  # noqa: SLF001
                        "wlan/multi-basic-settings", payload
                    )
                except AttributeError as err:
                    raise RuntimeError(
                        "huawei_lte_api internal API changed; "
                        "update integration or library"
                    ) from err

            try:
                await self._execute_with_retry(_set)
            except Exception:
                _LOGGER.exception("Set guest WiFi failed")
                raise

    async def send_sms(self, phone_numbers: list[str], message: str) -> None:
        """Send an SMS message to one or more numbers."""
        async with self._write_deadline("send_sms"), self._locked("send_sms"):
            try:
                await self._execute_with_retry(
                    lambda client: client.sms.send_sms(
                        phone_numbers=phone_numbers,
                        message=message,
                    )
                )
            except Exception:
                _LOGGER.exception("Send SMS failed")
                raise

    async def delete_sms(self, index: int) -> None:
        """Delete an SMS message by index."""
        async with self._write_deadline("delete_sms"), self._locked("delete_sms"):
            try:
                await self._execute_with_retry(
                    lambda client: client.sms.delete_sms(sms_id=index)
                )
            except Exception:
                _LOGGER.exception("Delete SMS failed")
                raise

    async def get_sms_list(
        self,
        page: int = 1,
        box_type: BoxTypeEnum = BoxTypeEnum.LOCAL_INBOX,
        read_count: int = 20,
    ) -> dict[str, Any]:
        """Fetch a list of SMS messages."""
        async with self._locked("get_sms_list"):
            try:
                return cast(
                    dict[str, Any],
                    await self._execute_with_retry(
                        lambda client: client.sms.get_sms_list(
                            page=page,
                            box_type=box_type,
                            read_count=read_count,
                            sort_type=SortTypeEnum.DATE,
                            ascending=False,
                            unread_preferred=True,
                        )
                    ),
                )
            except Exception:
                _LOGGER.exception("Get SMS list failed")
                raise
