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

from .const import (
    NETWORK_MODE_FALLBACK,
    NETWORK_MODE_LABELS,
    network_mode_label,
)
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import HuaweiAboutEntity, build_device_info

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
    # dev_standards Section 14 - the human-facing `about` note. Mandatory; a
    # sweep in `tests/test_entity_hygiene.py` fails when one is missing.
    about: str | None = None

    # dev_standards Section 22 — the write-confirmation exclusion, declared
    # where a reviewer reading this entity will see it.
    #
    # A write that re-establishes the connection makes the router answer
    # abnormally **while succeeding**, so a targeted read-back reports a
    # working command as failed. The protection is also structural — no reader
    # exists in `api.py::READ_BACK_ENDPOINTS` for the endpoints these need —
    # but the section asks for the exclusion to be visible on the entity
    # rather than left as an unwritten rule two modules away.
    #
    # `None` means the write is confirmable and is expected to confirm. A
    # string is the reason it never will be.
    no_confirmation: str | None = None


def _label_to_code(label: str) -> str:
    """Resolve a displayed option back to the code the router expects.

    Handles the `Unknown (nn)` form as well, so a mode this integration cannot
    name is still selectable rather than merely visible.
    """
    for code, name in NETWORK_MODE_LABELS.items():
        if name == label:
            return code
    if label.startswith("Unknown (") and label.endswith(")"):
        return label[len("Unknown (") : -1]
    return "00"


SELECTS: tuple[HuaweiSelectEntityDescription, ...] = (
    HuaweiSelectEntityDescription(
        key="network_mode",
        about=(
            "Restricts which radio technologies the router may use. `Auto` lets "
            "it choose. Pinning to a single mode can stabilize a marginal "
            "connection or can strand it entirely if that mode is unavailable "
            "where the router sits. Preferred Network Mode, the sensor, reads "
            "back what the router says is in force."
        ),
        translation_key="network_mode",
        # The fallback only. The live list comes from the router via the
        # `options` property below; this is what a device that will not publish
        # an `AccessList` keeps — see `NETWORK_MODE_FALLBACK`.
        options=[network_mode_label(c) or c for c in NETWORK_MODE_FALLBACK],
        entity_category=EntityCategory.CONFIG,
        group="system",
        # Confirmed, but inside `api.set_net_mode` rather than here, because the
        # router *sometimes* answers the write itself with `-1: Unknown` while
        # it re-registers the radio. This description previously carried a
        # `no_confirmation` reason saying a read-back would report a refused
        # write — true only of an *immediate* read-back. After the settle delay
        # the read is reliable, and it is the only thing that can tell an
        # applied change from a refused one, since both answer `-1`.
        #
        # **Sometimes, not always** — this comment claimed otherwise until
        # 2026-08-19, when the hardware check wrote `03` from `00` and the
        # router accepted it outright. What decides it is not isolated, so the
        # `-1` handling stays and is simply not the only path.
        value_fn=lambda data: (
            network_mode_label(data.get("net_mode", {}).get("NetworkMode"))
            if data
            else None
        ),
        setter_fn=lambda api, mode_label: api.set_net_mode(_label_to_code(mode_label)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform.

    **The mode list is not read here.** Platforms are forwarded before the
    router is logged in — Section 1's non-blocking startup — so a fetch at this
    point would find no client, fail, and fall back on every single startup. The
    list is read once after login and exposed through the `options` property
    below, which picks it up as soon as it lands.
    """
    coordinator = entry.runtime_data
    async_add_entities(
        [HuaweiRouterSelect(coordinator, description) for description in SELECTS]
    )


class HuaweiRouterSelect(
    HuaweiAboutEntity,
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator],
    SelectEntity,
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
    def options(self) -> list[str]:
        """Return the modes this router accepts, falling back to the full set.

        Read from `net.net_mode_list()` after login rather than fixed at setup:
        the reference H165-383 publishes `["00", "08", "03"]`, exactly the three
        its web interface offers, while the description's list carries every
        mode the integration knows. Offering the full set on a router that
        accepts three invites writes it will refuse.

        A router that will not publish a list keeps the full set, which is the
        pre-2026-08 behavior and no worse than it was.
        """
        codes = self.coordinator.supported_net_modes
        if self.entity_description.key != "network_mode" or not codes:
            return list(self.entity_description.options or [])
        return [network_mode_label(code) or code for code in codes]

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
