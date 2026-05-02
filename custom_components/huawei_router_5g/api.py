"""Huawei Router 5G API client."""

import asyncio
import logging
from typing import Any

from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from url_normalize import url_normalize

_LOGGER = logging.getLogger(__name__)


class HuaweiRouter5GAPI:
    """Async wrapper for the huawei-lte-api library."""

    def __init__(self, host, username, password, verify_ssl=False):
        """Initialize the API."""
        self.url = url_normalize(host)
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.connection = None
        self.client = None
        self._client_lock = asyncio.Lock()

    async def _ensure_client(self):
        """Ensure the client is initialized."""
        async with self._client_lock:
            if self.connection is None:
                self.connection = Connection(
                    self.url,
                    username=self.username,
                    password=self.password,
                    verify=self.verify_ssl,
                )
                self.client = Client(self.connection)

    async def login(self):
        """Authorize with the router."""
        await self._ensure_client()

        # The Connection object handles login if credentials are provided.
        # But we might need to explicitly call login if session expires.
        def _login():
            return self.client.user.login(self.username, self.password)

        try:
            await asyncio.to_thread(_login)
        except Exception as e:
            _LOGGER.debug("Login failed: %s", e)
            raise

    async def logout(self):
        """Logout from the router."""
        if not self.client:
            return
        try:
            await asyncio.to_thread(self.client.user.logout)
        except Exception as e:
            _LOGGER.debug("Logout failed: %s", e)

    async def get_data(self) -> dict[str, Any]:
        """Fetch all relevant data from the router."""
        await self._ensure_client()

        def _fetch():
            data = {}
            # Basic Device Info
            try:
                data["device_information"] = self.client.device.information()
            except Exception:
                _LOGGER.debug("Failed to fetch device_information")

            try:
                data["device_signal"] = self.client.device.signal()
            except Exception:
                _LOGGER.debug("Failed to fetch device_signal")

            # Monitoring
            try:
                data["monitoring_status"] = self.client.monitoring.status()
            except Exception:
                _LOGGER.debug("Failed to fetch monitoring_status")

            try:
                data["traffic_statistics"] = self.client.monitoring.traffic_statistics()
            except Exception:
                _LOGGER.debug("Failed to fetch traffic_statistics")

            try:
                data["month_statistics"] = self.client.monitoring.month_statistics()
            except Exception:
                _LOGGER.debug("Failed to fetch month_statistics")

            # Network
            try:
                data["current_plmn"] = self.client.net.current_plmn()
            except Exception:
                _LOGGER.debug("Failed to fetch current_plmn")

            try:
                data["net_mode"] = self.client.net.net_mode()
            except Exception:
                _LOGGER.debug("Failed to fetch net_mode")

            # SMS
            try:
                data["sms_count"] = self.client.sms.sms_count()
            except Exception:
                _LOGGER.debug("Failed to fetch sms_count")

            return data

        return await asyncio.to_thread(_fetch)

    async def reboot(self):
        """Reboot the router."""
        await self._ensure_client()
        await asyncio.to_thread(self.client.device.reboot)

    async def clear_traffic_statistics(self):
        """Clear traffic statistics."""
        await self._ensure_client()
        await asyncio.to_thread(self.client.monitoring.clear_traffic)

    async def set_mobile_data(self, enable: bool):
        """Enable or disable mobile data."""
        await self._ensure_client()

        def _set():
            self.client.dial_up.set_mobile_dataswitch(1 if enable else 0)

        await asyncio.to_thread(_set)
