"""Tests for the Huawei Router 5G DataUpdateCoordinator."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

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


@pytest.fixture
def mock_hass():
    """Mock Home Assistant."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    return hass
