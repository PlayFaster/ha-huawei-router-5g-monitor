"""Select platform for Huawei Router 5G."""

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from huawei_lte_api.enums.net import NetworkModeEnum

from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import build_device_info

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HuaweiSelectEntityDescription(SelectEntityDescription):
    """Describes Huawei select entity."""

    value_fn: Callable[[Any], str | None]
    setter_fn: Callable[[Any, str], Coroutine[Any, Any, None]]
    group: str = "system"


SELECTS: tuple[HuaweiSelectEntityDescription, ...] = (
    HuaweiSelectEntityDescription(
        key="network_mode",
        name="Preferred Network Mode",
        options=[
            NetworkModeEnum.MODE_AUTO.value,
            NetworkModeEnum.MODE_4G_3G_AUTO.value,
            NetworkModeEnum.MODE_4G_2G_AUTO.value,
            NetworkModeEnum.MODE_4G_ONLY.value,
            NetworkModeEnum.MODE_3G_2G_AUTO.value,
            NetworkModeEnum.MODE_3G_ONLY.value,
            NetworkModeEnum.MODE_2G_ONLY.value,
        ],
        entity_category=EntityCategory.CONFIG,
        group="system",
        value_fn=lambda data: (
            data.get("net_mode", {}).get("NetworkMode") if data else None
        ),
        setter_fn=lambda api, mode: api.set_net_mode(mode),
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the select platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [HuaweiRouterSelect(coordinator, description) for description in SELECTS]
    )


class HuaweiRouterSelect(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], SelectEntity
):
    """Representation of a Huawei Router select."""

    _attr_has_entity_name = True
    entity_description: HuaweiSelectEntityDescription

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        description: HuaweiSelectEntityDescription,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{description.key}"

    @property
    def device_info(self):
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self.entity_description.group)

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        try:
            await self.entity_description.setter_fn(self.coordinator.api, option)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.exception(
                "%s: Failed to set network mode to %s: %s",
                self.coordinator.entry.title,
                option,
                err,
            )
