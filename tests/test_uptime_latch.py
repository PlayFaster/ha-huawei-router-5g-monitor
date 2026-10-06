"""Boot-time latches: the restart boundary, drift hardening, and the guards.

Three counters, and they are not the same kind of thing. Only one of them is
a clock.

- `device_information.uptime` counts unconditionally from the last hardware
  boot. It can be asked "did you continue across that gap at wall rate?", so
  it carries the full mechanism: a measured drift rate, the shortfall test at
  startup, and the plausibility backstop on every poll.
- `traffic_statistics.CurrentConnectTime` resets on every WAN reconnect, and
  `TotalConnectTime` accumulates across reboots and **pauses whenever the
  session is down** — measured on a real reconnect, `tests/fixtures/
  huawei_reconnect_trace.json`. Legitimate downtime makes both under-run wall
  time, so a rate-based expectation would report resets that never happened.
  They carry a floor rule instead: below the stored value is a reset, at or
  above it is a continuation.

**The defect these exist to prevent was live on the development instance
while this was written.** `entry.data` held `last_system_uptime` = 61 against
a live counter of 213,412: the counter had been persisted once, one minute
after a boot nineteen days earlier, and never again. The reboot comparison is
`live < stored - UPTIME_REBOOT_MARGIN`, so it could only fire below 31
seconds — a window one poll wide, once per reboot. The router had in fact
rebooted two days before, and the sensor read three weeks.

Everything here is offline. The design and the nine decisions behind the
constants are in `.shared/info/uptime_timestamp/uptime_drift_analyzed.md`;
this project's measured departures from it are in the cross-project item.
"""

from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.huawei_router_5g.coordinator import (
    DRIFT_ACCUMULATOR_CAP,
    DRIFT_MIN_ACCUMULATED,
    MAX_DRIFT,
    MAX_PLAUSIBLE_UPTIME,
    UPTIME_WRITE_INTERVAL,
    HuaweiRouter5GDataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

_TRACE = json.loads(
    (Path(__file__).parent / "fixtures" / "huawei_reconnect_trace.json").read_text(
        encoding="utf-8"
    )
)

# The keys each latch publishes into the payload, and the keys it stores under.
_BOOT_KEYS = ("system_boot_time", "conn_start_time", "total_conn_start_time")
_COUNTER_KEYS = ("last_system_uptime", "last_conn_uptime", "last_total_conn_time")

NOW = datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC)
POLL = timedelta(minutes=3)
HUAWEI_RATE = 0.0
ZTE_RATE = 0.0434


class Router:
    """Three counters advancing as this hardware's do.

    `rate` is the fraction of every second the hardware counter loses.
    Positive is a slow counter, which the reference ZTE device does at 4.34%
    and this Huawei does not do at all — measured at 0% within quantization
    over eleven minutes. The parameter exists because the code must be
    correct for a device that does, not because this one does.

    The connection counters advance only while `connected`, which is what
    makes them unusable as clocks.
    """

    def __init__(
        self,
        rate: float = HUAWEI_RATE,
        uptime: float = 0.0,
        current: float = 0.0,
        total: float = 0.0,
    ) -> None:
        """Start all three counters, losing `rate` of every second thereafter."""
        self.rate = rate
        self.uptime = uptime
        self.current = current
        self.total = total
        self.connected = True

    def advance(self, seconds: float) -> None:
        """Advance by what this router would count over that wall interval."""
        counted = seconds * (1.0 - self.rate)
        self.uptime += counted
        if self.connected:
            self.current += counted
            self.total += counted

    def reboot(self) -> None:
        """Power cycle: the hardware counter and the session reset, the total does not."""
        self.uptime = 0.0
        self.current = 0.0

    def reconnect(self) -> None:
        """A WAN reconnect: only the current-session counter resets."""
        self.current = 0.0

    def clear_statistics(self) -> None:
        """The one event that moves the cumulative counter backwards."""
        self.total = 0.0


def _payload(router: Router) -> dict:
    """One poll's worth of router data, in the shape `get_data` returns."""
    return {
        "device_information": {"DeviceName": "B535", "uptime": str(int(router.uptime))},
        "traffic_statistics": {
            "CurrentConnectTime": str(int(router.current)),
            "TotalConnectTime": str(int(router.total)),
        },
    }


@pytest.fixture
def hass_stub():
    """A hass stub carrying the registries and store the latch path writes to."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    return hass


def _entry(**data):
    """A config entry carrying the given `entry.data` keys."""
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.title = "My Huawei Router"
    entry.data = {"mac": "dc7196112233", **data}
    entry.options = {}
    return entry


def _coordinator(hass, entry, router: Router | None = None):
    """Build a coordinator whose API returns the simulated router's payload."""
    api = MagicMock()
    if router is not None:
        api.get_data = AsyncMock(side_effect=lambda: _payload(router))
    coordinator = HuaweiRouter5GDataUpdateCoordinator(hass, entry, api)
    return coordinator


