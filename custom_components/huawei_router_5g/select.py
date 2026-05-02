"""Select platform for Huawei Router 5G."""

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import CONF_HOST
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from huawei_lte_api.enums.net import NetworkModeEnum

from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HuaweiSelectEntityDescription(SelectEntityDescription):
    """Describes Huawei select entity."""

    value_fn: Callable[[Any], str | None]
    setter_fn: Callable[[Any, str], Coroutine[Any, Any, None]]


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
        host = self.coordinator.entry.options[CONF_HOST]
        mac = self.coordinator.mac
        sub_id_prefix = mac if mac else f"host_{host}"

        return {
            "identifiers": {(DOMAIN, f"{sub_id_prefix}_system")},
            "name": f"{self.coordinator.entry.title} System",
            "manufacturer": "Huawei",
            "model": self.coordinator.model,
            "sw_version": self.coordinator.sw_version,
            "hw_version": self.coordinator.hw_version,
            "configuration_url": f"http://{host}",
        }

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.entity_description.setter_fn(self.coordinator.api, option)
        await self.coordinator.async_request_refresh()
