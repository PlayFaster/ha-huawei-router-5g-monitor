"""Section 19 — Integration Health and self-diagnosis.

The failure this entity exists for is the one Home Assistant does **not**
catch: a poll that *succeeds* while the data is wrong or a whole capability is
quietly missing. `api.get_data()` fetches fifteen endpoints and silently omits
any optional one that fails — only `device_information` raises — so
"successful poll, absent capability" is this integration's characteristic
silent failure.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from custom_components.huawei_router_5g.binary_sensor import (
    INTEGRATION_HEALTH_DESCRIPTION,
    HuaweiIntegrationHealthSensor,
)
from custom_components.huawei_router_5g.const import (
    ENDPOINT_NAMES,
    FETCH_STRIKE_LIMIT,
    HEALTH_DRIFT_STRIKE_LIMIT,
)
from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)


@pytest.fixture(autouse=True)
def mock_report_usage():
    """Suppress 'Frame helper not set up' warnings from HA internals."""
    with patch("homeassistant.helpers.frame.report_usage"):
        yield


@pytest.fixture
def mock_hass():
    """Mock Home Assistant."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.config_entries = MagicMock()
    return hass


@pytest.fixture
def coordinator(mock_hass, mock_config_entry):
    """Build a real coordinator with a mocked API."""
    return HuaweiRouter5GDataUpdateCoordinator(
        mock_hass, mock_config_entry, MagicMock()
    )


def _full_payload() -> dict:
    """Build a payload where every endpoint answered and the signal is sane."""
    payload: dict = {key: {"x": 1} for key in ENDPOINT_NAMES}
    payload["device_signal"] = {"rsrp": "-95dBm", "sinr": "6dB"}
    return payload


# ---------------------------------------------------------------------------
# Capability degradation
# ---------------------------------------------------------------------------


def test_a_missing_capability_is_reported_only_after_the_strike_budget(coordinator):
    """A capability must persist as missing before it is reported.

    A single dropped endpoint is ordinary; a sustained absence is the signal.
    The distinction is *blip vs. outage* — reporting on the first miss would
    make the sensor useless from jitter alone.
    """
    partial = {"device_information": {"DeviceName": "B535"}}

    for attempt in range(1, HEALTH_DRIFT_STRIKE_LIMIT):
        coordinator.update_health(partial, failed=False, cold_start=False)
        assert coordinator.health_snapshot["degraded_capabilities"] == [], (
            f"reported a degraded capability after only {attempt} miss(es)"
        )

    coordinator.update_health(partial, failed=False, cold_start=False)
    degraded = coordinator.health_snapshot["degraded_capabilities"]

    assert "SMS messages" in degraded
    assert "WiFi clients" in degraded
    # `degraded`, not `warning`: a capability was lost while the core still
    # works. `warning` is reserved for drift — see the drift test below.
    assert coordinator.health_snapshot["severity"] == "degraded"
    # Friendly names, not raw endpoint keys — this is read by users.
    assert "sms_list" not in degraded


def test_recovery_clears_the_verdict_in_the_same_cycle(coordinator):
    """A success must clear the verdict immediately, not on some later poll."""
    partial = {"device_information": {"DeviceName": "B535"}}
    for _ in range(HEALTH_DRIFT_STRIKE_LIMIT):
        coordinator.update_health(partial, failed=False, cold_start=False)
    assert coordinator.health_snapshot["issues"]

    coordinator.update_health(_full_payload(), failed=False, cold_start=False)

    assert coordinator.health_snapshot["issues"] == []
    assert coordinator.health_snapshot["severity"] == "ok"


def test_the_critical_endpoint_can_never_appear_as_degraded(coordinator):
    """`device_information` raises rather than being omitted.

    Listing it as a degradable capability would be dead reporting — the fetch
    fails outright instead, and the health sensor covers that separately.
    """
    payload = _full_payload()
    del payload["device_information"]

    for _ in range(HEALTH_DRIFT_STRIKE_LIMIT + 1):
        coordinator.update_health(payload, failed=False, cold_start=False)

    assert (
        "Device information"
        not in (coordinator.health_snapshot["degraded_capabilities"])
    )


