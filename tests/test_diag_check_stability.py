"""The checks in `scripts/diag_check.py` that can be driven without hardware.

The script itself needs the router and never runs in CI, but its judgement is
ordinary code: what counts as a difference between two downloads, whether a
capture agrees with the coordinator state beside it, and whether a live value
survived redaction. Those decisions are what make the script's verdict worth
anything, and getting them wrong is silent — a comparison that tolerates too
much reports PASS on a download that changed shape.

Two inputs are deliberately not comparable across files. Radio measurements and
counters move on their own, and the pseudonyms `diagnostics._Tokenizer` assigns
are allocated in first-seen order and are stable only within one download, so
`ip-5` in two files are unrelated values. `zte_router_5g` failed both halves of
its comparison for exactly that reason while behaving correctly, which is why
its equivalent tests exist and why these mirror them.

Aligned with `zte_router_5g/tests/test_diag_check_stability.py`, with the same
case names where the case exists in both projects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.diag_check import (
    EXPIRY_CODES,
    Report,
    _secrets,
    _serialize,
    check_captures,
    check_endpoints,
    check_redaction,
    check_sabotage,
    check_shape,
    check_stability,
)


def _artefact(
    payload: dict[str, Any] | None = None,
    *,
    success: bool = True,
    rejection: dict[str, Any] | None = None,
    login: dict[str, Any] | None = None,
    endpoints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a download of the shape `diagnostics.py` produces."""
    return {
        "entry": {"title": "Huawei 5G", "data": {}, "options": {}},
        "coordinator": {
            "consecutive_failures": 0,
            "last_update_success": success,
            "last_update_success_time": "2026-09-07T03:59:46+00:00",
            "data_available": True,
            "update_interval_seconds": 1230.0,
        },
        "data": payload if payload is not None else {"device_information": {"a": "1"}},
        "last_rejection": rejection,
        "login": login if login is not None else {"result": "ok", "error": None},
        "probes": {"global_module_switch": {"outcome": "answered", "type": "dict"}},
        "entity_resolution": {
            "sensor": {"total": 2, "resolved": 1, "no_value": ["b"], "raised": {}},
        },
        "endpoints": (
            endpoints
            if endpoints is not None
            else {
                key: {"outcome": "answered"}
                for key in (payload or {"device_information": {}})
            }
        ),
    }


def _passed(report: Report, fragment: str) -> bool:
    """Return whether the one check whose name contains `fragment` passed."""
    matches = [ok for ok, name, _ in report.checks if fragment in name]
    assert matches, f"no check named ...{fragment}..."
    return all(matches)


# ---------------------------------------------------------------------------
# check_shape — the published keys reach the file
# ---------------------------------------------------------------------------


def test_a_complete_document_passes_the_shape_check() -> None:
    """The document `diagnostics.py` builds today is the expected shape."""
    report = Report()
    check_shape(_artefact(), report, "1")

    assert report.failed == 0


@pytest.mark.parametrize(
    "key",
    [
        "last_rejection",
        "login",
        "data",
        "coordinator",
        "endpoints",
        "entity_resolution",
    ],
)
def test_a_missing_published_key_is_a_failure(key: str) -> None:
    """This is the seam the script exists for: a field that never reached the file."""
    artefact = _artefact()
    del artefact[key]

    report = Report()
    check_shape(artefact, report, "1")

    assert not _passed(report, "every published key reached the file")


def test_an_empty_payload_is_a_failure() -> None:
    """A download whose `data` block is empty is not evidence of anything."""
    report = Report()
    check_shape(_artefact({}), report, "1")

    assert not _passed(report, "the payload block is populated")


def test_a_truncated_coordinator_block_is_a_failure() -> None:
    """Every coordinator field is part of the contract, not just the block."""
    artefact = _artefact()
    del artefact["coordinator"]["data_available"]

    report = Report()
    check_shape(artefact, report, "1")

    assert not _passed(report, "the coordinator block is complete")


# ---------------------------------------------------------------------------
# check_captures — a capture must agree with the state beside it
# ---------------------------------------------------------------------------


def test_a_successful_poll_with_no_rejection_passes() -> None:
    """The healthy case, and what the reference router produces."""
    report = Report()
    check_captures(_artefact(), report, "1")

    assert report.failed == 0


def test_a_stale_rejection_beside_a_successful_poll_is_a_failure() -> None:
    """The clearing rule is what this catches, and it cannot be seen field by field.

    Both halves are well-formed on their own: a valid rejection record and a
    successful poll. Only the pairing is wrong, and it means the clear that
    should have run before the poll did not.
    """
    report = Report()
    check_captures(
        _artefact(rejection={"verdict": "expired", "code": "125002"}), report, "1"
    )

    assert not _passed(report, "left no rejection behind")


