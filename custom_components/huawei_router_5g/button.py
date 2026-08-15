"""Button platform for Huawei Router 5G Monitor."""

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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import REBOOT_REFRESH_DELAY, RECONNECT_REFRESH_DELAY
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


@dataclass(frozen=True, kw_only=True)
class HuaweiButtonEntityDescription(ButtonEntityDescription):
    """Describes a Huawei Router 5G button entity."""

    group: str = "system"
    # dev_standards Section 14 - the human-facing `about` note. Mandatory; a
    # sweep in `tests/test_entity_hygiene.py` fails when one is missing.
    about: str | None = None


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
