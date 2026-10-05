"""Huawei Router 5G API client."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
import contextlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import logging
import time
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

import huawei_lte_api
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
from packaging.version import InvalidVersion, Version

from .const import (
    FETCH_DEADLINE,
    LIBRARY_ADDED_ENDPOINTS,
    LOCK_TIMEOUT,
    NET_MODE_SETTLE,
    PROBE_TIMEOUT,
    REQUEST_TIMEOUT,
    WRITE_TIMEOUT,
)
from .helpers import _safe_int, confirm_write

_LOGGER = logging.getLogger(__name__)


def _read_library_version() -> Version | None:
    """Return the version of the `huawei-lte-api` modules in memory, if readable.

    `huawei_lte_api.__version__` is a constant of the loaded modules, so it
    describes what is running and not what is on disk: a guard install can
    change the files while the old classes stay loaded until the next restart.
    `None` when it is absent or unparsable, in which case callers make the call
    and let a real failure surface.
    """
    try:
        return Version(huawei_lte_api.__version__)
    except (AttributeError, InvalidVersion):
        return None


_LIBRARY_VERSION = _read_library_version()


def library_supports(first_version: str) -> bool:
    """Return whether the loaded library is at or above `first_version`.

    True when the version cannot be read, so an unreadable version never hides
    an endpoint.
    """
    return _LIBRARY_VERSION is None or Version(first_version) <= _LIBRARY_VERSION


def _call_added_endpoint(client: Client, key: str) -> Any:
    """Call a library method listed in `LIBRARY_ADDED_ENDPOINTS` by its table row.

    Reached by name so that Mypy passes on a library that lacks the method and
    on one that has it, without a `type: ignore` that is unused on the newer
    one. The two calls are therefore not type-checked; `test_library_contract`
    checks the table's names against the library instead.
    """
    group, method, _ = LIBRARY_ADDED_ENDPOINTS[key]
    return cast("Callable[[], Any]", getattr(getattr(client, group), method))()


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

        # Evidence for the diagnostics download. `coordinator.data` is `None`
        # until the first successful poll, so an integration that has never
        # succeeded produces an empty `data` block — which is exactly when the
        # download is asked for. These two carry what was rejected and what the
        # login saw, and both are sanitized on the way out.
        #
        # Aligned with `zte_router_5g`, which is the reference implementation
        # for this capture: same attribute names, same `verdict` vocabulary,
        # same clearing rule. Two fields it carries have no source here and are
        # absent rather than stubbed — the key presence map, because expiry is
        # stated by the router's own error code rather than inferred from the
        # payload shape, and `body_preview`, because `huaweiapi` parses the
        # response and this wrapper never sees a raw body.
        self.last_rejection: dict[str, Any] | None = None
        self.login_metadata: dict[str, Any] = {}

        # The outcome of every endpoint in the most recent poll, by name.
        #
        # **Absence from the payload has three causes and they are not the
        # same.** An endpoint can be refused by the router, skipped when the
        # fetch deadline expires part way down the list, or fail in a handler
        # that logs and continues. All three leave the key missing from `data`
        # and, without this, leave a reader of the download unable to tell
        # which happened — the confusion `zte_router_5g` named in
        # `[3.3.9-dev10]`, where a refusal was indistinguishable from an
        # eviction. `last_rejection` cannot answer it either: it is bounded to
        # the most recent, so a router refusing five endpoints reports one.
        #
        # Names and codes only, in the shape `diagnostics.py` publishes
        # unchanged. Written per poll, so it describes one pass rather than
        # accumulating across a session.
        self.endpoint_outcomes: dict[str, Any] = {}
        self._unsupported_logged = False

    def _log_unsupported_once(self) -> None:
        """Log, once per client, which endpoints the loaded library cannot serve."""
        if self._unsupported_logged:
            return
        # Called only when an endpoint has just been skipped, so the list is
        # never empty.
        skipped = sorted(
            key
            for key, (_, _, first) in LIBRARY_ADDED_ENDPOINTS.items()
            if not library_supports(first)
        )
        _LOGGER.info(
            "huawei-lte-api %s predates %s; these endpoints are skipped "
            "and read unknown until the library is 2.0.1 or later",
            getattr(huawei_lte_api, "__version__", "unknown"),
            ", ".join(skipped),
        )
        self._unsupported_logged = True

    @asynccontextmanager
    async def _write_deadline(self, operation: str) -> AsyncIterator[None]:
        """Stop waiting for a write that will not finish, and free the lock.

        The gap this closes: no write path had an outer timeout, and
        `asyncio.to_thread` cannot be canceled, so a write whose worker never
        returned held `_lock` with nothing able to release it. Polls and other
        writes then failed at `LOCK_TIMEOUT` one after another while the
        integration stayed unusable until a reload. Canceling the *await*
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

    def _record_login_metadata(self, result: str, error: str | None = None) -> None:
        """Record what the login attempt produced, for diagnostics.

        **Outcome only, and never a credential.** `zte_router_5g` records the
        response's header and cookie names beside this, because it manages its
        own session and can see them. `huaweiapi` owns the session here and
        returns a client or raises, so the response never reaches this wrapper
        and there is nothing further to capture — the reduction is recorded in
        the item's alignment table rather than being an omission.

        `error` carries the exception's class name, never its message: the
        message is library-formatted text that has been observed to interpolate
        the URL, and the class is what a reader needs.
        """
        self.login_metadata = {
            "result": result,
            # **Not "authenticated".** This says whether a username was
            # configured for this entry, which is a fact about the setup rather
            # than about the outcome — `result` carries the outcome. The field
            # was named `authenticated` until 2026-09-07, and a live download
            # showed `"result": "ok"` beside `"authenticated": false` on an
            # entry set up without a username, which reads as a failed login to
            # anyone who did not write the code.
            "username_configured": bool(self.username),
            "error": error,
        }

    async def _login_internal(self) -> None:
        """Perform internal login without locking."""
        self._reset_client()
        try:
            conn, client = await asyncio.to_thread(self._create_connection_sync)
            self._connection = conn
            self._client = client
            self._last_activity = datetime.now(UTC)
            self._record_login_metadata("ok")
        except (
            LoginErrorPasswordWrongException,
            LoginErrorUsernameWrongException,
        ) as err:
            self._connection = None
            self._client = None
            self._record_login_metadata("auth_failed", type(err).__name__)
            raise HuaweiAuthError(f"Authentication failed: {err}") from err
        except Exception as err:
            self._connection = None
            self._client = None
            self._record_login_metadata("connection_failed", type(err).__name__)
            raise HuaweiConnectionError(f"Cannot connect to router: {err}") from err

    def _record_verdict(
        self,
        verdict: str,
        *,
        code: str | None = None,
        key: str | None = None,
        error: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Hold the response behind a non-live verdict, for diagnostics.

        Names and codes only — the payload itself is sanitized by
        `diagnostics.py` on the way out, the same walker that already handles
        `coordinator.data`, so a rejected payload is no more revealing than an
        accepted one. Bounded to the most recent, and cleared by a live verdict
        so a stale rejection cannot outlive the fault.

        Aligned with `zte_router_5g._record_verdict`: same name, same clearing
        rule, same `verdict` vocabulary. `code` replaces that project's key
        presence map, because this router states expiry through its own error
        codes rather than leaving it to be inferred from which keys came back
        blank, and `key` names the endpoint the verdict was drawn at, which is
        per-endpoint here and whole-batch there.
        """
        if verdict == "live":
            self.last_rejection = None
            return

        record: dict[str, Any] = {"verdict": verdict}
        if code is not None:
            record["code"] = code
        if error is not None:
            record["error"] = error
        if key is not None:
            record["key"] = key
        if payload is not None:
            record["payload"] = dict(payload)
        self.last_rejection = record

    def _record_endpoint(
        self,
        key: str,
        outcome: str,
        code: str | None = None,
        *,
        result: Any = None,
        elapsed_ms: int | None = None,
    ) -> None:
        """Record one endpoint's outcome in the current poll's map.

        **`answered` on its own is too coarse to support an unfamiliar
        router.** A call that does not raise is recorded as answered whether it
        returned a full block, an empty mapping, or something that is not a
        mapping at all — and firmware that knows an endpoint, answers it
        politely and populates nothing is the common case on a model this
        integration has not seen. So an answered endpoint also carries how many
        keys came back, how many of them hold a value, and what type the router
        actually returned.

        Names and counts only. No key names and no values reach this map: the
        payload block itself is published beside it in the download and carries
        both, sanitized.
        """
        record: dict[str, Any] = {"outcome": outcome}
        if code is not None:
            record["code"] = code
        if elapsed_ms is not None:
            record["elapsed_ms"] = elapsed_ms
        if outcome == "answered":
            record["type"] = type(result).__name__
            if isinstance(result, dict):
                record["keys"] = len(result)
                record["populated"] = sum(
                    1 for v in result.values() if v not in (None, "", {}, [])
                )
        self.endpoint_outcomes[key] = record

    async def _execute_with_retry(self, func: Callable[[Client], Any]) -> Any:
        """Execute operation on client, retrying once on session expiry."""
        client = await self._ensure_client()
        res = None
        try:
            res = await asyncio.to_thread(lambda: func(client))
            self._last_activity = datetime.now(UTC)
        except (ResponseErrorLoginRequiredException, ResponseErrorException) as err:
            is_expired = isinstance(err, ResponseErrorLoginRequiredException)
            code = str(err.code) if isinstance(err, ResponseErrorException) else None
            if not is_expired and code is not None:
                is_expired = code in ("125002", "125003", "100003")

            # Recorded at the point the verdict is drawn, not at the point of
            # raising, so the expiry below — which is retried and often
            # recovers — still leaves evidence behind. A later live poll
            # clears it, so a rejection in the download is one the integration
            # had not yet recovered from.
            self._record_verdict("expired" if is_expired else "refused", code=code)

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

    # Endpoints this integration does **not** poll, probed once per diagnostics
    # download so a reporter's file says whether their router serves them.
    #
    # **Not added to the poll, deliberately.** The poll runs every 180 seconds
    # and takes about a second across its 26 endpoints; spending forty more
    # round trips per cycle to collect the same refusals for ever is the
    # reasoning already recorded against `monitoring.daily_data_limit`. A
    # download is a deliberate, infrequent act, which is where the cost belongs.
    #
    # Chosen from the 130 read-only, argument-free methods `huawei-lte-api`
    # 2.0.1 exposes, in two groups. The `*_feature_switch` and capability reads
    # come first because they are the router **stating** what it supports
    # rather than us inferring it from a silence. The rest are model-variant
    # reads — a cradle, a second WAN, a locked cell, a SIM PIN state — that
    # this reference device does not have and another might.
    #
    # Reads only. Nothing here writes, and nothing here takes an argument, so
    # no call can be shaped wrongly by a value from this side.
    DIAGNOSTIC_PROBES: tuple[tuple[str, Callable[[Client], Any]], ...] = (
        # --- What the router says it supports --------------------------------
        ("global_module_switch", lambda c: c.global_.module_switch()),
        ("system_devcapacity", lambda c: c.system.devcapacity()),
        ("device_feature_switch", lambda c: c.device.device_feature_switch()),
        ("net_feature_switch", lambda c: c.net.net_feature_switch()),
        (
            "monitoring_statistic_feature_switch",
            lambda c: c.monitoring.statistic_feature_switch(),
        ),
        ("sms_feature_switch", lambda c: c.sms.sms_feature_switch()),
        ("voice_featureswitch", lambda c: c.voice.featureswitch()),
        ("security_feature_switch", lambda c: c.security.feature_switch()),
        ("dhcp_feature_switch", lambda c: c.dhcp.feature_switch()),
        ("cradle_feature_switch", lambda c: c.cradle.feature_switch()),
        # --- Identity and firmware, where the polled reads are restricted ----
        ("device_basic_information", lambda c: c.device.basic_information()),
        ("device_vendorname", lambda c: c.device.vendorname()),
        ("device_boot_time", lambda c: c.device.boot_time()),
        ("device_autorun_version", lambda c: c.device.autorun_version()),
        ("system_deviceinfo", lambda c: c.system.deviceinfo()),
        ("system_deviceinfoex", lambda c: c.system.deviceinfoex()),
        # --- Radio and network detail this integration does not read ---------
        ("net_cell_info", lambda c: c.net.cell_info()),
        ("net_network", lambda c: c.net.network()),
        ("net_register", lambda c: c.net.register()),
        ("net_mode_list", lambda c: c.net.net_mode_list()),
        ("ntwk_celllock", lambda c: c.ntwk.celllock()),
        ("ntwk_dualwaninfo", lambda c: c.ntwk.dualwaninfo()),
        ("ntwk_lan_wan_config", lambda c: c.ntwk.lan_wan_config()),
        ("statistic_feature_roam", lambda c: c.statistic.feature_roam_statistic()),
        # --- SIM state, which explains a device reporting no service ---------
        ("pin_status", lambda c: c.pin.status()),
        ("pin_simlock", lambda c: c.pin.simlock()),
        # --- Antenna, on models that expose a choice -------------------------
        ("device_antenna_status", lambda c: c.device.antenna_status()),
        ("device_antenna_settings", lambda c: c.device.get_antenna_settings()),
        # --- Cradle, for the models that have one ----------------------------
        ("cradle_basic_info", lambda c: c.cradle.basic_info()),
        ("cradle_status_info", lambda c: c.cradle.status_info()),
        # --- Usage vocabularies this device does not answer ------------------
        ("monitoring_daily_data_limit", lambda c: c.monitoring.daily_data_limit()),
        (
            "monitoring_month_statistics_wlan",
            lambda c: c.monitoring.month_statistics_wlan(),
        ),
        ("monitoring_wifi_month_setting", lambda c: c.monitoring.wifi_month_setting()),
        # --- WiFi detail beyond the two blocks the poll reads ----------------
        ("wlan_basic_settings", lambda c: c.wlan.basic_settings()),
        ("wlan_station_information", lambda c: c.wlan.station_information()),
        ("wlan_multi_switch_settings", lambda c: c.wlan.multi_switch_settings()),
        ("wlan_wififrequence", lambda c: c.wlan.wififrequence()),
        ("wlan_wlandbho", lambda c: c.wlan.wlandbho()),
        ("wlan_wlanintelligent", lambda c: c.wlan.wlanintelligent()),
        # --- DHCP, which names the LAN this router is serving ----------------
        ("dhcp_settings", lambda c: c.dhcp.settings()),
        ("dial_up_auto_apn", lambda c: c.dial_up.auto_apn()),
        # --- Named by the survey as where to start ---------------------------
        #
        # `docs/huawei_how_to_access.md` → "Readable, never reviewed" records
        # these as found by an earlier endpoint sweep and never assessed, with
        # the note that the next person should start there rather than re-run
        # the probe. Probing them costs one call each and answers the question
        # that table left open for every model, not only this one.
        #
        # `diagnosis.time_reboot` is the notable one: the reference unit has a
        # scheduled reboot ENABLED, which explains a weekly uptime reset and
        # interacts with reboot detection.
        ("diagnosis_time_reboot", lambda c: c.diagnosis.time_reboot()),
        ("security_get_firewall_switch", lambda c: c.security.get_firewall_switch()),
        ("led_appctrlled", lambda c: c.led.appctrlled()),
        ("online_update_status", lambda c: c.online_update.status()),
        ("sms_config", lambda c: c.sms.config()),
    )

    # Endpoints deliberately absent from `DIAGNOSTIC_PROBES`, so nobody adds
    # them back without knowing why they went.
    #
    # `system.onlinestate` returns a list and `huawei-lte-api` calls `.get()`
    # on it, raising `AttributeError` inside the library before this code sees
    # a response. Measured 2026-09-07. The probe would report a library defect
    # as a property of the router, which is worse than not probing it.
    #
    # `diagnosis.diagnose_ping` and `diagnosis.diagnose_traceroute` ask the
    # router to *perform* a network operation. They read as reads and are not.
    PROBES_EXCLUDED: tuple[tuple[str, str], ...] = (
        ("system.onlinestate", "returns a list the library mishandles"),
        ("diagnosis.diagnose_ping", "runs a ping rather than reading state"),
        (
            "diagnosis.diagnose_traceroute",
            "runs a traceroute rather than reading state",
        ),
    )

    async def probe_diagnostic_endpoints(self) -> dict[str, Any]:
        """Call every `DIAGNOSTIC_PROBES` endpoint once and report what happened.

        **For the diagnostics download only**, and never from the poll. Each
        entry is recorded exactly as a polled endpoint is — `answered` with the
        returned type and key counts, `refused` with the router's own error
        code, or `unavailable` with the exception class — so a reader compares
        the two maps without learning a second vocabulary.

        **Key names are published; values are not.** A name is a property of the
        firmware and is what a supporter needs to see; a value from an endpoint
        nobody here has seen has no entry in `diagnostics.py`'s key lists and
        would be published intact by a sanitizer that matches on exact key
        names. Names and counts carry the finding without that risk.

        One failure never stops the sweep: the whole point is the shape of the
        set of failures, not the first one.

        **Called directly on one established session, never through
        `_execute_with_retry`.** That wrapper re-logs in on
        `ResponseErrorLoginRequiredException`, which `huawei-lte-api` raises for
        `100003` and for no other code — and `100003` is a refusal on this
        firmware, not an expiry. Measured 2026-09-07: a `100003` costs two
        logins through the wrapper against one for any other outcome, and a
        42-endpoint sweep accumulated enough logout/login churn that the router
        began answering `LoginErrorAlreadyLoginException` and then refused
        connections, turning the rest of the sweep into artefacts. The same 42
        calls on one session, called directly, completed in about 900 ms with
        every endpoint returning a real outcome. `docs/huawei_how_to_access.md`
        carries the mechanism, and had already warned that a bulk sweep produces
        false `100003` results.

        A refusal is the finding here, so nothing about it should provoke
        session recovery.
        """
        client = await self._ensure_client()
        results: dict[str, Any] = {}
        for key, call in self.DIAGNOSTIC_PROBES:
            started_at = time.monotonic()
            try:
                value = await asyncio.to_thread(call, client)
            except ResponseErrorException as err:
                results[key] = {"outcome": "refused", "code": str(err.code)}
            except Exception as err:  # noqa: BLE001 - a probe never raises out
                results[key] = {
                    "outcome": "unavailable",
                    "error": type(err).__name__,
                }
            else:
                record: dict[str, Any] = {
                    "outcome": "answered",
                    "type": type(value).__name__,
                    "elapsed_ms": int((time.monotonic() - started_at) * 1000),
                }
                if isinstance(value, dict):
                    record["keys"] = sorted(str(k) for k in value)
                    record["populated"] = sum(
                        1 for v in value.values() if v not in (None, "", {}, [])
                    )
                results[key] = record
        return results

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
                    (
                        "voice_volte",
                        lambda: _call_added_endpoint(client, "voice_volte"),
                    ),
                    (
                        "onekey_diag",
                        lambda: _call_added_endpoint(client, "onekey_diag"),
                    ),
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
                        for name in skipped:
                            self._record_endpoint(name, "skipped")
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

                    added = LIBRARY_ADDED_ENDPOINTS.get(key)
                    if added is not None and not library_supports(added[2]):
                        # Not a fault: the loaded library predates the method.
                        # Recorded apart from `unavailable`, with no rejection
                        # and no entry in `data`, so health does not count it
                        # as a lost capability.
                        self._record_endpoint(key, "unsupported")
                        self._log_unsupported_once()
                        continue

                    try:
                        started_at = time.monotonic()
                        data[key] = fetcher()
                        self._record_endpoint(
                            key,
                            "answered",
                            result=data[key],
                            elapsed_ms=int((time.monotonic() - started_at) * 1000),
                        )
                    except ResponseErrorLoginRequiredException as err:
                        _LOGGER.debug(
                            "Session expired during fetch of %s (%s). Re-logging.",
                            key,
                            err,
                        )
                        self._record_verdict("expired", key=key, payload=data)
                        self._record_endpoint(key, "expired")
                        raise HuaweiAuthError(f"Session expired: {err}") from err
                    except ResponseErrorException as err:
                        if str(err.code) in ("125002", "125003"):
                            _LOGGER.debug(
                                "Session expired during fetch of %s (%s). "
                                "Forcing re-login.",
                                key,
                                err,
                            )
                            self._record_verdict(
                                "expired", code=str(err.code), key=key, payload=data
                            )
                            self._record_endpoint(key, "expired", str(err.code))
                            raise HuaweiAuthError(f"Session expired: {err}") from err

                        # Every path below this line is a rejection, and two of
                        # the three swallow their own error — the endpoint goes
                        # missing from `data` and nothing is raised. Recording
                        # here rather than at the raise is what makes those two
                        # visible in the download at all.
                        self._record_verdict(
                            "refused", code=str(err.code), key=key, payload=data
                        )
                        self._record_endpoint(key, "refused", str(err.code))

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
                        # No error code to carry: the failure came from the
                        # transport or the library rather than from the router
                        # stating a refusal, so the verdict says only that the
                        # endpoint could not be read.
                        self._record_verdict(
                            "unavailable",
                            key=key,
                            error=type(err).__name__,
                            payload=data,
                        )
                        self._record_endpoint(key, "unavailable")

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
            # Cleared before the attempt, not after it. `_fetch` records its
            # own rejections as it goes and two of them do not raise, so
            # clearing on the way out would erase the evidence the poll had
            # just collected. A poll that records nothing therefore leaves this
            # `None`, which is `zte_router_5g`'s "cleared by a live verdict"
            # expressed against a fetch loop that can partially succeed.
            self._record_verdict("live")
            self.endpoint_outcomes = {}
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

        **That is one device's behavior, not a guarantee.** A model that took
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