def test_a_failed_poll_with_no_rejection_is_a_failure() -> None:
    """A poll that failed and recorded nothing is the defect the item was raised for."""
    report = Report()
    check_captures(_artefact(success=False), report, "1")

    assert not _passed(report, "left its verdict behind")


def test_a_failed_poll_carrying_its_verdict_passes() -> None:
    """A recorded failure is the download doing its job."""
    report = Report()
    check_captures(
        _artefact(success=False, rejection={"verdict": "expired", "code": "125002"}),
        report,
        "1",
    )

    assert report.failed == 0


def test_a_login_that_did_not_establish_a_session_is_a_failure() -> None:
    """The script logs in itself, so anything but `ok` means the run is unsound."""
    report = Report()
    check_captures(_artefact(login={"result": "auth_failed"}), report, "1")

    assert not _passed(report, "the session was established")


# ---------------------------------------------------------------------------
# check_redaction — over the whole document, not key by key
# ---------------------------------------------------------------------------


def test_a_leaked_credential_is_found_anywhere_in_the_document() -> None:
    """Buried under a key nobody thought to check, which is the realistic case."""
    artefact = _artefact({"some_future_block": {"note": "host is router-secret-1"}})

    report = Report()
    check_redaction(artefact, ["router-secret-1"], report, "1")

    assert not _passed(report, "no live identifier survived")


def test_a_document_with_no_redaction_marker_is_a_failure() -> None:
    """A file redacting nothing at all is the failure mode worth naming.

    A sanitizer that silently stopped running would leak everything while every
    per-value assertion still passed, because there would be no live value in
    this fixture to find.
    """
    report = Report()
    check_redaction(_artefact(), [], report, "1")

    assert not _passed(report, "redaction marker")


def test_a_short_credential_is_not_searched_for() -> None:
    """A two-character value matches by coincidence and proves nothing."""
    assert _secrets({"password": "abc", "username": "ad"}, {}) == []


def test_the_live_identifiers_are_drawn_from_the_entry() -> None:
    """The check asserts against this device's own values, not a fixture's."""
    secrets = _secrets(
        {
            "password": "hunter2secret",
            "host": "192.168.8.1",
            "username": "administrator",
        },
        {"mac": "DC:71:96:11:22:33"},
    )

    assert set(secrets) == {
        "hunter2secret",
        "192.168.8.1",
        "administrator",
        "DC:71:96:11:22:33",
    }


# ---------------------------------------------------------------------------
# check_stability — two runs, and what the device is allowed to change
# ---------------------------------------------------------------------------


def test_two_identical_downloads_are_stable() -> None:
    """The baseline: nothing moved, nothing reported."""
    report = Report()
    check_stability(_artefact(), _artefact(), report)

    assert report.failed == 0


def test_a_field_present_in_one_run_only_is_a_difference() -> None:
    """A download that changed shape between two runs minutes apart."""
    second = _artefact()
    second["data"]["device_information"]["b"] = "2"

    report = Report()
    check_stability(_artefact(), second, report)

    assert not _passed(report, "carry the same fields")


def test_a_stable_value_changing_is_a_difference() -> None:
    """The router's model name is not something the device changes on its own."""
    report = Report()
    check_stability(
        _artefact({"device_information": {"DeviceName": "H165-383"}}),
        _artefact({"device_information": {"DeviceName": "something-else"}}),
        report,
    )

    assert not _passed(report, "no stable value changed")


@pytest.mark.parametrize(
    "field", ["rsrp", "sinr", "cqi0", "dl_mcs", "uptime", "cell_id", "band"]
)
def test_a_radio_measurement_is_allowed_to_move(field: str) -> None:
    """These drift between two runs seconds apart; a diff on them is noise."""
    report = Report()
    check_stability(
        _artefact({"device_signal": {field: "1"}}),
        _artefact({"device_signal": {field: "2"}}),
        report,
    )

    assert report.failed == 0


def test_a_client_joining_the_network_is_not_a_difference() -> None:
    """The host list is the network's business, not the download's."""
    report = Report()
    check_stability(
        _artefact({"lan_host_info": {"Hosts": {"Host": [{"HostName": "name-1"}]}}}),
        _artefact(
            {
                "lan_host_info": {
                    "Hosts": {"Host": [{"HostName": "name-1"}, {"HostName": "name-2"}]}
                }
            }
        ),
        report,
    )

    assert report.failed == 0


@pytest.mark.parametrize("kind", ["ip", "mac", "cell", "phone", "ssid", "name"])
def test_renumbered_pseudonyms_are_not_a_difference(kind: str) -> None:
    """Tokens are allocated per download, so `ip-5` in two files are unrelated.

    Comparing them across files compares allocation order: a pass that read its
    keys in a different order renumbers every token and reports a permutation
    as a difference.
    """
    report = Report()
    check_stability(
        _artefact({"block": {"value": f"{kind}-1"}}),
        _artefact({"block": {"value": f"{kind}-7"}}),
        report,
    )

    assert report.failed == 0


