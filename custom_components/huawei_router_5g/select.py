"""Select platform for Huawei Router 5G."""

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import build_device_info

# Section 22. `1`, not `0`.
#
# `0` means *unlimited*. This platform issues commands with a real-world effect
# on the router, and `api.py` serializes every call behind an `asyncio.Lock`
# precisely because concurrent calls answer with "Busy" / `110001`. That lock is
# the actual safety mechanism; `PARALLEL_UPDATES = 1` states the same intent at
# the platform boundary and stops N concurrent service calls each occupying a
# Home Assistant task while they queue on it.
#
# Decided per write path rather than copied from `zte_router_5g` — see
# `number.py`, which reaches the opposite answer for the opposite reason.
PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HuaweiSelectEntityDescription(SelectEntityDescription):
    """Describes Huawei select entity."""

    value_fn: Callable[[Any], str | None]
    setter_fn: Callable[[Any, str], Coroutine[Any, Any, None]]
    group: str = "system"


NETWORK_MODE_MAPPING = {
    "Auto": "00",
    "4G/3G/2G Auto": "030201",
    "4G/3G Auto": "0302",
    "4G/2G Auto": "0301",
    "4G Only": "03",
    "3G/2G Auto": "0201",
    "3G Only": "02",
    "2G Only": "01",
}
NETWORK_MODE_INV_MAPPING = {v: k for k, v in NETWORK_MODE_MAPPING.items()}


SELECTS: tuple[HuaweiSelectEntityDescription, ...] = (
    HuaweiSelectEntityDescription(
        key="network_mode",
        translation_key="network_mode",
        options=list(NETWORK_MODE_MAPPING.keys()),
        entity_category=EntityCategory.CONFIG,
        group="system",
        value_fn=lambda data: (
            NETWORK_MODE_INV_MAPPING.get(
                str(data.get("net_mode", {}).get("NetworkMode"))
            )
            if data
            else None
        ),
        setter_fn=lambda api, mode_label: api.set_net_mode(
            NETWORK_MODE_MAPPING.get(mode_label, "00")
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    coordinator = entry.runtime_data
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
    def device_info(self) -> DeviceInfo:
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self.entity_description.group)

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option, raising if the router refused.

        A write path may never return a success-shaped result having done
        nothing. This previously logged and returned, so a rejected network-mode
        change reported success and then silently reverted on the next poll.
        """
        try:
            await self.entity_description.setter_fn(self.coordinator.api, option)
        except Exception as err:
            _LOGGER.exception(
                "%s: Failed to set network mode to %s",
                self.coordinator.entry.title,
                option,
            )
            raise HomeAssistantError(
                f"Failed to set network mode to {option}: {err}"
            ) from err

        # Outside the error boundary: the write has already succeeded, and a
        # blip while re-reading must not report it as failed.
        await self.coordinator.async_force_refresh()
