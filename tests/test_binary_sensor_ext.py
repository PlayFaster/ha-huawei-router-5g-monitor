"""Additional tests for the Huawei Router 5G binary sensor platform."""

from custom_components.huawei_router_5g.binary_sensor import (
    WIFI_5G_STATUS_DESCRIPTION,
    WIFI_24G_STATUS_DESCRIPTION,
    HuaweiWifi5GStatusSensor,
    HuaweiWifi24GStatusSensor,
)

# ---------------------------------------------------------------------------
# HuaweiWifiStatusSensor
# ---------------------------------------------------------------------------


def test_wifi_status_24g_on(mock_coordinator, mock_config_entry):
    """Return True when 2.4G is enabled in multi basic settings."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {"Ssid": [{"Index": "0", "WifiEnable": "1"}]}
        }
    }
    sensor = HuaweiWifi24GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_24G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is True


def test_wifi_status_24g_off(mock_coordinator, mock_config_entry):
    """Return False when 2.4G is disabled in multi basic settings."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {"Ssid": [{"Index": "0", "WifiEnable": "0"}]}
        }
    }
    sensor = HuaweiWifi24GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_24G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is False


def test_wifi_status_5g_on(mock_coordinator, mock_config_entry):
    """Return True when 5G is enabled in multi basic settings."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {"Ssid": [{"Index": "1", "WifiEnable": "1"}]}
        }
    }
    sensor = HuaweiWifi5GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_5G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is True


def test_wifi_status_none_when_missing(mock_coordinator, mock_config_entry):
    """Return None when keys are missing."""
    mock_coordinator.data = {"wlan_wifi_feature_switch": {}}
    sensor = HuaweiWifi24GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_24G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None


def test_wifi_status_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    sensor = HuaweiWifi24GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_24G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None
