"""Tests for the Huawei Router 5G switch platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.huawei_router_5g.const import CONF_STOP_POLLING, DOMAIN
from custom_components.huawei_router_5g.switch import (
    GUEST_WIFI_DESCRIPTION,
    MOBILE_DATA_DESCRIPTION,
    PAUSE_POLLING_DESCRIPTION,
    WIFI_DESCRIPTION,
    HuaweiGuestWifiSwitch,
    HuaweiMobileDataSwitch,
    HuaweiPausePollingSwitch,
    HuaweiWifiSwitch,
    async_setup_entry,
)
from tests.conftest import assert_is_root, without_about

# ---------------------------------------------------------------------------
# HuaweiPausePollingSwitch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_polling_turn_on(mock_coordinator, mock_config_entry):
    """Test that turning on (pause) persists the flag and writes state."""
    new_options = dict(mock_config_entry.options)
    new_options[CONF_STOP_POLLING] = False
    object.__setattr__(mock_config_entry, "options", new_options)

    switch = HuaweiPausePollingSwitch(
        mock_coordinator, mock_config_entry, PAUSE_POLLING_DESCRIPTION, False
    )
    switch.hass = MagicMock()
    switch.hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_on()

    switch.hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = switch.hass.config_entries.async_update_entry.call_args
    assert kwargs["options"][CONF_STOP_POLLING] is True
    switch.async_write_ha_state.assert_called_once()
    mock_coordinator.async_force_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_pause_polling_turn_off(mock_coordinator, mock_config_entry):
    """Test that turning off (resume) triggers an immediate refresh."""
    new_options = dict(mock_config_entry.options)
    new_options[CONF_STOP_POLLING] = True
    object.__setattr__(mock_config_entry, "options", new_options)

    switch = HuaweiPausePollingSwitch(
        mock_coordinator, mock_config_entry, PAUSE_POLLING_DESCRIPTION, True
    )
    switch.hass = MagicMock()
    switch.hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_off()

    _, kwargs = switch.hass.config_entries.async_update_entry.call_args
    assert kwargs["options"][CONF_STOP_POLLING] is False
    mock_coordinator.async_force_refresh.assert_called_once()


def test_pause_polling_is_on_from_options(mock_coordinator, mock_config_entry):
    """Test that is_on reflects the options value."""
    new_options = dict(mock_config_entry.options)
    new_options[CONF_STOP_POLLING] = True
    object.__setattr__(mock_config_entry, "options", new_options)

    switch = HuaweiPausePollingSwitch(
        mock_coordinator, mock_config_entry, PAUSE_POLLING_DESCRIPTION, True
    )
    assert switch.is_on is True


def test_pause_polling_device_info(mock_coordinator, mock_config_entry):
    """Test device_info for the pause polling switch."""
    switch = HuaweiPausePollingSwitch(
        mock_coordinator, mock_config_entry, PAUSE_POLLING_DESCRIPTION, False
    )
    info = switch.device_info
    mac = "DC:71:96:11:22:33"
    assert info["identifiers"] == {(DOMAIN, f"{mac}_system")}
    assert info["manufacturer"] == "Huawei"
    assert_is_root(info)


# ---------------------------------------------------------------------------
# HuaweiMobileDataSwitch
# ---------------------------------------------------------------------------


def test_mobile_data_is_on(mock_coordinator, mock_config_entry):
    """Return True when dataswitch is '1'."""
    mock_coordinator.data = {"mobile_dataswitch": {"dataswitch": "1"}}
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    assert switch.is_on is True


def test_mobile_data_is_off(mock_coordinator, mock_config_entry):
    """Return False when dataswitch is '0'."""
    mock_coordinator.data = {"mobile_dataswitch": {"dataswitch": "0"}}
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    assert switch.is_on is False


def test_mobile_data_is_none_when_absent(mock_coordinator, mock_config_entry):
    """Return None when mobile_dataswitch key is absent."""
    mock_coordinator.data = {}
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    assert switch.is_on is None


def test_mobile_data_is_none_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    assert switch.is_on is None


@pytest.mark.asyncio
async def test_mobile_data_turn_on(mock_coordinator, mock_config_entry):
    """Turning mobile data on writes, then confirms with a targeted read.

    Section 22: the confirmation is a single-endpoint read-back, **not** a
    debounced full refresh. Asserting the refresh is not called is the half of
    this that would catch a silent revert to the old behavior.
    """
    mock_api = MagicMock()
    mock_api.set_mobile_data = AsyncMock()
    mock_api.read_back = AsyncMock(return_value={"dataswitch": "1"})
    mock_coordinator.api = mock_api
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    switch.hass = MagicMock()
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_on()

    mock_api.set_mobile_data.assert_called_once_with(True)
    mock_api.read_back.assert_awaited_once_with("mobile_dataswitch")
    switch.async_write_ha_state.assert_called_once()
    mock_coordinator.async_force_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_mobile_data_turn_off(mock_coordinator, mock_config_entry):
    """Turning mobile data off writes, then confirms the off value."""
    mock_api = MagicMock()
    mock_api.set_mobile_data = AsyncMock()
    mock_api.read_back = AsyncMock(return_value={"dataswitch": "0"})
    mock_coordinator.api = mock_api
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    switch.hass = MagicMock()
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_off()

    mock_api.set_mobile_data.assert_called_once_with(False)
    switch.async_write_ha_state.assert_called_once()
    mock_coordinator.async_force_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_mobile_data_turn_on_error(mock_coordinator, mock_config_entry):
    """Test that API error during turn_on is handled gracefully."""
    mock_api = MagicMock()
    mock_api.set_mobile_data = AsyncMock(side_effect=Exception("Set fail"))
    mock_coordinator.api = mock_api
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    switch.hass = MagicMock()

    with pytest.raises(HomeAssistantError, match="Enable mobile data failed"):
        await switch.async_turn_on()
    mock_coordinator.async_force_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_mobile_data_turn_off_error(mock_coordinator, mock_config_entry):
    """Test that API error during turn_off is handled gracefully."""
    mock_api = MagicMock()
    mock_api.set_mobile_data = AsyncMock(side_effect=Exception("Set fail"))
    mock_coordinator.api = mock_api
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    switch.hass = MagicMock()

    with pytest.raises(HomeAssistantError, match="Disable mobile data failed"):
        await switch.async_turn_off()
    mock_coordinator.async_force_refresh.assert_not_called()


def test_mobile_data_is_none_missing_val(mock_coordinator, mock_config_entry):
    """Return None when dataswitch key is missing inside mobile_dataswitch."""
    mock_coordinator.data = {"mobile_dataswitch": {}}
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    assert switch.is_on is None


# ---------------------------------------------------------------------------
# HuaweiGuestWifiSwitch
# ---------------------------------------------------------------------------


def test_guest_wifi_is_on(mock_coordinator, mock_config_entry):
    """Return True when Guest SSID is enabled."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {"Index": "2", "WifiEnable": "1", "wifiisguestnetwork": "1"},
                    {"Index": "0", "WifiEnable": "1", "wifiisguestnetwork": "0"},
                ]
            }
        }
    }
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    assert switch.is_on is True


