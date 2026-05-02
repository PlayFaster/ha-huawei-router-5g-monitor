"""Switch platform for Huawei Router 5G."""

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HuaweiSwitchEntityDescription(SwitchEntityDescription):
    """Describes Huawei switch entity."""

    value_fn: Callable[[Any], bool | None]
    turn_on_fn: Callable[[Any], Coroutine[Any, Any, None]]
    turn_off_fn: Callable[[Any], Coroutine[Any, Any, None]]


SWITCHES: tuple[HuaweiSwitchEntityDescription, ...] = (
    HuaweiSwitchEntityDescription(
        key="mobile_data",
        name="Mobile Data",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: (
            data.get("monitoring_status", {}).get("ConnectionStatus") == "901"
        ),  # Simplified check
        turn_on_fn=lambda api: api.set_mobile_data(True),
        turn_off_fn=lambda api: api.set_mobile_data(False),
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the switch platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HuaweiRouterSwitch(coordinator, description) for description in SWITCHES
    )


class HuaweiRouterSwitch(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], SwitchEntity
):
    """Representation of a Huawei Router switch."""

    entity_description: HuaweiSwitchEntityDescription

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        description: HuaweiSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
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
        """Return true if the switch is on."""
        # Note: ConnectionStatus might not be the best indicator for switch state.
        # But for now it's a placeholder.
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.entity_description.turn_on_fn(self.coordinator.api)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.entity_description.turn_off_fn(self.coordinator.api)
        await self.coordinator.async_request_refresh()
