"""Tests for the data-usage projection and the §T-4 value helpers.

The projection is the one entity here that is **computed rather than read**, so
it is the one where a wrong answer looks entirely plausible. These tests are
therefore about arithmetic and about the edges, not about plumbing.

Two of them exist because `zte_router_5g` got the same things wrong first:
`test_a_disabled_cycle_is_recognised_in_every_spelling` (its guard tested
`== "off"` exactly, so `"0"` read as enabled) and
`test_projection_has_no_state_class` (a numeric sensor with no state class
otherwise reads as an oversight rather than a decision).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.huawei_router_5g.const import PROJECTION_CREDIBILITY_DAYS
from custom_components.huawei_router_5g.helpers import (
    cycle_bounds,
    project_cycle_usage,
)
from custom_components.huawei_router_5g.sensor import (
    SENSOR_TYPES,
    _antenna,
    _compute_projection,
    _current_apn_profile,
    _identifier,
    _month_used_bytes,
    _projected_bytes,
)

TZ = ZoneInfo("Europe/Dublin")
GB = 1024**3


def _data(**over: Any) -> dict[str, Any]:
    """Build a payload shaped like the live router's, with the plan enabled.

    `block__Field=value` overrides one field; `block=value` replaces the block.
    """
    base: dict[str, Any] = {
        "start_date": {
            "StartDay": "1",
            "SetMonthData": "1",
            "trafficmaxlimit": "2147483648000",
            "MonthThreshold": "80",
        },
        "month_statistics": {
            "CurrentMonthDownload": str(100 * GB),
            "CurrentMonthUpload": str(20 * GB),
        },
    }
    for key, value in over.items():
        block, _, field = key.partition("__")
        if field:
            base.setdefault(block, {})[field] = value
        else:
            base[block] = value
    return base


# ---------------------------------------------------------------------------
# project_cycle_usage — the arithmetic
# ---------------------------------------------------------------------------


def test_the_denominator_is_floored_at_one_day() -> None:
    """Seconds into a cycle, the projection must stay bounded.

    The naive `used / elapsed * length` divides by a number approaching zero,
    so half a gigabyte one second after a reset projects to over a million.
    """
    projected = project_cycle_usage(
        used=0.5 * GB,
        elapsed_days=1.0 / 86400.0,  # one second
        cycle_length_days=30,
        prior_rate=None,
        credibility_days=PROJECTION_CREDIBILITY_DAYS,
    )
    # Floored at one day, the rate is 0.5 GB/day over ~30 remaining days.
    assert projected == pytest.approx(0.5 * GB + 30 * 0.5 * GB, rel=0.01)


def test_a_prior_rate_moves_only_the_unobserved_remainder() -> None:
    """Observed bytes are a meter reading and must not be shrunk toward a prior.

    At day 20 of 30 most of the figure is measurement, so the prior can only
    touch the 10 days not yet seen.
    """
    used = 200.0 * GB
    blended = project_cycle_usage(
        used=used,
        elapsed_days=20.0,
        cycle_length_days=30,
        prior_rate=1.0 * GB,  # a much lower prior
        credibility_days=PROJECTION_CREDIBILITY_DAYS,
    )
    # Whatever the prior says, the observed 200 GB survives intact.
    assert blended > used
    run_rate_only = project_cycle_usage(
        used=used,
        elapsed_days=20.0,
        cycle_length_days=30,
        prior_rate=None,
        credibility_days=PROJECTION_CREDIBILITY_DAYS,
    )
    # ...and by day 20 the prior's influence is small, not dominant.
    assert blended == pytest.approx(run_rate_only, rel=0.05)


def test_the_projection_never_falls_below_what_is_already_used() -> None:
    """A forecast lower than the meter would be nonsense."""
    for elapsed in (0.0, 1.0, 15.0, 29.0, 30.0, 45.0):
        assert (
            project_cycle_usage(
                used=100.0 * GB,
                elapsed_days=elapsed,
                cycle_length_days=30,
                prior_rate=None,
                credibility_days=PROJECTION_CREDIBILITY_DAYS,
            )
            >= 100.0 * GB
        )


def test_a_cycle_past_its_end_projects_no_further() -> None:
    """Past the cycle length the remainder is zero, not negative."""
    assert project_cycle_usage(
        used=100.0 * GB,
        elapsed_days=40.0,
        cycle_length_days=30,
        prior_rate=None,
        credibility_days=PROJECTION_CREDIBILITY_DAYS,
    ) == pytest.approx(100.0 * GB)


# ---------------------------------------------------------------------------
# cycle_bounds
# ---------------------------------------------------------------------------


def test_the_cycle_in_flight_began_last_month_before_the_start_day() -> None:
    """On the 5th with a start day of 20, the cycle began on the 20th prior."""
    start, end, length = cycle_bounds(20, datetime(2026, 8, 5, 12, 0, tzinfo=TZ))
    assert (start.year, start.month, start.day) == (2026, 7, 20)
    assert (end.year, end.month, end.day) == (2026, 8, 20)
    assert length == 31


def test_a_start_day_of_31_is_clamped_to_the_month_length() -> None:
    """February has no 31st, and skipping would merge two cycles into one."""
    start, _end, _length = cycle_bounds(31, datetime(2026, 2, 15, 12, 0, tzinfo=TZ))
    assert (start.month, start.day) == (1, 31)
    start, _end, _length = cycle_bounds(31, datetime(2026, 3, 1, 12, 0, tzinfo=TZ))
    assert (start.month, start.day) == (2, 28)


def test_a_december_cycle_rolls_into_january() -> None:
    """The year boundary is the case an off-by-one hides in."""
    start, end, _length = cycle_bounds(1, datetime(2026, 12, 15, 12, 0, tzinfo=TZ))
    assert (start.year, start.month) == (2026, 12)
    assert (end.year, end.month) == (2027, 1)


def test_length_is_calendar_days_not_divided_seconds() -> None:
    """A cycle spanning a DST change is still 31 days, not 30.96."""
    _start, _end, length = cycle_bounds(1, datetime(2026, 3, 15, 12, 0, tzinfo=TZ))
    assert length == 31


# ---------------------------------------------------------------------------
# _projection — the edges
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spelling", ["0", "off", "OFF", "Off", "false", ""])
def test_a_disabled_cycle_is_recognised_in_every_spelling(spelling: str) -> None:
    """Reject a disabled cycle however the router spells it.

    **The ZTE defect, ported as a test rather than as a bug.**

    ZTE's guard tested `== "off"` exactly, so `"0"` and `"OFF"` read as
    *enabled* and it projected against a cycle the router was not keeping.
    Huawei reports `SetMonthData` as `"0"`/`"1"`, but casing is guaranteed
    nowhere in this API.
    """
    assert _compute_projection(_data(start_date__SetMonthData=spelling)) is None
    assert _projected_bytes(_data(start_date__SetMonthData=spelling)) is None


def test_an_enabled_cycle_projects() -> None:
    """The positive case, so the test above cannot pass by always returning None."""
    result = _compute_projection(_data())
    assert result is not None
    assert result.projected_bytes >= result.bytes_used


@pytest.mark.parametrize("bad", ["0", "32", "", "not-a-day", None])
def test_an_impossible_start_day_projects_nothing(bad: str | None) -> None:
    """Reject a start day outside 1 to 31 - it cannot describe a real cycle."""
    assert _compute_projection(_data(start_date__StartDay=bad)) is None


def test_missing_counters_project_nothing() -> None:
    """No usage figure means no projection, rather than a projection of zero."""
    assert _compute_projection(_data(month_statistics={})) is None


def test_confidence_rises_with_elapsed_time() -> None:
    """The attribute is how a user judges an early-cycle figure."""
    from custom_components.huawei_router_5g.sensor import _Projection

    def _at(weight: float) -> str:
        return _Projection(
            bytes_used=0,
            projected_bytes=0,
            cycle_start=datetime(2026, 8, 1, tzinfo=TZ),
            cycle_length_days=31,
            elapsed_days=0.0,
            weight=weight,
            basis="run_rate_only",
        ).confidence

    assert _at(0.1) == "low"
    assert _at(0.5) == "medium"
    assert _at(0.9) == "high"


def test_month_used_sums_both_directions() -> None:
    """Download alone would understate a heavy uploader's cycle."""
    assert _month_used_bytes(_data()) == 120 * GB
    assert _month_used_bytes(_data(month_statistics={"CurrentMonthUpload": "5"})) == 5
    assert _month_used_bytes({"month_statistics": {}}) is None


