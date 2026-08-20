"""Tests for the Huawei Router 5G DataUpdateCoordinator."""

import logging
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)


@pytest.fixture(autouse=True)
def mock_report_usage():
    """Suppress 'Frame helper not set up' warnings from HA internals."""
    with patch("homeassistant.helpers.frame.report_usage"):
        yield


@pytest.mark.asyncio
async def test_coordinator_communication_restoration_log(
    mock_hass, mock_config_entry, caplog
):
    """Test that the coordinator logs when communication is restored."""
    mock_api = MagicMock()
    # First call fails, second succeeds
    mock_api.get_data = AsyncMock(
        side_effect=[
            Exception("First Fail"),
            {"device_information": {"DeviceName": "B535"}},
        ]
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator.data = {"old": "data"}

    # 1. Trigger a failure
    await coordinator._async_update_data()
    assert coordinator.consecutive_failures == 1

    # 2. Trigger a success
    caplog.set_level(logging.INFO)
    await coordinator._async_update_data()

    assert coordinator.consecutive_failures == 0
    assert "Communication restored after 1 failures" in caplog.text


@pytest.mark.asyncio
async def test_the_sms_debug_log_carries_shape_and_never_contents(
    mock_hass, mock_config_entry, caplog
):
    """The SMS payload's shape may be logged. Its values may not.

    This asserted `"Raw SMS list" in caplog.text` until 2026-08-19, which is
    what the coordinator did: it logged the block verbatim, so a debug log held
    every sender number and every message body — the two fields `diagnostics.py`
    goes out of its way to pseudonymize, in the one file that has no redaction
    and that users are told to paste into issue reports.

    Asserting the absence of the values is the point. A test for the message
    text alone would pass again the moment someone reinstates the dump.
    """
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535"},
            "sms_list": {
                "Messages": {
                    "Message": [
                        {
                            "Index": "40001",
                            "Phone": "+353871234567",
                            "Content": "meet me at the usual place",
                            "Date": "2026-08-19 10:00:00",
                        }
                    ]
                }
            },
        }
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    caplog.set_level(logging.DEBUG)
    await coordinator._async_update_data()

    # The shape is there, which is what a payload-variance problem needs.
    assert "1 message(s)" in caplog.text
    assert "Content" in caplog.text and "Phone" in caplog.text

    # The values are not - at any level.
    assert "+353871234567" not in caplog.text
    assert "meet me at the usual place" not in caplog.text


@pytest.mark.asyncio
async def test_the_sms_shape_log_counts_a_lone_message_sent_as_a_dict(
    mock_hass, mock_config_entry, caplog
):
    """One message arrives as a bare dict, not a list of one.

    The router collapses a single-entry list, the same shape `parse_sms_list`
    has to tolerate. Counting it as one message rather than iterating its keys
    is the distinction this pins.
    """
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535"},
            "sms_list": {
                "Messages": {
                    "Message": {
                        "Index": "40003",
                        "Phone": "+353871234567",
                        "Content": "single",
                        "Date": "2026-08-19 11:00:00",
                    }
                }
            },
        }
    )
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    caplog.set_level(logging.DEBUG)
    await coordinator._async_update_data()

    assert "1 message(s)" in caplog.text
    assert "+353871234567" not in caplog.text


@pytest.mark.asyncio
async def test_a_new_sms_is_announced_without_the_senders_number(
    mock_hass, mock_config_entry, caplog
):
    """`info` reaches every log with nothing enabled, so it carries no identifier.

    The number is in the bus event, which is where an automation reads it —
    the README's own example uses `trigger.event.data.phone`.
    """
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, MagicMock()
    )
    # Past the first-run baseline, so the next message fires an event.
    coordinator.last_sms_timestamp = "2026-08-19 09:00:00"

    caplog.set_level(logging.INFO)
    coordinator._check_new_sms(
        {
            "sms_list": {
                "Messages": {
                    "Message": [
                        {
                            "Index": "40002",
                            "Phone": "+353871234567",
                            "Content": "bring milk",
                            "Date": "2026-08-19 10:00:00",
                        }
                    ]
                }
            }
        }
    )

    assert "New SMS received" in caplog.text
    assert "+353871234567" not in caplog.text

    # The event still carries what an automation needs.
    _, args, _ = mock_hass.bus.async_fire.mock_calls[0]
    assert args[1]["phone"] == "+353871234567"
    assert args[1]["content"] == "bring milk"


