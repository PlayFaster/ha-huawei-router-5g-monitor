"""Tests for the Huawei Router 5G binary sensor platform."""

from unittest.mock import MagicMock

import pytest

from custom_components.huawei_router_5g.binary_sensor import (
    BEST_CONN_DESCRIPTION,
    ENDC_STATUS_DESCRIPTION,
    LTE_CA_DESCRIPTION,
    MOBILE_CONN_DESCRIPTION,
    ROAMING_DESCRIPTION,
    SIM_STATUS_DESCRIPTION,
    SINGLE_SSID_MODE_DESCRIPTION,
    SMS_STORAGE_FULL_DESCRIPTION,
    VALUE_BINARY_SENSORS,
    WIFI_5G_STATUS_DESCRIPTION,
    WIFI_24G_STATUS_DESCRIPTION,
    WIFI_STATUS_DESCRIPTION,
    HuaweiBestConnectionSensor,
    HuaweiEndcStatusSensor,
    HuaweiLteCaSensor,
    HuaweiMobileConnectionSensor,
    HuaweiRoamingSensor,
    HuaweiSimStatusSensor,
    HuaweiSingleSsidModeSensor,
    HuaweiSmsStorageFullSensor,
    HuaweiValueBinarySensor,
    HuaweiWifi5GStatusSensor,
    HuaweiWifi24GStatusSensor,
    HuaweiWifiStatusSensor,
    _flag,
    async_setup_entry,
)
from custom_components.huawei_router_5g.const import DOMAIN
from tests.conftest import assert_links_to_parent

# ---------------------------------------------------------------------------
# HuaweiBestConnectionSensor
# ---------------------------------------------------------------------------


def test_best_connection_5g_active(mock_coordinator, mock_config_entry):
    """Return True when NSA 5G is present and health gates pass."""
    mock_coordinator.data = {
        "device_signal": {
            "band": "20MHz@500(B1) + 10MHz@152690(N28)",
            "rsrp": "-90dBm",
            "nrrsrp": "-95dBm",
        }
    }
    sensor = HuaweiBestConnectionSensor(
        mock_coordinator, mock_config_entry, BEST_CONN_DESCRIPTION
    )
    assert sensor.is_on is True
    assert sensor.icon is None


def test_best_connection_5g_inactive_no_nr_band(mock_coordinator, mock_config_entry):
    """Return False when NR band label is missing from band string."""
    mock_coordinator.data = {
        "device_signal": {
            "band": "20MHz@500(B1)",
            "rsrp": "-90dBm",
        }
    }
    sensor = HuaweiBestConnectionSensor(
        mock_coordinator, mock_config_entry, BEST_CONN_DESCRIPTION
    )
    assert sensor.is_on is False
    assert sensor.icon is None


def test_best_connection_lte_unhealthy(mock_coordinator, mock_config_entry):
    """Return False when LTE anchor health gate fails."""
    mock_coordinator.data = {
        "device_signal": {
            "band": "20MHz@500(B1) + 10MHz@152690(N28)",
            "rsrp": "-110dBm",  # Below -100 threshold
            "sinr": "10dB",  # Below 15 threshold
            "rsrq": "-15dB",  # Below -12 threshold
        }
    }
    sensor = HuaweiBestConnectionSensor(
        mock_coordinator, mock_config_entry, BEST_CONN_DESCRIPTION
    )
    assert sensor.is_on is False


def test_best_connection_no_signal_data(mock_coordinator, mock_config_entry):
    """Return None when device_signal is absent."""
    mock_coordinator.data = {}
    sensor = HuaweiBestConnectionSensor(
        mock_coordinator, mock_config_entry, BEST_CONN_DESCRIPTION
    )
    assert sensor.is_on is None


