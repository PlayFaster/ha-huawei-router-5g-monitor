"""Tests for the Huawei Router 5G select platform."""

from unittest.mock import AsyncMock, MagicMock

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
    select = HuaweiRouterSelect(
        mock_coordinator, SELECTS[0]
    )
    assert select.current_option == "Auto"

    # Mapping for '03' is '4G Only'
    mock_coordinator.data = {"net_mode": {"NetworkMode": "03"}}
    assert select.current_option == "4G Only"


def test_network_mode_select_none_when_missing(mock_coordinator, mock_config_entry):
    """Test current option when data is missing."""
    mock_coordinator.data = {}
    select = HuaweiRouterSelect(
        mock_coordinator, SELECTS[0]
    )
    assert select.current_option is None


@pytest.mark.asyncio
async def test_network_mode_select_option(mock_coordinator, mock_config_entry):
    """Test selecting an option."""
    select = HuaweiRouterSelect(
        mock_coordinator, SELECTS[0]
    )
    mock_coordinator.api.set_net_mode = AsyncMock()

    await select.async_select_option("4G Only")
    mock_coordinator.api.set_net_mode.assert_called_once_with("03")


@pytest.mark.asyncio
async def test_select_setup_entry():
    """Test platform setup."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    coordinator = MagicMock()
    hass.data = {DOMAIN: {"test": coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_called_once()
