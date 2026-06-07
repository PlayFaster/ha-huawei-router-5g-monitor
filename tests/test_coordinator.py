"""Tests for the Huawei Router 5G DataUpdateCoordinator."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)


@pytest.fixture(autouse=True)
def mock_report_usage():
    """Suppress 'Frame helper not set up' warnings from HA internals."""
    with patch("homeassistant.helpers.frame.report_usage"):
        yield


@pytest.mark.asyncio
async def test_coordinator_communication_restoration_log(
    mock_hass, mock_config_entry, caplog
):
    """Test that the coordinator logs when communication is restored."""
    mock_api = MagicMock()
    # First call fails, second succeeds
    mock_api.get_data = AsyncMock(
        side_effect=[
            Exception("First Fail"),
            {"device_information": {"DeviceName": "B535"}},
        ]
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator.data = {"old": "data"}

    # 1. Trigger a failure
    await coordinator._async_update_data()
    assert coordinator.consecutive_failures == 1

    # 2. Trigger a success
    caplog.set_level(logging.INFO)
    await coordinator._async_update_data()

    assert coordinator.consecutive_failures == 0
    assert "Communication restored after 1 failures" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_sms_debug_log(mock_hass, mock_config_entry, caplog):
    """Test that the coordinator logs the raw SMS list at debug level."""
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535"},
            "sms_list": {"Messages": {"Message": []}},
        }
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    caplog.set_level(logging.DEBUG)
    await coordinator._async_update_data()

    assert "Raw SMS list" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_sms_tracking_first_run(mock_hass, mock_config_entry):
    """Test that the first SMS fetch only sets the last_sms_timestamp."""
    mock_api = MagicMock()
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    data = {
        "sms_list": {
            "Messages": {
                "Message": [
                    {
                        "Index": "5",
                        "Phone": "123",
                        "Content": "A",
                        "Date": "2024-05-01 10:00:00",
                    },
                    {
                        "Index": "10",
                        "Phone": "456",
                        "Content": "B",
                        "Date": "2024-05-01 10:05:00",
                    },
                ]
            }
        }
    }

    with patch.object(mock_hass.bus, "async_fire") as mock_fire:
        coordinator._check_new_sms(data)

    assert coordinator.last_sms_timestamp == "2024-05-01 10:05:00"
    assert "10_2024-05-01 10:05:00" in coordinator.fired_sms_hashes
    mock_fire.assert_not_called()


@pytest.mark.asyncio
async def test_coordinator_sms_event_firing(mock_hass, mock_config_entry):
    """Test that new SMS messages trigger Home Assistant bus events."""
    mock_api = MagicMock()
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator.last_sms_timestamp = "2024-05-01 10:00:00"
    coordinator.fired_sms_hashes = {"10_2024-05-01 10:00:00"}

    data = {
        "sms_list": {
            "Messages": {
                "Message": [
                    {
                        "Index": "10",
                        "Phone": "123",
                        "Content": "Old",
                        "Date": "2024-05-01 10:00:00",
                    },
                    {
                        "Index": "11",
                        "Phone": "456",
                        "Content": "New1",
                        "Date": "2024-05-01 10:01:00",
                    },
                    {
                        "Index": "12",
                        "Phone": "789",
                        "Content": "New2",
                        "Date": "2024-05-01 10:02:00",
                    },
                ]
            }
        }
    }

    with patch.object(mock_hass.bus, "async_fire") as mock_fire:
        coordinator._check_new_sms(data)

    assert coordinator.last_sms_timestamp == "2024-05-01 10:02:00"
    assert mock_fire.call_count == 2

    # Verify first new message event
    call1 = mock_fire.call_args_list[0]
    assert call1[0][0] == "huawei_router_5g_sms_received"
    assert call1[0][1]["index"] == 11
    assert call1[0][1]["content"] == "New1"

    # Verify second new message event
    call2 = mock_fire.call_args_list[1]
    assert call2[0][0] == "huawei_router_5g_sms_received"
    assert call2[0][1]["index"] == 12
    assert call2[0][1]["content"] == "New2"


@pytest.mark.asyncio
async def test_coordinator_critical_data_missing(mock_hass, mock_config_entry):
    """Test that missing device_information raises UpdateFailed."""
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(return_value={"something": "else"})

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    with pytest.raises(UpdateFailed, match="Critical data missing"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_paused_polling(mock_hass, mock_config_entry, caplog):
    """Test paused polling logic: returns cached data or empty dict on failure."""
    from custom_components.huawei_router_5g.const import CONF_STOP_POLLING

    mock_api = MagicMock()
    object.__setattr__(mock_config_entry, "options", {CONF_STOP_POLLING: True})

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    # Scenario 1: Initial fetch fails while paused
    mock_api.get_data = AsyncMock(side_effect=Exception("Initial fail"))
    caplog.set_level(logging.WARNING)
    data = await coordinator._async_update_data()
    assert data == {}
    assert "Initial fetch failed while paused" in caplog.text

    # Scenario 2: Polling is paused and not first run
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    coordinator.data = {"cached": "data"}
    data = await coordinator._async_update_data()
    assert data == {"cached": "data"}
    assert "Polling is paused; returning cached data." in caplog.text


@pytest.mark.asyncio
async def test_coordinator_sms_hash_collision(mock_hass, mock_config_entry):
    """Test SMS hash handling when multiple messages have the same timestamp."""
    mock_api = MagicMock()
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator.last_sms_timestamp = "2024-05-01 10:00:00"
    coordinator.fired_sms_hashes = {"10_2024-05-01 10:00:00"}

    data = {
        "sms_list": {
            "Messages": {
                "Message": [
                    {
                        "Index": "11",
                        "Phone": "123",
                        "Content": "New1",
                        "Date": "2024-05-01 10:01:00",
                    },
                    {
                        "Index": "12",
                        "Phone": "456",
                        "Content": "New2",
                        "Date": "2024-05-01 10:01:00",  # Same timestamp!
                    },
                ]
            }
        }
    }

    with patch.object(mock_hass.bus, "async_fire") as mock_fire:
        coordinator._check_new_sms(data)

    assert coordinator.last_sms_timestamp == "2024-05-01 10:01:00"
    assert "11_2024-05-01 10:01:00" in coordinator.fired_sms_hashes
    assert "12_2024-05-01 10:01:00" in coordinator.fired_sms_hashes
    assert mock_fire.call_count == 2


@pytest.mark.asyncio
async def test_coordinator_init_restores_uptime_state(mock_hass, mock_config_entry):
    """Test that uptime/boot state is restored from entry.data at init."""
    object.__setattr__(
        mock_config_entry,
        "data",
        {
            **mock_config_entry.data,
            "system_boot_time": "2024-01-01T00:00:00",
            "last_system_uptime": "3600",
            "conn_start_time": "2024-01-01T01:00:00",
            "last_conn_uptime": "1800",
            "total_conn_start_time": "2024-01-01T02:00:00",
            "last_total_conn_time": "7200",
        },
    )
    mock_api = MagicMock()
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    assert coordinator._system_boot_time == dt_util.parse_datetime(
        "2024-01-01T00:00:00"
    )
    assert coordinator._last_system_uptime == 3600
    assert coordinator._conn_start_time == dt_util.parse_datetime("2024-01-01T01:00:00")
    assert coordinator._last_conn_uptime == 1800
    assert coordinator._total_conn_start_time == dt_util.parse_datetime(
        "2024-01-01T02:00:00"
    )
    assert coordinator._last_total_conn_time == 7200


@pytest.mark.asyncio
async def test_coordinator_system_uptime_first_latch(
    mock_hass, mock_config_entry, freezer
):
    """Test that system boot time is latched on first run."""
    freezer.move_to("2024-06-15 12:00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535", "uptime": "3600"},
        }
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-15 11:00:00+00:00")
    assert coordinator._system_boot_time == expected
    assert coordinator._last_system_uptime == 3600
    mock_hass.config_entries.async_update_entry.assert_called()


@pytest.mark.asyncio
async def test_coordinator_system_uptime_reboot_detected(
    mock_hass, mock_config_entry, freezer, caplog
):
    """Test that a significant uptime drop triggers reboot detection."""
    freezer.move_to("2024-06-15 13:00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535", "uptime": "30"},
        }
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator._system_boot_time = dt_util.parse_datetime("2024-06-15 11:00:00+00:00")
    coordinator._last_system_uptime = 3600
    coordinator.data = {"device_information": {"DeviceName": "B535"}}

    caplog.set_level(logging.DEBUG)
    await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-15 12:59:30+00:00")
    assert coordinator._system_boot_time == expected
    assert coordinator._last_system_uptime == 30
    assert "System boot time latched" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_connection_uptime_first_latch(
    mock_hass, mock_config_entry, freezer
):
    """Test that connection start time is latched on first run."""
    freezer.move_to("2024-06-15 12:00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535"},
            "traffic_statistics": {"CurrentConnectTime": "1800"},
        }
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-15 11:30:00+00:00")
    assert coordinator._conn_start_time == expected
    assert coordinator._last_conn_uptime == 1800


@pytest.mark.asyncio
async def test_coordinator_connection_uptime_reboot_detected(
    mock_hass, mock_config_entry, freezer, caplog
):
    """Test that a significant connection time drop triggers reboot detection."""
    freezer.move_to("2024-06-15 13:00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535"},
            "traffic_statistics": {"CurrentConnectTime": "10"},
        }
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator._conn_start_time = dt_util.parse_datetime("2024-06-15 11:00:00+00:00")
    coordinator._last_conn_uptime = 3600
    coordinator.data = {"device_information": {"DeviceName": "B535"}}

    caplog.set_level(logging.DEBUG)
    await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-15 12:59:50+00:00")
    assert coordinator._conn_start_time == expected
    assert "Connection start time latched" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_total_conn_uptime_first_latch(
    mock_hass, mock_config_entry, freezer
):
    """Test that total connection start time is latched on first run."""
    freezer.move_to("2024-06-15 12:00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535"},
            "traffic_statistics": {"TotalConnectTime": "86400"},
        }
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-14 12:00:00+00:00")
    assert coordinator._total_conn_start_time == expected
    assert coordinator._last_total_conn_time == 86400


@pytest.mark.asyncio
async def test_coordinator_total_conn_uptime_reboot_detected(
    mock_hass, mock_config_entry, freezer, caplog
):
    """Test that a significant total connect time drop triggers reboot detection."""
    freezer.move_to("2024-06-15 15:00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535"},
            "traffic_statistics": {"TotalConnectTime": "5"},
        }
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator._total_conn_start_time = dt_util.parse_datetime(
        "2024-06-15 10:00:00+00:00"
    )
    coordinator._last_total_conn_time = 7200
    coordinator.data = {"device_information": {"DeviceName": "B535"}}

    caplog.set_level(logging.DEBUG)
    await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-15 14:59:55+00:00")
    assert coordinator._total_conn_start_time == expected
    assert "Total connection start time latched" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_timeout_after_max_failures(
    mock_hass, mock_config_entry, caplog
):
    """Test that a timeout after maximum failures raises UpdateFailed."""
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(side_effect=TimeoutError("Request timed out"))

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator.data = {"device_information": {"DeviceName": "B535"}}
    coordinator.consecutive_failures = 3

    caplog.set_level(logging.ERROR)

    with pytest.raises(UpdateFailed, match="API request timed out"):
        await coordinator._async_update_data()

    assert coordinator.consecutive_failures == 4


@pytest.fixture
def mock_hass():
    """Mock Home Assistant."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    return hass