def test_a_token_changing_kind_is_a_difference() -> None:
    """Only the numbering is unstable. A MAC becoming an IP is a real change."""
    report = Report()
    check_stability(
        _artefact({"block": {"value": "mac-1"}}),
        _artefact({"block": {"value": "ip-1"}}),
        report,
    )

    assert not _passed(report, "no stable value changed")


def test_the_elapsed_time_is_not_a_difference() -> None:
    """The script's own bookkeeping is not part of the artefact under test."""
    first = _artefact()
    second = _artefact()
    first["_elapsed"] = 3.2
    second["_elapsed"] = 4.8

    report = Report()
    check_stability(first, second, report)

    assert report.failed == 0


# ---------------------------------------------------------------------------
# _serialize — the entry carries real datetimes, and the first run died on them
# ---------------------------------------------------------------------------


def test_a_download_carrying_a_datetime_is_serializable() -> None:
    """The stored entry holds `datetime` objects, and every site must survive them.

    `system_boot_time`, `conn_start_time` and `total_conn_start_time` are
    written back into the entry as real datetimes. Home Assistant serializes
    the download with its own encoder, so the user's file is valid JSON while a
    plain `json.dumps` on the same object raises — which is exactly how the
    first hardware run of this script ended, before it printed a verdict.
    """
    artefact = _artefact()
    artefact["entry"]["data"]["system_boot_time"] = datetime(2026, 8, 20, tzinfo=UTC)

    assert "2026-08-20" in _serialize(artefact)


def test_the_redaction_check_survives_a_datetime() -> None:
    """The crash was in a caller, so the guarantee is asserted at one too."""
    artefact = _artefact()
    artefact["entry"]["data"]["conn_start_time"] = datetime(2026, 8, 23, tzinfo=UTC)

    report = Report()
    check_redaction(artefact, ["nothing-to-find"], report, "1")

    assert _passed(report, "no live identifier survived")


# ---------------------------------------------------------------------------
# The volatile pattern, against the field names this router actually sends
# ---------------------------------------------------------------------------
#
# The first version of the pattern was adapted from `zte_router_5g`, whose API
# is snake_case. Huawei's is CamelCase, so `_time` matched nothing in
# `CurrentConnectTime` and five clocked fields were being compared across two
# runs that cannot hold still. The names below are taken verbatim from a real
# download; a pattern that stops covering one of them is a hardware failure
# nobody sees until the next attended run.


@pytest.mark.parametrize(
    ("block", "field"),
    [
        ("month_statistics", "MonthDuration"),
        ("month_statistics", "CurrentDayDuration"),
        ("month_statistics", "CurrentMonthDownload"),
        ("month_statistics", "CurrentDayUsed"),
        ("month_statistics", "MonthLastClearTime"),
        ("traffic_statistics", "CurrentConnectTime"),
        ("traffic_statistics", "CurrentDownloadRate"),
        ("traffic_statistics", "TotalConnectTime"),
        ("traffic_statistics", "TotalDownload"),
        ("monitoring_status", "CurrentWifiUser"),
        ("device_signal", "rsrp"),
        ("device_signal", "cell_id"),
        ("device_information", "uptime"),
    ],
)
def test_a_counter_this_router_sends_is_allowed_to_move(block: str, field: str) -> None:
    """Named from a real download, so the tolerance is measured not guessed."""
    report = Report()
    check_stability(
        _artefact({block: {field: "1"}}),
        _artefact({block: {field: "2"}}),
        report,
    )

    assert report.failed == 0


@pytest.mark.parametrize(
    ("block", "field"),
    [
        # Settings that live inside an otherwise-tolerated block, or beside one.
        ("traffic_statistics", "showtraffic"),
        ("start_date", "trafficmaxlimit"),
        ("start_date", "DataLimit"),
        ("start_date", "StartDay"),
        ("device_information", "DeviceName"),
        ("monitoring_status", "ConnectionStatus"),
    ],
)
def test_a_setting_is_not_allowed_to_move(block: str, field: str) -> None:
    """The tolerance must not swallow the values the check exists to watch.

    `showtraffic` and `trafficmaxlimit` are the trap: both carry the word
    `traffic`, both sit in or beside a block of counters, and neither is one.
    An earlier version of the pattern matched `traffic` anywhere and tolerated
    a data-limit change as though it were a byte count.
    """
    report = Report()
    check_stability(
        _artefact({block: {field: "1"}}),
        _artefact({block: {field: "2"}}),
        report,
    )

    assert not _passed(report, "no stable value changed")


# ---------------------------------------------------------------------------
# check_endpoints — the map must account for the payload beside it
# ---------------------------------------------------------------------------


