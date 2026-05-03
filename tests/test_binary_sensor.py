"""Tests for the Huawei Router 5G binary sensor platform."""

from unittest.mock import MagicMock

import pytest

from custom_components.huawei_router_5g.binary_sensor import (
    BEST_CONN_DESCRIPTION,
    LTE_CA_DESCRIPTION,
    SMS_STORAGE_FULL_DESCRIPTION,
    HuaweiBestConnectionSensor,
    HuaweiLteCaSensor,
    HuaweiSmsStorageFullSensor,
    async_setup_entry,
)
from custom_components.huawei_router_5g.const import DOMAIN

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
    assert sensor.icon == "mdi:signal-5g"


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
    assert sensor.icon == "mdi:signal-cellular-1"


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
    assert info["via_device"] == (DOMAIN, f"{mac}_system")


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
    assert info["via_device"] == (DOMAIN, f"{mac}_system")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_binary_sensor_setup_entry():
    """Test that async_setup_entry creates both binary sensors."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    coordinator = MagicMock()
    hass.data = {DOMAIN: {"test": coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 7
