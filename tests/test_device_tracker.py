"""Additional tests for the Huawei Router 5G device tracker platform."""

from unittest.mock import MagicMock

import pytest

from custom_components.huawei_router_5g.const import DOMAIN
from custom_components.huawei_router_5g.device_tracker import (
    HuaweiRouterDeviceTracker,
    async_setup_entry,
)


def test_device_tracker_properties(mock_coordinator, mock_config_entry):
    """Test client tracking properties."""
    tracker = HuaweiRouterDeviceTracker(
        mock_coordinator, "AA:BB:CC:DD:EE:01"
    )

    mock_coordinator.data = {
        "lan_host_info": {
            "Hosts": {
                "Host": [
                    {
                        "HostName": "Laptop-1",
                        "MacAddress": "AA:BB:CC:DD:EE:01",
                        "Active": "1",
                        "InterfaceType": "Ethernet",
                    }
                ]
            }
        },
        "wlan_host_list": {"Hosts": {"Host": []}},
    }

    assert tracker.name == "Laptop-1"
    assert tracker.unique_id == "AA:BB:CC:DD:EE:01"
    assert tracker.is_connected is True
    assert tracker.mac_address == "AA:BB:CC:DD:EE:01"
    assert tracker.hostname == "Laptop-1"


def test_device_tracker_update_state(mock_coordinator, mock_config_entry):
    """Test updating client state from coordinator data."""
    tracker = HuaweiRouterDeviceTracker(
        mock_coordinator, "AA:BB:CC:DD:EE:01"
    )

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


@pytest.mark.asyncio
async def test_device_tracker_setup_entry():
    """Test platform setup."""
    hass = MagicMock()
    entry = MagicMock()
    entry.unique_id = "huawei_unique_123"
    entry.entry_id = "test"
    coordinator = MagicMock()
    coordinator.entry = entry
    coordinator.data = {
        "lan_host_info": {"Hosts": {"Host": [{"MacAddress": "AA:BB:CC:DD:EE:01", "Active": "1"}]}},
        "wlan_host_list": {"Hosts": {"Host": []}},
    }
    hass.data = {DOMAIN: {"test": coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