@pytest.mark.asyncio
async def test_coordinator_sms_tracking_first_run(mock_hass, mock_config_entry):
    """Test that the first SMS fetch only sets the last_sms_timestamp."""
    mock_api = MagicMock()
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    data = {
        "sms_list": {
            "Messages": {
                "Message": [
                    {
                        "Index": "5",
                        "Phone": "123",
                        "Content": "A",
                        "Date": "2024-05-01 10:00:00",
                    },
                    {
                        "Index": "10",
                        "Phone": "456",
                        "Content": "B",
                        "Date": "2024-05-01 10:05:00",
                    },
                ]
            }
        }
    }

    with patch.object(mock_hass.bus, "async_fire") as mock_fire:
        coordinator._check_new_sms(data)

    assert coordinator.last_sms_timestamp == "2024-05-01 10:05:00"
    assert "10_2024-05-01 10:05:00" in coordinator.fired_sms_hashes
    mock_fire.assert_not_called()


@pytest.mark.asyncio
async def test_coordinator_sms_event_firing(mock_hass, mock_config_entry):
    """Test that new SMS messages trigger Home Assistant bus events."""
    mock_api = MagicMock()
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator.last_sms_timestamp = "2024-05-01 10:00:00"
    coordinator.fired_sms_hashes = {"10_2024-05-01 10:00:00"}

    data = {
        "sms_list": {
            "Messages": {
                "Message": [
                    {
                        "Index": "10",
                        "Phone": "123",
                        "Content": "Old",
                        "Date": "2024-05-01 10:00:00",
                    },
                    {
                        "Index": "11",
                        "Phone": "456",
                        "Content": "New1",
                        "Date": "2024-05-01 10:01:00",
                    },
                    {
                        "Index": "12",
                        "Phone": "789",
                        "Content": "New2",
                        "Date": "2024-05-01 10:02:00",
                    },
                ]
            }
        }
    }

    with patch.object(mock_hass.bus, "async_fire") as mock_fire:
        coordinator._check_new_sms(data)

    assert coordinator.last_sms_timestamp == "2024-05-01 10:02:00"
    assert mock_fire.call_count == 2

    # The payload is a **published contract** — documented in README.md and
    # used as an automation trigger — so every field is asserted, not just the
    # two that are obviously interesting. `entry_id` is what a multi-router
    # user filters on to tell which router a message arrived at; dropping it
    # fires every such automation for both routers. Covers finding ASSERT.2
    # from recommendations_20260815.md Part 2.
    call1 = mock_fire.call_args_list[0]
    assert call1[0][0] == "huawei_router_5g_sms_received"
    assert call1[0][1]["entry_id"] == mock_config_entry.entry_id
    assert call1[0][1]["index"] == 11
    assert call1[0][1]["phone"] == "456"
    assert call1[0][1]["content"] == "New1"
    assert call1[0][1]["date"] == "2024-05-01 10:01:00"

    # Distinct values per message, so a swap between the two events cannot pass.
    call2 = mock_fire.call_args_list[1]
    assert call2[0][0] == "huawei_router_5g_sms_received"
    assert call2[0][1]["entry_id"] == mock_config_entry.entry_id
    assert call2[0][1]["index"] == 12
    assert call2[0][1]["phone"] == "789"
    assert call2[0][1]["content"] == "New2"
    assert call2[0][1]["date"] == "2024-05-01 10:02:00"