async def _poll(coordinator, now: datetime) -> dict:
    """Drive one full poll at a pinned clock."""
    with patch.object(dt_util, "now", return_value=now):
        return await coordinator._async_update_data()


async def _run(
    coordinator,
    router: Router,
    *,
    start: datetime,
    polls: int,
    interval: timedelta = POLL,
) -> datetime:
    """Poll a simulated router repeatedly and return the clock afterwards."""
    now = start
    for _ in range(polls):
        await _poll(coordinator, now)
        now += interval
        router.advance(interval.total_seconds())
    return now


def _persist(entry, coordinator) -> None:
    """Copy the anchors a poll wrote back onto the entry, as HA would."""
    updates = {}
    for latch in coordinator._latches:
        if latch.boot_time is not None:
            updates[latch.boot_key] = latch.boot_time.isoformat()
    entry.data = {**entry.data, **updates}


def _restore(coordinator, entry, stored: dict | None = None) -> None:
    """Re-seed a freshly built coordinator the way setup does.

    The anchors come from `entry.data`, which the constructor already read;
    the counters and accumulators come from the store, which is what
    `async_load_stored_uptime` does at setup.
    """
    if stored is None:
        return
    for latch in coordinator._latches:
        block = stored.get(latch.counter_key)
        if isinstance(block, dict):
            coordinator._restore_latch(latch, block)


# ---------------------------------------------------------------------------
# The defect, stated as a test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_restart_after_a_reboot_does_not_keep_the_old_timestamp(hass_stub):
    """The live failure: a reboot inside a Home Assistant gap must be detected.

    Reproduces the development instance exactly. The stored counter is 61 s,
    frozen at a latch nineteen days ago; the router has since rebooted and now
    reports 213,412 s. The running-session comparison cannot fire, because the
    live reading is not below `61 - 30`. Nothing else looked at the gap, so
    the nineteen-day-old anchor survived and the sensor read three weeks.
    """
    stale_anchor = "2026-08-20T17:31:35+00:00"
    entry = _entry(system_boot_time=stale_anchor, last_system_uptime=61)
    router = Router(uptime=213412)
    coordinator = _coordinator(hass_stub, entry, router)

    data = await _poll(coordinator, NOW)

    assert data["system_boot_time"] != dt_util.parse_datetime(stale_anchor), (
        "the stale anchor survived a gap containing a reboot"
    )


# ---------------------------------------------------------------------------
# Drift measurement — the hardware counter
# ---------------------------------------------------------------------------
#
# Rates deliberately span PLAUSIBILITY_TOLERANCE. A suite that stopped at the
# rate it measured passed a build, on the reference project, in which any
# device drifting past the tolerance re-latched on every poll — the anchor was
# not corrected for drift, so the observed ratio sat a full `rate` from the
# predicted one. This device measures 0.00%; the sweep is what makes the code
# correct for one that does not.


@pytest.mark.parametrize("rate", [0.0, ZTE_RATE, 0.08, 0.12, -0.02])
@pytest.mark.asyncio
async def test_the_measured_rate_converges_on_the_real_one(hass_stub, rate):
    """The rate is learned from consecutive polls, never from the anchor."""
    router = Router(rate=rate)
    coordinator = _coordinator(hass_stub, _entry(), router)

    await _run(coordinator, router, start=NOW, polls=40, interval=timedelta(minutes=30))

    measured = coordinator._drift_rate(coordinator._system_latch)
    assert measured is not None
    assert abs(measured - rate) < 0.005


@pytest.mark.asyncio
async def test_the_rate_is_withheld_until_enough_has_accumulated(hass_stub):
    """Below the minimum there is nothing to say, and nothing to divide by.

    The guard is evaluated before the division, which is what stops a fresh
    install dividing by a zero denominator.
    """
    router = Router(rate=ZTE_RATE)
    coordinator = _coordinator(hass_stub, _entry(), router)
    assert coordinator._drift_rate(coordinator._system_latch) is None

    await _run(coordinator, router, start=NOW, polls=3, interval=timedelta(minutes=5))

    assert coordinator._system_latch.drift_sum_wall < DRIFT_MIN_ACCUMULATED
    assert coordinator._drift_rate(coordinator._system_latch) is None


@pytest.mark.asyncio
async def test_short_and_negative_intervals_are_excluded(hass_stub):
    """Quantization dominates a short interval; a reset is not a rate."""
    router = Router(rate=ZTE_RATE)
    coordinator = _coordinator(hass_stub, _entry(), router)

    await _run(coordinator, router, start=NOW, polls=6, interval=timedelta(seconds=30))
    assert coordinator._system_latch.drift_interval_count == 0

    # A reboot is a negative advance, and must not pollute the rate. Measured
    # on its own coordinator: the interval *preceding* a reboot is a perfectly
    # ordinary one and would otherwise be counted here, hiding the point.
    rebooting = Router(rate=ZTE_RATE, uptime=86400)
    second = _coordinator(hass_stub, _entry(), rebooting)
    await _poll(second, NOW)
    second._system_latch.startup_reconciled = True
    rebooting.reboot()
    await _poll(second, NOW + timedelta(minutes=30))

    assert second._system_latch.drift_interval_count == 0