def test_best_connection_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator has no data at all."""
    mock_coordinator.data = None
    sensor = HuaweiBestConnectionSensor(
        mock_coordinator, mock_config_entry, BEST_CONN_DESCRIPTION
    )
    assert sensor.is_on is None


def test_best_connection_device_info(mock_coordinator, mock_config_entry):
    """Test device_info links to the signal sub-device."""
    sensor = HuaweiBestConnectionSensor(
        mock_coordinator, mock_config_entry, BEST_CONN_DESCRIPTION
    )
    info = sensor.device_info
    mac = "DC:71:96:11:22:33"
    assert info["identifiers"] == {(DOMAIN, f"{mac}_signal")}
    assert info["manufacturer"] == "Huawei"
    assert_links_to_parent(info, f"{mac}_system")


# ---------------------------------------------------------------------------
# HuaweiLteCaSensor
# ---------------------------------------------------------------------------


def test_lte_ca_active(mock_coordinator, mock_config_entry):
    """Return True when '+' is present in the band string."""
    mock_coordinator.data = {"device_signal": {"band": "20MHz(B1) + 15MHz(B3)"}}
    sensor = HuaweiLteCaSensor(mock_coordinator, mock_config_entry, LTE_CA_DESCRIPTION)
    assert sensor.is_on is True


def test_lte_ca_inactive(mock_coordinator, mock_config_entry):
    """Return False when '+' is missing from the band string."""
    mock_coordinator.data = {"device_signal": {"band": "20MHz(B1)"}}
    sensor = HuaweiLteCaSensor(mock_coordinator, mock_config_entry, LTE_CA_DESCRIPTION)
    assert sensor.is_on is False


def test_lte_ca_no_data(mock_coordinator, mock_config_entry):
    """Return None when band data is missing."""
    mock_coordinator.data = {"device_signal": {}}
    sensor = HuaweiLteCaSensor(mock_coordinator, mock_config_entry, LTE_CA_DESCRIPTION)
    assert sensor.is_on is None


# ---------------------------------------------------------------------------
# HuaweiSmsStorageFullSensor
# ---------------------------------------------------------------------------


def test_sms_storage_full_true(mock_coordinator, mock_config_entry):
    """Return True when SmsStorageFull flag is '1'."""
    mock_coordinator.data = {"monitoring_check_notifications": {"SmsStorageFull": "1"}}
    sensor = HuaweiSmsStorageFullSensor(
        mock_coordinator, mock_config_entry, SMS_STORAGE_FULL_DESCRIPTION
    )
    assert sensor.is_on is True


def test_sms_storage_full_false(mock_coordinator, mock_config_entry):
    """Return False when SmsStorageFull flag is '0'."""
    mock_coordinator.data = {"monitoring_check_notifications": {"SmsStorageFull": "0"}}
    sensor = HuaweiSmsStorageFullSensor(
        mock_coordinator, mock_config_entry, SMS_STORAGE_FULL_DESCRIPTION
    )
    assert sensor.is_on is False


def test_sms_storage_full_none_when_missing(mock_coordinator, mock_config_entry):
    """Return None when SmsStorageFull key is absent."""
    mock_coordinator.data = {"monitoring_status": {}}
    sensor = HuaweiSmsStorageFullSensor(
        mock_coordinator, mock_config_entry, SMS_STORAGE_FULL_DESCRIPTION
    )
    assert sensor.is_on is None


def test_sms_storage_full_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is absent."""
    mock_coordinator.data = None
    sensor = HuaweiSmsStorageFullSensor(
        mock_coordinator, mock_config_entry, SMS_STORAGE_FULL_DESCRIPTION
    )
    assert sensor.is_on is None


def test_sms_storage_full_device_info(mock_coordinator, mock_config_entry):
    """Test device_info links to the SMS sub-device."""
    sensor = HuaweiSmsStorageFullSensor(
        mock_coordinator, mock_config_entry, SMS_STORAGE_FULL_DESCRIPTION
    )
    info = sensor.device_info
    mac = "DC:71:96:11:22:33"
    assert info["identifiers"] == {(DOMAIN, f"{mac}_sms")}
    assert_links_to_parent(info, f"{mac}_system")