@pytest.mark.asyncio
async def test_coordinator_critical_data_missing(mock_hass, mock_config_entry):
    """Test that missing device_information raises UpdateFailed."""
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(return_value={"something": "else"})

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    with pytest.raises(UpdateFailed, match="Critical data missing"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_paused_polling(mock_hass, mock_config_entry, caplog):
    """Test paused polling logic: returns cached data or empty dict on failure."""
    from custom_components.huawei_router_5g.const import CONF_STOP_POLLING

    mock_api = MagicMock()
    object.__setattr__(mock_config_entry, "options", {CONF_STOP_POLLING: True})

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    # Scenario 1: Initial fetch fails while paused
    mock_api.get_data = AsyncMock(side_effect=Exception("Initial fail"))
    caplog.set_level(logging.WARNING)
    data = await coordinator._async_update_data()
    assert data == {}
    assert "Initial fetch failed while paused" in caplog.text

    # Scenario 2: Polling is paused and not first run
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    coordinator.data = {"cached": "data"}
    data = await coordinator._async_update_data()
    assert data == {"cached": "data"}
    assert "Polling is paused; returning cached data." in caplog.text


@pytest.mark.asyncio
async def test_coordinator_sms_hash_collision(mock_hass, mock_config_entry):
    """Test SMS hash handling when multiple messages have the same timestamp."""
    mock_api = MagicMock()
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator.last_sms_timestamp = "2024-05-01 10:00:00"
    coordinator.fired_sms_hashes = {"10_2024-05-01 10:00:00"}

    data = {
        "sms_list": {
            "Messages": {
                "Message": [
                    {
                        "Index": "11",
                        "Phone": "123",
                        "Content": "New1",
                        "Date": "2024-05-01 10:01:00",
                    },
                    {
                        "Index": "12",
                        "Phone": "456",
                        "Content": "New2",
                        "Date": "2024-05-01 10:01:00",  # Same timestamp!
                    },
                ]
            }
        }
    }

    with patch.object(mock_hass.bus, "async_fire") as mock_fire:
        coordinator._check_new_sms(data)

    assert coordinator.last_sms_timestamp == "2024-05-01 10:01:00"
    assert "11_2024-05-01 10:01:00" in coordinator.fired_sms_hashes
    assert "12_2024-05-01 10:01:00" in coordinator.fired_sms_hashes
    assert mock_fire.call_count == 2


@pytest.mark.asyncio
async def test_coordinator_init_restores_uptime_state(mock_hass, mock_config_entry):
    """Test that uptime/boot state is restored from entry.data at init."""
    object.__setattr__(
        mock_config_entry,
        "data",
        {
            **mock_config_entry.data,
            "system_boot_time": "2024-01-01T00:00:00",
            "last_system_uptime": "3600",
            "conn_start_time": "2024-01-01T01:00:00",
            "last_conn_uptime": "1800",
            "total_conn_start_time": "2024-01-01T02:00:00",
            "last_total_conn_time": "7200",
        },
    )
    mock_api = MagicMock()
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    assert coordinator._system_boot_time == dt_util.parse_datetime(
        "2024-01-01T00:00:00"
    )
    assert coordinator._last_system_uptime == 3600
    assert coordinator._conn_start_time == dt_util.parse_datetime("2024-01-01T01:00:00")
    assert coordinator._last_conn_uptime == 1800
    assert coordinator._total_conn_start_time == dt_util.parse_datetime(
        "2024-01-01T02:00:00"
    )
    assert coordinator._last_total_conn_time == 7200


@pytest.mark.asyncio
async def test_coordinator_system_uptime_first_latch(mock_hass, mock_config_entry):
    """Test that system boot time is latched on first run."""
    fixed_now = dt_util.parse_datetime("2024-06-15 12:00:00+00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535", "uptime": "3600"},
        }
    )

    with patch.object(dt_util, "now", return_value=fixed_now):
        coordinator = HuaweiRouter5GDataUpdateCoordinator(
            mock_hass, mock_config_entry, mock_api
        )
        await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-15 11:00:00+00:00")
    assert coordinator._system_boot_time == expected
    assert coordinator._last_system_uptime == 3600
    mock_hass.config_entries.async_update_entry.assert_called()


