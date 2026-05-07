"""Huawei Router 5G API client."""

import asyncio
import logging
from typing import Any

from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from huawei_lte_api.enums.sms import BoxTypeEnum, SortTypeEnum
from huawei_lte_api.exceptions import (
    LoginErrorPasswordWrongException,
    LoginErrorUsernameWrongException,
    ResponseErrorException,
    ResponseErrorLoginRequiredException,
)
from url_normalize import url_normalize

from .helpers import _safe_int

_LOGGER = logging.getLogger(__name__)


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
        self.url = url_normalize(host, default_scheme="http")
        self.username = username
        self.password = password
        self._connection: Connection | None = None
        self._client: Client | None = None
        self._lock = asyncio.Lock()

    def _create_connection_sync(self) -> tuple[Connection, Client]:
        """Create a new Connection and Client (blocking, runs in thread).

        The Connection constructor triggers login automatically when
        credentials are provided.
        """
        conn = Connection(
            self.url,
            username=self.username,
            password=self.password,
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
        """Logout and release the connection."""
        async with self._lock:
            if self._connection is None:
                return
            try:
                await asyncio.to_thread(self._connection.logout)
            except Exception as err:
                _LOGGER.debug("Logout failed: %s", err)
            finally:
                self._reset_client()

    def _reset_client(self) -> None:
        """Clear the stored connection and client."""
        self._connection = None
        self._client = None

    async def _ensure_client(self) -> None:
        """Create a client if one does not exist."""
        if self._client is None:
            await self._login_internal()

    async def _login_internal(self) -> None:
        """Perform internal login without locking."""
        self._reset_client()
        try:
            conn, client = await asyncio.to_thread(self._create_connection_sync)
            self._connection = conn
            self._client = client
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

    async def get_data(self) -> dict[str, Any]:
        """Fetch all available data from the router."""
        async with self._lock:
            await self._ensure_client()

            def _fetch() -> dict[str, Any]:
                data: dict[str, Any] = {}
                client = self._client

                for key, fetcher in [
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
                ]:
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

            try:
                return await asyncio.to_thread(_fetch)
            except HuaweiAuthError:
                self._reset_client()
                raise
            except Exception as err:
                _LOGGER.exception("Failed to fetch router data")
                self._reset_client()
                raise HuaweiConnectionError(f"Data fetch failed: {err}") from err

    async def reboot(self) -> None:
        """Reboot the router."""
        async with self._lock:
            await self._ensure_client()
            try:
                await asyncio.to_thread(self._client.device.reboot)
                self._reset_client()
            except Exception:
                _LOGGER.exception("Reboot failed")
                self._reset_client()
                raise

    async def clear_traffic_statistics(self) -> None:
        """Clear the traffic statistics counters."""
        async with self._lock:
            await self._ensure_client()
            try:
                await asyncio.to_thread(self._client.monitoring.clear_traffic)
            except Exception:
                _LOGGER.exception("Clear traffic failed")
                raise

    async def set_mobile_data(self, enable: bool) -> None:
        """Enable or disable the mobile data connection."""
        async with self._lock:
            await self._ensure_client()

            def _set() -> None:
                self._client.dial_up.set_mobile_dataswitch(1 if enable else 0)

            try:
                await asyncio.to_thread(_set)
            except Exception:
                _LOGGER.exception("Set mobile data failed")
                raise

    async def set_net_mode(self, mode: str) -> None:
        """Set the preferred network mode."""
        async with self._lock:
            await self._ensure_client()

            from huawei_lte_api.enums.net import LTEBandEnum, NetworkBandEnum

            def _set() -> None:
                self._client.net.set_net_mode(
                    lte_band=LTEBandEnum.ALL.value,
                    network_band=NetworkBandEnum.ALL.value,
                    network_mode=mode,
                )

            try:
                await asyncio.to_thread(_set)
            except Exception:
                _LOGGER.exception("Set net mode failed")
                raise

    async def set_guest_wifi(self, enable: bool) -> None:
        """Enable or disable the guest WiFi network."""
        async with self._lock:
            await self._ensure_client()

            def _set() -> None:
                multi_settings = self._client.wlan.multi_basic_settings()
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
                    self._client.wlan._session.post_set(
                        "wlan/multi-basic-settings", payload
                    )
                except AttributeError as err:
                    raise RuntimeError(
                        "huawei_lte_api internal API changed; "
                        "update integration or library"
                    ) from err

            try:
                await asyncio.to_thread(_set)
            except Exception:
                _LOGGER.exception("Set guest WiFi failed")
                raise

    async def send_sms(self, phone_numbers: list[str], message: str) -> None:
        """Send an SMS message to one or more numbers."""
        async with self._lock:
            await self._ensure_client()

            try:
                await asyncio.to_thread(
                    self._client.sms.send_sms,
                    phone_numbers=phone_numbers,
                    message=message,
                )
            except Exception:
                _LOGGER.exception("Send SMS failed")
                raise

    async def delete_sms(self, index: int) -> None:
        """Delete an SMS message by index."""
        async with self._lock:
            await self._ensure_client()

            try:
                await asyncio.to_thread(self._client.sms.delete_sms, sms_id=index)
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
            await self._ensure_client()

            try:
                return await asyncio.to_thread(
                    self._client.sms.get_sms_list,
                    page=page,
                    box_type=box_type,
                    read_count=read_count,
                    sort_type=SortTypeEnum.DATE,
                    ascending=False,
                    unread_preferred=True,
                )
            except Exception:
                _LOGGER.exception("Get SMS list failed")
                raise
