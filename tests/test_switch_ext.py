"""Additional tests for the Huawei Router 5G switch platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.huawei_router_5g.switch import (
    GUEST_WIFI_DESCRIPTION,
    MOBILE_DATA_DESCRIPTION,
    PAUSE_POLLING_DESCRIPTION,
    HuaweiGuestWifiSwitch,
    HuaweiMobileDataSwitch,
    HuaweiPausePollingSwitch,
)

# ---------------------------------------------------------------------------
# HuaweiPausePollingSwitch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_polling_switch(mock_coordinator, mock_config_entry):
    """Test pause polling logic."""
    switch = HuaweiPausePollingSwitch(
        mock_coordinator, mock_config_entry, PAUSE_POLLING_DESCRIPTION, False
    )
    switch.hass = MagicMock()
    switch.hass.config_entries.async_update_entry = MagicMock()

    # Mock async_write_ha_state to avoid platform errors in unit tests
    switch.async_write_ha_state = MagicMock()

    # Turn On (Pause)
    await switch.async_turn_on()
    # Check if options were updated
    update_call = switch.hass.config_entries.async_update_entry.call_args
    assert update_call[1]["options"]["stop_polling"] is True

    # Turn Off (Resume)
    switch.hass.config_entries.async_update_entry.reset_mock()
    await switch.async_turn_off()
    update_call = switch.hass.config_entries.async_update_entry.call_args
    assert update_call[1]["options"]["stop_polling"] is False


# ---------------------------------------------------------------------------
# HuaweiMobileDataSwitch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mobile_data_switch(mock_coordinator, mock_config_entry):
    """Test mobile data switch."""
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    mock_coordinator.api.set_mobile_data = AsyncMock()

    # Turn On
    await switch.async_turn_on()
    mock_coordinator.api.set_mobile_data.assert_called_with(True)

    # Turn Off
    await switch.async_turn_off()
    mock_coordinator.api.set_mobile_data.assert_called_with(False)

    # State
    mock_coordinator.data = {"mobile_dataswitch": {"dataswitch": "1"}}
    assert switch.is_on is True
    mock_coordinator.data = {"mobile_dataswitch": {"dataswitch": "0"}}
    assert switch.is_on is False


# ---------------------------------------------------------------------------
# HuaweiGuestWifiSwitch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guest_wifi_switch(mock_coordinator, mock_config_entry):
    """Test guest WiFi switch."""
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    mock_coordinator.api.set_guest_wifi = AsyncMock()

    # Turn On
    await switch.async_turn_on()
    mock_coordinator.api.set_guest_wifi.assert_called_with(True)

    # Attributes
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {
                        "Index": "2",
                        "WifiEnable": "1",
                        "wifiisguestnetwork": "1",
                        "WifiSsid": "GuestSSID",
                    }
                ]
            }
        }
    }
    assert switch.is_on is True
    assert switch.extra_state_attributes["ssid"] == "GuestSSID"