@pytest.mark.asyncio
async def test_a_runaway_sample_cannot_move_the_rate_past_the_clamp(hass_stub):
    """One bad interval cannot suppress detection or invent a false alarm."""
    coordinator = _coordinator(hass_stub, _entry())
    latch = coordinator._system_latch
    latch.drift_sum_wall = DRIFT_MIN_ACCUMULATED * 2
    latch.drift_sum_counter = 0.0

    assert coordinator._drift_rate(latch) == MAX_DRIFT

    latch.drift_sum_counter = latch.drift_sum_wall * 3
    assert coordinator._drift_rate(latch) == -MAX_DRIFT


@pytest.mark.asyncio
async def test_the_cap_lets_the_estimate_follow_a_firmware_fix(hass_stub):
    """A timer corrected in firmware must move the estimate, not be averaged away."""
    coordinator = _coordinator(hass_stub, _entry())
    latch = coordinator._system_latch
    latch.drift_sum_wall = DRIFT_ACCUMULATOR_CAP * 2
    latch.drift_sum_counter = DRIFT_ACCUMULATOR_CAP * 2 * (1 - ZTE_RATE)

    coordinator._record_drift_sample(latch, 0, NOW)
    latch.last_counter = 0
    latch.last_poll_at = NOW
    coordinator._record_drift_sample(latch, 3600, NOW + timedelta(hours=1))

    assert latch.drift_sum_wall <= DRIFT_ACCUMULATOR_CAP + 3600


# ---------------------------------------------------------------------------
# The timestamp does not move on its own
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rate", [0.0, ZTE_RATE, 0.08, 0.12, -0.02])
@pytest.mark.asyncio
async def test_a_running_router_never_moves_the_timestamp(hass_stub, rate):
    """Whatever the counter's rate, an unbroken session holds every anchor."""
    router = Router(rate=rate, uptime=3600, current=1800, total=90000)
    coordinator = _coordinator(hass_stub, _entry(), router)

    first = await _poll(coordinator, NOW)
    anchors = {key: first[key] for key in _BOOT_KEYS}
    router.advance(POLL.total_seconds())

    now = await _run(coordinator, router, start=NOW + POLL, polls=200, interval=POLL)
    last = await _poll(coordinator, now)

    assert {key: last[key] for key in _BOOT_KEYS} == anchors


@pytest.mark.asyncio
async def test_restarts_across_a_month_never_move_the_timestamp(hass_stub):
    """A month of restarts with no reboot must not move the anchor once."""
    router = Router(rate=ZTE_RATE, uptime=86400, current=3600, total=900000)
    entry = _entry()
    now = NOW
    anchor = None
    for _ in range(30):
        coordinator = _coordinator(hass_stub, entry, router)
        _restore(coordinator, entry)
        data = await _poll(coordinator, now)
        if anchor is None:
            anchor = data["system_boot_time"]
            entry.data = {**entry.data, "system_boot_time": anchor.isoformat()}
        assert data["system_boot_time"] == anchor, "a restart moved the anchor"
        _persist(entry, coordinator)
        now += timedelta(days=1)
        router.advance(86400)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_counter_drop_is_a_reboot_unconditionally(hass_stub):
    """Nothing vetoes a counter drop — no rate, no bound, no clamp."""
    router = Router(rate=ZTE_RATE, uptime=86400)
    coordinator = _coordinator(hass_stub, _entry(), router)
    now = await _run(coordinator, router, start=NOW, polls=3)
    before = coordinator._system_latch.boot_time

    router.reboot()
    await _poll(coordinator, now)

    assert coordinator._system_latch.boot_time > before


@pytest.mark.asyncio
async def test_a_reboot_inside_an_offline_gap_is_detected(hass_stub):
    """The case the running comparison cannot see, and the store answers."""
    router = Router(rate=ZTE_RATE, uptime=200000)
    entry = _entry()
    coordinator = _coordinator(hass_stub, entry, router)
    now = await _run(
        coordinator, router, start=NOW, polls=4, interval=timedelta(hours=1)
    )
    _persist(entry, coordinator)
    stale = coordinator._system_latch.boot_time

    # Home Assistant is away for two days; the router reboots during it.
    now += timedelta(days=2)
    router.reboot()
    router.advance(3600)

    restarted = _coordinator(hass_stub, entry, router)
    _restore(restarted, entry, stored=coordinator._store_record())
    await _poll(restarted, now)

    assert restarted._system_latch.boot_time > stale


@pytest.mark.asyncio
async def test_a_clean_restart_preserves_the_timestamp_exactly(hass_stub):
    """No reboot in the gap means the anchor survives it untouched."""
    router = Router(rate=ZTE_RATE, uptime=200000)
    entry = _entry()
    coordinator = _coordinator(hass_stub, entry, router)
    now = await _run(
        coordinator, router, start=NOW, polls=4, interval=timedelta(hours=1)
    )
    _persist(entry, coordinator)
    anchor = coordinator._system_latch.boot_time

    now += timedelta(hours=6)
    router.advance(6 * 3600)

    restarted = _coordinator(hass_stub, entry, router)
    _restore(restarted, entry, stored=coordinator._store_record())
    await _poll(restarted, now)

    assert restarted._system_latch.boot_time == anchor


