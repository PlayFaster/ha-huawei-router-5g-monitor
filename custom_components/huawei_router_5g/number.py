"""Number platform for Huawei Router 5G Monitor."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.const import CONF_HOST, UnitOfTime
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SCAN_INTERVAL, DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HuaweiNumberEntityDescription(NumberEntityDescription):
    """Describes a Huawei Router 5G number entity."""

    group: str = "system"


POLLING_INTERVAL_DESCRIPTION = HuaweiNumberEntityDescription(
    key="polling_interval",
    translation_key="polling_interval",
    native_min_value=30,
    native_max_value=3600,
    native_step=30,
    native_unit_of_measurement=UnitOfTime.SECONDS,
    entity_category=EntityCategory.CONFIG,
    group="system",
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the number platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    initial_value = entry.options.get(CONF_SCAN_INTERVAL, 180)

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
        initial_value: float,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_native_value = initial_value
        self._refresh_task = None

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change — debounce before persisting."""
        self._attr_native_value = value
        self.async_write_ha_state()

        if self._refresh_task:
            self._refresh_task.cancel()

        self._refresh_task = asyncio.create_task(self._async_debounced_apply(value))

    async def _async_debounced_apply(self, value: float) -> None:
        """Apply the new interval and persist to ConfigEntry options after 2 s."""
        try:
            await asyncio.sleep(2)
            val_int = int(value)

            _LOGGER.debug("Applying new polling interval: %s seconds", val_int)

            self.coordinator.update_interval = timedelta(seconds=val_int)

            new_options = dict(self._entry.options)
            new_options[CONF_SCAN_INTERVAL] = val_int
            self.hass.config_entries.async_update_entry(
                self._entry, options=new_options
            )

            await self.coordinator.async_request_refresh()

        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.error("Failed to apply polling interval change: %s", err)

    @property
    def device_info(self):
        """Return device information with sub-device support."""
        host = self._entry.options[CONF_HOST]
        group = self.entity_description.group

        group_names = {
            "system": "System",
            "signal": "Signal",
            "data": "Data",
            "sms": "SMS",
        }
        display_group = group_names.get(group, group.capitalize())
        sub_name = f"{self._entry.title} {display_group}"

        mac = self.coordinator.mac
        sub_id_prefix = mac if mac else f"host_{host}"

        info = {
            "identifiers": {(DOMAIN, f"{sub_id_prefix}_{group}")},
            "name": sub_name,
            "manufacturer": "Huawei",
            "model": self.coordinator.model,
            "sw_version": self.coordinator.sw_version,
            "hw_version": self.coordinator.hw_version,
            "configuration_url": f"http://{host}",
        }

        if group != "system":
            info["via_device"] = (DOMAIN, f"{sub_id_prefix}_system")

        return info
