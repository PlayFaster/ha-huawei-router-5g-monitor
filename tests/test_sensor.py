"""Tests for the Huawei Router 5G sensor platform."""

from unittest.mock import MagicMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.huawei_router_5g.const import DOMAIN
from custom_components.huawei_router_5g.sensor import (
    SENSOR_TYPES,
    HuaweiRouterSensor,
    async_setup_entry,
)

# ---------------------------------------------------------------------------
# System sensors
# ---------------------------------------------------------------------------


def test_sensor_model_name(mock_coordinator, mock_config_entry):
    """Test model name extraction from device_information."""
    mock_coordinator.data = {"device_information": {"DeviceName": "B535s-232"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "model_name")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == "B535s-232"


def test_sensor_sw_version(mock_coordinator, mock_config_entry):
    """Test software version extraction."""
    mock_coordinator.data = {
        "device_information": {"SoftwareVersion": "11.0.1.1(H192SP1C983)"}
    }
    desc = next(d for d in SENSOR_TYPES if d.key == "sw_version")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == "11.0.1.1(H192SP1C983)"


def test_sensor_last_updated(mock_coordinator, mock_config_entry):
    """Test last_updated returns coordinator timestamp."""
    now = dt_util.now()
    mock_coordinator.last_update_success_time = now
    mock_coordinator.data = {"some": "data"}
    desc = next(d for d in SENSOR_TYPES if d.key == "last_updated")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == now


def test_sensor_total_connection_time(mock_coordinator, mock_config_entry):
    """Test total connection time is parsed as integer."""
    mock_coordinator.data = {"traffic_statistics": {"TotalConnectTime": "86400"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "total_connection_time")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 86400


# ---------------------------------------------------------------------------
# Signal sensors
# ---------------------------------------------------------------------------


def test_sensor_network_type(mock_coordinator, mock_config_entry):
    """Test network type is mapped to human-readable label."""
    mock_coordinator.data = {"monitoring_status": {"CurrentNetworkType": "19"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "network_type")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == "LTE"


def test_sensor_signal_bars(mock_coordinator, mock_config_entry):
    """Test signal bars integer extraction."""
    mock_coordinator.data = {"monitoring_status": {"SignalIcon": "4"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "signal_bars")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 4


def test_sensor_rsrp_parsing(mock_coordinator, mock_config_entry):
    """Test RSRP value is parsed with unit stripped."""
    mock_coordinator.data = {"device_signal": {"rsrp": "-95dBm"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "rsrp")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == -95.0


def test_sensor_rsrq_parsing(mock_coordinator, mock_config_entry):
    """Test RSRQ value is parsed with unit stripped."""
    mock_coordinator.data = {"device_signal": {"rsrq": "-12dB"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "rsrq")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == -12.0


def test_sensor_sinr_parsing(mock_coordinator, mock_config_entry):
    """Test SINR value with positive dB suffix."""
    mock_coordinator.data = {"device_signal": {"sinr": "6dB"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "sinr")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 6.0


def test_sensor_rsrp_guard_band_min(mock_coordinator, mock_config_entry):
    """Test RSRP guard band filters implausibly low values."""
    mock_coordinator.data = {"device_signal": {"rsrp": "-200dBm"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "rsrp")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value is None


def test_sensor_rsrp_guard_band_max(mock_coordinator, mock_config_entry):
    """Test RSRP guard band filters implausibly high values."""
    mock_coordinator.data = {"device_signal": {"rsrp": "-10dBm"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "rsrp")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value is None


def test_sensor_nr5g_band(mock_coordinator, mock_config_entry):
    """Test 5G NR band extraction from composite band string."""
    mock_coordinator.data = {"device_signal": {"band": "20MHz(B1) + 10MHz(N28)"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "nr5g_band")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == "N28"


def test_sensor_nr5g_band_empty(mock_coordinator, mock_config_entry):
    """Test empty band string returns None."""
    mock_coordinator.data = {"device_signal": {"band": ""}}
    desc = next(d for d in SENSOR_TYPES if d.key == "nr5g_band")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value is None


def test_sensor_operator(mock_coordinator, mock_config_entry):
    """Test operator full name extraction."""
    mock_coordinator.data = {"current_plmn": {"FullName": "Three"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "operator")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == "Three"


# ---------------------------------------------------------------------------
# Data sensors
# ---------------------------------------------------------------------------


def test_sensor_download_rate(mock_coordinator, mock_config_entry):
    """Test download rate integer extraction."""
    mock_coordinator.data = {"traffic_statistics": {"CurrentDownloadRate": "102400"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "current_download_rate")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 102400


def test_sensor_total_download(mock_coordinator, mock_config_entry):
    """Test total download byte count."""
    mock_coordinator.data = {"traffic_statistics": {"TotalDownload": "5368709120"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "total_download")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 5368709120


def test_sensor_total_data_sum(mock_coordinator, mock_config_entry):
    """Test total data sums download and upload."""
    mock_coordinator.data = {
        "traffic_statistics": {
            "TotalDownload": "1073741824",
            "TotalUpload": "536870912",
        }
    }
    desc = next(d for d in SENSOR_TYPES if d.key == "total_data")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 1073741824 + 536870912


def test_sensor_total_data_none_when_missing(mock_coordinator, mock_config_entry):
    """Test total data returns None when source keys are absent."""
    mock_coordinator.data = {"traffic_statistics": {}}
    desc = next(d for d in SENSOR_TYPES if d.key == "total_data")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value is None


def test_sensor_month_download(mock_coordinator, mock_config_entry):
    """Test monthly download byte count."""
    mock_coordinator.data = {"month_statistics": {"CurrentMonthDownload": "2147483648"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "month_download")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 2147483648


def test_sensor_month_download_gb(mock_coordinator, mock_config_entry):
    """Test monthly download GB conversion (2GB → 2.0)."""
    mock_coordinator.data = {"month_statistics": {"CurrentMonthDownload": "2147483648"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "month_download_gb")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 2.0


# ---------------------------------------------------------------------------
# SMS sensors
# ---------------------------------------------------------------------------


def test_sensor_sms_unread(mock_coordinator, mock_config_entry):
    """Test total unread SMS sums local and SIM unread."""
    mock_coordinator.data = {"sms_count": {"LocalUnread": "2", "SimUnread": "1"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "sms_unread")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 3


def test_sensor_sms_total(mock_coordinator, mock_config_entry):
    """Test total SMS sums local inbox/outbox/draft."""
    mock_coordinator.data = {
        "sms_count": {
            "LocalInbox": "10",
            "LocalOutbox": "3",
            "LocalDraft": "1",
        }
    }
    desc = next(d for d in SENSOR_TYPES if d.key == "sms_total")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 14


def test_sensor_lte_bandwidth(mock_coordinator, mock_config_entry):
    """Test LTE bandwidth parsing (from dlbandwidth/ulbandwidth API keys)."""
    mock_coordinator.data = {
        "device_signal": {"dlbandwidth": "20.0", "ulbandwidth": "15.0"}
    }

    desc_dl = next(d for d in SENSOR_TYPES if d.key == "lte_downlink_bandwidth")
    sensor_dl = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc_dl)
    assert sensor_dl.native_value == 20.0

    desc_ul = next(d for d in SENSOR_TYPES if d.key == "lte_uplink_bandwidth")
    sensor_ul = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc_ul)
    assert sensor_ul.native_value == 15.0


def test_sensor_lte_frequency(mock_coordinator, mock_config_entry):
    """Test LTE frequency parsing (from ltedlfreq/lteulfreq API keys)."""
    mock_coordinator.data = {
        "device_signal": {"ltedlfreq": "21600", "lteulfreq": "19700"}
    }

    desc_dl = next(d for d in SENSOR_TYPES if d.key == "lte_downlink_frequency")
    sensor_dl = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc_dl)
    assert sensor_dl.native_value == 2160.0

    desc_ul = next(d for d in SENSOR_TYPES if d.key == "lte_uplink_frequency")
    sensor_ul = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc_ul)
    assert sensor_ul.native_value == 1970.0


def test_sensor_sms_total_attributes(mock_coordinator, mock_config_entry):
    """Test that sms_total has detailed breakdown in extra_state_attributes."""
    mock_coordinator.data = {
        "sms_count": {
            "LocalUnread": "2",
            "LocalRead": "8",
            "LocalSent": "0",
            "LocalDraft": "0",
            "LocalMax": "500",
            "SimUnread": "0",
            "SimRead": "0",
            "SimMax": "20",
        }
    }
    desc = next(d for d in SENSOR_TYPES if d.key == "sms_total")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    attrs = sensor.extra_state_attributes
    assert attrs["local_unread"] == 2
    assert attrs["local_read"] == 8
    assert attrs["local_max"] == 500
    assert attrs["sim_max"] == 20


def test_sensor_sms_total_attributes_error(mock_coordinator, mock_config_entry):
    """Test that bad sms_count data returns empty attributes."""
    mock_coordinator.data = {"sms_count": {"LocalUnread": "fail"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "sms_total")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# Device info (sub-device grouping)
# ---------------------------------------------------------------------------


def test_sensor_device_info_system_group(mock_coordinator, mock_config_entry):
    """Test that system group sensor is the root device (no via_device)."""
    mac = "DC:71:96:11:22:33"
    desc = next(d for d in SENSOR_TYPES if d.key == "model_name")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    info = sensor.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_system")}
    assert info["name"] == "My Huawei Router System"
    assert "via_device" not in info
    assert info["manufacturer"] == "Huawei"


def test_sensor_device_info_signal_group(mock_coordinator, mock_config_entry):
    """Test that signal group sensor links via system device."""
    mac = "DC:71:96:11:22:33"
    desc = next(d for d in SENSOR_TYPES if d.key == "rsrp")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    info = sensor.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_signal")}
    assert info["name"] == "My Huawei Router Signal"
    assert info["via_device"] == (DOMAIN, f"{mac}_system")


def test_sensor_device_info_data_group(mock_coordinator, mock_config_entry):
    """Test that data group sensor links via system device."""
    mac = "DC:71:96:11:22:33"
    desc = next(d for d in SENSOR_TYPES if d.key == "total_download")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    info = sensor.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_data")}
    assert info["name"] == "My Huawei Router Data"
    assert info["via_device"] == (DOMAIN, f"{mac}_system")


def test_sensor_device_info_sms_group(mock_coordinator, mock_config_entry):
    """Test that SMS group sensor links via system device."""
    mac = "DC:71:96:11:22:33"
    desc = next(d for d in SENSOR_TYPES if d.key == "sms_total")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    info = sensor.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_sms")}
    assert info["name"] == "My Huawei Router SMS"
    assert info["via_device"] == (DOMAIN, f"{mac}_system")


def test_sensor_device_info_fallback_host(mock_coordinator, mock_config_entry):
    """Test device_info falls back to host when MAC is unavailable."""
    mock_coordinator.mac = None
    desc = next(d for d in SENSOR_TYPES if d.key == "rsrp")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    info = sensor.device_info
    assert "host_http://192.168.8.1" in str(info["identifiers"])


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_sensor_no_data_returns_none(mock_coordinator, mock_config_entry):
    """Test that all sensors return None when coordinator has no data."""
    mock_coordinator.data = None
    desc = next(d for d in SENSOR_TYPES if d.key == "rsrp")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value is None


def test_sensor_empty_data_returns_none(mock_coordinator, mock_config_entry):
    """Test sensors gracefully handle empty coordinator data."""
    mock_coordinator.data = {}
    desc = next(d for d in SENSOR_TYPES if d.key == "rsrp")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value is None


@pytest.mark.asyncio
async def test_sensor_setup_entry():
    """Test that async_setup_entry creates one sensor per description."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    hass.data = {DOMAIN: {"test": MagicMock()}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == len(SENSOR_TYPES)
