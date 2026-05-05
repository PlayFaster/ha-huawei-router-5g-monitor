"""Tests for Huawei Router 5G binary sensors coverage."""

from unittest.mock import MagicMock

import pytest

from custom_components.huawei_router_5g.binary_sensor import (
    HuaweiEndcRestrictedSensor,
    HuaweiEndcStatusSensor,
    HuaweiLteCaSensor,
    HuaweiMobileConnectionSensor,
    HuaweiRoamingSensor,
    HuaweiSimStatusSensor,
    HuaweiSingleSsidModeSensor,
    HuaweiWifi5GStatusSensor,
    HuaweiWifi24GStatusSensor,
)


@pytest.fixture
def mock_coordinator():
    """Mock coordinator fixture."""
    coord = MagicMock()
    coord.data = {}
    return coord


def test_wifi_24g_fallback(mock_coordinator):
    """Test 2.4G WiFi status sensor fallback logic."""
    sensor = HuaweiWifi24GStatusSensor(mock_coordinator, MagicMock(), MagicMock())
    # No ID path match, fallback to index 0
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [{"Index": "0", "WifiEnable": "1", "wifiisguestnetwork": "0"}]
            }
        }
    }
    assert sensor.is_on is True


def test_wifi_5g_fallbacks(mock_coordinator):
    """Test 5G WiFi status sensor fallback logic."""
    sensor = HuaweiWifi5GStatusSensor(mock_coordinator, MagicMock(), MagicMock())

    # Priority 0 match (via ID)
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {
                        "ID": "Radio.2.Ssid.1",
                        "WifiEnable": "1",
                        "wifiisguestnetwork": "0",
                    }
                ]
            }
        }
    }
    assert sensor.is_on is True

    # Fallback 1: Name
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {
                        "WifiSsid": "MyNet_5G",
                        "WifiEnable": "1",
                        "wifiisguestnetwork": "0",
                    }
                ]
            }
        }
    }
    assert sensor.is_on is True

    # Fallback 2: Index 1
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [{"Index": "1", "WifiEnable": "1", "wifiisguestnetwork": "0"}]
            }
        }
    }
    assert sensor.is_on is True

    # Fallback 3: Index 5
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [{"Index": "5", "WifiEnable": "1", "wifiisguestnetwork": "0"}]
            }
        }
    }
    assert sensor.is_on is True

    # Fallback 4: Index not 0
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [{"Index": "3", "WifiEnable": "1", "wifiisguestnetwork": "0"}]
            }
        }
    }
    assert sensor.is_on is True


def test_other_sensors(mock_coordinator):
    """Test miscellaneous binary sensors."""
    endc = HuaweiEndcStatusSensor(mock_coordinator, MagicMock(), MagicMock())
    mock_coordinator.data = {"monitoring_status": {"EndcStatus": "1"}}
    assert endc.is_on is True

    endc_rest = HuaweiEndcRestrictedSensor(mock_coordinator, MagicMock(), MagicMock())
    mock_coordinator.data = {"monitoring_status": {"endcRestrictedStatus": "1"}}
    assert endc_rest.is_on is True

    single_ssid = HuaweiSingleSsidModeSensor(mock_coordinator, MagicMock(), MagicMock())
    mock_coordinator.data = {"wlan_multi_basic_settings": {"DbhoEnable": "1"}}
    assert single_ssid.is_on is True

    mock_coordinator.data = {"wlan_wifi_feature_switch": {"wifi_dbdc_enable": "1"}}
    assert single_ssid.is_on is True

    roaming = HuaweiRoamingSensor(mock_coordinator, MagicMock(), MagicMock())
    mock_coordinator.data = {"monitoring_status": {"RoamingStatus": "1"}}
    assert roaming.is_on is True

    sim = HuaweiSimStatusSensor(mock_coordinator, MagicMock(), MagicMock())
    mock_coordinator.data = {"monitoring_status": {"SimStatus": "2"}}
    assert sim.is_on is True

    mock_coordinator.data = {"monitoring_status": {}}
    assert sim.is_on is None

    mobile = HuaweiMobileConnectionSensor(mock_coordinator, MagicMock(), MagicMock())
    mock_coordinator.data = {"monitoring_status": {"ConnectionStatus": "901"}}
    assert mobile.is_on is True

    lte_ca = HuaweiLteCaSensor(mock_coordinator, MagicMock(), MagicMock())
    mock_coordinator.data = {"device_signal": {"band": "B3+B7"}}
    assert lte_ca.is_on is True
    mock_coordinator.data = {"device_signal": {"band": "B3"}}
    assert lte_ca.is_on is False
