"""What the coordinator is holding the moment it is built.

Written from the first mutation run to cover `coordinator.py`. Its `__init__`
produced **61 survivors** and the six `contextlib.suppress` blocks a further
27 — because nothing had ever asserted the *initial* state of a coordinator, or
driven the restore path with input that actually fails.

Two failure shapes are covered, and they are different:

- **The starting values.** A counter that begins at `None` instead of `0`, or a
  set that begins as `None`, breaks on first use — but only on a path no test
  reaches from a fresh object, because every existing test seeds what it needs
  first.
- **The restore, when it goes wrong.** Six blocks read latch state back out of
  `ConfigEntry.data` under `contextlib.suppress`. The suppression is deliberate:
  a corrupt stored value must not stop the integration loading. But a test that
  only ever supplies *valid* data never enters the handler, so narrowing what is
  suppressed changes nothing observable and every mutation of those argument
  lists survives.

The second is the more valuable half. `ValueError` and `TypeError` are both
reachable there — `int("abc")` raises the first, `int(None)` the second — and a
suppress list missing either turns a corrupt entry into a config entry that
cannot be set up at all.
"""

from unittest.mock import MagicMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.huawei_router_5g.const import DEFAULT_SCAN_INTERVAL
from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)

# The six keys `__init__` restores, paired with the attribute each lands on.
# Split by the kind of parsing they do, because the two groups suppress
# different exceptions and fail in different ways.
_TIMESTAMP_LATCHES = (
    ("system_boot_time", "_system_boot_time"),
    ("conn_start_time", "_conn_start_time"),
    ("total_conn_start_time", "_total_conn_start_time"),
)
_COUNTER_LATCHES = (
    ("last_system_uptime", "_last_system_uptime"),
    ("last_conn_uptime", "_last_conn_uptime"),
    ("last_total_conn_time", "_last_total_conn_time"),
)


@pytest.fixture
def mock_hass():
    """Return a hass stub sufficient to construct a coordinator.

    Local rather than shared: `test_coordinator.py` defines its own identical
    fixture, and a coordinator needs only the two attributes touched during
    construction.
    """
    hass = MagicMock()
    hass.config_entries = MagicMock()
    return hass


def _entry(data: dict | None = None, options: dict | None = None):
    """Build a config entry stub with writable `data` and `options`."""
    entry = MagicMock()
    entry.entry_id = "test"
    entry.title = "My Huawei Router"
    entry.data = data if data is not None else {}
    entry.options = options if options is not None else {}
    return entry


def _build(hass, data=None, options=None):
    """Construct a coordinator the way `async_setup_entry` does."""
    return HuaweiRouter5GDataUpdateCoordinator(hass, _entry(data, options), MagicMock())


# ---------------------------------------------------------------------------
# Starting values
# ---------------------------------------------------------------------------


def test_a_fresh_coordinator_starts_with_usable_containers(mock_hass) -> None:
    """The mutable containers must be real, empty containers — not `None`.

    `fired_sms_hashes` is the sharp one: mutated to `None` it raises
    `AttributeError` on the first `.add()`, which is the SMS de-duplication
    path. That mutation survived, which means no test had ever driven that
    path from a freshly built coordinator — every one seeded the set first.
    """
    coordinator = _build(mock_hass)

    assert coordinator.fired_sms_hashes == set()
    assert coordinator._endpoint_strikes == {}
    assert coordinator.reload_signature == {}
    coordinator.fired_sms_hashes.add("hash")  # must not raise


def test_a_fresh_coordinator_starts_with_the_right_scalars(mock_hass) -> None:
    """`0` and `False` are not interchangeable with `None` here.

    `consecutive_failures` is compared against a strike limit, so `None` fails
    at the first comparison rather than at the third failure. `_force_refresh_once`
    gates whether an explicit action overrides the pause.
    """
    coordinator = _build(mock_hass)

    assert coordinator.consecutive_failures == 0
    assert coordinator._force_refresh_once is False
    assert coordinator._pending_refresh is None
    assert coordinator.projection_cache is None


def test_last_update_success_time_starts_as_none_not_empty(mock_hass) -> None:
    """`None` and `""` differ where it matters.

    This value is published directly by the Last Updated sensor. `None` reads
    as *unknown*; `""` is a string, and a timestamp sensor handed one is not
    the same entity state.
    """
    coordinator = _build(mock_hass)

    assert coordinator.last_update_success_time is None
    assert coordinator.last_sms_timestamp is None


def test_the_health_snapshot_starts_unknown_and_empty(mock_hass) -> None:
    """Section 19's published attribute names **and values** are a contract.

    Users write templates against `severity`, `issues`, `degraded_capabilities`,
    `drift` and `last_good_update`. A key renamed at construction — even in
    case — silently breaks every template written for it, and nothing errors.

    **`severity` starts `"unknown"`, not `None`.** Nothing has been fetched at
    construction, so there is no verdict to report — and `None` rendered as
    "Unknown" beside three blank lists, which a user cannot distinguish from a
    sensor that never populated. Section 19 forbids `None` for this attribute.
    """
    snapshot = _build(mock_hass).health_snapshot

    assert set(snapshot) == {
        "severity",
        "issues",
        "degraded_capabilities",
        "drift",
        "last_good_update",
    }
    assert snapshot["severity"] == "unknown"
    assert snapshot["issues"] == []
    assert snapshot["degraded_capabilities"] == []
    assert snapshot["drift"] == []
    assert snapshot["last_good_update"] is None