# ---------------------------------------------------------------------------
# The §T-4 value helpers
# ---------------------------------------------------------------------------


def test_identifiers_are_returned_verbatim_as_strings() -> None:
    """`01` must not become `1`, and a 15-digit IMEI must not go scientific."""
    data = {"device_information": {"ImeiSvn": "01", "Imei": "860123456789012"}}
    assert _identifier(data, "ImeiSvn") == "01"
    assert _identifier(data, "Imei") == "860123456789012"
    assert _identifier({"device_information": {"Imei": ""}}, "Imei") is None
    assert _identifier(None, "Imei") is None


@pytest.mark.parametrize(
    ("code", "expected"),
    [("0", "Internal"), ("1", "External"), ("2", "2"), ("", None)],
)
def test_antenna_codes_decode_and_unknown_ones_pass_through(
    code: str, expected: str | None
) -> None:
    """An unmapped code shows as itself rather than as a wrong word.

    `0` and `1` were confirmed by controlled change against a live B535 on
    2026-08-15. `Mix` needs no code of its own — it is the two per-antenna
    fields disagreeing.
    """
    assert (
        _antenna({"antenna_type": {"antenna1type": code}}, "antenna1type") == expected
    )


def test_the_current_apn_is_matched_on_index_not_position() -> None:
    """The router returned its profiles ordered 1, 3, 2.

    Indexing the list would name the wrong APN — which is a wrong answer that
    looks entirely right.
    """
    data = {
        "dial_up_profiles": {
            "CurrentProfile": "3",
            "Profiles": {
                "Profile": [
                    {"Index": "1", "Name": "First", "ApnName": "one.example"},
                    {"Index": "3", "Name": "Third", "ApnName": "three.example"},
                    {"Index": "2", "Name": "Second", "ApnName": "two.example"},
                ]
            },
        }
    }
    assert (_current_apn_profile(data) or {})["ApnName"] == "three.example"


