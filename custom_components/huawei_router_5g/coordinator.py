"""DataUpdateCoordinator for Huawei Router 5G."""

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_SCAN_INTERVAL, CONF_STOP_POLLING
from .helpers import get_router_model

_LOGGER = logging.getLogger(__name__)


class HuaweiRouter5GDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Huawei Router data with resilience and pausing."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.entry = entry
        self.consecutive_failures = 0
        self.last_update_success_time = None

        # Load hardware identity from persistent ConfigEntry data (Flat Identity pattern).
        self.model = entry.data.get("model", "Huawei Router")
        self.sw_version = entry.data.get("sw_version")
        self.hw_version = entry.data.get("hw_version")
        self.mac = entry.data.get("mac")

        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, 180)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{entry.title} Data",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the API with resilience and pause support."""
        is_paused = self.entry.options.get(CONF_STOP_POLLING, False)
        is_first_run = self.data is None

        if is_paused and not is_first_run:
            _LOGGER.debug(
                "%s: Polling is paused; returning cached data.", self.entry.title
            )
            return self.data

        try:
            async with asyncio.timeout(30):
                data = await self.api.get_data()

                dev_info = data.get("device_information") or {}
                new_model = get_router_model(dev_info)
                new_sw = dev_info.get("SoftwareVersion")
                new_hw = dev_info.get("HardwareVersion")

                if (
                    new_model != self.model
                    or new_sw != self.sw_version
                    or new_hw != self.hw_version
                ):
                    _LOGGER.info(
                        "%s: Hardware metadata updated: %s sw=%s hw=%s",
                        self.entry.title,
                        new_model,
                        new_sw,
                        new_hw,
                    )
                    self.model = new_model
                    self.sw_version = new_sw
                    self.hw_version = new_hw

                    new_entry_data = dict(self.entry.data)
                    new_entry_data.update(
                        {
                            "model": new_model,
                            "sw_version": new_sw,
                            "hw_version": new_hw,
                        }
                    )
                    self.hass.config_entries.async_update_entry(
                        self.entry, data=new_entry_data
                    )

                self.last_update_success_time = dt_util.now()
                self.consecutive_failures = 0
                return data

        except TimeoutError as err:
            self.consecutive_failures += 1
            if self.data is not None and self.consecutive_failures <= 3:
                _LOGGER.warning(
                    "%s: Fetch timed out (failure %d/3), holding last known values.",
                    self.entry.title,
                    self.consecutive_failures,
                )
                return self.data
            _LOGGER.error("%s: API request timed out.", self.entry.title)
            raise UpdateFailed("API request timed out") from err

        except Exception as err:
            self.consecutive_failures += 1
            if self.data is not None and self.consecutive_failures <= 3:
                _LOGGER.warning(
                    "%s: Fetch failed (failure %d/3), holding last known values: %s",
                    self.entry.title,
                    self.consecutive_failures,
                    err,
                )
                return self.data

            if is_paused:
                _LOGGER.warning(
                    "%s: Initial fetch failed while paused. Starting with empty data.",
                    self.entry.title,
                )
                return {}

            _LOGGER.error(
                "%s: Connection lost. Marking entities unavailable.", self.entry.title
            )
            raise UpdateFailed(f"Communication error: {err}") from err
