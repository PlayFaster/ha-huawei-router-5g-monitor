"""Device tracker platform for Huawei Router 5G."""

import logging
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.const import CONF_HOST
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the device tracker platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Initialize tracked devices
    tracked_macs = set()

    def _get_entities():
        new_entities = []
        data = coordinator.data
        hosts = []
        for key in ["lan_host_info", "wlan_host_list"]:
            try:
                hosts.extend(data.get(key, {}).get("Hosts", {}).get("Host", []))
            except (AttributeError, KeyError, TypeError):
                continue

        for host in hosts:
            mac = host.get("MacAddress")
            if mac and mac not in tracked_macs:
                tracked_macs.add(mac)
                new_entities.append(HuaweiRouterDeviceTracker(coordinator, mac))
        return new_entities

    # Add initial entities
    async_add_entities(_get_entities(), True)

    # Register listener for new devices
    def _async_update_listener():
        new_entities = _get_entities()
        if new_entities:
            async_add_entities(new_entities, True)

    coordinator.async_add_listener(_async_update_listener)


class HuaweiRouterDeviceTracker(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], ScannerEntity
):
    """Representation of a Huawei Router tracked device.

    Naming: has_entity_name is explicitly False. The name property prepends the router
    title (e.g. "Huawei 5G NPG3 Hub") to produce a scoped entity_id of the form
    device_tracker.huawei_5g_npg3_hub — the router prefix disambiguates across multiple
    routers without including the "Clients" sub-device segment, which adds length but
    no information (every tracker from this integration is a client by definition).
    UI grouping under the Clients sub-device is preserved independently via device_info.
    See .notes/sub_devices_and_trackers.md for the full design rationale.
    """

    _attr_has_entity_name = False  # intentional — entity name includes router title prefix

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
        hosts = []
        for key in ["lan_host_info", "wlan_host_list"]:
            try:
                hosts.extend(data.get(key, {}).get("Hosts", {}).get("Host", []))
            except (AttributeError, KeyError, TypeError):
                continue
        return next((h for h in hosts if h.get("MacAddress") == self._mac), None)

    @property
    def name(self) -> str:
        """Return router-scoped name: '<entry.title> <hostname>'."""
        host = self._host_data
        hostname = (host.get("HostName") or self._mac) if host else self._mac
        return f"{self.coordinator.entry.title} {hostname}"

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected to the network."""
        host = self._host_data
        if not host:
            return False
        # Active: "1" or "0"
        return host.get("Active") == "1" or host.get("Active") is None

    @property
    def ip_address(self) -> str | None:
        """Return the primary ip address of the device."""
        host = self._host_data
        if host:
            ip = host.get("IpAddress")
            if ip:
                return ip.split(";")[0]
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

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information with sub-device support."""
        host = self.coordinator.entry.options[CONF_HOST]
        mac = self.coordinator.mac
        sub_id_prefix = mac if mac else f"host_{host}"

        return {
            "identifiers": {(DOMAIN, f"{sub_id_prefix}_clients")},
            "name": f"{self.coordinator.entry.title} Clients",
            "manufacturer": "Huawei",
            "model": self.coordinator.model,
            "sw_version": self.coordinator.sw_version,
            "hw_version": self.coordinator.hw_version,
            "configuration_url": f"http://{host}",
            "via_device": (DOMAIN, f"{sub_id_prefix}_system"),
        }