def test_lte_ca_no_coordinator_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    sensor = HuaweiLteCaSensor(mock_coordinator, mock_config_entry, LTE_CA_DESCRIPTION)
    assert sensor.is_on is None


# ---------------------------------------------------------------------------
# HuaweiWifiStatusSensor
# ---------------------------------------------------------------------------


def test_wifi_status_on(mock_coordinator, mock_config_entry):
    """Return True when WifiStatus is '1'."""
    mock_coordinator.data = {"monitoring_status": {"WifiStatus": "1"}}
    sensor = HuaweiWifiStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_STATUS_DESCRIPTION
    )
    assert sensor.is_on is True


def test_wifi_status_off(mock_coordinator, mock_config_entry):
    """Return False when WifiStatus is '0'."""
    mock_coordinator.data = {"monitoring_status": {"WifiStatus": "0"}}
    sensor = HuaweiWifiStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_STATUS_DESCRIPTION
    )
    assert sensor.is_on is False


def test_wifi_status_missing_key(mock_coordinator, mock_config_entry):
    """Return None when WifiStatus key is missing."""
    mock_coordinator.data = {"monitoring_status": {}}
    sensor = HuaweiWifiStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None


def test_wifi_status_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    sensor = HuaweiWifiStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None


# ---------------------------------------------------------------------------
# HuaweiWifi24GStatusSensor
# ---------------------------------------------------------------------------


def test_wifi_24g_status_on(mock_coordinator, mock_config_entry):
    """Return True when wifi24g (Index 0) is enabled."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [{"Index": "0", "WifiEnable": "1", "wifiisguestnetwork": "0"}]
            }
        }
    }
    sensor = HuaweiWifi24GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_24G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is True


def test_wifi_24g_status_on_dynamic(mock_coordinator, mock_config_entry):
    """Return True when wifi24g is found by dynamic path."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {
                        "ID": "InternetGatewayDevice.X_Config.Wifi.Radio.1.Ssid.1.",
                        "WifiEnable": "1",
                        "Index": "10",
                    }
                ]
            }
        }
    }
    sensor = HuaweiWifi24GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_24G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is True


def test_wifi_24g_status_no_ssid_match(mock_coordinator, mock_config_entry):
    """Return None when no matching SSID is found."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {
                        "ID": "InternetGatewayDevice.X_Config.Wifi.Radio.2.Ssid.1.",
                        "WifiEnable": "1",
                        "Index": "5",
                    }
                ]
            }
        }
    }
    sensor = HuaweiWifi24GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_24G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None


def test_wifi_24g_status_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    sensor = HuaweiWifi24GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_24G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None


# ---------------------------------------------------------------------------
# HuaweiWifi5GStatusSensor
# ---------------------------------------------------------------------------


def test_wifi_5g_status_on(mock_coordinator, mock_config_entry):
    """Return True when wifi5g (Index 1) is enabled."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [{"Index": "1", "WifiEnable": "1", "wifiisguestnetwork": "0"}]
            }
        }
    }
    sensor = HuaweiWifi5GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_5G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is True


def test_wifi_5g_status_on_dynamic(mock_coordinator, mock_config_entry):
    """Return True when wifi5g is found by dynamic path (Radio.2)."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {
                        "ID": "InternetGatewayDevice.X_Config.Wifi.Radio.2.Ssid.1.",
                        "WifiEnable": "1",
                        "Index": "5",
                    }
                ]
            }
        }
    }
    sensor = HuaweiWifi5GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_5G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is True


def test_wifi_5g_status_fallback_index_5(mock_coordinator, mock_config_entry):
    """Return True when using fallback Index 5."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [{"Index": "5", "WifiEnable": "1", "wifiisguestnetwork": "0"}]
            }
        }
    }
    sensor = HuaweiWifi5GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_5G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is True


