"""Button platform for Huawei Router 5G Monitor."""

import logging
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import build_device_info

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HuaweiButtonEntityDescription(ButtonEntityDescription):
    """Describes a Huawei Router 5G button entity."""

    group: str = "system"


REBOOT_DESCRIPTION = HuaweiButtonEntityDescription(
    key="reboot",
    translation_key="reboot",
    icon="mdi:restart",
    device_class=ButtonDeviceClass.RESTART,
    group="system",
)

CLEAR_TRAFFIC_DESCRIPTION = HuaweiButtonEntityDescription(
    key="clear_traffic",
    translation_key="clear_traffic",
    icon="mdi:chart-line-variant",
    group="data",
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the button platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = entry.runtime_data

    async_add_entities(
        [
            HuaweiRebootButton(coordinator, entry, REBOOT_DESCRIPTION),
            HuaweiClearTrafficButton(coordinator, entry, CLEAR_TRAFFIC_DESCRIPTION),
        ],
        True,
    )


class HuaweiButton(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], ButtonEntity
):
    """Base class for Huawei Router 5G buttons."""

    _attr_has_entity_name = True
    entity_description: HuaweiButtonEntityDescription

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry,
        description: HuaweiButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

    @property
    def device_info(self):
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self.entity_description.group)


class HuaweiRebootButton(HuaweiButton):
    """Button to reboot the Huawei router."""

    async def async_press(self) -> None:
        """Handle the button press — trigger a device reboot."""
        try:
            await self.coordinator.api.reboot()
        except Exception as err:
            _LOGGER.error("%s: Reboot failed: %s", self._entry.title, err)


class HuaweiClearTrafficButton(HuaweiButton):
    """Button to clear traffic statistics."""

    async def async_press(self) -> None:
        """Handle the button press — clear traffic counters."""
        try:
            await self.coordinator.api.clear_traffic_statistics()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error(
                "%s: Clear traffic statistics failed: %s", self._entry.title, err
            )
