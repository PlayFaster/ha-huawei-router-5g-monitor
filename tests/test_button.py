"""Tests for the Huawei Router 5G button platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.huawei_router_5g.button import (
    CLEAR_TRAFFIC_DESCRIPTION,
    REBOOT_DESCRIPTION,
    HuaweiClearTrafficButton,
    HuaweiRebootButton,
    async_setup_entry,
)
from custom_components.huawei_router_5g.const import DOMAIN

# ---------------------------------------------------------------------------
# HuaweiRebootButton
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reboot_button_press(mock_coordinator, mock_config_entry):
    """Test that pressing reboot calls api.reboot()."""
    mock_api = MagicMock()
    mock_api.reboot = AsyncMock()
    mock_coordinator.api = mock_api

    button = HuaweiRebootButton(mock_coordinator, mock_config_entry, REBOOT_DESCRIPTION)
    await button.async_press()

    mock_api.reboot.assert_called_once()


@pytest.mark.asyncio
async def test_reboot_button_press_error(mock_coordinator, mock_config_entry):
    """Test that reboot API errors raise HomeAssistantError."""
    mock_api = MagicMock()
    mock_api.reboot = AsyncMock(side_effect=Exception("Reboot fail"))
    mock_coordinator.api = mock_api

    button = HuaweiRebootButton(mock_coordinator, mock_config_entry, REBOOT_DESCRIPTION)
    with pytest.raises(HomeAssistantError, match="Reboot failed"):
        await button.async_press()


def test_reboot_button_device_info(mock_coordinator, mock_config_entry):
    """Test device_info for the reboot button is in the system group."""
    button = HuaweiRebootButton(mock_coordinator, mock_config_entry, REBOOT_DESCRIPTION)
    mac = "DC:71:96:11:22:33"
    info = button.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_system")}
    assert info["manufacturer"] == "Huawei"
    assert "via_device" not in info


# ---------------------------------------------------------------------------
# HuaweiClearTrafficButton
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_traffic_button_press(mock_coordinator, mock_config_entry):
    """Test that pressing clear traffic calls the API and triggers a refresh."""
    mock_api = MagicMock()
    mock_api.clear_traffic_statistics = AsyncMock()
    mock_coordinator.api = mock_api

    button = HuaweiClearTrafficButton(
        mock_coordinator, mock_config_entry, CLEAR_TRAFFIC_DESCRIPTION
    )
    await button.async_press()

    mock_api.clear_traffic_statistics.assert_called_once()
    mock_coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_clear_traffic_button_press_error(mock_coordinator, mock_config_entry):
    """Test that clear traffic API errors raise HomeAssistantError."""
    mock_api = MagicMock()
    mock_api.clear_traffic_statistics = AsyncMock(side_effect=Exception("Clear fail"))
    mock_coordinator.api = mock_api

    button = HuaweiClearTrafficButton(
        mock_coordinator, mock_config_entry, CLEAR_TRAFFIC_DESCRIPTION
    )
    with pytest.raises(HomeAssistantError, match="Clear traffic statistics failed"):
        await button.async_press()
    mock_coordinator.async_request_refresh.assert_not_called()


def test_clear_traffic_button_device_info(mock_coordinator, mock_config_entry):
    """Test device_info for the clear traffic button is in the data group."""
    button = HuaweiClearTrafficButton(
        mock_coordinator, mock_config_entry, CLEAR_TRAFFIC_DESCRIPTION
    )
    mac = "DC:71:96:11:22:33"
    info = button.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_data")}
    assert info["via_device"] == (DOMAIN, f"{mac}_system")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_button_setup_entry():
    """Test that async_setup_entry creates both buttons."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    coordinator = MagicMock()
    coordinator.api = MagicMock()
    hass.data = {DOMAIN: {"test": coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 2