# ---------------------------------------------------------------------------
# Contract drift — the highest-value check
# ---------------------------------------------------------------------------


def test_a_renamed_signal_block_is_reported_as_drift(coordinator):
    """A non-empty response that parses to nothing meaningful is drift.

    This is the direct catch for a firmware field rename: the poll succeeds,
    the block is present and non-empty, and every field the integration reads
    is gone. Nothing else in the component would notice.
    """
    payload = _full_payload()
    payload["device_signal"] = {"signal_strength_dbm": "-95", "quality": "-12"}

    coordinator.update_health(payload, failed=False, cold_start=False)

    assert coordinator.health_snapshot["drift"], "a renamed signal block was not caught"
    assert "renamed" in coordinator.health_snapshot["drift"][0]
    assert coordinator.health_snapshot["severity"] == "warning"


def test_one_recognised_field_is_enough_to_clear_the_drift_check(coordinator):
    """A weak signal is not a renamed field.

    Without this the check would fire on any router reporting only a subset of
    the metrics, which is the false-alarm shape Section 19 warns about.
    """
    payload = _full_payload()
    payload["device_signal"] = {"rsrp": "-95dBm", "sinr": None, "rsrq": ""}

    coordinator.update_health(payload, failed=False, cold_start=False)
    assert coordinator.health_snapshot["drift"] == []


def test_an_empty_signal_block_is_not_drift(coordinator):
    """An absent block is a *degradation*, not a rename.

    Conflating the two would report "the firmware renamed these fields" every
    time an endpoint simply failed, which sends the user looking for the wrong
    problem.
    """
    payload = _full_payload()
    payload["device_signal"] = {}

    coordinator.update_health(payload, failed=False, cold_start=False)
    assert coordinator.health_snapshot["drift"] == []


# ---------------------------------------------------------------------------
# Total outage — cold start vs. runtime
# ---------------------------------------------------------------------------


def test_a_cold_start_is_flagged_on_the_very_first_failure(coordinator):
    """Cold start bypasses the strike budget.

    There are no held values, so waiting out three polls leaves the user with a
    wholly unavailable integration and no explanation. Section 19 names this
    exception explicitly — and a sibling project's docstring claimed it while
    the code did the opposite for months, with two tests pinning the wrong
    behavior.
    """
    coordinator.consecutive_failures = 1
    coordinator.update_health(None, failed=True, cold_start=True)

    assert coordinator.health_snapshot["severity"] == "error"
    assert coordinator.health_snapshot["issues"]


def test_at_runtime_both_edges_of_the_strike_budget_are_pinned(coordinator):
    """A single blip raises no alarm; a sustained outage does.

    Both edges deliberately: a test asserting only the flag-at-three case
    passes against a mutation that flags at one.
    """
    coordinator.consecutive_failures = FETCH_STRIKE_LIMIT - 1
    coordinator.update_health(None, failed=True, cold_start=False)
    assert coordinator.health_snapshot["issues"] == []

    coordinator.consecutive_failures = FETCH_STRIKE_LIMIT
    coordinator.update_health(None, failed=True, cold_start=False)
    assert coordinator.health_snapshot["severity"] == "error"


def test_an_empty_successful_payload_is_not_total_degradation(coordinator):
    """`{}` from a paused cold start must not read as fifteen dead endpoints.

    Treating it as total degradation would alarm a user who has simply
    switched polling off.
    """
    coordinator.update_health({}, failed=False, cold_start=False)

    assert coordinator.health_snapshot["issues"] == []
    assert coordinator.health_snapshot["degraded_capabilities"] == []


# ---------------------------------------------------------------------------
# Never make things worse
# ---------------------------------------------------------------------------


