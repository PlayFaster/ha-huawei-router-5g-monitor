"""What the poll path reports, raises and persists.

`_async_update_data` produced **152 of the 356 survivors** in the first
mutation run to cover `coordinator.py` — across only 60 distinct lines. The
existing tests drive the path and assert what it *returns*; almost nothing
asserted its side effects, and the side effects are the point of the method.

Three clusters, and each is a different kind of invisible:

- **`update_health(...)` — 33 survivors on four call sites.** The flags decide
  what the Integration Health sensor says. Swap `cold_start` and a first-run
  failure is reported as a degradation of a working integration, or the
  reverse; nothing raises either way.
- **Repair-issue arguments — ~21.** `is_fixable`, `is_persistent`, the
  translation key and the placeholder that names which router. A wrong
  `is_persistent` means a warning that never clears, or an auth error that
  vanishes on restart and leaves the user with no working entities and no
  repair card.
- **Latch persistence — ~15.** The uptime latches are written back to
  `ConfigEntry.data` so a restart does not re-derive a boot time from a
  counter that has moved. A key mutated here is not read back next time, and
  the sensor silently re-latches.

The health assertions read `coordinator.health_snapshot` rather than a mock,
because that dict is the published contract Section 19 defines.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.huawei_router_5g.api import HuaweiAuthError
from custom_components.huawei_router_5g.const import (
    REPAIR_AUTH_FAILED,
    REPAIR_CONN_ERROR,
)
from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)

GOOD = {"device_information": {"DeviceName": "B535-232"}}


@pytest.fixture
def hass_stub():
    """Return a hass stub with the registries the poll path writes to."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    return hass


def _coordinator(hass, *, options=None, data=None):
    """Build a coordinator whose API is a stub the test drives."""
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.title = "My Huawei Router"
    entry.data = data if data is not None else {}
    entry.options = options if options is not None else {}
    coordinator = HuaweiRouter5GDataUpdateCoordinator(hass, entry, MagicMock())
    coordinator.api.get_data = AsyncMock()
    return coordinator


# ---------------------------------------------------------------------------
# The health verdict — which flags reach `update_health`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_held_failure_is_not_reported_as_a_cold_start(hass_stub) -> None:
    """Failure 1 of 3 with data in hand is a *degradation*, not a cold start.

    `cold_start=False` here is what tells Section 19 the integration was
    working a moment ago. Reported as a cold start, a routine blip reads as an
    integration that has never worked.
    """
    coordinator = _coordinator(hass_stub)
    coordinator.data = GOOD
    coordinator.api.get_data.side_effect = TimeoutError

    with patch.object(coordinator, "update_health") as health:
        assert await coordinator._async_update_data() == GOOD

    health.assert_called_once_with(None, failed=True, cold_start=False)


