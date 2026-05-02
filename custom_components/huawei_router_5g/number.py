"""Number platform for Huawei Router 5G."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import UnitOfTime
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import build_device_info

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HuaweiNumberEntityDescription(NumberEntityDescription):
    """Describes Huawei number entity."""

    group: str = "system"


# Define the entity description for static metadata
POLLING_INTERVAL_DESCRIPTION = HuaweiNumberEntityDescription(
    key="polling_interval",
    translation_key="polling_interval",
    native_min_value=30,
    native_max_value=3600,
    native_step=30,
    native_unit_of_measurement=UnitOfTime.SECONDS,
    mode="slider",
    entity_category=EntityCategory.CONFIG,
    group="system",
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the number platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Read initial value from entry options (survives restarts)
    initial_value = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    async_add_entities(
        [
            HuaweiPollingInterval(
                coordinator, entry, POLLING_INTERVAL_DESCRIPTION, initial_value
            )
        ]
    )


class HuaweiPollingInterval(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], NumberEntity
):
    """Number entity to control the polling interval with persistence."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description: HuaweiNumberEntityDescription

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry,
        description: HuaweiNumberEntityDescription,
        initial_value,
    ):
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = description
        self._group = description.group

        # Registry identification
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

        # Local state
        self._attr_native_value = initial_value
        self._refresh_task = None

    async def async_set_native_value(self, value: float) -> None:
        """Handle the UI slider change."""
        # Update local UI state immediately for responsiveness
        self._attr_native_value = value
        self.async_write_ha_state()

        # Cancel any pending update task to reset the debounce timer
        if self._refresh_task:
            self._refresh_task.cancel()

        # Start a new debounced task
        self._refresh_task = asyncio.create_task(self._async_debounced_apply(value))

    async def _async_debounced_apply(self, value: float) -> None:
        """Apply change and persist to ConfigEntry Options after a delay."""
        try:
            # Wait for 2 seconds of inactivity before committing
            await asyncio.sleep(2)
            val_int = int(value)

            _LOGGER.debug("Applying new polling interval: %s seconds", val_int)

            # 1. Update the coordinator's actual update interval
            self.coordinator.update_interval = timedelta(seconds=val_int)

            # 2. Persist to ConfigEntry Options (saves to .storage/core.config_entries)
            # This ensures the setting survives a Home Assistant restart.
            new_options = dict(self._entry.options)
            new_options[CONF_SCAN_INTERVAL] = val_int
            self.hass.config_entries.async_update_entry(
                self._entry, options=new_options
            )

            # 3. Trigger an immediate refresh using the new interval
            await self.coordinator.async_request_refresh()

        except asyncio.CancelledError:
            # Task was cancelled because the user moved the slider again
            pass
        except Exception as err:
            _LOGGER.error("Failed to apply polling interval change: %s", err)

    @property
    def device_info(self):
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self._group)

