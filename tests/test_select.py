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


@pytest.mark.asyncio
async def test_setup_offers_only_the_modes_the_router_accepts():
    """The option list comes from the router, not from a table.

    The reference H165-383 publishes `["00", "08", "03"]` — exactly the three
    its web interface offers. The select previously offered eight modes copied
    from `huawei-lte-api`'s `NetworkModeEnum`, **five of which this router
    rejects**, while omitting `08`, the mode it was actually in.
    """
    entry = MagicMock()
    entry.entry_id = "test"
    coordinator = MagicMock()
    coordinator.api.get_supported_net_modes = AsyncMock(return_value=["00", "08", "03"])
    entry.runtime_data = coordinator

    added = []
    await async_setup_entry(MagicMock(), entry, lambda items: added.extend(items))

    options = added[0].entity_description.options
    assert options == ["Auto", "5G Only", "4G Only"]


@pytest.mark.asyncio
async def test_setup_falls_back_when_the_router_will_not_list_modes():
    """A router that will not publish a list keeps the full fallback set."""
    entry = MagicMock()
    entry.entry_id = "test"
    coordinator = MagicMock()
    coordinator.api.get_supported_net_modes = AsyncMock(return_value=None)
    entry.runtime_data = coordinator

    added = []
    await async_setup_entry(MagicMock(), entry, lambda items: added.extend(items))

    options = added[0].entity_description.options
    assert "Auto" in options
    assert "5G Only" in options
    assert len(options) == 9


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
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.huawei_router_5g.select import SELECTS, HuaweiRouterSelect

    mock_coordinator.api.set_net_mode = AsyncMock(side_effect=Exception("refused"))
    entity = HuaweiRouterSelect(mock_coordinator, SELECTS[0])

    with pytest.raises(HomeAssistantError, match="Failed to set network mode"):
        await entity.async_select_option("4G Only")

    mock_coordinator.async_force_refresh.assert_not_called()
