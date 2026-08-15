"""Tests for the Huawei Router 5G button platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.button import ButtonDeviceClass
from homeassistant.exceptions import HomeAssistantError

from custom_components.huawei_router_5g.button import (
    CLEAR_TRAFFIC_DESCRIPTION,
    REBOOT_DESCRIPTION,
    RECONNECT_DESCRIPTION,
    REFRESH_DESCRIPTION,
    HuaweiClearTrafficButton,
    HuaweiRebootButton,
    HuaweiReconnectButton,
    HuaweiRefreshButton,
    async_setup_entry,
)
from custom_components.huawei_router_5g.const import DOMAIN
from tests.conftest import assert_is_root, assert_links_to_parent

# ---------------------------------------------------------------------------
# HuaweiRefreshButton
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_button_press(mock_coordinator, mock_config_entry):
    """Test that pressing refresh triggers an immediate coordinator refresh."""
    button = HuaweiRefreshButton(
        mock_coordinator, mock_config_entry, REFRESH_DESCRIPTION
    )
    await button.async_press()

    mock_coordinator.async_force_refresh.assert_called_once()


def test_refresh_button_device_info(mock_coordinator, mock_config_entry):
    """Test device_info for the refresh button is in the system group."""
    button = HuaweiRefreshButton(
        mock_coordinator, mock_config_entry, REFRESH_DESCRIPTION
    )
    mac = "DC:71:96:11:22:33"
    info = button.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_system")}
    assert_is_root(info)


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
    assert_is_root(info)


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
    mock_coordinator.async_force_refresh.assert_called_once()


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
    mock_coordinator.async_force_refresh.assert_not_called()


def test_clear_traffic_button_device_info(mock_coordinator, mock_config_entry):
    """Test device_info for the clear traffic button is in the data group."""
    button = HuaweiClearTrafficButton(
        mock_coordinator, mock_config_entry, CLEAR_TRAFFIC_DESCRIPTION
    )
    mac = "DC:71:96:11:22:33"
    info = button.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_data")}
    assert_links_to_parent(info, f"{mac}_system")


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
    assert len(entities) == 4
    # Named rather than counted: a bare count passes if a button is registered
    # twice and another dropped.
    assert {e.entity_description.key for e in entities} == {
        "refresh",
        "reboot",
        "reconnect",
        "clear_traffic",
    }


# ---------------------------------------------------------------------------
# Reconnect (§T-4e)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnect_button_calls_the_api() -> None:
    """The button must reach `api.reconnect`, not `reboot` or `dial`."""
    coordinator = MagicMock()
    coordinator.api.reconnect = AsyncMock()
    entry = MagicMock()
    entry.unique_id = "abc"

    button = HuaweiReconnectButton(coordinator, entry, RECONNECT_DESCRIPTION)
    await button.async_press()

    coordinator.api.reconnect.assert_awaited_once()
    coordinator.api.reboot.assert_not_called()


@pytest.mark.asyncio
async def test_reconnect_failure_raises_rather_than_reporting_success() -> None:
    """§22 / §O-4: an unverified write must never report success.

    Reporting a silent success on a control with a real-world effect invites
    the user to press it again.
    """
    coordinator = MagicMock()
    coordinator.api.reconnect = AsyncMock(side_effect=OSError("boom"))
    entry = MagicMock()
    entry.unique_id = "abc"

    button = HuaweiReconnectButton(coordinator, entry, RECONNECT_DESCRIPTION)
    with pytest.raises(HomeAssistantError, match="Reconnect failed"):
        await button.async_press()


def test_reconnect_is_not_declared_as_a_restart() -> None:
    """Reboot owns `RESTART`; sharing it makes the two read as duplicates."""
    assert RECONNECT_DESCRIPTION.device_class is None
    assert REBOOT_DESCRIPTION.device_class is ButtonDeviceClass.RESTART
