"""Huawei Router 5G API client."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from huawei_lte_api.enums.device import ControlModeEnum
from huawei_lte_api.enums.sms import BoxTypeEnum, SortTypeEnum
from huawei_lte_api.exceptions import (
    LoginErrorPasswordWrongException,
    LoginErrorUsernameWrongException,
    ResponseErrorException,
    ResponseErrorLoginRequiredException,
)

from .const import REQUEST_TIMEOUT
from .helpers import _safe_int

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
        self._last_activity = datetime.now(UTC)

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
        async with self._lock:
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
        async with self._lock:
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
        """Clear the stored connection and client."""
        self._connection = None
        self._client = None

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
        async with self._lock:
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
                ]
                for key, fetcher in fetch_tasks:
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
        async with self._lock:
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
        async with self._lock:
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
        async with self._lock:
            try:
                await self._execute_with_retry(
                    lambda client: client.monitoring.set_clear_traffic()
                )
            except Exception:
                _LOGGER.exception("Clear traffic failed")
                raise

    async def set_mobile_data(self, enable: bool) -> None:
        """Enable or disable the mobile data connection."""
        async with self._lock:
            try:
                await self._execute_with_retry(
                    lambda client: client.dial_up.set_mobile_dataswitch(
                        1 if enable else 0
                    )
                )
            except Exception:
                _LOGGER.exception("Set mobile data failed")
                raise

    async def set_net_mode(self, mode: str) -> None:
        """Set the preferred network mode."""
        async with self._lock:
            from huawei_lte_api.enums.net import LTEBandEnum, NetworkBandEnum

            try:
                await self._execute_with_retry(
                    lambda client: client.net.set_net_mode(
                        lteband=LTEBandEnum.ALL.value,
                        networkband=NetworkBandEnum.ALL.value,
                        networkmode=mode,
                    )
                )
            except Exception:
                _LOGGER.exception("Set net mode failed")
                raise

    async def set_guest_wifi(self, enable: bool) -> None:
        """Enable or disable the guest WiFi network."""
        async with self._lock:

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
        async with self._lock:
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
        async with self._lock:
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
        async with self._lock:
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
