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
    HEALTH_STRIKE_LIMIT,
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

    for attempt in range(1, HEALTH_STRIKE_LIMIT):
        coordinator.update_health(partial, failed=False, cold_start=False)
        assert coordinator.health_snapshot["degraded_capabilities"] == [], (
            f"reported a degraded capability after only {attempt} miss(es)"
        )

    coordinator.update_health(partial, failed=False, cold_start=False)
    degraded = coordinator.health_snapshot["degraded_capabilities"]

    assert "SMS messages" in degraded
    assert "WiFi clients" in degraded
    assert coordinator.health_snapshot["severity"] == "warning"
    # Friendly names, not raw endpoint keys — this is read by users.
    assert "sms_list" not in degraded


def test_recovery_clears_the_verdict_in_the_same_cycle(coordinator):
    """A success must clear the verdict immediately, not on some later poll."""
    partial = {"device_information": {"DeviceName": "B535"}}
    for _ in range(HEALTH_STRIKE_LIMIT):
        coordinator.update_health(partial, failed=False, cold_start=False)
    assert coordinator.health_snapshot["issues"]

    coordinator.update_health(_full_payload(), failed=False, cold_start=False)

    assert coordinator.health_snapshot["issues"] == []
    assert coordinator.health_snapshot["severity"] is None


def test_the_critical_endpoint_can_never_appear_as_degraded(coordinator):
    """`device_information` raises rather than being omitted.

    Listing it as a degradable capability would be dead reporting — the fetch
    fails outright instead, and the health sensor covers that separately.
    """
    payload = _full_payload()
    del payload["device_information"]

    for _ in range(HEALTH_STRIKE_LIMIT + 1):
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
    coordinator.consecutive_failures = HEALTH_STRIKE_LIMIT - 1
    coordinator.update_health(None, failed=True, cold_start=False)
    assert coordinator.health_snapshot["issues"] == []

    coordinator.consecutive_failures = HEALTH_STRIKE_LIMIT
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
    """A malformed payload must degrade to "unknown", not raise.

    This exists to diagnose a broken update; taking the update down with it
    would be strictly worse than not having it at all.
    """
    caplog.set_level(logging.DEBUG)

    with patch.object(
        coordinator, "_compute_health", side_effect=ValueError("malformed")
    ):
        coordinator.update_health({"anything": 1}, failed=False, cold_start=False)

    assert coordinator.health_snapshot["issues"] == []
    assert coordinator.health_snapshot["severity"] is None
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
