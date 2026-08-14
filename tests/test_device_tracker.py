"""Additional tests for the Huawei Router 5G device tracker platform."""

from unittest.mock import MagicMock

import pytest

from custom_components.huawei_router_5g.const import DOMAIN
from custom_components.huawei_router_5g.device_tracker import (
    HuaweiRouterDeviceTracker,
    async_setup_entry,
)
from tests.conftest import assert_links_to_parent


def test_device_tracker_properties(mock_coordinator, mock_config_entry):
    """Test client tracking properties."""
    tracker = HuaweiRouterDeviceTracker(mock_coordinator, "AA:BB:CC:DD:EE:01")

    mock_coordinator.data = {
        "lan_host_info": {
            "Hosts": {
                "Host": [
                    {
                        "HostName": "Laptop-1",
                        "MacAddress": "AA:BB:CC:DD:EE:01",
                        "Active": "1",
                        "InterfaceType": "Ethernet",
                        "AssociatedSsid": "MyWiFi",
                        "AddressSource": "DHCP",
                        "IpAddress": "192.168.8.100;192.168.8.101",
                    }
                ]
            }
        },
        "wlan_host_list": {"Hosts": {"Host": []}},
    }

    assert tracker.name == "Laptop-1"
    # Entry-scoped, not the bare MAC. `ScannerEntity.unique_id` returns the
    # MAC, which collides across two routers tracking the same client — HA
    # then refuses the second entity outright rather than suffixing it.
    assert tracker.unique_id == "huawei_unique_123_AA:BB:CC:DD:EE:01"
    assert tracker.is_connected is True
    assert tracker.mac_address == "AA:BB:CC:DD:EE:01"
    assert tracker.hostname == "Laptop-1"
    assert tracker.ip_address == "192.168.8.100"
    assert tracker.extra_state_attributes == {
        "interface_type": "Ethernet",
        "associated_ssid": "MyWiFi",
        "address_source": "DHCP",
    }


def test_device_tracker_ip_address_variants(mock_coordinator):
    """Test IP address parsing edge cases."""
    tracker = HuaweiRouterDeviceTracker(mock_coordinator, "MAC1")

    # Simple IP
    mock_coordinator.data = {
        "lan_host_info": {
            "Hosts": {"Host": [{"MacAddress": "MAC1", "IpAddress": "10.0.0.1"}]}
        },
        "wlan_host_list": {"Hosts": {"Host": []}},
    }
    assert tracker.ip_address == "10.0.0.1"

    # Missing IP
    mock_coordinator.data = {
        "lan_host_info": {"Hosts": {"Host": [{"MacAddress": "MAC1"}]}},
        "wlan_host_list": {"Hosts": {"Host": []}},
    }
    assert tracker.ip_address is None


def test_device_tracker_missing_host(mock_coordinator):
    """Test fallbacks when host is missing from coordinator data."""
    tracker = HuaweiRouterDeviceTracker(mock_coordinator, "LOST_MAC")

    # Data exists but not for this MAC
    mock_coordinator.data = {
        "lan_host_info": {"Hosts": {"Host": [{"MacAddress": "OTHER", "Active": "1"}]}},
        "wlan_host_list": {"Hosts": {"Host": []}},
    }

    assert tracker.is_connected is False
    assert tracker.name == "LOST_MAC"
    assert tracker.hostname is None
    assert tracker.extra_state_attributes == {}


def test_device_tracker_malformed_data(mock_coordinator):
    """Test resilience to malformed coordinator data."""
    tracker = HuaweiRouterDeviceTracker(mock_coordinator, "MAC1")

    # lan_host_info is not a dict
    mock_coordinator.data = {
        "lan_host_info": "invalid",
        "wlan_host_list": {"Hosts": {"Host": []}},
    }
    assert tracker.is_connected is False

    # Hosts is missing
    mock_coordinator.data = {
        "lan_host_info": {},
        "wlan_host_list": {"Hosts": {"Host": []}},
    }
    assert tracker.is_connected is False


def test_device_tracker_update_state(mock_coordinator, mock_config_entry):
    """Test updating client state from coordinator data."""
    tracker = HuaweiRouterDeviceTracker(mock_coordinator, "AA:BB:CC:DD:EE:01")

    # Simulate coordinator data update where client becomes inactive
    mock_coordinator.data = {
        "lan_host_info": {
            "Hosts": {
                "Host": [
                    {
                        "HostName": "Laptop-1",
                        "MacAddress": "AA:BB:CC:DD:EE:01",
                        "Active": "0",
                    }
                ]
            }
        },
        "wlan_host_list": {"Hosts": {"Host": []}},
    }

    assert tracker.is_connected is False


