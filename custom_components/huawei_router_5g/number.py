"""Number platform for Huawei Router 5G."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import build_device_info

_LOGGER = logging.getLogger(__name__)

# Section 22. `0`, deliberately — and deliberately different from
# `zte_router_5g`, which sets `1` on every writable platform.
#
# The only entity here is the polling interval, and it does **not** command the
# router: it writes to `ConfigEntry.options`, which Home Assistant owns and
# serializes itself. There is no session to tear down and no command to
# duplicate, so `1` would buy nothing. The value follows the write path, not the
# platform's name.
PARALLEL_UPDATES = 0


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
    mode=NumberMode.SLIDER,
    entity_category=EntityCategory.CONFIG,
    group="system",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = entry.runtime_data

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
        entry: ConfigEntry,
        description: HuaweiNumberEntityDescription,
        initial_value: float,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = description
        self._group = description.group

        # Registry identification
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

        # Local state
        self._attr_native_value = initial_value
        self._refresh_task: asyncio.Task[None] | None = None
        # The value a pending debounce is going to write. Held separately from
        # `_attr_native_value` so removal can flush it, and cleared once the
        # debounce commits.
        self._pending_value: float | None = None

    async def async_set_native_value(self, value: float) -> None:
        """Handle the UI slider change."""
        # Update local UI state immediately for responsiveness
        self._attr_native_value = value
        self.async_write_ha_state()
        self._pending_value = value

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

            self._pending_value = None

            # 3. Trigger an immediate refresh using the new interval
            await self.coordinator.async_force_refresh()

        except asyncio.CancelledError:
            # Task was cancelled because the user moved the slider again
            pass
        except Exception:
            _LOGGER.exception("Failed to apply polling interval change")

    async def async_will_remove_from_hass(self) -> None:
        """Flush a pending debounced write, then cancel the task.

        Cancelling without writing loses the value. The window is only two
        seconds, but a reload is exactly what lands inside it: an options
        change reloads the entry, so a user who moves the slider and
        immediately changes a setting watches the interval snap back with no
        explanation and nothing logged.

        Only the persistence is flushed — no refresh is requested, because the
        entity is being torn down.
        """
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None

        if self._pending_value is None:
            return

        val_int = int(self._pending_value)
        self._pending_value = None
        _LOGGER.debug("Flushing pending polling interval on removal: %ss", val_int)
        self.coordinator.update_interval = timedelta(seconds=val_int)
        new_options = dict(self._entry.options)
        new_options[CONF_SCAN_INTERVAL] = val_int
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self._group)
