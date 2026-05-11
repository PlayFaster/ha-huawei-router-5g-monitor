"""Device tracker platform for Huawei Router 5G."""

import logging
from typing import Any

from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import build_device_info

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the device tracker platform."""
    coordinator = entry.runtime_data

    # Initialize tracked devices
    tracked_macs = set()

    def _get_entities() -> list[HuaweiRouterDeviceTracker]:
        new_entities: list[HuaweiRouterDeviceTracker] = []
        data = coordinator.data
        if not data:
            return new_entities
        hosts = []
        for key in ["lan_host_info", "wlan_host_list"]:
            hosts_data = data.get(key)
            if isinstance(hosts_data, dict):
                hosts.extend(hosts_data.get("Hosts", {}).get("Host", []))

        for host in hosts:
            mac = host.get("MacAddress")
            if mac and mac not in tracked_macs:
                tracked_macs.add(mac)
                new_entities.append(HuaweiRouterDeviceTracker(coordinator, mac))
        return new_entities

    # Add initial entities
    async_add_entities(_get_entities(), True)

    # Register listener for new devices
    def _async_update_listener() -> None:
        new_entities = _get_entities()
        if new_entities:
            async_add_entities(new_entities, True)

    entry.async_on_unload(coordinator.async_add_listener(_async_update_listener))


class HuaweiRouterDeviceTracker(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], ScannerEntity
):
    """Representation of a Huawei Router tracked device."""

    def __init__(
        self, coordinator: HuaweiRouter5GDataUpdateCoordinator, mac: str
    ) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{mac}"

    @property
    def _host_data(self) -> dict[str, Any] | None:
        """Get host data from coordinator."""
        data = self.coordinator.data
        if not data:
            return None
        hosts = []
        for key in ["lan_host_info", "wlan_host_list"]:
            hosts_data = data.get(key)
            if isinstance(hosts_data, dict):
                hosts.extend(hosts_data.get("Hosts", {}).get("Host", []))
        return next((h for h in hosts if h.get("MacAddress") == self._mac), None)

    @property
    def name(self) -> str:
        """Return the name of the device."""
        host = self._host_data
        if host:
            return host.get("HostName") or self._mac
        return self._mac

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected to the network."""
        host = self._host_data
        if not host:
            return False
        # Active: "1" or "0"
        return host.get("Active") == "1"

    @property
    def ip_address(self) -> str | None:
        """Return the primary ip address of the device."""
        host = self._host_data
        if host:
            ip = host.get("IpAddress")
            if ip:
                return str(ip).split(";")[0]
        return None

    @property
    def mac_address(self) -> str:
        """Return the mac address of the device."""
        return self._mac

    @property
    def hostname(self) -> str | None:
        """Return hostname of the device."""
        host = self._host_data
        if host:
            return host.get("HostName")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device specific attributes."""
        host = self._host_data
        if not host:
            return {}
        return {
            "interface_type": host.get("InterfaceType"),
            "associated_ssid": host.get("AssociatedSsid"),
            "address_source": host.get("AddressSource"),
        }

    @property  # type: ignore[misc]
    def device_info(self) -> DeviceInfo:
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, "clients")