@pytest.mark.asyncio
async def test_the_plausibility_backstop_catches_a_stale_anchor(hass_stub):
    """An anchor that has *become* wrong is caught without a restart."""
    router = Router(rate=ZTE_RATE, uptime=86400)
    coordinator = _coordinator(hass_stub, _entry(), router)
    await _run(coordinator, router, start=NOW, polls=40, interval=timedelta(minutes=30))
    assert coordinator._drift_rate(coordinator._system_latch) is not None

    # Corrupt the anchor by hand, as a missed reboot would.
    coordinator._system_latch.boot_time = NOW - timedelta(days=30)
    await _poll(coordinator, NOW + timedelta(days=1))

    assert coordinator._system_latch.boot_time > NOW - timedelta(days=30)


@pytest.mark.asyncio
async def test_a_backward_candidate_is_never_treated_as_a_reboot(hass_stub, caplog):
    """A reboot moves the start forward; a backward move is something else."""
    router = Router(rate=ZTE_RATE, uptime=86400)
    coordinator = _coordinator(hass_stub, _entry(), router)
    await _run(coordinator, router, start=NOW, polls=40, interval=timedelta(minutes=30))

    # The anchor has to be implausible *and* later than the instant the
    # counter implies. That means a counter reading longer than the elapsed
    # time since the anchor — the shape a counter running fast would produce,
    # which has never been measured but is not ruled out.
    now = NOW + timedelta(days=1)
    latch = coordinator._system_latch
    latch.boot_time = now - timedelta(seconds=router.uptime * 0.8)
    before = latch.boot_time
    caplog.set_level(logging.WARNING)
    await _poll(coordinator, now)

    assert latch.boot_time == before
    assert "candidate instant is earlier" in caplog.text


# ---------------------------------------------------------------------------
# Cold start
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cold_start_retains_a_healthy_anchor(hass_stub):
    """Nothing learned and nothing stored, but the anchor is credible."""
    router = Router(uptime=7200)
    entry = _entry(system_boot_time=(NOW - timedelta(hours=2)).isoformat())
    coordinator = _coordinator(hass_stub, entry, router)
    _restore(coordinator, entry)
    anchor = coordinator._system_latch.boot_time

    await _poll(coordinator, NOW)

    assert coordinator._system_latch.boot_time == anchor


@pytest.mark.asyncio
async def test_cold_start_relatches_a_stale_anchor(hass_stub):
    """The observed failure: an anchor far older than the counter allows."""
    router = Router(uptime=7200)
    entry = _entry(system_boot_time=(NOW - timedelta(days=20)).isoformat())
    coordinator = _coordinator(hass_stub, entry, router)
    _restore(coordinator, entry)

    await _poll(coordinator, NOW)

    assert coordinator._system_latch.boot_time == NOW - timedelta(hours=2)


@pytest.mark.asyncio
async def test_a_fresh_install_latches_unconditionally(hass_stub):
    """No anchor at all is not a judgement call."""
    router = Router(uptime=3600)
    coordinator = _coordinator(hass_stub, _entry(), router)

    await _poll(coordinator, NOW)

    assert coordinator._system_latch.boot_time == NOW - timedelta(hours=1)


@pytest.mark.asyncio
async def test_an_anchor_with_no_elapsed_time_is_implausible(hass_stub):
    """An anchor dated at or after now cannot be judged against a counter."""
    coordinator = _coordinator(hass_stub, _entry())
    latch = coordinator._system_latch

    assert coordinator._cold_start_implausible(latch, 3600, NOW) is True

    latch.boot_time = NOW
    assert coordinator._cold_start_implausible(latch, 3600, NOW) is True


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unset_clock_defers_rather_than_latching(hass_stub, caplog):
    """A host with no battery-backed clock must not anchor decades adrift."""
    router = Router(uptime=3600)
    coordinator = _coordinator(hass_stub, _entry(), router)

    caplog.set_level(logging.DEBUG)
    await _poll(coordinator, datetime(1970, 1, 2, tzinfo=UTC))

    assert coordinator._system_latch.boot_time is None
    assert "deferring" in caplog.text


@pytest.mark.asyncio
async def test_an_implausible_counter_is_rejected(hass_stub, caplog):
    """A counter beyond ten years is rejected rather than believed."""
    router = Router(uptime=MAX_PLAUSIBLE_UPTIME + 1)
    coordinator = _coordinator(hass_stub, _entry(), router)

    caplog.set_level(logging.WARNING)
    await _poll(coordinator, NOW)

    assert coordinator._system_latch.boot_time is None
    assert "implausible" in caplog.text