def test_guest_wifi_is_none_no_data(mock_coordinator, mock_config_entry):
    """Return None when coordinator data is None."""
    mock_coordinator.data = None
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    assert switch.is_on is None


def test_guest_wifi_is_none_missing_key(mock_coordinator, mock_config_entry):
    """Return None when Guest SSID is absent."""
    mock_coordinator.data = {"wlan_multi_basic_settings": {"Ssids": {"Ssid": []}}}
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    assert switch.is_on is None


@pytest.mark.asyncio
async def test_guest_wifi_turn_on(mock_coordinator, mock_config_entry):
    """Turning guest WiFi on writes, then confirms by re-reading the SSID.

    The guest flag is nested inside the SSID list rather than being a flat
    key, so this also exercises the extractor that finds it by
    `wifiisguestnetwork` rather than by position.
    """
    mock_api = MagicMock()
    mock_api.set_guest_wifi = AsyncMock()
    mock_api.read_back = AsyncMock(
        return_value={
            "Ssids": {"Ssid": [{"wifiisguestnetwork": "1", "WifiEnable": "1"}]}
        }
    )
    mock_coordinator.api = mock_api
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    switch.hass = MagicMock()
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_on()

    mock_api.set_guest_wifi.assert_called_once_with(True)
    mock_api.read_back.assert_awaited_once_with("wlan_multi_basic_settings")
    switch.async_write_ha_state.assert_called_once()
    mock_coordinator.async_force_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_guest_wifi_turn_off(mock_coordinator, mock_config_entry):
    """Turning guest WiFi off writes, then confirms by re-reading the SSID.

    The guest flag is nested inside the SSID list rather than being a flat
    key, so this also exercises the extractor that finds it by
    `wifiisguestnetwork` rather than by position.
    """
    mock_api = MagicMock()
    mock_api.set_guest_wifi = AsyncMock()
    mock_api.read_back = AsyncMock(
        return_value={
            "Ssids": {"Ssid": [{"wifiisguestnetwork": "1", "WifiEnable": "0"}]}
        }
    )
    mock_coordinator.api = mock_api
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    switch.hass = MagicMock()
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_off()

    mock_api.set_guest_wifi.assert_called_once_with(False)
    mock_api.read_back.assert_awaited_once_with("wlan_multi_basic_settings")
    switch.async_write_ha_state.assert_called_once()
    mock_coordinator.async_force_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_guest_wifi_turn_on_error(mock_coordinator, mock_config_entry):
    """A refused guest-WiFi enable is raised, and no refresh is issued."""
    mock_api = MagicMock()
    mock_api.set_guest_wifi = AsyncMock(side_effect=Exception("Set fail"))
    mock_coordinator.api = mock_api
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    switch.hass = MagicMock()

    with pytest.raises(HomeAssistantError, match="Enable guest WiFi failed"):
        await switch.async_turn_on()
    # Previously a `finally` refreshed here, which made a failed write look
    # like a successful one that had merely been re-read.
    mock_coordinator.async_force_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_guest_wifi_turn_off_error(mock_coordinator, mock_config_entry):
    """A refused guest-WiFi disable is raised, and no refresh is issued."""
    mock_api = MagicMock()
    mock_api.set_guest_wifi = AsyncMock(side_effect=Exception("Set fail"))
    mock_coordinator.api = mock_api
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    switch.hass = MagicMock()

    with pytest.raises(HomeAssistantError, match="Disable guest WiFi failed"):
        await switch.async_turn_off()
    mock_coordinator.async_force_refresh.assert_not_called()