def test_health_computation_can_never_crash_the_poll_it_diagnoses(coordinator, caplog):
    """A malformed payload must degrade, not raise.

    This exists to diagnose a broken update; taking the update down with it
    would be strictly worse than not having it at all. That half is unchanged.

    **What it degrades *to* changed on 2026-08-16**, after `masked_errors_check`
    raised it as a Class A finding. The snapshot previously came back clean —
    `severity: None`, no issues — so a verdict that had stopped working
    reported "no problems" indefinitely, and the only trace was a DEBUG line.
    The one state this sensor must never report cleanly is its own failure, so
    it now carries `health_verdict_unavailable` and warns once per session.
    """
    caplog.set_level(logging.DEBUG)

    with patch.object(
        coordinator, "_compute_health", side_effect=ValueError("malformed")
    ):
        coordinator.update_health({"anything": 1}, failed=False, cold_start=False)

    # Still degrades rather than raising — the original guarantee.
    assert coordinator.health_snapshot is not None

    # ...but it no longer claims to be healthy.
    assert coordinator.health_snapshot["severity"] == "error"
    assert coordinator.health_snapshot["issues"] == ["health_verdict_unavailable"]
    assert "Health computation failed" in caplog.text


# ---------------------------------------------------------------------------
# The entity itself
# ---------------------------------------------------------------------------


def test_the_sensor_stays_available_when_everything_else_is_not(mock_config_entry):
    """Section 19: never `unavailable`, ever.

    The inherited `CoordinatorEntity.available` returns `last_update_success`,
    which takes this sensor down at exactly the moment it has something to say.
    A user reads `unavailable` as "this sensor is broken", not "my router is
    down", so its silence would be indistinguishable from health.
    """
    coordinator = MagicMock()
    coordinator.last_update_success = False
    coordinator.data = None
    coordinator.health_snapshot = {
        "severity": "error",
        "issues": ["The router has never answered."],
        "degraded_capabilities": [],
        "drift": [],
        "last_good_update": None,
    }
    sensor = HuaweiIntegrationHealthSensor(
        coordinator, mock_config_entry, INTEGRATION_HEALTH_DESCRIPTION
    )

    assert sensor.available is True
    assert sensor.is_on is True


def test_the_sensor_is_off_when_there_is_nothing_to_report(mock_config_entry):
    """`off` means healthy — and it must be reachable, not just the default."""
    coordinator = MagicMock()
    coordinator.health_snapshot = {
        "severity": None,
        "issues": [],
        "degraded_capabilities": [],
        "drift": [],
        "last_good_update": "2026-08-09T10:00:00+00:00",
    }
    sensor = HuaweiIntegrationHealthSensor(
        coordinator, mock_config_entry, INTEGRATION_HEALTH_DESCRIPTION
    )

    assert sensor.is_on is False
    assert sensor.available is True
    assert sensor.extra_state_attributes["last_good_update"] == (
        "2026-08-09T10:00:00+00:00"
    )


def test_the_sensor_copies_the_snapshot_rather_than_exposing_it(mock_config_entry):
    """Attributes must not hand out the coordinator's live lists.

    Home Assistant keeps the returned dict; a caller mutating a list it was
    given would be editing coordinator state from a read path.
    """
    coordinator = MagicMock()
    coordinator.health_snapshot = {
        "severity": "warning",
        "issues": ["SMS messages is not responding."],
        "degraded_capabilities": ["SMS messages"],
        "drift": [],
        "last_good_update": None,
    }
    sensor = HuaweiIntegrationHealthSensor(
        coordinator, mock_config_entry, INTEGRATION_HEALTH_DESCRIPTION
    )

    attrs = sensor.extra_state_attributes
    attrs["issues"].append("injected")

    assert coordinator.health_snapshot["issues"] == ["SMS messages is not responding."]


# ---------------------------------------------------------------------------
# Section 19 — the repair and severity contract sweeps (chore C-022, step 8)
# ---------------------------------------------------------------------------

# The §19 vocabulary, written as the literal strings that reach the user.
# Deliberately not imported from the component: comparing a published value
# against the constant that produced it compares the code with itself, and a
# rename would pass here while every automation matching on `severity` broke.
SEVERITY_VOCABULARY = frozenset({"ok", "degraded", "warning", "error", "unknown"})