def test_a_single_apn_profile_is_accepted_as_a_dict() -> None:
    """Accept a bare dict, which this API returns instead of a one-element list."""
    data = {
        "dial_up_profiles": {
            "CurrentProfile": "1",
            "Profiles": {"Profile": {"Index": "1", "ApnName": "only.example"}},
        }
    }
    assert (_current_apn_profile(data) or {})["ApnName"] == "only.example"


def test_an_unmatched_current_profile_yields_nothing() -> None:
    """Better no APN than the wrong one."""
    data = {
        "dial_up_profiles": {
            "CurrentProfile": "9",
            "Profiles": {"Profile": [{"Index": "1", "ApnName": "one.example"}]},
        }
    }
    assert _current_apn_profile(data) is None
    assert _current_apn_profile({"dial_up_profiles": {}}) is None
    assert _current_apn_profile(None) is None


# ---------------------------------------------------------------------------
# The state-class guard
# ---------------------------------------------------------------------------


def test_projection_has_no_state_class() -> None:
    """Ported from ZTE, and the reason is worth restating.

    The projection is an **estimate**, and the usage it derives from is already
    in long-term statistics via the month total. Recording the forecast as well
    stores a second series that is a re-derivation of the first and that changes
    retroactively as the cycle fills.

    Without this test, the omission reads as an oversight rather than a
    decision, and the obvious "fix" is to add one.
    """
    projection = next(d for d in SENSOR_TYPES if d.key == "projected_usage")
    assert projection.state_class is None


# ---------------------------------------------------------------------------
# The `confidence` attribute — documented since the sensor shipped, and until
# now never actually published
# ---------------------------------------------------------------------------


def _projection_sensor(data: dict[str, Any] | None):
    """Build the Projected Usage sensor over a given payload."""
    from unittest.mock import MagicMock

    from custom_components.huawei_router_5g.sensor import HuaweiRouterSensor

    description = next(d for d in SENSOR_TYPES if d.key == "projected_usage")
    coordinator = MagicMock()
    coordinator.data = data
    return HuaweiRouterSensor(coordinator, MagicMock(), description)


def test_the_projection_publishes_the_confidence_it_is_judged_by() -> None:
    """An estimate with no way to weigh it is a number, not information.

    `docs/all_sensors.md` and the README have both described a `confidence`
    attribute since the sensor shipped, and `_Projection` has computed one all
    along — it was simply never put into `extra_state_attributes`. Two
    documents agreeing with each other about a thing the code does not do is
    exactly the drift a both-directions check exists to catch.
    """
    sensor = _projection_sensor(_data())
    attrs = sensor.extra_state_attributes

    assert attrs["confidence"] in ("low", "medium", "high")
    assert attrs["cycle_length_days"] >= 28
    assert attrs["elapsed_days"] >= 0
    assert attrs["basis"]
    assert attrs["cycle_start"]
    # The note travels with them; it is not displaced by the entity having
    # attributes of its own.
    assert attrs["about"].startswith("An estimate")


