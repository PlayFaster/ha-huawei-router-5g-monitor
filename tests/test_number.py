"""Tests for the Huawei Router 5G number platform."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.huawei_router_5g.const import CONF_SCAN_INTERVAL, DOMAIN
from custom_components.huawei_router_5g.number import (
    POLLING_INTERVAL_DESCRIPTION,
    HuaweiPollingInterval,
    async_setup_entry,
)

# ---------------------------------------------------------------------------
# HuaweiPollingInterval — state
# ---------------------------------------------------------------------------


def test_polling_interval_initial_value(mock_coordinator, mock_config_entry):
    """Test that the initial native_value comes from the constructor."""
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 300
    )
    assert entity.native_value == 300


def test_polling_interval_device_info(mock_coordinator, mock_config_entry):
    """Test device_info is in the system group (no via_device)."""
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    mac = "DC:71:96:11:22:33"
    info = entity.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_system")}
    assert info["manufacturer"] == "Huawei"
    assert "via_device" not in info


# ---------------------------------------------------------------------------
# HuaweiPollingInterval — set value (debounce)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_native_value_updates_state(mock_coordinator, mock_config_entry):
    """Test that async_set_native_value immediately updates the displayed value."""
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.async_write_ha_state = MagicMock()
    entity.hass = MagicMock()

    created_coros = []

    def capture_and_discard(coro):
        created_coros.append(coro)
        return MagicMock()

    with patch("asyncio.create_task", side_effect=capture_and_discard):
        await entity.async_set_native_value(600)

    for coro in created_coros:
        coro.close()

    assert entity.native_value == 600
    entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_debounce_cancels_previous_task(mock_coordinator, mock_config_entry):
    """Test that a second value change cancels the first debounce task."""
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.async_write_ha_state = MagicMock()
    entity.hass = MagicMock()

    tasks = []
    coros = []

    def fake_create_task(coro):
        coros.append(coro)
        task = MagicMock()
        tasks.append(task)
        return task

    with patch("asyncio.create_task", side_effect=fake_create_task):
        await entity.async_set_native_value(300)
        await entity.async_set_native_value(600)

    for coro in coros:
        coro.close()

    assert len(tasks) == 2
    tasks[0].cancel.assert_called_once()


@pytest.mark.asyncio
async def test_debounced_apply_persists_and_refreshes(
    mock_coordinator, mock_config_entry
):
    """Test that _async_debounced_apply updates the coordinator and persists options."""
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.hass = MagicMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        await entity._async_debounced_apply(300)

    assert mock_coordinator.update_interval == timedelta(seconds=300)
    entity.hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = entity.hass.config_entries.async_update_entry.call_args
    assert kwargs["options"][CONF_SCAN_INTERVAL] == 300
    mock_coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_debounced_apply_cancelled(mock_coordinator, mock_config_entry):
    """Test that CancelledError inside the debounce is swallowed silently."""
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.hass = MagicMock()

    with patch("asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
        await entity._async_debounced_apply(300)  # should not raise

    mock_coordinator.async_request_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_debounced_apply_error(mock_coordinator, mock_config_entry):
    """Test that a non-cancel error inside the debounce is swallowed."""
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.hass = MagicMock()

    with patch("asyncio.sleep", new=AsyncMock(side_effect=Exception("Fail"))):
        await entity._async_debounced_apply(300)  # should not raise


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_number_setup_entry():
    """Test that async_setup_entry creates one number entity."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    entry.options = {CONF_SCAN_INTERVAL: 120}
    coordinator = MagicMock()
    hass.data = {DOMAIN: {"test": coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert entities[0].native_value == 120


@pytest.mark.asyncio
async def test_number_setup_entry_default_interval():
    """Test that setup uses 180s default when SCAN_INTERVAL is absent."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test"
    entry.options = {}
    coordinator = MagicMock()
    hass.data = {DOMAIN: {"test": coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)
    entities = async_add_entities.call_args[0][0]
    assert entities[0].native_value == 180


# ---------------------------------------------------------------------------
# HuaweiPollingInterval — lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_will_remove_from_hass_with_task(
    mock_coordinator, mock_config_entry
):
    """Test that async_will_remove_from_hass cancels pending debounce."""
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.hass = MagicMock()
    entity._refresh_task = MagicMock()

    await entity.async_will_remove_from_hass()

    entity._refresh_task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_async_will_remove_from_hass_no_task(mock_coordinator, mock_config_entry):
    """Test async_will_remove_from_hass when no refresh task exists."""
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.hass = MagicMock()

    await entity.async_will_remove_from_hass()  # should not raise
