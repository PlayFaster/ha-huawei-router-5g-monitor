"""Button platform for Huawei Router 5G Monitor."""

import logging
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import REBOOT_REFRESH_DELAY, RECONNECT_REFRESH_DELAY
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import (
    HuaweiAboutEntity,
    _stale_tracker_entities,
    build_device_info,
)

_LOGGER = logging.getLogger(__name__)

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


@dataclass(frozen=True, kw_only=True)
class HuaweiButtonEntityDescription(ButtonEntityDescription):
    """Describes a Huawei Router 5G button entity."""

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


REFRESH_DESCRIPTION = HuaweiButtonEntityDescription(
    key="refresh",
    about=(
        "Fetches from the router immediately instead of waiting for the next "
        "poll. It works **even while Pause Polling is on** - an explicit "
        "action by a person overrides the pause, while the next scheduled "
        "poll still respects it."
    ),
    translation_key="refresh",
    entity_category=EntityCategory.CONFIG,
    group="system",
)

REBOOT_DESCRIPTION = HuaweiButtonEntityDescription(
    key="reboot",
    about=(
        "Restarts the router. Everything on the network loses its connection "
        "for a minute or two. A follow-up refresh is scheduled about sixty "
        "seconds later so the entities recover without waiting for the next "
        "poll."
    ),
    translation_key="reboot",
    device_class=ButtonDeviceClass.RESTART,
    group="system",
)

RECONNECT_DESCRIPTION = HuaweiButtonEntityDescription(
    key="reconnect",
    about=(
        "Drops the mobile data session and dials it again, which often re- "
        "homes the router to a different cell. The LAN and WiFi stay up. The "
        "router refuses the library's dedicated reconnect call, so this "
        "issues a disconnect followed by a connect, and schedules a follow-up "
        "refresh about twenty seconds later."
    ),
    translation_key="reconnect",
    # Deliberately NOT ButtonDeviceClass.RESTART - that belongs to Reboot, and
    # giving both the same class invites a user to read them as duplicates of
    # one another. Reconnect leaves the device running.
    group="system",
    no_confirmation=(
        "Re-establishing the data session is the whole point of this button, "
        "so the router is expected to answer abnormally immediately after it. "
        "A follow-up refresh twenty seconds later reports the outcome instead."
    ),
)

CLEAR_TRAFFIC_DESCRIPTION = HuaweiButtonEntityDescription(
    key="clear_traffic",
    about=(
        "Resets the router's traffic statistics to zero. **Irreversible** - "
        "the lifetime and monthly counters are held on the router, not here, "
        "so nothing in Home Assistant can restore them. It sets Counters Last "
        "Reset; it does not change Billing Cycle Day."
    ),
    translation_key="clear_traffic",
    group="data",
)


CLEANUP_DESCRIPTION = HuaweiButtonEntityDescription(
    key="cleanup_unused_entities",
    about=(
        "Removes the tracker entities for clients the router no longer "
        "reports. A device seen once leaves a permanent entity, so this is "
        "how a guest's phone gets cleared. **This button commits the removal "
        "with no preview** - run the Clean up unused entities action first if "
        "you want to see the list, because it defaults to a dry run. Nothing "
        "is removed while the router has not answered, so an outage cannot "
        "look like every client leaving at once."
    ),
    translation_key="cleanup_unused_entities",
    entity_category=EntityCategory.CONFIG,
    group="clients",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = entry.runtime_data

    async_add_entities(
        [
            HuaweiRefreshButton(coordinator, entry, REFRESH_DESCRIPTION),
            HuaweiRebootButton(coordinator, entry, REBOOT_DESCRIPTION),
            HuaweiReconnectButton(coordinator, entry, RECONNECT_DESCRIPTION),
            HuaweiClearTrafficButton(coordinator, entry, CLEAR_TRAFFIC_DESCRIPTION),
            HuaweiCleanupButton(coordinator, entry, CLEANUP_DESCRIPTION),
        ],
        True,
    )


class HuaweiButton(
    HuaweiAboutEntity,
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator],
    ButtonEntity,
):
    """Base class for Huawei Router 5G buttons."""

    _attr_has_entity_name = True
    entity_description: HuaweiButtonEntityDescription

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry: ConfigEntry,
        description: HuaweiButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self.entity_description.group)


class HuaweiRefreshButton(HuaweiButton):
    """Button to trigger an immediate data refresh."""

    async def async_press(self) -> None:
        """Handle the button press — trigger an immediate coordinator refresh."""
        await self.coordinator.async_force_refresh()


class HuaweiRebootButton(HuaweiButton):
    """Button to reboot the Huawei router."""

    async def async_press(self) -> None:
        """Handle the button press — trigger a device reboot."""
        try:
            await self.coordinator.api.reboot()
        except Exception as err:
            raise HomeAssistantError(f"Reboot failed: {err}") from err
        # Only after the write succeeded. Scheduling first would refresh
        # against a router that was never asked to restart.
        self.coordinator.async_schedule_refresh(REBOOT_REFRESH_DELAY)


class HuaweiReconnectButton(HuaweiButton):
    """Button to drop and re-establish the data session."""

    async def async_press(self) -> None:
        """Handle the button press - re-establish the data connection."""
        try:
            await self.coordinator.api.reconnect()
        except Exception as err:
            raise HomeAssistantError(f"Reconnect failed: {err}") from err
        self.coordinator.async_schedule_refresh(RECONNECT_REFRESH_DELAY)


class HuaweiClearTrafficButton(HuaweiButton):
    """Button to clear traffic statistics."""

    async def async_press(self) -> None:
        """Handle the button press — clear traffic counters."""
        try:
            await self.coordinator.api.clear_traffic_statistics()
            await self.coordinator.async_force_refresh()
        except Exception as err:
            raise HomeAssistantError(f"Clear traffic statistics failed: {err}") from err


class HuaweiCleanupButton(HuaweiButton):
    """Commit-only button removing trackers for clients that have left.

    The same work as the `cleanup_unused_entities` action, reached the way
    `unifi_network_monitor` reaches its equivalent — a button beats writing a
    service call for something a user does occasionally and by hand.

    **Two deliberate differences from the action.**

    The action iterates every config entry, because a service is global and
    its report is keyed by entry title for exactly that reason. A button is an
    entity: it belongs to one device, which belongs to one entry, and it
    cleans only that entry. With a single router the two are
    indistinguishable; with two, reusing the action's loop would mean pressing
    the button on one router silently removed trackers on the other.

    And there is no `dry_run`. A button takes no arguments, so it can only be
    the commit step — which is why the note points at the action for the
    preview. `unifi_network_monitor` is commit-only for the same reason.

    Placed on **Clients** rather than System, unlike UniFi's, because every
    entity it can remove lives there.
    """

    async def async_press(self) -> None:
        """Remove this entry's trackers for clients the router no longer lists.

        No reload afterwards, unlike UniFi's: that one removes whole devices
        and has to rebuild. This only removes registry rows for trackers
        already gone from the payload, and the registry handles that itself.
        """
        stale = _stale_tracker_entities(self.hass, self._entry)
        if not stale:
            return

        registry = er.async_get(self.hass)
        for item in stale:
            _LOGGER.info(
                "%s: Removing tracker for a client the router no longer reports: %s",
                self._entry.title,
                item.entity_id,
            )
            registry.async_remove(item.entity_id)