def test_a_map_matching_the_payload_passes() -> None:
    """Every block came from an endpoint that answered, and vice versa."""
    report = Report()
    check_endpoints(_artefact({"device_signal": {"rsrp": "1"}}), report, "1")

    assert report.failed == 0


def test_a_block_no_endpoint_claims_is_a_failure() -> None:
    """A payload block with no `answered` endpoint behind it is unexplained."""
    report = Report()
    check_endpoints(
        _artefact(
            {"device_signal": {"rsrp": "1"}, "sms_count": {"LocalInbox": "0"}},
            endpoints={"device_signal": {"outcome": "answered"}},
        ),
        report,
        "1",
    )

    assert not _passed(report, "accounts for the payload")


def test_an_endpoint_that_answered_nothing_is_a_failure() -> None:
    """The inverse drift: the map says answered and no block arrived."""
    report = Report()
    check_endpoints(
        _artefact(
            {"device_signal": {"rsrp": "1"}},
            endpoints={
                "device_signal": {"outcome": "answered"},
                "sms_count": {"outcome": "answered"},
            },
        ),
        report,
        "1",
    )

    assert not _passed(report, "accounts for the payload")


def test_a_refused_endpoint_explains_its_own_absence() -> None:
    """The point of the map: absent from `data`, accounted for here."""
    report = Report()
    check_endpoints(
        _artefact(
            {"device_signal": {"rsrp": "1"}},
            endpoints={
                "device_signal": {"outcome": "answered"},
                "security_sip": {"outcome": "refused", "code": "100002"},
            },
        ),
        report,
        "1",
    )

    assert report.failed == 0


def test_an_unknown_outcome_is_a_failure() -> None:
    """The vocabulary is closed; a new verdict must be added deliberately."""
    report = Report()
    check_endpoints(
        _artefact(
            {"device_signal": {"rsrp": "1"}},
            endpoints={
                "device_signal": {"outcome": "answered"},
                "security_sip": {"outcome": "something_new"},
            },
        ),
        report,
        "1",
    )

    assert not _passed(report, "known verdicts")


def test_an_empty_map_is_a_failure() -> None:
    """A poll that recorded no outcomes at all did not run, or did not record."""
    report = Report()
    check_endpoints(_artefact(endpoints={}), report, "1")

    assert not _passed(report, "the endpoint map is populated")


# ---------------------------------------------------------------------------
# check_sabotage — the expiry codes, against what the router actually answered
# ---------------------------------------------------------------------------


def test_a_sabotaged_run_classified_as_expired_passes() -> None:
    """The expected outcome: the session went, and `api.py` knew it had."""
    report = Report()
    check_sabotage(
        _artefact(
            rejection={"verdict": "expired", "code": "125002", "key": "device_signal"},
            endpoints={
                "device_information": {"outcome": "answered"},
                "device_signal": {"outcome": "expired", "code": "125002"},
            },
        ),
        report,
        "1",
    )

    assert report.failed == 0


def test_a_lost_session_read_as_refused_is_a_failure() -> None:
    """The finding this check exists to produce, and it is about `api.py`.

    A router answering an expiry with a code outside the three `api.py` keys on
    is classified `refused`, which means the integration retries the endpoint
    forever instead of re-logging in. The script cannot fix that; it can make
    the run fail and name the code.
    """
    report = Report()
    check_sabotage(
        _artefact(
            rejection={"verdict": "refused", "code": "999999"},
            endpoints={"device_signal": {"outcome": "refused", "code": "999999"}},
        ),
        report,
        "1",
    )

    assert not _passed(report, "classified as an expiry")
    assert not _passed(report, "one api.py classifies on")


def test_a_sabotage_that_did_not_land_is_a_failure() -> None:
    """Every endpoint answering means the session was never actually lost."""
    report = Report()
    check_sabotage(
        _artefact(
            rejection={"verdict": "expired", "code": "125002"},
            endpoints={"device_signal": {"outcome": "answered"}},
        ),
        report,
        "1",
    )

    assert not _passed(report, "names what the lost session cost")


def test_a_sabotaged_run_that_recorded_nothing_is_a_failure() -> None:
    """A session taken away and no rejection recorded is the original defect."""
    report = Report()
    check_sabotage(_artefact(), report, "1")

    assert not _passed(report, "recorded as a rejection")


@pytest.mark.parametrize("code", EXPIRY_CODES)
def test_each_documented_expiry_code_is_accepted(code: str) -> None:
    """The three codes `api.py` classifies on are the three checked for."""
    report = Report()
    check_sabotage(
        _artefact(
            rejection={"verdict": "expired", "code": code},
            endpoints={"device_signal": {"outcome": "expired", "code": code}},
        ),
        report,
        "1",
    )

    assert report.failed == 0
