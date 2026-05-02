"""Button platform for Huawei Router 5G."""

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HuaweiButtonEntityDescription(ButtonEntityDescription):
    """Describes Huawei button entity."""

    press_fn: Callable[[Any], Coroutine[Any, Any, None]]


BUTTONS: tuple[HuaweiButtonEntityDescription, ...] = (
    HuaweiButtonEntityDescription(
        key="reboot",
        name="Reboot",
        device_class=None,
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda api: api.reboot(),
    ),
    HuaweiButtonEntityDescription(
        key="clear_traffic_statistics",
        name="Clear Traffic Statistics",
        device_class=None,
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda api: api.clear_traffic_statistics(),
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the button platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HuaweiRouterButton(coordinator, description) for description in BUTTONS
    )


class HuaweiRouterButton(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], ButtonEntity
):
    """Representation of a Huawei Router button."""

    entity_description: HuaweiButtonEntityDescription

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        description: HuaweiButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
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

    async def async_press(self) -> None:
        """Press the button."""
        await self.entity_description.press_fn(self.coordinator.api)
        await self.coordinator.async_request_refresh()
