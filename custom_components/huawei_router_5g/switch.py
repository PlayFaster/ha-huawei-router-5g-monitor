"""Switch platform for Huawei Router 5G Monitor."""

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STOP_POLLING, DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import build_device_info

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HuaweiSwitchEntityDescription(SwitchEntityDescription):
    """Describes a Huawei Router 5G switch entity."""

    group: str = "system"


PAUSE_POLLING_DESCRIPTION = HuaweiSwitchEntityDescription(
    key="pause_polling",
    name="Pause Polling",
    translation_key="pause_polling",
    icon="mdi:pause-circle-outline",
    entity_category=EntityCategory.CONFIG,
    group="system",
)

MOBILE_DATA_DESCRIPTION = HuaweiSwitchEntityDescription(
    key="mobile_data",
    name="Mobile Data",
    translation_key="mobile_data",
    icon="mdi:signal-4g",
    entity_category=EntityCategory.CONFIG,
    group="system",
)

GUEST_WIFI_DESCRIPTION = HuaweiSwitchEntityDescription(
    key="wifi_guest_network",
    name="Wi-Fi Guest Network",
    translation_key="wifi_guest_network",
    icon="mdi:wifi-lock",
    entity_category=EntityCategory.CONFIG,
    group="system",
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the switch platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

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
        entry,
        description: HuaweiSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._group = description.group

    @property
    def device_info(self):
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self._group)


class HuaweiPausePollingSwitch(HuaweiSwitch):
    """Switch to pause/resume data polling with persistence across restarts."""

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry,
        description: HuaweiSwitchEntityDescription,
        initial_state: bool,
    ) -> None:
        """Initialize the pause polling switch."""
        super().__init__(coordinator, entry, description)
        self._attr_is_on = initial_state

    @property
    def is_on(self) -> bool:
        """Return True if polling is paused."""
        return self._entry.options.get(CONF_STOP_POLLING, False)

    async def async_turn_on(self, **kwargs) -> None:
        """Pause polling."""
        _LOGGER.debug("Pausing Huawei Router polling")
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs) -> None:
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
            await self.coordinator.async_request_refresh()


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

    async def async_turn_on(self, **kwargs) -> None:
        """Enable mobile data."""
        try:
            await self.coordinator.api.set_mobile_data(True)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("%s: Enable mobile data failed: %s", self._entry.title, err)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable mobile data."""
        try:
            await self.coordinator.api.set_mobile_data(False)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("%s: Disable mobile data failed: %s", self._entry.title, err)


class HuaweiGuestWifiSwitch(HuaweiSwitch):
    """Switch to enable or disable the guest WiFi network."""

    @property
    def is_on(self) -> bool | None:
        """Return True if guest WiFi is enabled."""
        data = self.coordinator.data
        if not data:
            return None
        status = data.get("wlan_wifi_guest_network_switch") or {}
        val = status.get("WifiEnable")
        if val is None:
            return None
        return str(val) == "1"

    async def async_turn_on(self, **kwargs) -> None:
        """Enable guest WiFi."""
        try:
            await self.coordinator.api.set_guest_wifi(True)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("%s: Enable guest WiFi failed: %s", self._entry.title, err)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable guest WiFi."""
        try:
            await self.coordinator.api.set_guest_wifi(False)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("%s: Disable guest WiFi failed: %s", self._entry.title, err)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        data = self.coordinator.data
        if not data:
            return {}
        status = data.get("wlan_wifi_guest_network_switch") or {}
        return {"ssid": status.get("WifiSsid")}
