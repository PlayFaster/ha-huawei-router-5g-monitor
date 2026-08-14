"""Device tracker platform for Huawei Router 5G."""

import logging
from typing import Any

from homeassistant.components.device_tracker import (  # type: ignore[attr-defined]
    ScannerEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import build_device_info

# Section 22. `0` (unlimited) — this platform is read-only. Entities are
# coordinator-driven with no per-entity polling, so there is nothing to
# serialize.
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

    # dev_standards Section 14. A device tracker publishes one entity per
    # client on the network, so these attributes are written to the recorder
    # once per client per poll. `associated_ssid` in particular is network
    # topology that does not belong in long-term history.
    _unrecorded_attributes = frozenset(
        {"interface_type", "associated_ssid", "address_source"}
    )

    def __init__(
        self, coordinator: HuaweiRouter5GDataUpdateCoordinator, mac: str
    ) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self._mac = mac

    @property
    def unique_id(self) -> str | None:
        """Scope the unique ID to this config entry.

        `ScannerEntity.unique_id` is a property returning the bare MAC address,
        which is **not** unique across config entries. Two Huawei routers
        seeing the same client produce the same id, and Home Assistant's
        response is to refuse the second entity outright — `entity_platform`
        logs "does not generate unique IDs ... ignoring" and the client simply
        never appears under the second router. That is not the `_2` suffix
        behavior, which applies to entity **ids**, not unique ids.

        This must be a property override. `_attr_unique_id` was set in
        `__init__` for a long time and did nothing at all, because the base
        class defines `unique_id` as a property and a property wins over the
        attribute it would otherwise read.

        Existing installations are migrated in `async_setup_entry`, so entity
        ids, names, areas and enabled state are preserved.
        """
        return f"{self.coordinator.entry.unique_id}_{self._mac}"

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