@pytest.mark.asyncio
async def test_coordinator_system_uptime_reboot_detected(
    mock_hass, mock_config_entry, caplog
):
    """Test that a significant uptime drop triggers reboot detection."""
    fixed_now = dt_util.parse_datetime("2024-06-15 13:00:00+00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535", "uptime": "30"},
        }
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator._system_boot_time = dt_util.parse_datetime("2024-06-15 11:00:00+00:00")
    coordinator._last_system_uptime = 3600
    coordinator.data = {"device_information": {"DeviceName": "B535"}}

    caplog.set_level(logging.DEBUG)
    with patch.object(dt_util, "now", return_value=fixed_now):
        await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-15 12:59:30+00:00")
    assert coordinator._system_boot_time == expected
    assert coordinator._last_system_uptime == 30
    assert "System boot time latched" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_connection_uptime_first_latch(mock_hass, mock_config_entry):
    """Test that connection start time is latched on first run."""
    fixed_now = dt_util.parse_datetime("2024-06-15 12:00:00+00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535"},
            "traffic_statistics": {"CurrentConnectTime": "1800"},
        }
    )

    with patch.object(dt_util, "now", return_value=fixed_now):
        coordinator = HuaweiRouter5GDataUpdateCoordinator(
            mock_hass, mock_config_entry, mock_api
        )
        await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-15 11:30:00+00:00")
    assert coordinator._conn_start_time == expected
    assert coordinator._last_conn_uptime == 1800


@pytest.mark.asyncio
async def test_coordinator_connection_uptime_reboot_detected(
    mock_hass, mock_config_entry, caplog
):
    """Test that a significant connection time drop triggers reboot detection."""
    fixed_now = dt_util.parse_datetime("2024-06-15 13:00:00+00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535"},
            "traffic_statistics": {"CurrentConnectTime": "10"},
        }
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator._conn_start_time = dt_util.parse_datetime("2024-06-15 11:00:00+00:00")
    coordinator._last_conn_uptime = 3600
    coordinator.data = {"device_information": {"DeviceName": "B535"}}

    caplog.set_level(logging.DEBUG)
    with patch.object(dt_util, "now", return_value=fixed_now):
        await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-15 12:59:50+00:00")
    assert coordinator._conn_start_time == expected
    assert "Connection start time latched" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_total_conn_uptime_first_latch(mock_hass, mock_config_entry):
    """Test that total connection start time is latched on first run."""
    fixed_now = dt_util.parse_datetime("2024-06-15 12:00:00+00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535"},
            "traffic_statistics": {"TotalConnectTime": "86400"},
        }
    )

    with patch.object(dt_util, "now", return_value=fixed_now):
        coordinator = HuaweiRouter5GDataUpdateCoordinator(
            mock_hass, mock_config_entry, mock_api
        )
        await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-14 12:00:00+00:00")
    assert coordinator._total_conn_start_time == expected
    assert coordinator._last_total_conn_time == 86400


@pytest.mark.asyncio
async def test_coordinator_total_conn_uptime_reboot_detected(
    mock_hass, mock_config_entry, caplog
):
    """Test that a significant total connect time drop triggers reboot detection."""
    fixed_now = dt_util.parse_datetime("2024-06-15 15:00:00+00:00")
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {"DeviceName": "B535"},
            "traffic_statistics": {"TotalConnectTime": "5"},
        }
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator._total_conn_start_time = dt_util.parse_datetime(
        "2024-06-15 10:00:00+00:00"
    )
    coordinator._last_total_conn_time = 7200
    coordinator.data = {"device_information": {"DeviceName": "B535"}}

    caplog.set_level(logging.DEBUG)
    with patch.object(dt_util, "now", return_value=fixed_now):
        await coordinator._async_update_data()

    expected = dt_util.parse_datetime("2024-06-15 14:59:55+00:00")
    assert coordinator._total_conn_start_time == expected
    assert "Total connection start time latched" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_timeout_after_max_failures(
    mock_hass, mock_config_entry, caplog
):
    """Test that a timeout after maximum failures raises UpdateFailed."""
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(side_effect=TimeoutError("Request timed out"))
    # A timeout now invalidates the connection and probes the router, so both
    # hooks must be awaitable on the stub.
    mock_api.invalidate = AsyncMock()
    mock_api.probe_liveness = AsyncMock(return_value=False)

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator.data = {"device_information": {"DeviceName": "B535"}}
    coordinator.consecutive_failures = 3

    caplog.set_level(logging.ERROR)

    with pytest.raises(UpdateFailed, match="API request timed out"):
        await coordinator._async_update_data()

    assert coordinator.consecutive_failures == 4