def test_device_tracker_device_info(mock_coordinator, mock_config_entry):
    """Test device_info generation including fallbacks."""
    tracker = HuaweiRouterDeviceTracker(mock_coordinator, "MAC1")
    # mock_config_entry already has host http://192.168.8.1 in conftest.py
    # and title "My Huawei Router"
    mock_coordinator.mac = "00:11:22:33:44:55"
    mock_coordinator.model = "H165-383"
    mock_coordinator.sw_version = "1.0.1"
    mock_coordinator.hw_version = "v1"

    info = tracker.device_info
    assert info["identifiers"] == {(DOMAIN, "00:11:22:33:44:55_clients")}
    assert info["name"] == "My Huawei Router Clients"
    assert_links_to_parent(info, "00:11:22:33:44:55_system")
    assert info["configuration_url"] == "http://192.168.8.1"

    # Test fallback to host if MAC missing
    mock_coordinator.mac = None
    info = tracker.device_info
    assert info["identifiers"] == {(DOMAIN, "host_http://192.168.8.1_clients")}


@pytest.mark.asyncio
async def test_device_tracker_setup_entry_and_listener():
    """Test platform setup and dynamic discovery via listener."""
    hass = MagicMock()
    entry = MagicMock()
    entry.unique_id = "huawei_unique_123"
    entry.entry_id = "test"
    coordinator = MagicMock()
    coordinator.entry = entry
    # Start with one device
    coordinator.data = {
        "lan_host_info": {"Hosts": {"Host": [{"MacAddress": "MAC1", "Active": "1"}]}},
        "wlan_host_list": {"Hosts": {"Host": []}},
    }
    entry.runtime_data = coordinator

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)

    # Initial setup
    assert async_add_entities.call_count == 1
    initial_entities = async_add_entities.call_args[0][0]
    assert len(initial_entities) == 1
    assert initial_entities[0].mac_address == "MAC1"

    # Extract the listener registered in async_setup_entry
    listener = coordinator.async_add_listener.call_args[0][0]

    # Simulate new device discovered
    coordinator.data = {
        "lan_host_info": {
            "Hosts": {
                "Host": [
                    {"MacAddress": "MAC1", "Active": "1"},
                    {"MacAddress": "MAC2", "Active": "1"},
                ]
            }
        },
        "wlan_host_list": {"Hosts": {"Host": []}},
    }

    # Trigger listener
    listener()

    # Verify new entities added
    assert async_add_entities.call_count == 2
    new_entities = async_add_entities.call_args[0][0]
    assert len(new_entities) == 1
    assert new_entities[0].mac_address == "MAC2"


@pytest.mark.asyncio
async def test_device_tracker_setup_entry_malformed_initial():
    """Test setup resilience when initial data is malformed."""
    hass = MagicMock()
    entry = MagicMock()
    coordinator = MagicMock()
    coordinator.entry = entry
    # data has no 'lan_host_info'
    coordinator.data = {}
    entry.runtime_data = coordinator

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_called_once_with([], True)


def test_device_tracker_no_data(mock_coordinator):
    """Test tracker returns None properties when coordinator data is None."""
    tracker = HuaweiRouterDeviceTracker(mock_coordinator, "MAC1")
    mock_coordinator.data = None

    assert tracker.hostname is None
    assert tracker.is_connected is False
    assert tracker.ip_address is None


@pytest.mark.asyncio
async def test_setup_skips_a_non_dict_host_source_and_keeps_going():
    """A malformed `lan_host_info` must not hide the clients in `wlan_host_list`.

    The discovery loop iterates two keys and guards each with `isinstance(...,
    dict)`. Nothing previously exercised the guard **failing on the first key
    while the second still yields hosts**, so "skipped and continued" and
    "skipped and stopped" were indistinguishable — the loop-guard shape that
    needs two items with the unwanted one first.
    """
    hass = MagicMock()
    entry = MagicMock()
    entry.unique_id = "huawei_unique_123"
    coordinator = MagicMock()
    coordinator.entry = entry
    coordinator.data = {
        # A router that returns an error string here instead of an object.
        "lan_host_info": "ERROR",
        "wlan_host_list": {"Hosts": {"Host": [{"MacAddress": "WMAC1"}]}},
    }
    entry.runtime_data = coordinator

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    assert [e.mac_address for e in entities] == ["WMAC1"], (
        "the wlan_host_list clients were dropped when lan_host_info was malformed"
    )


@pytest.mark.asyncio
async def test_listener_does_not_call_add_entities_when_nothing_is_new():
    """A poll that discovers no new client must not call `async_add_entities`.

    Calling it with an empty list on every poll is harmless but wasteful, and
    the guard that prevents it had never been exercised in the false direction.
    """
    hass = MagicMock()
    entry = MagicMock()
    entry.unique_id = "huawei_unique_123"
    coordinator = MagicMock()
    coordinator.entry = entry
    coordinator.data = {
        "lan_host_info": {"Hosts": {"Host": [{"MacAddress": "MAC1"}]}},
        "wlan_host_list": {"Hosts": {"Host": []}},
    }
    entry.runtime_data = coordinator

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    assert async_add_entities.call_count == 1

    listener = coordinator.async_add_listener.call_args[0][0]

    # Same single client on the next poll — already tracked, so nothing is new.
    listener()

    assert async_add_entities.call_count == 1, (
        "async_add_entities was called again with no new clients"
    )