def test_guest_wifi_extra_attributes(mock_coordinator, mock_config_entry):
    """Test extra attributes for guest wifi."""
    mock_coordinator.data = {
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {
                        "Index": "2",
                        "WifiEnable": "1",
                        "wifiisguestnetwork": "1",
                        "WifiSsid": "GuestNet",
                    }
                ]
            }
        }
    }
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    assert without_about(switch.extra_state_attributes) == {"ssid": "GuestNet"}


def test_guest_wifi_extra_attributes_no_data(mock_coordinator, mock_config_entry):
    """Test extra attributes for guest wifi when no data is available."""
    mock_coordinator.data = None
    switch = HuaweiGuestWifiSwitch(
        mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION
    )
    assert without_about(switch.extra_state_attributes) == {}


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_switch_setup_entry():
    """Test that async_setup_entry creates both switches."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    entry.options = {CONF_STOP_POLLING: False}
    coordinator = MagicMock()
    hass.data = {DOMAIN: {"test": coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 4
    assert {e.entity_description.key for e in entities} == {
        "pause_polling",
        "mobile_data",
        "wifi",
        "wifi_guest_network",
    }


# ---------------------------------------------------------------------------
# Master WiFi switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_wifi_switch_reads_the_radio_state() -> None:
    """`WifiStatus` tracks the radios, and is already polled.

    Reading the radio block instead would be a second round trip for the same
    fact. Confirmed to follow the radios in both directions on a live B535.
    """
    coordinator = MagicMock()
    entry = MagicMock()
    entry.unique_id = "abc"
    switch = HuaweiWifiSwitch(coordinator, entry, WIFI_DESCRIPTION)

    coordinator.data = {"monitoring_status": {"WifiStatus": "1"}}
    assert switch.is_on is True
    coordinator.data = {"monitoring_status": {"WifiStatus": "0"}}
    assert switch.is_on is False
    coordinator.data = {"monitoring_status": {}}
    assert switch.is_on is None
    coordinator.data = None
    assert switch.is_on is None


@pytest.mark.asyncio
async def test_the_wifi_switch_writes_and_then_confirms() -> None:
    """The confirmation sits outside the error boundary.

    Inside it, a read blip reports a successful write as failed and invites the
    user to retry a command with a real-world effect.

    Confirmation is a targeted read of `monitoring_status.WifiStatus` — the
    same key `is_on` reads, and one already polled, so the radio block is not
    fetched a second time for the same fact.
    """
    coordinator = MagicMock()
    coordinator.api.set_wifi = AsyncMock()
    coordinator.api.read_back = AsyncMock(return_value={"WifiStatus": "1"})
    coordinator.async_force_refresh = AsyncMock()
    entry = MagicMock()
    entry.unique_id = "abc"
    switch = HuaweiWifiSwitch(coordinator, entry, WIFI_DESCRIPTION)
    switch.hass = MagicMock()
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_on()
    coordinator.api.set_wifi.assert_awaited_once_with(True)
    coordinator.api.read_back.assert_awaited_with("monitoring_status")

    coordinator.api.read_back = AsyncMock(return_value={"WifiStatus": "0"})
    await switch.async_turn_off()
    coordinator.api.set_wifi.assert_awaited_with(False)

    assert switch.async_write_ha_state.call_count == 2
    coordinator.async_force_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_refused_wifi_write_raises_rather_than_reporting_success() -> None:
    """§22 / §O-4: an unverified write must never report success."""
    coordinator = MagicMock()
    coordinator.api.set_wifi = AsyncMock(side_effect=OSError("nope"))
    coordinator.async_force_refresh = AsyncMock()
    entry = MagicMock()
    entry.unique_id = "abc"
    switch = HuaweiWifiSwitch(coordinator, entry, WIFI_DESCRIPTION)

    with pytest.raises(HomeAssistantError, match="Enable WiFi failed"):
        await switch.async_turn_on()
    coordinator.async_force_refresh.assert_not_awaited()


# ---------------------------------------------------------------------------
# What the user actually sees after a write
#
# Every switch below reflects router state, so each is driven through its real
# write path and asked the only question that matters: after a confirmed write,
# what does `is_on` report *at the moment the state is published*?
#
# The existing tests assert that the publish happened and, separately, that
# `is_on` reads a hand-set payload. Both passed for a fortnight while every
# toggle published the pre-write value, because nothing joined them. Adding a
# fourth switch adds a row here rather than needing a new test.
# ---------------------------------------------------------------------------

_DEVICE_SWITCHES = [
    pytest.param(
        HuaweiMobileDataSwitch,
        MOBILE_DATA_DESCRIPTION,
        "set_mobile_data",
        "mobile_dataswitch",
        {"mobile_dataswitch": {"dataswitch": "0"}},
        {"dataswitch": "1"},
        id="mobile_data",
    ),
    pytest.param(
        HuaweiWifiSwitch,
        WIFI_DESCRIPTION,
        "set_wifi",
        "monitoring_status",
        {"monitoring_status": {"WifiStatus": "0"}},
        {"WifiStatus": "1"},
        id="wifi",
    ),
    pytest.param(
        HuaweiGuestWifiSwitch,
        GUEST_WIFI_DESCRIPTION,
        "set_guest_wifi",
        "wlan_multi_basic_settings",
        {
            "wlan_multi_basic_settings": {
                "Ssids": {
                    "Ssid": [{"wifiisguestnetwork": "1", "WifiEnable": "0"}],
                }
            }
        },
        {"Ssids": {"Ssid": [{"wifiisguestnetwork": "1", "WifiEnable": "1"}]}},
        id="guest_wifi",
    ),
]


def _switch_under_test(
    cls, description, setter, read_back_block, stale, mock_coordinator, entry
):
    """Build a switch whose coordinator payload is deliberately pre-write."""
    api = MagicMock()
    setattr(api, setter, AsyncMock())
    api.read_back = AsyncMock(return_value=read_back_block)
    mock_coordinator.api = api
    # **The payload stays stale on purpose.** A confirmed read-back does not
    # update it, so anything reading it publishes the old position.
    mock_coordinator.data = stale

    switch = cls(mock_coordinator, entry, description)
    switch.hass = MagicMock()
    return switch, api


@pytest.mark.parametrize(
    ("cls", "description", "setter", "endpoint", "stale", "read_back_block"),
    _DEVICE_SWITCHES,
)
@pytest.mark.asyncio
async def test_a_confirmed_write_publishes_the_new_position(
    cls,
    description,
    setter,
    endpoint,
    stale,
    read_back_block,
    mock_coordinator,
    mock_config_entry,
):
    """After a confirmed write the switch must report the value it just set."""
    switch, api = _switch_under_test(
        cls,
        description,
        setter,
        read_back_block,
        stale,
        mock_coordinator,
        mock_config_entry,
    )

    # Capture what `is_on` reads at the instant the state is written, which is
    # what reaches the frontend. Asserting afterwards would miss a publish that
    # sent the old value and was corrected later.
    published: list[bool | None] = []
    switch.async_write_ha_state = MagicMock(
        side_effect=lambda: published.append(switch.is_on)
    )

    await switch.async_turn_on()

    api.read_back.assert_awaited_once_with(endpoint)
    assert published == [True], (
        f"{description.key} published {published} - the coordinator payload is "
        "still pre-write, so the position must come from the latch"
    )
    assert switch.is_on is True


@pytest.mark.parametrize(
    ("cls", "description", "setter", "endpoint", "stale", "read_back_block"),
    _DEVICE_SWITCHES,
)
@pytest.mark.asyncio
async def test_an_unverified_write_leaves_the_position_alone(
    cls,
    description,
    setter,
    endpoint,
    stale,
    read_back_block,
    mock_coordinator,
    mock_config_entry,
):
    """A read-back that cannot answer must not move the switch either way.

    `None` is unverified, not failed. The write may well have applied, but
    nothing here knows it, so the position stays where the router last put it
    and the next poll settles it.
    """
    switch, api = _switch_under_test(
        cls,
        description,
        setter,
        read_back_block,
        stale,
        mock_coordinator,
        mock_config_entry,
    )
    api.read_back = AsyncMock(return_value=None)
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_on()

    assert switch.is_on is False
    switch.async_write_ha_state.assert_not_called()


@pytest.mark.parametrize(
    ("cls", "description", "setter", "endpoint", "stale", "read_back_block"),
    _DEVICE_SWITCHES,
)
@pytest.mark.asyncio
async def test_a_refused_write_leaves_the_position_alone(
    cls,
    description,
    setter,
    endpoint,
    stale,
    read_back_block,
    mock_coordinator,
    mock_config_entry,
):
    """A read-back that disagrees twice is a refusal: raise, and do not move."""
    switch, api = _switch_under_test(
        cls,
        description,
        setter,
        read_back_block,
        stale,
        mock_coordinator,
        mock_config_entry,
    )
    # The router keeps reporting the old value.
    api.read_back = AsyncMock(return_value=stale[endpoint])
    switch.async_write_ha_state = MagicMock()

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()

    assert switch.is_on is False
    switch.async_write_ha_state.assert_not_called()


@pytest.mark.parametrize(
    ("cls", "description", "setter", "endpoint", "stale", "read_back_block"),
    _DEVICE_SWITCHES,
)
@pytest.mark.asyncio
async def test_a_poll_missing_the_key_holds_the_last_position(
    cls,
    description,
    setter,
    endpoint,
    stale,
    read_back_block,
    mock_coordinator,
    mock_config_entry,
):
    """Section 22: never render a missing key as an off position.

    A degraded poll that omits the block must leave the switch where the router
    last put it, not drop it to off or to unknown.
    """
    switch, _api = _switch_under_test(
        cls,
        description,
        setter,
        read_back_block,
        stale,
        mock_coordinator,
        mock_config_entry,
    )
    switch.async_write_ha_state = MagicMock()

    # A good poll establishes the position...
    mock_coordinator.data = {endpoint: read_back_block}
    switch._handle_coordinator_update()
    assert switch.is_on is True

    # ...and a poll that drops the block entirely must not disturb it.
    mock_coordinator.data = {}
    switch._handle_coordinator_update()
    assert switch.is_on is True