def test_every_latch_starts_unset(mock_hass) -> None:
    """A latch that starts at anything but `None` is a frozen wrong answer.

    Each is recomputed exactly once per genuine counter reset and then held, so
    a bad starting value is not corrected by the next poll — it is held.
    """
    coordinator = _build(mock_hass)

    for _, attr in _TIMESTAMP_LATCHES + _COUNTER_LATCHES:
        assert getattr(coordinator, attr) is None, f"{attr} did not start unset"


# ---------------------------------------------------------------------------
# Hardware identity
# ---------------------------------------------------------------------------


def test_the_model_falls_back_when_the_entry_has_none(mock_hass) -> None:
    """The fallback is user-visible: it names the device in the registry."""
    assert _build(mock_hass).model == "Huawei Router"


def test_hardware_identity_is_read_from_the_entry(mock_hass) -> None:
    """Each field comes from its own key — a swap is invisible until seen."""
    coordinator = _build(
        mock_hass,
        data={
            "model": "B535s-232",
            "sw_version": "11.0.1.1",
            "hw_version": "Ver.A",
            "mac": "dc7196112233",
        },
    )

    assert coordinator.model == "B535s-232"
    assert coordinator.sw_version == "11.0.1.1"
    assert coordinator.hw_version == "Ver.A"
    assert coordinator.mac == "dc7196112233"


def test_the_scan_interval_comes_from_options_and_falls_back(mock_hass) -> None:
    """The default must be the shared constant, not a number typed twice."""
    assert _build(mock_hass).update_interval.total_seconds() == DEFAULT_SCAN_INTERVAL
    assert (
        _build(mock_hass, options={"scan_interval": 45}).update_interval.total_seconds()
        == 45
    )


# ---------------------------------------------------------------------------
# Restoring the latches — including when the stored value is corrupt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("key", "attr"), _TIMESTAMP_LATCHES)
def test_a_stored_timestamp_latch_is_restored(mock_hass, key: str, attr: str) -> None:
    """Each key must land on its own attribute.

    Parametrized over all three because the three blocks are near-identical
    lines, which is exactly where a copy-paste lands a value on the wrong
    attribute and nothing complains.
    """
    stored = "2026-08-15T10:00:00+00:00"
    coordinator = _build(mock_hass, data={key: stored})

    assert getattr(coordinator, attr) == dt_util.parse_datetime(stored)


@pytest.mark.parametrize(("key", "attr"), _COUNTER_LATCHES)
def test_a_stored_counter_latch_is_restored_as_an_int(
    mock_hass, key: str, attr: str
) -> None:
    """Stored as a string by the registry, needed as an int for comparison."""
    coordinator = _build(mock_hass, data={key: "3600"})

    assert getattr(coordinator, attr) == 3600
    assert isinstance(getattr(coordinator, attr), int)


@pytest.mark.parametrize(("key", "attr"), _COUNTER_LATCHES)
@pytest.mark.parametrize(
    ("corrupt", "raises"),
    [("not-a-number", "ValueError"), (object(), "TypeError")],
)
def test_a_corrupt_counter_latch_is_suppressed_not_fatal(
    mock_hass, key: str, attr: str, corrupt, raises: str
) -> None:
    """A corrupt stored value must never stop the entry loading.

    **This is the test the suppress mutants needed.** `int()` raises
    `ValueError` on a non-numeric string and `TypeError` on a non-numeric
    type, and both are reachable from data written by an older version. Every
    prior test supplied a valid value, so the handler was never entered and
    narrowing the suppressed set changed nothing observable.

    Construction must succeed and the latch must be left unset, which is the
    safe state: unset means "recompute on the next reading", not "trust this".
    """
    coordinator = _build(mock_hass, data={key: corrupt})

    assert getattr(coordinator, attr) is None, (
        f"a corrupt {key} ({raises}) left a value on {attr}"
    )


@pytest.mark.parametrize(("key", "attr"), _TIMESTAMP_LATCHES)
def test_a_corrupt_timestamp_latch_is_suppressed_not_fatal(
    mock_hass, key: str, attr: str
) -> None:
    """Same for the timestamp latches, which suppress broadly on purpose.

    `parse_datetime` returns `None` for an unparsable string rather than
    raising, so the value that actually reaches the handler is a wrong *type* —
    which is why these three blocks suppress `Exception` rather than a named
    pair.
    """
    coordinator = _build(mock_hass, data={key: object()})

    assert getattr(coordinator, attr) is None


@pytest.mark.parametrize(("key", "attr"), _TIMESTAMP_LATCHES + _COUNTER_LATCHES)
def test_an_absent_latch_key_leaves_the_attribute_unset(
    mock_hass, key: str, attr: str
) -> None:
    """The common case — a first run, with nothing stored yet."""
    coordinator = _build(mock_hass, data={})

    assert getattr(coordinator, attr) is None


def test_a_zero_counter_latch_is_restored_rather_than_skipped(mock_hass) -> None:
    """Zero is a real uptime and must survive the guard.

    The check is `is not None`, deliberately, because `if v:` would discard a
    stored `0` — a router that has just rebooted — and silently re-latch on the
    next reading.
    """
    coordinator = _build(mock_hass, data={"last_system_uptime": 0})

    assert coordinator._last_system_uptime == 0
