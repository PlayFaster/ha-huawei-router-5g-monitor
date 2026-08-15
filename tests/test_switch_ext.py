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
from tests.conftest import without_about

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


def test_guest_wifi_is_on_single_ssid_dict(mock_coordinator, mock_config_entry):
    """Test is_on when Ssid is a single dict (not list)."""
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": {"Index": "2", "WifiEnable": "1", "wifiisguestnetwork": "1"}
            }
        }
    }
    assert switch.is_on is True


def test_guest_wifi_extra_state_attributes_single_ssid_dict(
    mock_coordinator, mock_config_entry
):
    """Test extra_state_attributes when Ssid is a single dict."""
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": {
                    "Index": "2",
                    "WifiEnable": "1",
                    "wifiisguestnetwork": "1",
                    "WifiSsid": "GuestDict",
                }
            }
        }
    }
    assert without_about(switch.extra_state_attributes) == {"ssid": "GuestDict"}


def test_guest_wifi_extra_state_attributes_no_guest_ssid(
    mock_coordinator, mock_config_entry
):
    """Test extra_state_attributes when no SSID is a guest network."""
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [{"Index": "0", "WifiEnable": "1", "wifiisguestnetwork": "0"}]
            }
        }
    }
    assert without_about(switch.extra_state_attributes) == {}


def test_guest_wifi_skips_non_guest_ssids_before_finding_the_guest_one(
    mock_coordinator, mock_config_entry
):
    """The guest-SSID search must walk past the primary SSIDs to reach the guest.

    `is_on` loops the SSID list looking for `wifiisguestnetwork == "1"`. Every
    existing test put the guest network first, so the *continue* was never
    taken — "found it at position 0" and "searched the list" were
    indistinguishable, and a mutation stopping the loop after one item would
    have passed.

    A real router lists the 2.4 GHz and 5 GHz primaries before the guest
    network, which is the ordering asserted here.
    """
    from custom_components.huawei_router_5g.switch import (
        GUEST_WIFI_DESCRIPTION,
        HuaweiGuestWifiSwitch,
    )

    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {
                        "wifiisguestnetwork": "0",
                        "WifiSsid": "Home-2.4G",
                        "WifiEnable": "0",
                    },
                    {
                        "wifiisguestnetwork": "0",
                        "WifiSsid": "Home-5G",
                        "WifiEnable": "0",
                    },
                    {
                        "wifiisguestnetwork": "1",
                        "WifiSsid": "Home-Guest",
                        "WifiEnable": "1",
                    },
                ]
            }
        }
    }

    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )

    # The two primaries are disabled and the guest is enabled, so a loop that
    # stopped early would report False rather than True.
    assert switch.is_on is True
    assert without_about(switch.extra_state_attributes) == {"ssid": "Home-Guest"}


# ---------------------------------------------------------------------------
# Write refusal — a write may never report success having done nothing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("turn_on", [True, False])
async def test_mobile_data_write_failure_raises(
    mock_coordinator, mock_config_entry, turn_on
):
    """A refused mobile-data write must surface, not log and return.

    Previously the exception was caught and logged, so the service call
    succeeded and the switch simply sprang back on the next poll. The
    distinction being asserted is *the caller is told* — and that no refresh
    was issued, because there is nothing new to read.
    """
    from homeassistant.exceptions import HomeAssistantError

    mock_api = MagicMock()
    mock_api.set_mobile_data = AsyncMock(side_effect=Exception("Router refused"))
    mock_coordinator.api = mock_api
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    switch.hass = MagicMock()

    call = switch.async_turn_on if turn_on else switch.async_turn_off
    with pytest.raises(HomeAssistantError, match="mobile data failed"):
        await call()

    mock_coordinator.async_force_refresh.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("turn_on", [True, False])
async def test_guest_wifi_write_failure_raises(
    mock_coordinator, mock_config_entry, turn_on
):
    """A refused guest-WiFi write must surface.

    This one was masked twice: the exception was swallowed, and a `finally`
    refresh then made the switch look as though it had merely been re-read.
    """
    from homeassistant.exceptions import HomeAssistantError

    mock_api = MagicMock()
    mock_api.set_guest_wifi = AsyncMock(side_effect=Exception("Router refused"))
    mock_coordinator.api = mock_api
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    switch.hass = MagicMock()

    call = switch.async_turn_on if turn_on else switch.async_turn_off
    with pytest.raises(HomeAssistantError, match="guest WiFi failed"):
        await call()

    mock_coordinator.async_force_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_a_successful_write_is_not_reported_as_failed_by_a_refresh_blip(
    mock_coordinator, mock_config_entry
):
    """A blip while re-reading must not fail a write that already succeeded.

    The post-write refresh sits **outside** the error boundary on purpose. If
    it were inside, a transient read failure would report the write as failed
    and invite the user to retry a command with a real-world effect.
    """
    mock_api = MagicMock()
    mock_api.set_mobile_data = AsyncMock()
    mock_coordinator.api = mock_api
    mock_coordinator.async_force_refresh = AsyncMock(
        side_effect=Exception("transient read failure")
    )
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    switch.hass = MagicMock()

    # The refresh failure propagates as itself — it is emphatically not
    # relabelled as "Enable mobile data failed", which is the misreport.
    with pytest.raises(Exception, match="transient read failure"):
        await switch.async_turn_on()

    mock_api.set_mobile_data.assert_awaited_once_with(True)