@pytest.mark.parametrize("value", ["2026-08-01T10:00:00", "not a datetime", ""])
@pytest.mark.asyncio
async def test_a_naive_or_unparsable_anchor_is_treated_as_absent(hass_stub, value):
    """Subtracting naive from aware raises; absent routes to a clean latch."""
    entry = _entry(system_boot_time=value)
    coordinator = _coordinator(hass_stub, entry, Router(uptime=3600))
    _restore(coordinator, entry)

    assert coordinator._system_latch.boot_time is None

    await _poll(coordinator, NOW)
    assert coordinator._system_latch.boot_time == NOW - timedelta(hours=1)


@pytest.mark.asyncio
async def test_a_small_backward_step_is_logged_not_absorbed(hass_stub, caplog):
    """Nothing establishes that these counters never step back. Say when they do."""
    router = Router(uptime=3600)
    coordinator = _coordinator(hass_stub, _entry(), router)
    await _poll(coordinator, NOW)
    coordinator._system_latch.startup_reconciled = True

    router.uptime = 3590
    caplog.set_level(logging.INFO)
    await _poll(coordinator, NOW + POLL)

    assert "stepped back" in caplog.text


@pytest.mark.asyncio
async def test_a_move_without_a_counter_drop_is_flagged(hass_stub, caplog):
    """The signature of this whole bug class, made greppable."""
    router = Router(rate=ZTE_RATE, uptime=86400)
    coordinator = _coordinator(hass_stub, _entry(), router)
    await _run(coordinator, router, start=NOW, polls=40, interval=timedelta(minutes=30))

    coordinator._system_latch.boot_time = NOW - timedelta(days=30)
    caplog.set_level(logging.WARNING)
    await _poll(coordinator, NOW + timedelta(days=1))

    assert "without a counter drop" in caplog.text


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_store_record_carries_every_latch(hass_stub):
    """Three blocks, each with the fields the sibling projects use."""
    router = Router(uptime=3600, current=1800, total=90000)
    coordinator = _coordinator(hass_stub, _entry(), router)
    await _poll(coordinator, NOW)

    record = coordinator._store_record()

    assert set(record) == set(_COUNTER_KEYS)
    for block in record.values():
        assert set(block) >= {
            "last_uptime",
            "written_at",
            "sum_wall",
            "sum_counter",
            "interval_count",
        }


@pytest.mark.asyncio
async def test_the_counter_is_flushed_on_the_interval_not_every_poll(hass_stub):
    """The write cadence is what bounds how stale the stored counter can be.

    It is also the whole fix: the counter used to reach disk only at a latch,
    which is why one instance held 61 s for nineteen days.
    """
    router = Router(uptime=3600)
    coordinator = _coordinator(hass_stub, _entry(), router)
    coordinator._store = MagicMock()

    await _poll(coordinator, NOW)
    first = coordinator._store.async_delay_save.call_count

    await _poll(coordinator, NOW + timedelta(minutes=1))
    assert coordinator._store.async_delay_save.call_count == first

    await _poll(coordinator, NOW + UPTIME_WRITE_INTERVAL + timedelta(minutes=1))
    assert coordinator._store.async_delay_save.call_count > first


@pytest.mark.asyncio
async def test_a_failing_store_load_never_reaches_setup(hass_stub):
    """No storage fault may fail entry setup; the cold-start path works without it."""
    coordinator = _coordinator(hass_stub, _entry())

    with patch("custom_components.huawei_router_5g.coordinator.Store") as store_class:
        store_class.return_value.async_load = AsyncMock(
            side_effect=RuntimeError("disk on fire")
        )
        await coordinator.async_load_stored_uptime()

    assert coordinator._system_latch.stored_counter is None


@pytest.mark.parametrize("payload", [None, [], "nonsense", {"last_system_uptime": 5}])
@pytest.mark.asyncio
async def test_an_unusable_store_record_falls_back_cleanly(hass_stub, payload):
    """Anything that is not a dict of blocks means nothing was learned."""
    coordinator = _coordinator(hass_stub, _entry())

    with patch("custom_components.huawei_router_5g.coordinator.Store") as store_class:
        store_class.return_value.async_load = AsyncMock(return_value=payload)
        await coordinator.async_load_stored_uptime()

    assert coordinator._system_latch.stored_counter is None


@pytest.mark.asyncio
async def test_a_full_store_record_is_read_back(hass_stub):
    """Every field round-trips, including the accumulators."""
    coordinator = _coordinator(hass_stub, _entry())
    record = {
        "last_system_uptime": {
            "last_uptime": 4321,
            "written_at": "2026-09-01T10:00:00+00:00",
            "sum_wall": 7200.0,
            "sum_counter": 6888.0,
            "interval_count": 9,
            "rate_min": 0.041,
            "rate_max": 0.047,
        }
    }

    with patch("custom_components.huawei_router_5g.coordinator.Store") as store_class:
        store_class.return_value.async_load = AsyncMock(return_value=record)
        await coordinator.async_load_stored_uptime()

    latch = coordinator._system_latch
    assert latch.stored_counter == 4321
    assert latch.stored_written_at == datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    assert latch.drift_interval_count == 9
    assert latch.drift_rate_min == 0.041
    assert latch.drift_rate_max == 0.047