def test_the_projection_publishes_only_the_note_when_there_is_no_cycle() -> None:
    """A disabled monthly plan produces no figure, so there is nothing to judge.

    The attributes must not be half-populated in that case, and the note must
    still be there — it is the only thing telling a reader why the state is
    unknown.
    """
    sensor = _projection_sensor(_data(start_date__SetMonthData="0"))
    attrs = sensor.extra_state_attributes

    assert sensor.native_value is None
    assert set(attrs) == {"about"}


def test_every_projection_attribute_is_excluded_from_the_recorder() -> None:
    """Section 14: none of this is a time series.

    `confidence` changes a handful of times per cycle and the cycle context is
    constant within one, so recording them writes a row per poll to describe
    something that did not move.
    """
    from custom_components.huawei_router_5g.sensor import HuaweiRouterSensor

    assert {
        "confidence",
        "cycle_start",
        "cycle_length_days",
        "elapsed_days",
        "basis",
    } <= HuaweiRouterSensor._unrecorded_attributes


# ---------------------------------------------------------------------------
# Mutation findings, recommendations_20260815.md
# ---------------------------------------------------------------------------


def test_the_blended_rate_is_exactly_the_weighted_mean() -> None:
    """The forecast a user reads, pinned to a hand-computed value.

    Covers finding BVA.1 from recommendations_20260815.md.

    `test_a_prior_rate_moves_only_the_unobserved_remainder` asserts a
    direction and a bound, and four mutations of the blend line satisfy that
    for its inputs: `+` becoming `-`, `*` becoming `/`, and the weight
    becoming `1.0 + weight` or `2.0 - weight`. A range assertion cannot
    separate a correct weighted mean from an incorrect one.

    Every term here is deliberately distinct so no two mutations coincide:
        weight       = 10 / (10 + 5)  = 2/3
        current_rate = 100 / 10       = 10.0
        rate         = 2/3·10 + 1/3·5 = 8.333...
        projected    = 100 + 20·rate  = 266.666...
    """
    projected = project_cycle_usage(
        used=100.0,
        elapsed_days=10.0,
        cycle_length_days=30,
        prior_rate=5.0,
        credibility_days=5.0,
    )

    assert projected == pytest.approx(266.6666667, rel=1e-6)


def test_the_cycle_boundary_is_exactly_local_midnight() -> None:
    """The normalisation was never exercised, because no test made it work.

    Covers finding BVA.2 from recommendations_20260815.md. Every `now` in the
    cycle tests was constructed at a round time, so zeroing the time-of-day
    was a no-op on every input the suite supplied and all four components
    could be deleted with the suite green.

    It is not cosmetic: `elapsed_days` is measured from `start`, so a boundary
    carrying the current time-of-day skews the projection by up to a day at
    the point in the cycle where it is least stable anyway.

    The four components are asserted individually so a failure names the one
    that was lost.
    """
    awkward = datetime(2026, 8, 15, 17, 43, 21, 123456, tzinfo=TZ)

    start, end, _ = cycle_bounds(1, awkward)

    for boundary in (start, end):
        assert boundary.hour == 0
        assert boundary.minute == 0
        assert boundary.second == 0
        assert boundary.microsecond == 0


def test_a_now_exactly_on_the_boundary_belongs_to_the_new_cycle() -> None:
    """`start > now`, not `>=` — one instant a month turns on it.

    Covers finding BVA.3 from recommendations_20260815.md. Under `>=` the
    first moment of a new cycle rolls back a whole month: `elapsed_days` jumps
    from zero to about thirty and the projection is computed against the
    previous cycle.
    """
    start, _, length = cycle_bounds(1, datetime(2026, 8, 1, 0, 0, 0, 0, tzinfo=TZ))

    assert start == datetime(2026, 8, 1, 0, 0, tzinfo=TZ)
    assert length == 31


def test_a_january_date_before_the_start_day_rolls_back_to_december() -> None:
    """The backward roll is a different branch from the forward one.

    Covers finding COMBO.1 from recommendations_20260815.md.
    `test_a_december_cycle_rolls_into_january` covers a December cycle whose
    *end* lands in January. This is the other direction: a January `now`
    falling before the start day, so the cycle in flight began last December —
    and the year arithmetic behind it had three surviving mutations.
    """
    start, end, _ = cycle_bounds(15, datetime(2027, 1, 9, 12, 0, tzinfo=TZ))

    assert start.year == 2026
    assert start.month == 12
    assert start.day == 15
    assert end == datetime(2027, 1, 15, 0, 0, tzinfo=TZ)