def test_wifi_5g_status_fallback_non_guest(mock_coordinator, mock_config_entry):
    """Return True when using fallback first non-guest SSID not Index 0."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {"Index": "0", "WifiEnable": "1", "wifiisguestnetwork": "0"},
                    {"Index": "2", "WifiEnable": "1", "wifiisguestnetwork": "0"},
                ]
            }
        }
    }
    sensor = HuaweiWifi5GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_5G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is True


def test_wifi_5g_status_no_match(mock_coordinator, mock_config_entry):
    """Return None when no matching SSID is found."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [{"Index": "0", "WifiEnable": "1", "wifiisguestnetwork": "0"}]
            }
        }
    }
    sensor = HuaweiWifi5GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_5G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None


def test_wifi_5g_status_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    sensor = HuaweiWifi5GStatusSensor(
        mock_coordinator, mock_config_entry, WIFI_5G_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None


# ---------------------------------------------------------------------------
# HuaweiEndcStatusSensor
# ---------------------------------------------------------------------------


def test_endc_status_on(mock_coordinator, mock_config_entry):
    """Return True when EndcStatus is '1'."""
    mock_coordinator.data = {"monitoring_status": {"EndcStatus": "1"}}
    sensor = HuaweiEndcStatusSensor(
        mock_coordinator, mock_config_entry, ENDC_STATUS_DESCRIPTION
    )
    assert sensor.is_on is True


def test_endc_status_off(mock_coordinator, mock_config_entry):
    """Return False when EndcStatus is '0'."""
    mock_coordinator.data = {"monitoring_status": {"EndcStatus": "0"}}
    sensor = HuaweiEndcStatusSensor(
        mock_coordinator, mock_config_entry, ENDC_STATUS_DESCRIPTION
    )
    assert sensor.is_on is False


def test_endc_status_missing(mock_coordinator, mock_config_entry):
    """Return None when EndcStatus key is missing."""
    mock_coordinator.data = {"monitoring_status": {}}
    sensor = HuaweiEndcStatusSensor(
        mock_coordinator, mock_config_entry, ENDC_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None


def test_endc_status_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    sensor = HuaweiEndcStatusSensor(
        mock_coordinator, mock_config_entry, ENDC_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None


# ---------------------------------------------------------------------------
# HuaweiSingleSsidModeSensor
# ---------------------------------------------------------------------------


def test_single_ssid_mode_dbho(mock_coordinator, mock_config_entry):
    """Return True when DbhoEnable is '1'."""
    mock_coordinator.data = {"wlan_multi_basic_settings": {"DbhoEnable": "1"}}
    sensor = HuaweiSingleSsidModeSensor(
        mock_coordinator, mock_config_entry, SINGLE_SSID_MODE_DESCRIPTION
    )
    assert sensor.is_on is True


def test_single_ssid_mode_feature_switch(mock_coordinator, mock_config_entry):
    """Return True when feature switch indicates single SSID mode."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {"DbhoEnable": "0"},
        "wlan_wifi_feature_switch": {"stafrequenceenable": "1"},
    }
    sensor = HuaweiSingleSsidModeSensor(
        mock_coordinator, mock_config_entry, SINGLE_SSID_MODE_DESCRIPTION
    )
    assert sensor.is_on is True


def test_single_ssid_mode_dbdc_enable(mock_coordinator, mock_config_entry):
    """Return True when wifi_dbdc_enable is '1'."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {"DbhoEnable": "0"},
        "wlan_wifi_feature_switch": {
            "stafrequenceenable": "0",
            "wifi_dbdc_enable": "1",
        },
    }
    sensor = HuaweiSingleSsidModeSensor(
        mock_coordinator, mock_config_entry, SINGLE_SSID_MODE_DESCRIPTION
    )
    assert sensor.is_on is True


def test_single_ssid_mode_false(mock_coordinator, mock_config_entry):
    """Return False when no single SSID mode indicators are present."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {"DbhoEnable": "0"},
        "wlan_wifi_feature_switch": {
            "stafrequenceenable": "0",
            "wifi_dbdc_enable": "0",
        },
    }
    sensor = HuaweiSingleSsidModeSensor(
        mock_coordinator, mock_config_entry, SINGLE_SSID_MODE_DESCRIPTION
    )
    assert sensor.is_on is False


def test_single_ssid_mode_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    sensor = HuaweiSingleSsidModeSensor(
        mock_coordinator, mock_config_entry, SINGLE_SSID_MODE_DESCRIPTION
    )
    assert sensor.is_on is None


# ---------------------------------------------------------------------------
# HuaweiRoamingSensor
# ---------------------------------------------------------------------------


def test_roaming_on(mock_coordinator, mock_config_entry):
    """Return True when RoamingStatus is '1'."""
    mock_coordinator.data = {"monitoring_status": {"RoamingStatus": "1"}}
    sensor = HuaweiRoamingSensor(
        mock_coordinator, mock_config_entry, ROAMING_DESCRIPTION
    )
    assert sensor.is_on is True


def test_roaming_off(mock_coordinator, mock_config_entry):
    """Return False when RoamingStatus is '0'."""
    mock_coordinator.data = {"monitoring_status": {"RoamingStatus": "0"}}
    sensor = HuaweiRoamingSensor(
        mock_coordinator, mock_config_entry, ROAMING_DESCRIPTION
    )
    assert sensor.is_on is False


def test_roaming_missing(mock_coordinator, mock_config_entry):
    """Return None when RoamingStatus key is missing."""
    mock_coordinator.data = {"monitoring_status": {}}
    sensor = HuaweiRoamingSensor(
        mock_coordinator, mock_config_entry, ROAMING_DESCRIPTION
    )
    assert sensor.is_on is None


def test_roaming_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    sensor = HuaweiRoamingSensor(
        mock_coordinator, mock_config_entry, ROAMING_DESCRIPTION
    )
    assert sensor.is_on is None


# ---------------------------------------------------------------------------
# HuaweiSimStatusSensor
# ---------------------------------------------------------------------------


def test_sim_status_problem(mock_coordinator, mock_config_entry):
    """Return True when SimStatus is not '1'."""
    for status in ("0", "2", "3", "99"):
        mock_coordinator.data = {"monitoring_status": {"SimStatus": status}}
        sensor = HuaweiSimStatusSensor(
            mock_coordinator, mock_config_entry, SIM_STATUS_DESCRIPTION
        )
        assert sensor.is_on is True


def test_sim_status_ready(mock_coordinator, mock_config_entry):
    """Return False when SimStatus is '1'."""
    mock_coordinator.data = {"monitoring_status": {"SimStatus": "1"}}
    sensor = HuaweiSimStatusSensor(
        mock_coordinator, mock_config_entry, SIM_STATUS_DESCRIPTION
    )
    assert sensor.is_on is False


def test_sim_status_missing(mock_coordinator, mock_config_entry):
    """Return None when SimStatus key is missing."""
    mock_coordinator.data = {"monitoring_status": {}}
    sensor = HuaweiSimStatusSensor(
        mock_coordinator, mock_config_entry, SIM_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None


def test_sim_status_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    sensor = HuaweiSimStatusSensor(
        mock_coordinator, mock_config_entry, SIM_STATUS_DESCRIPTION
    )
    assert sensor.is_on is None


# ---------------------------------------------------------------------------
# HuaweiMobileConnectionSensor
# ---------------------------------------------------------------------------


def test_mobile_connection_active(mock_coordinator, mock_config_entry):
    """Return True when ConnectionStatus is '901'."""
    mock_coordinator.data = {"monitoring_status": {"ConnectionStatus": "901"}}
    sensor = HuaweiMobileConnectionSensor(
        mock_coordinator, mock_config_entry, MOBILE_CONN_DESCRIPTION
    )
    assert sensor.is_on is True


def test_mobile_connection_inactive(mock_coordinator, mock_config_entry):
    """Return False when ConnectionStatus is not '901'."""
    mock_coordinator.data = {"monitoring_status": {"ConnectionStatus": "902"}}
    sensor = HuaweiMobileConnectionSensor(
        mock_coordinator, mock_config_entry, MOBILE_CONN_DESCRIPTION
    )
    assert sensor.is_on is False


def test_mobile_connection_missing(mock_coordinator, mock_config_entry):
    """Return None when ConnectionStatus key is missing."""
    mock_coordinator.data = {"monitoring_status": {}}
    sensor = HuaweiMobileConnectionSensor(
        mock_coordinator, mock_config_entry, MOBILE_CONN_DESCRIPTION
    )
    assert sensor.is_on is None


def test_mobile_connection_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    sensor = HuaweiMobileConnectionSensor(
        mock_coordinator, mock_config_entry, MOBILE_CONN_DESCRIPTION
    )
    assert sensor.is_on is None


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_binary_sensor_setup_entry():
    """Test that async_setup_entry creates all binary sensors."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    coordinator = MagicMock()
    hass.data = {DOMAIN: {"test": coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    # 13 purpose-built subclasses plus every VALUE_BINARY_SENSORS description.
    # Derived rather than hard-coded, so adding a description cannot silently
    # skip registration - the count would still match a stale literal.
    assert len(entities) == 13 + len(VALUE_BINARY_SENSORS)


# ---------------------------------------------------------------------------
# §T-4 value-driven binary sensors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("2", True),
        ("true", True),
        ("0", False),
        ("off", False),
        ("OFF", False),
        ("false", False),
        (None, None),
        ("", None),
    ],
)
def test_a_router_flag_maps_to_a_bool(raw, expected) -> None:
    """`0`/`off`/`false` are all off, in any casing.

    An exact match on one spelling is the defect `zte_router_5g` shipped in its
    projection guard, and nothing in this API guarantees casing.
    """
    data = {"monitoring_status": {"poorSignalStatus": raw}}
    assert _flag(data, "monitoring_status", "poorSignalStatus") is expected


def test_a_missing_block_reads_as_unavailable_not_false() -> None:
    """An endpoint that failed its fetch must not publish a confident `off`."""
    assert _flag({}, "csps_state", "psstate") is None
    assert _flag(None, "csps_state", "psstate") is None
    assert _flag({"csps_state": None}, "csps_state", "psstate") is None


@pytest.mark.parametrize("description", VALUE_BINARY_SENSORS)
def test_every_value_binary_sensor_reads_its_flag(description) -> None:
    """Each description must actually resolve against a realistic payload.

    A `value_fn` pointed at the wrong block or a misspelled key returns None
    forever and looks exactly like an endpoint the router does not support.
    """
    data = {
        "monitoring_status": {"poorSignalStatus": "1", "speedLimitStatus": "1"},
        "csps_state": {"psstate": "1", "csstate": "1"},
        "start_date": {"SetMonthData": "1"},
        "converged_status": {"SimLockEnable": "1"},
        "dial_up_connection": {"RoamAutoConnectEnable": "1"},
        "security_sip": {"SipStatus": "1"},
        "security_upnp": {"UpnpStatus": "1"},
        "voice_volte": {"volte_enable": "1"},
    }
    coordinator = MagicMock()
    coordinator.data = data
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = HuaweiValueBinarySensor(coordinator, entry, description)
    assert sensor.is_on is True, f"{description.key} did not resolve"


def test_a_description_without_a_value_fn_reports_unavailable() -> None:
    """The guard exists so a mistake degrades rather than raises.

    Covered by a test rather than silenced with a `pragma: no cover` — a
    suppression would need a reviewed allow-list entry claiming the branch
    cannot be reached, which is a claim, not a fact.
    """
    coordinator = MagicMock()
    coordinator.data = {}
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = HuaweiValueBinarySensor(coordinator, entry, BEST_CONN_DESCRIPTION)
    assert sensor.is_on is None