@pytest.mark.parametrize("written", ["2026-09-01T10:00:00", "not a datetime", ""])
@pytest.mark.asyncio
async def test_a_naive_or_unparsable_written_at_is_treated_as_absent(
    hass_stub, written
):
    """`written_at` carries the same aware/naive hazard as the anchor.

    Without the record's date the gap cannot be measured, so the floor
    comparison applies instead of the shortfall test.
    """
    coordinator = _coordinator(hass_stub, _entry())
    record = {"last_system_uptime": {"last_uptime": 100, "written_at": written}}

    with patch("custom_components.huawei_router_5g.coordinator.Store") as store_class:
        store_class.return_value.async_load = AsyncMock(return_value=record)
        await coordinator.async_load_stored_uptime()

    assert coordinator._system_latch.stored_written_at is None


@pytest.mark.asyncio
async def test_the_store_is_keyed_to_the_entry(hass_stub):
    """Two routers must not share one record."""
    coordinator = _coordinator(hass_stub, _entry())

    with patch("custom_components.huawei_router_5g.coordinator.Store") as store_class:
        store_class.return_value.async_load = AsyncMock(return_value=None)
        await coordinator.async_load_stored_uptime()

    assert "entry-1" in store_class.call_args[0][2]


@pytest.mark.asyncio
async def test_a_store_record_dated_ahead_of_now_falls_back(hass_stub, caplog):
    """A write dated in the future says nothing about the gap."""
    router = Router(uptime=7200)
    entry = _entry(system_boot_time=(NOW - timedelta(hours=2)).isoformat())
    coordinator = _coordinator(hass_stub, entry, router)
    _restore(coordinator, entry)
    latch = coordinator._system_latch
    latch.stored_counter = 100
    latch.stored_written_at = NOW + timedelta(days=1)

    caplog.set_level(logging.WARNING)
    await _poll(coordinator, NOW)

    assert "dated ahead of now" in caplog.text
    assert latch.boot_time == NOW - timedelta(hours=2)


@pytest.mark.asyncio
async def test_a_store_record_dated_ahead_still_relatches_a_stale_anchor(hass_stub):
    """Falling back is not the same as giving up."""
    router = Router(uptime=7200)
    entry = _entry(system_boot_time=(NOW - timedelta(days=20)).isoformat())
    coordinator = _coordinator(hass_stub, entry, router)
    _restore(coordinator, entry)
    latch = coordinator._system_latch
    latch.stored_counter = 100
    latch.stored_written_at = NOW + timedelta(days=1)

    await _poll(coordinator, NOW)

    assert latch.boot_time == NOW - timedelta(hours=2)


@pytest.mark.asyncio
async def test_a_latch_drops_the_legacy_counter_keys_from_entry_data(hass_stub):
    """The frozen copy is removed, not merely ignored."""
    entry = _entry(last_system_uptime=61, last_conn_uptime=1102)
    coordinator = _coordinator(hass_stub, entry, Router(uptime=3600))

    await _poll(coordinator, NOW)

    written = hass_stub.config_entries.async_update_entry.call_args.kwargs["data"]
    assert "last_system_uptime" not in written
    assert "last_conn_uptime" not in written


# ---------------------------------------------------------------------------
# The connection counters — the floor rule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_reconnect_relatches_only_the_session_counter(hass_stub):
    """Replays the captured reconnect: one anchor moves, two do not.

    `tests/fixtures/huawei_reconnect_trace.json`, measured 2026-09-08. The
    session counter fell 43,864 to 9; the cumulative counter did not reset and
    the hardware counter was unaffected.
    """
    samples = _TRACE["samples"]
    router = Router(
        uptime=samples[0]["uptime"],
        current=samples[0]["current"],
        total=samples[0]["total"],
    )
    coordinator = _coordinator(hass_stub, _entry(), router)
    base = datetime.fromtimestamp(samples[0]["wall"], UTC)
    await _poll(coordinator, base)
    for latch in coordinator._latches:
        latch.startup_reconciled = True
    before = {latch.counter_key: latch.boot_time for latch in coordinator._latches}

    for sample in samples[1:]:
        router.uptime = sample["uptime"]
        router.current = sample["current"]
        router.total = sample["total"]
        await _poll(coordinator, datetime.fromtimestamp(sample["wall"], UTC))

    assert coordinator._conn_latch.boot_time > before["last_conn_uptime"]
    assert coordinator._total_latch.boot_time == before["last_total_conn_time"]
    assert coordinator._system_latch.boot_time == before["last_system_uptime"]