def _raised_repair_keys() -> set[str]:
    """Return every repair key the source can actually raise.

    Read from `coordinator.py` rather than from a list, because a
    hand-maintained inventory of raise sites is one more thing to forget.
    """
    import re
    from pathlib import Path

    from custom_components.huawei_router_5g import coordinator as coordinator_module

    source = Path(coordinator_module.__file__).read_text(encoding="utf-8")
    return set(re.findall(r'f"\{(REPAIR_[A-Z_]+)\}_\{self\.entry\.entry_id\}"', source))


def test_every_repair_the_code_raises_is_registered_for_removal() -> None:
    """A repair the removal list omits outlives the integration.

    `async_remove_entry` deletes exactly the list it is given. `conn_error` is
    `is_fixable=False`, so a card left behind by an entry that no longer
    exists has no route out of the Repairs panel at all, and `auth_failed`
    would offer a repair flow for an integration that has been deleted.

    Chore `C-022` step 8c, the one that has recurred twice in this family.
    """
    from custom_components.huawei_router_5g import const

    raised = {getattr(const, name) for name in _raised_repair_keys()}
    registered = set(const.REPAIR_NAMES)

    assert raised, "no repair raise sites found — the sweep is reading nothing"
    assert raised <= registered, (
        f"raised but never deleted on removal: {sorted(raised - registered)}"
    )


@pytest.mark.parametrize(
    ("data", "failed", "cold_start"),
    [
        ({"device_information": {"DeviceName": "B535"}}, False, False),
        (None, True, False),
        (None, True, True),
        ({}, True, False),
    ],
)
def test_every_published_severity_is_in_the_section_19_vocabulary(
    data, failed, cold_start, coordinator
):
    """No path may publish a severity outside the five, and never `None`.

    Each test elsewhere asserts the severity of the case it was written for,
    so nothing notices when one path stops setting one — which is how a
    `severity=None` mutation survived a run on `wifi_ssid_monitor`. This
    sweeps the paths instead of the values.

    Chore `C-022` step 8d.
    """

    coordinator.update_health(data, failed=failed, cold_start=cold_start)

    published = coordinator.health_snapshot["severity"]
    assert published in SEVERITY_VOCABULARY
    assert isinstance(published, str) and published


def test_every_finding_is_classified_exactly_once(coordinator) -> None:
    """A finding is drift or a lost capability, never both and never neither.

    The two mean different things to the user — a block that is missing is a
    capability that has gone, a block that arrives carrying none of its
    contract keys means the readings cannot be trusted — and `issues` is the
    union of the two lists. A finding in both would be reported twice; one in
    neither would be reported without ever being named.

    Chore `C-022` step 8e.
    """

    data = {
        "device_information": {"DeviceName": "B535"},
        "device_signal": {"unexpected": "value"},
    }

    for _ in range(HEALTH_DRIFT_STRIKE_LIMIT):
        coordinator.update_health(data, failed=False, cold_start=False)

    snapshot = coordinator.health_snapshot
    degraded = set(snapshot["degraded_capabilities"])
    drift = set(snapshot["drift"])

    assert degraded, "the fixture should have lost capabilities"
    assert drift, "the fixture should have produced drift"
    assert not (degraded & drift), "a finding is classified twice"
    assert len(snapshot["issues"]) == len(degraded) + len(drift)


def test_the_severity_sweep_still_sweeps_something() -> None:
    """The guard cannot quietly shrink to a set of one.

    A sweep that inspects almost nothing passes for the same reason a correct
    one does, so the count is asserted alongside the property.

    Chore `C-022` step 8f.
    """
    from custom_components.huawei_router_5g.const import ENDPOINT_NAMES

    assert len(SEVERITY_VOCABULARY) == 5
    assert len(ENDPOINT_NAMES) >= 20
    assert len(_raised_repair_keys()) >= 2
