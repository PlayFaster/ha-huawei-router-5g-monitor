"""Binary sensor platform for Huawei Router 5G."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HuaweiBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes Huawei binary sensor entity."""

    value_fn: Callable[[Any], bool | None]


BINARY_SENSORS: tuple[HuaweiBinarySensorEntityDescription, ...] = (
    HuaweiBinarySensorEntityDescription(
        key="mobile_connection",
        name="Mobile Connection",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: (
            data.get("monitoring_status", {}).get("ConnectionStatus") == "901"
        ),  # 901 is connected usually
    ),
    HuaweiBinarySensorEntityDescription(
        key="sms_storage_full",
        name="SMS Storage Full",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            data.get("monitoring_status", {}).get("SmsStorageFull") == "1"
        ),
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the binary sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HuaweiRouterBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class HuaweiRouterBinarySensor(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of a Huawei Router binary sensor."""

    entity_description: HuaweiBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        description: HuaweiBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.unique_id)},
            "name": coordinator.entry.title,
            "manufacturer": "Huawei",
            "model": coordinator.model,
            "sw_version": coordinator.sw_version,
            "hw_version": coordinator.hw_version,
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self.entity_description.value_fn(self.coordinator.data)