@pytest.mark.asyncio
async def test_the_cumulative_counter_survives_a_long_offline_gap(hass_stub):
    """Downtime under-runs wall time legitimately, and must not re-latch.

    The measured device has lost 3.8 hours to outages since April. A shortfall
    test would read a long gap containing downtime as a statistics clear; the
    floor rule cannot, because the counter never went backwards.
    """
    router = Router(uptime=200000, current=3600, total=12000000)
    entry = _entry()
    coordinator = _coordinator(hass_stub, entry, router)
    await _poll(coordinator, NOW)
    _persist(entry, coordinator)
    anchor = coordinator._total_latch.boot_time

    # A week away, with two days of it disconnected: the cumulative counter
    # advances by five days, not seven.
    router.uptime += 7 * 86400
    router.total += 5 * 86400
    restarted = _coordinator(hass_stub, entry, router)
    _restore(restarted, entry, stored=coordinator._store_record())
    await _poll(restarted, NOW + timedelta(days=7))

    assert restarted._total_latch.boot_time == anchor


@pytest.mark.asyncio
async def test_a_statistics_clear_is_detected_by_the_floor_rule(hass_stub):
    """The one event that moves the cumulative counter backwards."""
    router = Router(uptime=200000, total=12000000)
    entry = _entry()
    coordinator = _coordinator(hass_stub, entry, router)
    await _poll(coordinator, NOW)
    _persist(entry, coordinator)
    anchor = coordinator._total_latch.boot_time

    router.clear_statistics()
    router.advance(600)
    restarted = _coordinator(hass_stub, entry, router)
    _restore(restarted, entry, stored=coordinator._store_record())
    await _poll(restarted, NOW + timedelta(hours=1))

    assert restarted._total_latch.boot_time > anchor


@pytest.mark.asyncio
async def test_the_cumulative_counter_measures_no_drift_rate(hass_stub):
    """A counter that pauses cannot be a clock, so no rate is claimed for it."""
    router = Router(rate=ZTE_RATE, uptime=3600, total=90000)
    coordinator = _coordinator(hass_stub, _entry(), router)

    await _run(coordinator, router, start=NOW, polls=40, interval=timedelta(minutes=30))

    assert coordinator._drift_rate(coordinator._system_latch) is not None
    assert coordinator._drift_rate(coordinator._total_latch) is None
    assert coordinator._total_latch.drift_interval_count == 0


@pytest.mark.asyncio
async def test_the_cumulative_anchor_is_not_judged_by_plausibility(hass_stub):
    """Its ratio falls with every outage, and that is not a fault.

    The displayed instant is `now - cumulative connected seconds`, which is not
    a real event: it moves later by exactly the accumulated downtime. A
    two-sided plausibility check would eventually re-latch a correct anchor.
    """
    router = Router(uptime=3600, total=90000)
    coordinator = _coordinator(hass_stub, _entry(), router)
    await _run(coordinator, router, start=NOW, polls=40, interval=timedelta(minutes=30))
    anchor = coordinator._total_latch.boot_time

    # Six months of the counter advancing at half wall rate: heavy downtime,
    # no reset.
    now = NOW + timedelta(days=180)
    router.uptime += 180 * 86400
    router.total += 90 * 86400
    await _poll(coordinator, now)

    assert coordinator._total_latch.boot_time == anchor


@pytest.mark.asyncio
async def test_a_cumulative_anchor_ahead_of_the_counter_is_still_caught(hass_stub):
    """One-sided, not absent: the counter cannot exceed the elapsed time."""
    coordinator = _coordinator(hass_stub, _entry())
    latch = coordinator._total_latch
    latch.boot_time = NOW - timedelta(hours=1)

    assert coordinator._cold_start_implausible(latch, 7200, NOW) is True
    assert coordinator._cold_start_implausible(latch, 60, NOW) is False


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_drift_picture_is_published(hass_stub):
    """Every constant here was set from one device; this is how a report carries a rate."""
    router = Router(rate=ZTE_RATE, uptime=3600)
    coordinator = _coordinator(hass_stub, _entry(), router)
    await _run(coordinator, router, start=NOW, polls=40, interval=timedelta(minutes=30))

    picture = coordinator.uptime_diagnostics

    assert picture["drift_rate_pct"] == pytest.approx(ZTE_RATE * 100, abs=0.5)
    assert picture["drift_intervals"] > 0
    assert picture["drift_deficit_seconds"] > 0


@pytest.mark.asyncio
async def test_the_drift_picture_is_empty_before_measurement(hass_stub):
    """Nothing measured must read as nothing measured, not as zero drift."""
    picture = _coordinator(hass_stub, _entry()).uptime_diagnostics

    assert picture["drift_rate_pct"] is None
    assert picture["drift_rate_min_pct"] is None
    assert picture["drift_rate_max_pct"] is None
    assert picture["drift_intervals"] == 0


@pytest.mark.asyncio
async def test_every_latch_reports_its_own_state(hass_stub):
    """The diagnostics download carries all three, and says which one pauses."""
    router = Router(uptime=3600, current=1800, total=90000)
    coordinator = _coordinator(hass_stub, _entry(), router)
    await _poll(coordinator, NOW)

    state = coordinator.uptime_state

    assert set(state["latches"]) == set(_COUNTER_KEYS)
    assert state["latches"]["last_total_conn_time"]["pauses"] is True
    assert state["latches"]["last_system_uptime"]["pauses"] is False
    assert state["latches"]["last_system_uptime"]["live_counter"] == 3600


