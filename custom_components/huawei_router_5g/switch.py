"""Switch platform for Huawei Router 5G Monitor."""

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STOP_POLLING
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import build_device_info

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HuaweiSwitchEntityDescription(SwitchEntityDescription):
    """Describes a Huawei Router 5G switch entity."""

    group: str = "system"


PAUSE_POLLING_DESCRIPTION = HuaweiSwitchEntityDescription(
    key="pause_polling",
    translation_key="pause_polling",
    entity_category=EntityCategory.CONFIG,
    group="system",
)

MOBILE_DATA_DESCRIPTION = HuaweiSwitchEntityDescription(
    key="mobile_data",
    translation_key="mobile_data",
    entity_category=EntityCategory.CONFIG,
    group="system",
)

GUEST_WIFI_DESCRIPTION = HuaweiSwitchEntityDescription(
    key="wifi_guest_network",
    translation_key="wifi_guest_network",
    entity_category=EntityCategory.CONFIG,
    group="wifi",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = entry.runtime_data

    initial_pause_state = entry.options.get(CONF_STOP_POLLING, False)

    async_add_entities(
        [
            HuaweiPausePollingSwitch(
                coordinator, entry, PAUSE_POLLING_DESCRIPTION, initial_pause_state
            ),
            HuaweiMobileDataSwitch(coordinator, entry, MOBILE_DATA_DESCRIPTION),
            HuaweiGuestWifiSwitch(coordinator, entry, GUEST_WIFI_DESCRIPTION),
        ]
    )


class HuaweiSwitch(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], SwitchEntity
):
    """Base class for Huawei Router 5G switches."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description: HuaweiSwitchEntityDescription

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry: ConfigEntry,
        description: HuaweiSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._group = description.group

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self._group)


class HuaweiPausePollingSwitch(HuaweiSwitch):
    """Switch to pause/resume data polling with persistence across restarts."""

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry: ConfigEntry,
        description: HuaweiSwitchEntityDescription,
        initial_state: bool,
    ) -> None:
        """Initialize the pause polling switch."""
        super().__init__(coordinator, entry, description)
        self._attr_is_on = initial_state

    @property
    def is_on(self) -> bool:
        """Return True if polling is paused."""
        return bool(self._entry.options.get(CONF_STOP_POLLING, False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Pause polling."""
        _LOGGER.debug("Pausing Huawei Router polling")
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Resume polling."""
        _LOGGER.debug("Resuming Huawei Router polling")
        await self._async_set_state(False)

    async def _async_set_state(self, state: bool) -> None:
        """Persist pause state to ConfigEntry options and notify HA."""
        new_options = dict(self._entry.options)
        new_options[CONF_STOP_POLLING] = state
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        self.async_write_ha_state()

        if not state:
            await self.coordinator.async_force_refresh()


class HuaweiMobileDataSwitch(HuaweiSwitch):
    """Switch to enable or disable the mobile data connection."""

    @property
    def is_on(self) -> bool | None:
        """Return True if mobile data is enabled."""
        data = self.coordinator.data
        if not data:
            return None
        mobile_sw = data.get("mobile_dataswitch") or {}
        val = mobile_sw.get("dataswitch")
        if val is None:
            return None
        return str(val) == "1"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable mobile data."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable mobile data."""
        await self._async_set(False)

    async def _async_set(self, enable: bool) -> None:
        """Write the mobile-data state, raising if the router refused.

        A write path may never return a success-shaped result having done
        nothing. This previously logged the exception and returned, so a failed
        toggle looked identical to a successful one: the service call
        succeeded, the switch sprang back on the next poll, and the only
        evidence was a log line. `button.py` already had this right.
        """
        action = "Enable" if enable else "Disable"
        try:
            await self.coordinator.api.set_mobile_data(enable)
        except Exception as err:
            _LOGGER.exception("%s: %s mobile data failed", self._entry.title, action)
            raise HomeAssistantError(f"{action} mobile data failed: {err}") from err

        # Outside the error boundary on purpose. The write has already
        # succeeded; a blip while re-reading must not report the write as
        # failed and invite a retry of a command with a real-world effect.
        await self.coordinator.async_force_refresh()


class HuaweiGuestWifiSwitch(HuaweiSwitch):
    """Switch to enable or disable the guest WiFi network."""

    # dev_standards Section 14. The guest SSID is a static string republished
    # on every poll; recording it adds a row per poll and puts the network name
    # into long-term history.
    _unrecorded_attributes = frozenset({"ssid"})

    @property
    def is_on(self) -> bool | None:
        """Return True if guest WiFi is enabled."""
        data = self.coordinator.data
        if not data:
            return None
        multi_settings = data.get("wlan_multi_basic_settings") or {}
        ssids = multi_settings.get("Ssids", {}).get("Ssid", [])
        if isinstance(ssids, dict):
            ssids = [ssids]

        for ssid in ssids:
            if str(ssid.get("wifiisguestnetwork")) == "1":
                return str(ssid.get("WifiEnable")) == "1"
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable guest WiFi."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable guest WiFi."""
        await self._async_set(False)

    async def _async_set(self, enable: bool) -> None:
        """Write the guest-WiFi state, raising if the router refused.

        The previous form logged the failure and then refreshed in a `finally`,
        which masked it twice over: the service call reported success, and the
        refresh made the switch look as though it had simply been re-read.
        """
        action = "Enable" if enable else "Disable"
        try:
            await self.coordinator.api.set_guest_wifi(enable)
        except Exception as err:
            _LOGGER.exception("%s: %s guest WiFi failed", self._entry.title, action)
            raise HomeAssistantError(f"{action} guest WiFi failed: {err}") from err

        # Outside the error boundary — see HuaweiMobileDataSwitch._async_set.
        await self.coordinator.async_force_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        data = self.coordinator.data
        if not data:
            return {}
        multi_settings = data.get("wlan_multi_basic_settings") or {}
        ssids = multi_settings.get("Ssids", {}).get("Ssid", [])
        if isinstance(ssids, dict):
            ssids = [ssids]

        for ssid in ssids:
            if str(ssid.get("wifiisguestnetwork")) == "1":
                return {"ssid": ssid.get("WifiSsid")}
        return {}
