"""Tests for the Huawei Router 5G select platform."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.huawei_router_5g.const import DOMAIN
from custom_components.huawei_router_5g.select import (
    SELECTS,
    HuaweiRouterSelect,
    async_setup_entry,
)


def test_network_mode_select_current_option(mock_coordinator, mock_config_entry):
    """Test current option mapping."""
    # Mapping for '00' is 'Auto'
    mock_coordinator.data = {"net_mode": {"NetworkMode": "00"}}
    select = HuaweiRouterSelect(mock_coordinator, SELECTS[0])
    assert select.current_option == "Auto"

    # Mapping for '03' is '4G Only'
    mock_coordinator.data = {"net_mode": {"NetworkMode": "03"}}
    assert select.current_option == "4G Only"


def test_network_mode_select_none_when_missing(mock_coordinator, mock_config_entry):
    """Test current option when data is missing."""
    mock_coordinator.data = {}
    select = HuaweiRouterSelect(mock_coordinator, SELECTS[0])
    assert select.current_option is None


@pytest.mark.asyncio
async def test_network_mode_select_option(mock_coordinator, mock_config_entry):
    """Test selecting an option."""
    select = HuaweiRouterSelect(mock_coordinator, SELECTS[0])
    mock_coordinator.api.set_net_mode = AsyncMock()

    await select.async_select_option("4G Only")
    mock_coordinator.api.set_net_mode.assert_called_once_with("03")


@pytest.mark.asyncio
async def test_network_mode_select_option_failure(mock_coordinator, mock_config_entry):
    """A failed option write is logged **and** raised to the caller."""
    from homeassistant.exceptions import HomeAssistantError

    select = HuaweiRouterSelect(mock_coordinator, SELECTS[0])
    mock_coordinator.api.set_net_mode = AsyncMock(side_effect=Exception("API Error"))

    with (
        patch("custom_components.huawei_router_5g.select._LOGGER") as mock_logger,
        pytest.raises(HomeAssistantError, match="Failed to set network mode"),
    ):
        await select.async_select_option("4G Only")

    assert mock_logger.exception.called
    assert "Failed to set network mode" in mock_logger.exception.call_args[0][0]


def test_select_device_info(mock_coordinator, mock_config_entry):
    """Test device_info generation for select entities."""
    select = HuaweiRouterSelect(mock_coordinator, SELECTS[0])
    info = select.device_info
    assert info["identifiers"] == {(DOMAIN, "DC:71:96:11:22:33_system")}
    assert info["manufacturer"] == "Huawei"


@pytest.mark.asyncio
async def test_select_setup_entry():
    """Test platform setup."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    coordinator = MagicMock()
    coordinator.api.get_supported_net_modes = AsyncMock(return_value=None)
    entry.runtime_data = coordinator
    hass.data = {DOMAIN: {"test": coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_called_once()


def test_options_come_from_the_router(mock_coordinator, mock_config_entry):
    """The option list comes from the router, not from a table.

    The reference H165-383 publishes `["00", "08", "03"]` — exactly the three
    its web interface offers. The select previously offered eight modes copied
    from `huawei-lte-api`'s `NetworkModeEnum`, **five of which this router
    rejects**, while omitting `08`, the mode it was actually in.
    """
    mock_coordinator.supported_net_modes = ["00", "08", "03"]
    select = HuaweiRouterSelect(mock_coordinator, SELECTS[0])
    assert select.options == ["Auto", "5G Only", "4G Only"]


def test_options_fall_back_until_the_router_has_answered(
    mock_coordinator, mock_config_entry
):
    """The full set stands while the list is unknown, and is replaced when it lands.

    **This is why `options` is a property rather than fixed at setup.** Platforms
    are forwarded before the router is logged in, so the list cannot exist yet
    when the entity is built; reading it there fell back on every startup. `None`
    means *not yet known*, which is not the same as "none accepted" — showing
    nothing would be worse than showing too much.
    """
    mock_coordinator.supported_net_modes = None
    select = HuaweiRouterSelect(mock_coordinator, SELECTS[0])
    assert "Auto" in select.options
    assert "5G Only" in select.options
    assert len(select.options) == 9

    mock_coordinator.supported_net_modes = ["00", "03"]
    assert select.options == ["Auto", "4G Only"]


def test_an_unmapped_mode_is_named_not_hidden():
    """`Unknown (nn)` beats `unknown`, and must round-trip back to the code.

    This is the `08` lesson in test form: an unmapped code used to return
    `None`, so a router in a perfectly valid mode read as `unknown` —
    indistinguishable from a dead endpoint. It must also remain selectable.
    """
    from custom_components.huawei_router_5g.const import network_mode_label
    from custom_components.huawei_router_5g.select import _label_to_code

    assert network_mode_label("77") == "Unknown (77)"
    assert _label_to_code("Unknown (77)") == "77"
    assert network_mode_label("08") == "5G Only"
    assert _label_to_code("5G Only") == "08"
    assert network_mode_label(None) is None


@pytest.mark.asyncio
async def test_network_mode_write_failure_raises(mock_coordinator, mock_config_entry):
    """A refused network-mode change must surface, not log and return.

    Previously the exception was logged and swallowed, so the select reported
    success and then silently reverted on the next poll — the user's only
    evidence was a log line they had no reason to look at.
    """
    from custom_components.huawei_router_5g.select import SELECTS, HuaweiRouterSelect
    from homeassistant.exceptions import HomeAssistantError

    mock_coordinator.api.set_net_mode = AsyncMock(side_effect=Exception("refused"))
    entity = HuaweiRouterSelect(mock_coordinator, SELECTS[0])

    with pytest.raises(HomeAssistantError, match="Failed to set network mode"):
        await entity.async_select_option("4G Only")

    mock_coordinator.async_force_refresh.assert_not_called()


def test_an_unrecognized_label_falls_back_to_auto():
    """A label matching no known mode resolves to Auto rather than raising.

    Unreachable through the UI, which only ever submits an option the entity
    published. It exists so a malformed service call cannot send an arbitrary
    string to the radio.
    """
    from custom_components.huawei_router_5g.select import _label_to_code

    assert _label_to_code("Not A Mode") == "00"


# ---------------------------------------------------------------------------
# A current network mode absent from the router's list (dev2 plan I11)
# ---------------------------------------------------------------------------


def test_a_current_mode_outside_the_list_is_added_and_shown(
    mock_coordinator, mock_config_entry
):
    """Home Assistant shows `unknown` for an option not in the options."""
    mock_coordinator.supported_net_modes = ["00", "08", "03"]
    mock_coordinator.data = {"net_mode": {"NetworkMode": "02"}}
    select = HuaweiRouterSelect(mock_coordinator, SELECTS[0])

    assert select.current_option == "3G Only"
    assert select.options == ["Auto", "5G Only", "4G Only", "3G Only"]


def test_with_no_list_the_fallback_set_gains_the_current_mode(
    mock_coordinator, mock_config_entry
):
    """A router that publishes no list keeps every known mode, plus its own."""
    mock_coordinator.supported_net_modes = None
    mock_coordinator.data = {"net_mode": {"NetworkMode": "99"}}
    select = HuaweiRouterSelect(mock_coordinator, SELECTS[0])

    assert len(select.options) == 10
    assert "Auto" in select.options
    assert select.options[-1] == "Unknown (99)"


@pytest.mark.asyncio
async def test_a_write_of_the_added_mode_is_refused_naming_the_list(
    mock_coordinator, mock_config_entry
):
    """The router refuses a mode outside its list, so nothing is sent."""
    from homeassistant.exceptions import HomeAssistantError

    mock_coordinator.supported_net_modes = ["00", "08", "03"]
    mock_coordinator.data = {"net_mode": {"NetworkMode": "02"}}
    mock_coordinator.api.set_net_mode = AsyncMock()
    select = HuaweiRouterSelect(mock_coordinator, SELECTS[0])

    with pytest.raises(HomeAssistantError) as caught:
        await select.async_select_option("3G Only")

    assert caught.value.translation_key == "network_mode_not_listed"
    assert caught.value.translation_placeholders == {
        "mode": "3G Only",
        "modes": "Auto, 5G Only, 4G Only",
    }

    mock_coordinator.api.set_net_mode.assert_not_called()


@pytest.mark.asyncio
async def test_a_mode_change_inside_a_window_is_refused_with_a_warning(
    mock_coordinator, mock_config_entry
):
    """The gate's refusal is logged as a warning, without a traceback."""
    from custom_components.huawei_router_5g.api import HuaweiExpectedUnavailableError
    from homeassistant.exceptions import HomeAssistantError

    mock_coordinator.api.set_net_mode = AsyncMock(
        side_effect=HuaweiExpectedUnavailableError("reboot", 42)
    )
    select = HuaweiRouterSelect(mock_coordinator, SELECTS[0])

    with (
        patch("custom_components.huawei_router_5g.select._LOGGER") as logger,
        pytest.raises(HomeAssistantError) as caught,
    ):
        await select.async_select_option("4G Only")

    assert caught.value.translation_key == "router_restarting"

    logger.warning.assert_called_once()
    logger.exception.assert_not_called()
