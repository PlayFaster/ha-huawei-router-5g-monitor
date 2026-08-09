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


def test_5g_status_name_fallback_skips_the_guest_network(
    mock_coordinator, mock_config_entry
):
    """The 5 GHz name fallback must not match the guest network.

    With no `Radio.2.Ssid.1` path present, `is_on` falls back to matching an
    SSID whose name contains "5G" but not "2.4G", explicitly excluding guest
    networks. Nothing exercised the guest-exclusion branch **while a real 5 GHz
    SSID followed it**, so a mutation dropping the exclusion would have been
    invisible: it would simply have returned the guest network's state.

    Here the guest is enabled and the real 5 GHz radio is disabled, so matching
    the wrong one gives the wrong answer rather than the same answer.
    """
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {
                        "ID": "InternetGatewayDevice.X.Guest.1",
                        "wifiisguestnetwork": "1",
                        "WifiSsid": "Guest-5G",
                        "WifiEnable": "1",
                    },
                    {
                        "ID": "InternetGatewayDevice.X.Other.1",
                        "wifiisguestnetwork": "0",
                        "WifiSsid": "Home-5G",
                        "WifiEnable": "0",
                    },
                ]
            }
        }
    }

    sensor = HuaweiWifi5GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_5G_STATUS_DESCRIPTION
    )

    assert sensor.is_on is False, "the guest 5G network was matched instead"
