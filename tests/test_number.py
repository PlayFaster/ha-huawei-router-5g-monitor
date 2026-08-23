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
from tests.conftest import assert_is_root

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
    assert_is_root(info)


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
    mock_coordinator.async_force_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_debounced_apply_cancelled(mock_coordinator, mock_config_entry):
    """Test that CancelledError inside the debounce is swallowed silently."""
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.hass = MagicMock()

    with patch("asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
        await entity._async_debounced_apply(300)  # should not raise

    mock_coordinator.async_force_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_debounced_apply_error(mock_coordinator, mock_config_entry):
    """A failure inside the debounce must abort the write, not half-apply it.

    "Should not raise" was the whole assertion, which is satisfied equally by
    swallowing the error *after* persisting a value the user never confirmed.
    What matters is that nothing downstream happened: the coordinator interval
    is untouched, options are not rewritten, and no refresh is requested.
    """
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.hass = MagicMock()
    interval_before = mock_coordinator.update_interval

    with patch("asyncio.sleep", new=AsyncMock(side_effect=Exception("Fail"))):
        await entity._async_debounced_apply(300)

    assert mock_coordinator.update_interval is interval_before
    entity.hass.config_entries.async_update_entry.assert_not_called()
    mock_coordinator.async_force_refresh.assert_not_called()


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
    task = MagicMock()
    entity._refresh_task = task

    await entity.async_will_remove_from_hass()

    task.cancel.assert_called_once()
    # The slot is released so a later removal cannot cancel a dead task.
    assert entity._refresh_task is None


@pytest.mark.asyncio
async def test_async_will_remove_from_hass_no_task(mock_coordinator, mock_config_entry):
    """Removal with no pending debounce must leave the entity's state alone.

    The previous form asserted only that it did not raise, which cannot tell
    "there was no task to cancel" apart from "a task was created and
    canceled". Assert the slot is still empty.
    """
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.hass = MagicMock()
    assert entity._refresh_task is None

    await entity.async_will_remove_from_hass()

    assert entity._refresh_task is None


@pytest.mark.asyncio
async def test_removal_flushes_a_pending_debounced_write(
    mock_coordinator, mock_config_entry
):
    """A value set inside the debounce window must be persisted on removal.

    The debounce is two seconds and a reload lands squarely inside it — an
    options change is enough to trigger one. Canceling the task without
    writing discarded the value silently: the slider snapped back with nothing
    logged and no error.

    The distinction is *flushed vs. canceled*, so this asserts the options
    write actually happened with the new value, not merely that removal did
    not raise.
    """
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    await entity.async_set_native_value(600)
    assert entity._refresh_task is not None

    await entity.async_will_remove_from_hass()

    entity.hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = entity.hass.config_entries.async_update_entry.call_args
    assert kwargs["options"][CONF_SCAN_INTERVAL] == 600
    assert mock_coordinator.update_interval == timedelta(seconds=600)
    # Torn down, so nothing should be asked to fetch.
    mock_coordinator.async_force_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_removal_after_the_debounce_committed_does_not_write_again(
    mock_coordinator, mock_config_entry
):
    """A committed value must not be written a second time on removal.

    The flush is driven by a pending-value slot that the debounce clears when
    it commits. Without that, every removal would re-persist the last value and
    re-fire the entry-update listeners.
    """
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        await entity._async_debounced_apply(600)

    assert entity._pending_value is None
    entity.hass.config_entries.async_update_entry.reset_mock()

    await entity.async_will_remove_from_hass()

    entity.hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_the_slider_publishes_the_value_the_user_chose(
    mock_coordinator, mock_config_entry
):
    """What `native_value` reads at the moment of the publish, not after it.

    The other tests in this file stub `async_write_ha_state` with a bare
    `MagicMock` and assert the stored option separately, so nothing joins the
    two halves: a publish carrying the previous value satisfies both. This is
    the optimistic publish, made before the debounce commits anything, and it
    is the one the user sees — publishing the old value makes the slider snap
    back under their finger. `stubbed_publish_tests.md`.
    """
    entity = HuaweiPollingInterval(
        mock_coordinator, mock_config_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    entity.hass = MagicMock()
    published: list[float | None] = []
    entity.async_write_ha_state = MagicMock(
        side_effect=lambda: published.append(entity.native_value)
    )

    def close_and_discard(coro):
        # The debounced task is not what this test is about, and leaving its
        # coroutine unawaited raises a ResourceWarning that would land on
        # whichever test happens to run next.
        coro.close()
        return MagicMock()

    with patch.object(asyncio, "create_task", close_and_discard):
        await entity.async_set_native_value(600)

    assert published == [600]