@pytest.fixture
def mock_hass():
    """Mock Home Assistant."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    return hass


@pytest.mark.asyncio
async def test_coordinator_config_entry_associated(mock_hass, mock_config_entry):
    """Coordinator passes config_entry to base so HA honours pref_disable_polling."""
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, MagicMock()
    )
    assert coordinator.config_entry is mock_config_entry


# ---------------------------------------------------------------------------
# Section 13 — an explicit user action must fetch even while polling is paused
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forced_refresh_fetches_while_polling_is_paused(
    mock_hass, mock_config_entry, caplog
):
    """A forced cycle must bypass the pause short-circuit and really fetch.

    This is the regression `dev_standards` Section 13 names by example: a
    Refresh Now wired to a bare `async_request_refresh()` returns cached data
    and reports success at exactly the moment the user asked for a fresh
    reading. The distinction being asserted is *fetched vs. did not fetch* —
    not that the call returned.
    """
    from custom_components.huawei_router_5g.const import CONF_STOP_POLLING

    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={"device_information": {"DeviceName": "B535"}}
    )
    object.__setattr__(mock_config_entry, "options", {CONF_STOP_POLLING: True})

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator.data = {"cached": "data"}

    caplog.set_level(logging.DEBUG)
    coordinator._force_refresh_once = True
    data = await coordinator._async_update_data()

    assert mock_api.get_data.await_count == 1, "forced cycle did not reach the router"
    assert data != {"cached": "data"}
    assert data["device_information"]["DeviceName"] == "B535"
    assert "fetching despite paused polling" in caplog.text


@pytest.mark.asyncio
async def test_force_flag_is_consumed_after_one_cycle(mock_hass, mock_config_entry):
    """The flag is one-shot: the *next* scheduled poll must respect the pause.

    A flag that survived its cycle would silently disable pausing altogether
    after a single button press, which is a worse defect than the one being
    fixed and would not be visible in any single-cycle test.
    """
    from custom_components.huawei_router_5g.const import CONF_STOP_POLLING

    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={"device_information": {"DeviceName": "B535"}}
    )
    object.__setattr__(mock_config_entry, "options", {CONF_STOP_POLLING: True})

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )
    coordinator.data = {"cached": "data"}

    coordinator._force_refresh_once = True
    await coordinator._async_update_data()
    assert coordinator._force_refresh_once is False
    assert mock_api.get_data.await_count == 1

    # Second cycle is a scheduled poll — it must be short-circuited.
    second = await coordinator._async_update_data()
    assert mock_api.get_data.await_count == 1, "scheduled poll fetched while paused"
    assert second == coordinator.data


@pytest.mark.asyncio
async def test_async_force_refresh_sets_the_flag_then_requests(
    mock_hass, mock_config_entry
):
    """`async_force_refresh` sets the flag *before* requesting the refresh.

    Order matters: `async_request_refresh` can run the update inline, so a flag
    set afterwards would arrive too late to be consumed by the cycle it was
    meant for.
    """
    mock_api = MagicMock()
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    seen: list[bool] = []

    async def _capture() -> None:
        seen.append(coordinator._force_refresh_once)

    with patch.object(coordinator, "async_request_refresh", side_effect=_capture):
        await coordinator.async_force_refresh()

    assert seen == [True], "flag was not set before async_request_refresh was awaited"


@pytest.mark.asyncio
async def test_async_force_refresh_clears_the_flag_when_the_request_raises(
    mock_hass, mock_config_entry
):
    """A failed request must not leave the flag set.

    Otherwise the next *scheduled* poll inherits the force and fetches despite
    the pause — self-correcting after one cycle, but Section 13 asks that every
    path out clears it.
    """
    mock_api = MagicMock()
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    with (
        patch.object(
            coordinator, "async_request_refresh", side_effect=RuntimeError("boom")
        ),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await coordinator.async_force_refresh()

    assert coordinator._force_refresh_once is False


@pytest.mark.asyncio
async def test_uptime_latches_hold_across_a_steady_second_poll(
    mock_hass, mock_config_entry
):
    """A normal second poll must reuse the latched times, not recompute them.

    All three reboot-detection latches — system uptime, current connection and
    total connection — recompute a start time only when there is no latch yet
    **or** the counter has dropped by more than `UPTIME_REBOOT_MARGIN`. Every
    existing test hit the first poll, where all three latch. The steady-state
    path, which is what runs on every poll after the first, was the single
    largest group of unexercised branches in the component.

    The distinction that matters is *frozen vs. drifting*: these timestamps
    feed uptime-derived sensors, so recomputing them each poll would make the
    displayed boot time crawl forward and never settle.
    """
    mock_api = MagicMock()

    def _payload(sys_uptime: str, conn: str, total: str) -> dict:
        return {
            "device_information": {"DeviceName": "B535", "uptime": sys_uptime},
            "traffic_statistics": {
                "CurrentConnectTime": conn,
                "TotalConnectTime": total,
            },
        }

    mock_api.get_data = AsyncMock(
        side_effect=[
            _payload("1000", "500", "90000"),
            # 180s later — all three counters have advanced, nothing rebooted.
            _payload("1180", "680", "90180"),
        ]
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, mock_api
    )

    first = await coordinator._async_update_data()
    coordinator.data = first
    latched = (
        first["system_boot_time"],
        first["conn_start_time"],
        first["total_conn_start_time"],
    )
    assert all(t is not None for t in latched)

    second = await coordinator._async_update_data()

    assert (
        second["system_boot_time"],
        second["conn_start_time"],
        second["total_conn_start_time"],
    ) == latched, "a steady poll recomputed the latched start times"

    # And the last-seen counters advanced, so a genuine drop is still detectable.
    assert coordinator._last_system_uptime == 1180
    assert coordinator._last_conn_uptime == 680
    assert coordinator._last_total_conn_time == 90180


# ---------------------------------------------------------------------------
# Follow-up refresh after a disruptive button
# ---------------------------------------------------------------------------


def _refresh_coordinator(hass):
    """Build a coordinator with a writable `options`, which MockConfigEntry lacks."""
    entry = MagicMock()
    entry.entry_id = "test"
    entry.title = "My Huawei Router"
    entry.options = {}
    entry.data = {}
    coordinator = HuaweiRouter5GDataUpdateCoordinator(hass, entry, MagicMock())
    coordinator.update_interval = timedelta(seconds=1200)
    return coordinator


@pytest.mark.asyncio
async def test_a_disruptive_write_schedules_one_follow_up_refresh(
    mock_hass, mock_config_entry
):
    """The reading straight after a reboot or reconnect is stale by definition.

    Without this the entities sit wrong until the next scheduled poll, which is
    twenty minutes by default.
    """
    coordinator = _refresh_coordinator(mock_hass)
    coordinator.update_interval = timedelta(seconds=1200)

    with patch(
        "custom_components.huawei_router_5g.coordinator.async_call_later"
    ) as later:
        coordinator.async_schedule_refresh(20)

    later.assert_called_once()
    assert later.call_args[0][1] == 20


@pytest.mark.asyncio
async def test_firing_the_scheduled_callback_actually_refreshes(mock_hass):
    """The timer must do the thing, not merely be set.

    Every other test around `async_schedule_refresh` patches `async_call_later`
    and asserts it was **called** with the right delay. None of them ever ran
    the callback, so the whole mechanism could have scheduled a function that
    did nothing and the suite would have stayed green — the follow-up refresh
    after Reboot and Reconnect is the only way a user sees the result of the
    button they pushed, and with polling paused it is the only fetch at all.

    Captures the scheduled callable and invokes it, which is what Home
    Assistant does when the delay elapses.
    """
    coordinator = _refresh_coordinator(mock_hass)
    coordinator.async_force_refresh = AsyncMock()

    with patch(
        "custom_components.huawei_router_5g.coordinator.async_call_later"
    ) as later:
        coordinator.async_schedule_refresh(20)

    # async_call_later(hass, delay, action) — the action is the third argument.
    action = later.call_args[0][2]
    await action(None)

    coordinator.async_force_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_pending_handle_is_cleared_when_the_callback_fires(mock_hass):
    """A fired timer must not leave a handle that unload would then cancel.

    `async_cancel_scheduled_refresh` calls the stored handle. If firing left it
    in place, unload would invoke an already-spent cancel callback — and worse,
    a second button press would believe a refresh was still pending and replace
    a timer that had already run.
    """
    coordinator = _refresh_coordinator(mock_hass)
    coordinator.async_force_refresh = AsyncMock()

    with patch(
        "custom_components.huawei_router_5g.coordinator.async_call_later"
    ) as later:
        coordinator.async_schedule_refresh(60)

    assert coordinator._pending_refresh is not None
    await later.call_args[0][2](None)
    assert coordinator._pending_refresh is None


@pytest.mark.asyncio
async def test_the_follow_up_refresh_fires_even_while_polling_is_paused(mock_hass):
    """Section 13: an explicit user action must not be swallowed by the pause.

    The follow-up is part of the button press, not background polling — and
    with polling paused it is the *only* way the user ever sees the result of
    the button they pushed. Every other write path here already forces through
    the pause; this one was the exception until 2026-08-15.
    """
    coordinator = _refresh_coordinator(mock_hass)
    coordinator.entry.options = {"stop_polling": True}

    with patch(
        "custom_components.huawei_router_5g.coordinator.async_call_later"
    ) as later:
        coordinator.async_schedule_refresh(20)

    later.assert_called_once()


@pytest.mark.asyncio
async def test_a_paused_integration_ignores_the_interval_shortcut(mock_hass):
    """While paused there is no scheduled poll to defer to.

    The interval check exists to avoid a redundant fetch. Paused, the poll it
    would defer to returns cached data, so deferring would mean the user never
    sees the result at all.
    """
    coordinator = _refresh_coordinator(mock_hass)
    coordinator.update_interval = timedelta(seconds=30)
    coordinator.entry.options = {"stop_polling": True}

    with patch(
        "custom_components.huawei_router_5g.coordinator.async_call_later"
    ) as later:
        coordinator.async_schedule_refresh(60)

    later.assert_called_once()


@pytest.mark.asyncio
async def test_no_follow_up_when_the_poll_interval_already_covers_it(
    mock_hass, mock_config_entry
):
    """On a short interval the ordinary poll gets there first.

    This is the owner's "if the polling interval is greater than a minute"
    condition, generalised: schedule only when the follow-up would land before
    the next poll would.
    """
    coordinator = _refresh_coordinator(mock_hass)
    coordinator.update_interval = timedelta(seconds=30)

    with patch(
        "custom_components.huawei_router_5g.coordinator.async_call_later"
    ) as later:
        coordinator.async_schedule_refresh(60)

    later.assert_not_called()


@pytest.mark.asyncio
async def test_a_second_press_replaces_the_pending_refresh(
    mock_hass, mock_config_entry
):
    """Two presses must not queue two fetches."""
    coordinator = _refresh_coordinator(mock_hass)
    coordinator.update_interval = timedelta(seconds=1200)

    first = MagicMock()

    with patch(
        "custom_components.huawei_router_5g.coordinator.async_call_later",
        side_effect=[first, MagicMock()],
    ):
        coordinator.async_schedule_refresh(20)
        coordinator.async_schedule_refresh(20)

    first.assert_called_once_with()


@pytest.mark.asyncio
async def test_the_scheduled_refresh_forces_past_a_pause_set_later(
    mock_hass, mock_config_entry
):
    """It routes through `async_force_refresh`, not `async_request_refresh`.

    If the user pauses polling between the press and the timer firing, a plain
    request would be swallowed by the pause short-circuit at exactly the moment
    the data is known to be stale.
    """
    coordinator = _refresh_coordinator(mock_hass)
    coordinator.update_interval = timedelta(seconds=1200)

    coordinator.async_force_refresh = AsyncMock()

    captured = {}

    def _capture(_hass, _delay, action):
        captured["fire"] = action
        return MagicMock()

    with patch(
        "custom_components.huawei_router_5g.coordinator.async_call_later",
        side_effect=_capture,
    ):
        coordinator.async_schedule_refresh(20)

    await captured["fire"](None)
    coordinator.async_force_refresh.assert_awaited_once()
    assert coordinator._pending_refresh is None


@pytest.mark.asyncio
async def test_cancelling_a_pending_refresh_is_idempotent(mock_hass):
    """Unload calls this unconditionally, whether or not one is pending."""
    coordinator = _refresh_coordinator(mock_hass)
    handle = MagicMock()
    coordinator._pending_refresh = handle

    coordinator.async_cancel_scheduled_refresh()
    coordinator.async_cancel_scheduled_refresh()

    handle.assert_called_once_with()
    assert coordinator._pending_refresh is None


# ---------------------------------------------------------------------------
# testing_deeper_lev1_review findings, recommendations_20260815.md Part 2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_repeated_poll_of_an_unchanged_inbox_fires_nothing(
    mock_hass, mock_config_entry
):
    """The steady state is the same message list, poll after poll.

    Covers finding IDEM.1 from recommendations_20260815.md Part 2.

    Every other test calls `_check_new_sms` exactly once, so the
    de-duplication is only ever observed as "the first call did the right
    thing". The regression that misses is one character: `>` becoming `>=` at
    the timestamp comparison re-qualifies every message at the latest
    timestamp on every subsequent poll, firing a duplicate event every cycle
    forever — with the whole suite green.

    The third call is what separates "de-duplication works" from
    "de-duplication has stopped firing anything at all".
    """
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, MagicMock()
    )

    def _msg(index: str, date: str) -> dict:
        return {"Index": index, "Phone": "123", "Content": f"m{index}", "Date": date}

    first = {
        "sms_list": {
            "Messages": {
                "Message": [
                    _msg("1", "2024-05-01 10:00:00"),
                    _msg("2", "2024-05-01 10:01:00"),
                ]
            }
        }
    }

    with patch.object(mock_hass.bus, "async_fire") as fire:
        # First poll establishes the baseline silently — nothing pre-existing
        # may be replayed into the user's automations.
        coordinator._check_new_sms(first)
        assert fire.call_count == 0

        baseline_timestamp = coordinator.last_sms_timestamp
        baseline_hashes = set(coordinator.fired_sms_hashes)

        # Second poll: the router still holds exactly the same two messages.
        coordinator._check_new_sms(first)
        assert fire.call_count == 0, "an unchanged inbox fired an event again"
        assert coordinator.last_sms_timestamp == baseline_timestamp
        assert set(coordinator.fired_sms_hashes) == baseline_hashes

        # Third poll: one genuinely new message, which must still fire.
        second = {
            "sms_list": {
                "Messages": {
                    "Message": [
                        *first["sms_list"]["Messages"]["Message"],
                        _msg("3", "2024-05-01 10:02:00"),
                    ]
                }
            }
        }
        coordinator._check_new_sms(second)

    assert fire.call_count == 1, "a genuinely new message did not fire"
    assert fire.call_args[0][1]["index"] == 3
