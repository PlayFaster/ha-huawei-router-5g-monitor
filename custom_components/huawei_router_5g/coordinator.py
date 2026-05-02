"""DataUpdateCoordinator for Huawei Router 5G."""

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_SCAN_INTERVAL, CONF_STOP_POLLING, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class HuaweiRouter5GDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Huawei Router data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api):
        """Initialize the coordinator."""
        self.api = api
        self.entry = entry
        self.consecutive_failures = 0
        self.last_update_success_time = None

        self.model = entry.data.get("model", "Huawei Router")
        self.sw_version = entry.data.get("sw_version")
        self.hw_version = entry.data.get("hw_version")
        self.mac = entry.data.get("mac")

        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{entry.title} Data",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        is_paused = self.entry.options.get(CONF_STOP_POLLING, False)
        if is_paused and self.data is not None:
            return self.data

        try:
            async with asyncio.timeout(30):
                data = await self.api.get_data()

                # Update hardware info if available
                dev_info = data.get("device_information")
                if dev_info:
                    new_sw = dev_info.get("SoftwareVersion")
                    new_model = dev_info.get("DeviceName")
                    new_hw = dev_info.get("HardwareVersion")

                    if (
                        new_sw != self.sw_version
                        or new_model != self.model
                        or new_hw != self.hw_version
                    ):
                        self.sw_version = new_sw
                        self.model = new_model
                        self.hw_version = new_hw

                        _LOGGER.info(
                            "Updating device info for %s: %s, %s, %s",
                            self.entry.title,
                            self.model,
                            self.sw_version,
                            self.hw_version,
                        )

                        new_data = dict(self.entry.data)
                        new_data.update(
                            {
                                "sw_version": self.sw_version,
                                "model": self.model,
                                "hw_version": self.hw_version,
                            }
                        )
                        self.hass.config_entries.async_update_entry(
                            self.entry, data=new_data
                        )

                self.last_update_success_time = dt_util.now()
                self.consecutive_failures = 0
                return data

        except Exception as err:
            self.consecutive_failures += 1
            if self.data is not None and self.consecutive_failures <= 2:
                _LOGGER.warning(
                    "%s: Fetch failed. Holding last known values.", self.entry.title
                )
                return self.data
            raise UpdateFailed(f"Error communicating with API: {err}") from err
