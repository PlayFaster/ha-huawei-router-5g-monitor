"""Huawei Router 5G API client."""

import asyncio
import logging
from typing import Any

from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from url_normalize import url_normalize

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
        await self._reset_client()
        try:
            conn, client = await asyncio.to_thread(self._create_connection_sync)
            self._connection = conn
            self._client = client
        except Exception as err:
            self._connection = None
            self._client = None
            err_lower = str(err).lower()
            if any(
                k in err_lower
                for k in ("password", "credentials", "unauthori", "wrong", "403")
            ):
                raise HuaweiAuthError(f"Authentication failed: {err}") from err
            raise HuaweiConnectionError(f"Cannot connect to router: {err}") from err

    async def logout(self) -> None:
        """Logout and release the connection."""
        if self._connection is None:
            return
        try:
            await asyncio.to_thread(self._connection.logout)
        except Exception as err:
            _LOGGER.debug("Logout failed: %s", err)
        finally:
            await self._reset_client()

    async def _reset_client(self) -> None:
        """Clear the stored connection and client."""
        self._connection = None
        self._client = None

    async def _ensure_client(self) -> None:
        """Create a client if one does not exist."""
        if self._client is None:
            await self.login()

    async def get_data(self) -> dict[str, Any]:
        """Fetch all available data from the router."""
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
                ("traffic_statistics", lambda: client.monitoring.traffic_statistics()),
                ("month_statistics", lambda: client.monitoring.month_statistics()),
                ("current_plmn", lambda: client.net.current_plmn()),
                ("net_mode", lambda: client.net.net_mode()),
                ("sms_count", lambda: client.sms.sms_count()),
                (
                    "sms_list",
                    lambda: client.sms.get_sms_list(
                        page=1,
                        box_type=1,  # LOCAL_INBOX
                        read_count=20,
                        sort_type=0,  # DATE
                        ascending=False,
                        unread_preferred=True,
                    ),
                ),
                ("mobile_dataswitch", lambda: client.dial_up.mobile_dataswitch()),
                ("lan_host_info", lambda: client.lan.host_info()),
                ("wlan_host_list", lambda: client.wlan.host_list()),
                ("wlan_wifi_feature_switch", lambda: client.wlan.wifi_feature_switch()),
                (
                    "wlan_wifi_guest_network_switch",
                    lambda: client.wlan.wifi_guest_network_switch(),
                ),
            ]:
                try:
                    data[key] = fetcher()
                except Exception as err:
                    err_str = str(err)
                    # If we hit a session/auth error mid-fetch, we MUST stop and re-login
                    # 125002: session timeout/not logged in
                    # 125003: token error
                    if "125002" in err_str or "125003" in err_str:
                        _LOGGER.debug(
                            "Session expired during fetch of %s (%s). Forcing re-login.",
                            key,
                            err_str,
                        )
                        raise HuaweiAuthError(f"Session expired: {err}") from err

                    _LOGGER.debug("Failed to fetch %s: %s", key, err)

            return data

        try:
            return await asyncio.to_thread(_fetch)
        except HuaweiAuthError:
            # Propagate auth errors immediately to trigger re-login logic
            await self._reset_client()
            raise
        except Exception as err:
            _LOGGER.exception("Failed to fetch router data")
            await self._reset_client()
            raise HuaweiConnectionError(f"Data fetch failed: {err}") from err

    async def reboot(self) -> None:
        """Reboot the router."""
        await self._ensure_client()
        try:
            await asyncio.to_thread(self._client.device.reboot)
        except Exception:
            _LOGGER.exception("Reboot failed")
            await self._reset_client()
            raise

    async def clear_traffic_statistics(self) -> None:
        """Clear the traffic statistics counters."""
        await self._ensure_client()
        try:
            await asyncio.to_thread(self._client.monitoring.clear_traffic)
        except Exception:
            _LOGGER.exception("Clear traffic failed")
            raise

    async def set_mobile_data(self, enable: bool) -> None:
        """Enable or disable the mobile data connection."""
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
        await self._ensure_client()

        from huawei_lte_api.enums.net import LTEBandEnum, NetworkBandEnum

        def _set() -> None:
            self._client.net.set_net_mode(
                mode, LTEBandEnum.ALL.value, NetworkBandEnum.ALL.value
            )

        try:
            await asyncio.to_thread(_set)
        except Exception:
            _LOGGER.exception("Set net mode failed")
            raise

    async def set_guest_wifi(self, enable: bool) -> None:
        """Enable or disable the guest WiFi network."""
        await self._ensure_client()

        try:
            await asyncio.to_thread(
                self._client.wlan.wifi_guest_network_switch, 1 if enable else 0
            )
        except Exception:
            _LOGGER.exception("Set guest WiFi failed")
            raise

    async def send_sms(self, phone_numbers: list[str], message: str) -> None:
        """Send an SMS message to one or more numbers."""
        await self._ensure_client()

        try:
            await asyncio.to_thread(
                self._client.sms.send_sms, phone_numbers=phone_numbers, message=message
            )
        except Exception:
            _LOGGER.exception("Send SMS failed")
            raise

    async def delete_sms(self, index: int) -> None:
        """Delete an SMS message by index."""
        await self._ensure_client()

        try:
            await asyncio.to_thread(self._client.sms.delete_sms, index=index)
        except Exception:
            _LOGGER.exception("Delete SMS failed")
            raise