@pytest.mark.asyncio
async def test_the_runtime_comparison_needs_a_previous_reading(hass_stub):
    """Reconciled but with nothing seen yet is a real state, and it must wait.

    It arises when the startup path returns without recording a reading — a
    guard rejected it, or the store answered the question before any counter
    was kept. Comparing against `None` would raise; there is simply nothing
    to compare yet.
    """
    coordinator = _coordinator(hass_stub, _entry())
    latch = coordinator._system_latch
    latch.startup_reconciled = True

    coordinator._apply_runtime_uptime(latch, 3600, NOW, {})

    assert latch.boot_time is None


@pytest.mark.asyncio
async def test_an_anchor_at_or_after_now_is_left_to_the_startup_path(hass_stub):
    """A ratio needs elapsed time in the denominator.

    An anchor dated at or after `now` yields none, so the backstop declines to
    judge rather than dividing. The cold-start comparison already rejects such
    an anchor, which is where it gets corrected.
    """
    router = Router(rate=ZTE_RATE, uptime=3600)
    coordinator = _coordinator(hass_stub, _entry(), router)
    await _run(coordinator, router, start=NOW, polls=40, interval=timedelta(minutes=30))
    latch = coordinator._system_latch

    latch.boot_time = NOW + timedelta(days=1)
    coordinator._check_anchor_plausible(latch, 3600, NOW, {})

    assert latch.boot_time == NOW + timedelta(days=1)


@pytest.mark.asyncio
async def test_a_store_block_without_a_counter_restores_the_rest(hass_stub):
    """The fields are additive, so a missing one means "not learned yet".

    A block written before a field existed must not discard the fields that
    were written, and must not be mistaken for a stored counter of zero.
    """
    coordinator = _coordinator(hass_stub, _entry())
    latch = coordinator._system_latch

    coordinator._restore_latch(latch, {"sum_wall": 7200.0, "sum_counter": 6888.0})

    assert latch.stored_counter is None
    assert latch.drift_sum_wall == 7200.0


@pytest.mark.asyncio
async def test_no_rate_is_derived_for_a_pausing_counter_even_if_one_accumulated(
    hass_stub,
):
    """The refusal is checked twice, and each check has to hold on its own.

    `_record_drift_sample` declines to accumulate for a pausing counter, and
    `_drift_rate` declines to divide what it finds. Either alone makes the
    other invisible to a test that only ever polls — the accumulators are
    empty, so the rate is `None` for the wrong reason. Populated by hand, so
    the second guard is the one under test.
    """
    coordinator = _coordinator(hass_stub, _entry())
    latch = coordinator._total_latch
    latch.drift_sum_wall = DRIFT_MIN_ACCUMULATED * 2
    latch.drift_sum_counter = latch.drift_sum_wall * 0.9

    assert coordinator._drift_rate(latch) is None


@pytest.mark.asyncio
async def test_a_shortfall_inside_the_margin_is_not_a_reboot(hass_stub):
    """The margin absorbs rate-estimate error, and must not be a tripwire.

    A gap the counter crossed slightly slower than predicted is ordinary: the
    rate is an estimate and the error it carries scales with the gap. Without
    the margin every restart after a long absence re-latches, which is the
    failure mode this design replaced rather than a fix for it.
    """
    router = Router(uptime=200000)
    entry = _entry()
    coordinator = _coordinator(hass_stub, entry, router)
    await _poll(coordinator, NOW)
    _persist(entry, coordinator)
    anchor = coordinator._system_latch.boot_time

    # Six hours away. The counter advances by all but 400 s of it — inside the
    # 2% margin (432 s) and far outside the sub-second noise a test that
    # advances the counter exactly would exercise.
    gap = timedelta(hours=6)
    router.uptime += gap.total_seconds() - 400

    restarted = _coordinator(hass_stub, entry, router)
    _restore(restarted, entry, stored=coordinator._store_record())
    await _poll(restarted, NOW + gap)

    assert restarted._system_latch.boot_time == anchor


@pytest.mark.asyncio
async def test_a_short_gap_is_covered_by_the_margin_floor(hass_stub):
    """On a short gap the proportional term is too small to absorb anything.

    Ten minutes away puts 2% at twelve seconds, which poll latency alone can
    exceed. The floor is what covers quantization and the interval between
    the last write and the actual stop; without it a brief restart re-latches
    on nothing.
    """
    router = Router(uptime=200000)
    entry = _entry()
    coordinator = _coordinator(hass_stub, entry, router)
    await _poll(coordinator, NOW)
    _persist(entry, coordinator)
    anchor = coordinator._system_latch.boot_time

    gap = timedelta(minutes=10)
    # Short by 100 s: inside the 300 s floor, far outside the 12 s the
    # proportional term would allow on its own.
    router.uptime += gap.total_seconds() - 100

    restarted = _coordinator(hass_stub, entry, router)
    _restore(restarted, entry, stored=coordinator._store_record())
    await _poll(restarted, NOW + gap)

    assert restarted._system_latch.boot_time == anchor