@pytest.mark.asyncio
async def test_a_first_run_failure_is_reported_as_a_cold_start(hass_stub) -> None:
    """No data yet means cold start — the flag is derived, not assumed."""
    coordinator = _coordinator(hass_stub)
    coordinator.data = None
    coordinator.api.get_data.side_effect = TimeoutError

    with (
        patch.object(coordinator, "update_health") as health,
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    health.assert_called_once_with(None, failed=True, cold_start=True)


@pytest.mark.asyncio
async def test_a_paused_first_run_failure_starts_empty_and_says_so(
    hass_stub,
) -> None:
    """Paused with nothing cached: return `{}` rather than failing setup.

    Entities exist and read unknown, which is the Section 1 bargain. The
    `cold_start=True` is unconditional here — the branch is only reachable on
    a first run — so a mutation to `self.data is None` survives unless the
    call is asserted.
    """
    coordinator = _coordinator(hass_stub, options={"stop_polling": True})
    coordinator.data = None
    coordinator.api.get_data.side_effect = ValueError("boom")

    with patch.object(coordinator, "update_health") as health:
        assert await coordinator._async_update_data() == {}

    health.assert_called_once_with(None, failed=True, cold_start=True)


@pytest.mark.asyncio
async def test_a_successful_poll_reports_success(hass_stub) -> None:
    """Both flags matter: `failed=False` and `cold_start=False`."""
    coordinator = _coordinator(hass_stub)
    coordinator.api.get_data.return_value = GOOD

    with patch.object(coordinator, "update_health") as health:
        await coordinator._async_update_data()

    health.assert_called_once_with(GOOD, failed=False, cold_start=False)


@pytest.mark.asyncio
async def test_a_payload_missing_device_information_is_a_failure(hass_stub) -> None:
    """The critical block is the one that makes a payload usable at all."""
    coordinator = _coordinator(hass_stub)
    coordinator.data = None
    coordinator.api.get_data.return_value = {"monitoring_status": {}}

    with (
        patch.object(coordinator, "update_health") as health,
        pytest.raises(UpdateFailed, match="Critical data missing"),
    ):
        await coordinator._async_update_data()

    health.assert_called_once_with(None, failed=True, cold_start=True)


# ---------------------------------------------------------------------------
# Repair issues — every argument is user-visible
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_auth_failure_raises_a_fixable_persistent_repair(hass_stub) -> None:
    """Auth failure must survive a restart and offer the reauth flow.

    `is_fixable=True` is what puts the *Fix* button on the card; without it the
    user is told something is wrong and given nothing to do. `is_persistent=True`
    is what stops the card vanishing on restart while the integration is still
    unauthenticated — the state in which every entity is unavailable.

    The `entry_title` placeholder is asserted because with two routers
    configured, a repair card that does not name one is not actionable.
    """
    coordinator = _coordinator(hass_stub)
    coordinator.data = None
    coordinator.api.get_data.side_effect = HuaweiAuthError("nope")

    with (
        patch(
            "custom_components.huawei_router_5g.coordinator.ir.async_create_issue"
        ) as issue,
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await coordinator._async_update_data()

    _, args, kwargs = issue.mock_calls[0]
    assert args[2] == f"{REPAIR_AUTH_FAILED}_entry-1"
    assert kwargs["is_fixable"] is True
    assert kwargs["is_persistent"] is True
    assert kwargs["translation_key"] == "auth_failed"
    assert kwargs["translation_placeholders"] == {"entry_title": "My Huawei Router"}
    assert kwargs["data"] == {"entry_id": "entry-1"}


@pytest.mark.asyncio
async def test_a_timeout_raises_a_transient_repair(hass_stub) -> None:
    """A connection timeout is the opposite case, and the flags invert.

    `is_fixable=False` because there is nothing for the user to fix in a
    dialog, and `is_persistent=False` so the card clears itself once the router
    answers again. Persisting this one would leave a permanent warning about a
    problem that resolved by itself.
    """
    coordinator = _coordinator(hass_stub)
    coordinator.data = None
    coordinator.api.get_data.side_effect = TimeoutError

    with (
        patch(
            "custom_components.huawei_router_5g.coordinator.ir.async_create_issue"
        ) as issue,
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    _, args, kwargs = issue.mock_calls[0]
    assert args[2] == f"{REPAIR_CONN_ERROR}_entry-1"
    assert kwargs["is_fixable"] is False
    assert kwargs["is_persistent"] is False
    assert kwargs["translation_key"] == "conn_error"
    assert kwargs["translation_placeholders"] == {"entry_title": "My Huawei Router"}


@pytest.mark.asyncio
async def test_a_held_failure_raises_no_repair_at_all(hass_stub) -> None:
    """Within the strike budget the user is told nothing, deliberately.

    A repair card on the first blip of a router that recovers by itself is
    noise, and noise is what makes the real ones ignored.
    """
    coordinator = _coordinator(hass_stub)
    coordinator.data = GOOD
    coordinator.api.get_data.side_effect = TimeoutError

    with patch(
        "custom_components.huawei_router_5g.coordinator.ir.async_create_issue"
    ) as issue:
        await coordinator._async_update_data()

    issue.assert_not_called()


# ---------------------------------------------------------------------------
# The pause, and the one-shot force flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_paused_poll_returns_cache_without_fetching(hass_stub) -> None:
    """Paused means paused: no round trip at all."""
    coordinator = _coordinator(hass_stub, options={"stop_polling": True})
    coordinator.data = GOOD

    assert await coordinator._async_update_data() == GOOD
    coordinator.api.get_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_force_flag_overrides_the_pause_exactly_once(hass_stub) -> None:
    """Section 13: an explicit action fetches through the pause, once.

    The flag is consumed at the top of the method before anything can
    short-circuit, so a second poll behind the same press must not fetch again.
    """
    coordinator = _coordinator(hass_stub, options={"stop_polling": True})
    coordinator.data = GOOD
    coordinator.api.get_data.return_value = GOOD
    coordinator._force_refresh_once = True

    await coordinator._async_update_data()
    assert coordinator.api.get_data.await_count == 1
    assert coordinator._force_refresh_once is False

    await coordinator._async_update_data()
    assert coordinator.api.get_data.await_count == 1


@pytest.mark.asyncio
async def test_a_first_run_fetches_even_while_paused(hass_stub) -> None:
    """With no data at all, a pause must not leave every entity unknown."""
    coordinator = _coordinator(hass_stub, options={"stop_polling": True})
    coordinator.data = None
    coordinator.api.get_data.return_value = GOOD

    await coordinator._async_update_data()

    coordinator.api.get_data.assert_awaited_once()


# ---------------------------------------------------------------------------
# The strike budget
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_fourth_consecutive_failure_stops_holding(hass_stub) -> None:
    """Three held failures, then the entities are allowed to go unavailable.

    The boundary is the whole rule. Held one poll too long and a router that
    has been off for ten minutes still shows live-looking values.
    """
    coordinator = _coordinator(hass_stub)
    coordinator.data = GOOD
    coordinator.api.get_data.side_effect = TimeoutError

    for expected in (1, 2, 3):
        assert await coordinator._async_update_data() == GOOD
        assert coordinator.consecutive_failures == expected

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.consecutive_failures == 4


@pytest.mark.asyncio
async def test_a_session_expiry_is_retried_once_before_counting(hass_stub) -> None:
    """The router drops idle sessions; one silent retry is expected.

    A retry that never happens turns every session expiry into a visible
    failure, and the expiry is routine.
    """
    coordinator = _coordinator(hass_stub)
    coordinator.data = GOOD
    coordinator.api.get_data.side_effect = [HuaweiAuthError("expired"), GOOD]

    assert await coordinator._async_update_data() == GOOD
    assert coordinator.api.get_data.await_count == 2
    assert coordinator.consecutive_failures == 0


# ---------------------------------------------------------------------------
# The health verdict failing to compute is itself a health problem
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_health_computation_is_visible_not_silent(
    hass_stub, caplog
) -> None:
    """A broken health verdict must not report as healthy at DEBUG level.

    **Found by `masked_errors_check` 2026-08-16, Class A.** The wrapper around
    `_compute_health` is correct and must stay — a verdict that crashed the
    poll it is diagnosing would be worse than no verdict. What was wrong is
    where the failure went: `_LOGGER.debug`, then a snapshot that reads
    *healthy*.

    Integration Health exists to explain an outage. If the thing that explains
    outages breaks, it reports "no problems" for ever, at a log level nobody
    runs. The first failure is now a warning, and the snapshot says the verdict
    is unavailable rather than clean.
    """
    coordinator = _coordinator(hass_stub)

    with patch.object(
        coordinator, "_compute_health", side_effect=ValueError("bad payload")
    ):
        coordinator.update_health(GOOD, failed=False, cold_start=False)

    assert "health" in caplog.text.lower()
    assert any(r.levelname == "WARNING" for r in caplog.records), (
        "a failed health computation was not raised above DEBUG"
    )
    snapshot = coordinator.health_snapshot
    assert snapshot["severity"] is not None, "a broken verdict reported as healthy"
    assert any("health" in str(i).lower() for i in snapshot["issues"]), (
        "the snapshot does not say the verdict itself is unavailable"
    )


@pytest.mark.asyncio
async def test_repeated_health_failures_warn_only_once(hass_stub, caplog) -> None:
    """One warning per session, not one per poll.

    A verdict that is broken is broken on every poll. Warning each time turns
    a real signal into log spam at the polling interval, which is how a
    warning stops being read.
    """
    coordinator = _coordinator(hass_stub)

    with patch.object(
        coordinator, "_compute_health", side_effect=ValueError("bad payload")
    ):
        for _ in range(4):
            coordinator.update_health(GOOD, failed=False, cold_start=False)

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1, f"expected one warning, got {len(warnings)}"
