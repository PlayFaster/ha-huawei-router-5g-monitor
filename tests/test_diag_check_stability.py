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
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.diag_check import (
    EXPIRY_CODES,
    LOGIN_BOUND,
    LoginBudget,
    Report,
    RunStoppedError,
    _midpoll_ensure,
    _recording_get_data,
    _refusal_ensure,
    _sabotaging_ensure,
    _secrets,
    _select_entry,
    _serialize,
    check_captures,
    check_endpoints,
    check_health,
    check_mid_poll,
    check_probes,
    check_redaction,
    check_refusal,
    check_refusal_expired,
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
        "premise": {"outcome": "not_made", "code": None},
        "probe_sessions_lost": 0,
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
        "premise",
        "probe_sessions_lost",
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


def test_a_map_matching_the_payload_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every block came from an endpoint that answered, and vice versa."""
    # These maps carry no `voice_volte` or `onekey_diag`, which a library
    # that has them must answer; the case is about payload accounting.
    _old_library(monkeypatch, supports=False)
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


def test_a_refused_endpoint_explains_its_own_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The point of the map: absent from `data`, accounted for here."""
    # These maps carry no `voice_volte` or `onekey_diag`, which a library
    # that has them must answer; the case is about payload accounting.
    _old_library(monkeypatch, supports=False)
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


def _old_library(monkeypatch: pytest.MonkeyPatch, *, supports: bool) -> None:
    """Make the script believe the loaded library has, or lacks, the added methods."""
    monkeypatch.setattr("scripts.diag_check.library_supports", lambda _first: supports)


def test_unsupported_is_a_known_verdict_for_an_added_endpoint_on_an_old_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Below the first version the two added endpoints may read `unsupported`."""
    _old_library(monkeypatch, supports=False)
    report = Report()
    check_endpoints(
        _artefact(
            {"device_signal": {"rsrp": "1"}},
            endpoints={
                "device_signal": {"outcome": "answered"},
                "voice_volte": {"outcome": "unsupported"},
                "onekey_diag": {"outcome": "unsupported"},
            },
        ),
        report,
        "1",
    )

    assert _passed(report, "known verdicts")


def test_unsupported_on_any_other_endpoint_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`unsupported` must not become a way for an ordinary endpoint to pass."""
    _old_library(monkeypatch, supports=False)
    report = Report()
    check_endpoints(
        _artefact(
            {"device_signal": {"rsrp": "1"}},
            endpoints={
                "device_signal": {"outcome": "answered"},
                "security_sip": {"outcome": "unsupported"},
            },
        ),
        report,
        "1",
    )

    assert not _passed(report, "known verdicts")


def test_unsupported_on_a_library_that_has_the_method_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At or above the first version the two endpoints must answer."""
    _old_library(monkeypatch, supports=True)
    report = Report()
    check_endpoints(
        _artefact(
            {"device_signal": {"rsrp": "1"}},
            endpoints={
                "device_signal": {"outcome": "answered"},
                "voice_volte": {"outcome": "unsupported"},
                "onekey_diag": {"outcome": "answered"},
            },
        ),
        report,
        "1",
    )

    assert not _passed(report, "known verdicts")
    assert not _passed(report, "voice_volte answered on a library that has it")
    assert _passed(report, "onekey_diag answered on a library that has it")


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


def test_a_sabotage_run_where_every_endpoint_is_answered_or_unsupported_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On an old library the two skipped endpoints must not fake a disturbance.

    The check passes when any endpoint is not `answered`. On 1.11.0 the two
    `unsupported` endpoints would satisfy it on every run, so a sabotage that
    never took effect would still pass.
    """
    _old_library(monkeypatch, supports=False)
    report = Report()
    check_sabotage(
        _artefact(
            rejection={"verdict": "expired", "code": "125002"},
            endpoints={
                "device_signal": {"outcome": "answered"},
                "voice_volte": {"outcome": "unsupported"},
                "onekey_diag": {"outcome": "unsupported"},
            },
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


# ---------------------------------------------------------------------------
# check_probes - the sweep's two new verdicts (dev16 plan I4)
# ---------------------------------------------------------------------------


def test_probe_verdicts_not_run_and_session_lost_are_accepted() -> None:
    """A sweep cut short, or a session that ended, is a known verdict."""
    artefact = _artefact()
    artefact["probes"] = {
        "a": {"outcome": "answered", "type": "dict"},
        "b": {"outcome": "session_lost"},
        "c": {"outcome": "not_run", "reason": "login_failed"},
    }

    report = Report()
    check_probes(artefact, report, "1")

    assert _passed(report, "every probe outcome is a known verdict")


def test_an_unknown_probe_verdict_is_still_a_failure() -> None:
    """The set is closed: a verdict nobody has named fails the check."""
    artefact = _artefact()
    artefact["probes"] = {"a": {"outcome": "mystery"}}

    report = Report()
    check_probes(artefact, report, "1")

    assert not _passed(report, "every probe outcome is a known verdict")


# ---------------------------------------------------------------------------
# The modes of the live check (dev16 plan I2)
# ---------------------------------------------------------------------------
#
# The modes patch the client the integration holds and are run against real
# routers by hand. These tests hold the patches themselves: each one has an
# effect, and removing the effect fails the test that names it. A wrapper that
# silently stops acting would let a live run report a recovery that never had
# anything to recover from.


class _Group:
    """A stand-in for one endpoint group of the library client."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def status(self) -> str:
        self.calls.append("status")
        return "answered"

    def net_mode(self) -> str:
        self.calls.append("net_mode")
        return "answered"


def _fake_client() -> Any:
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    return SimpleNamespace(
        monitoring=_Group(), net=_Group(), user=MagicMock(), logouts=0
    )


def _original_ensure(clients: list[Any]) -> Any:
    """An `_ensure_client` that hands out a new fake client on each call."""

    async def original(_self: Any) -> Any:
        client = _fake_client()
        clients.append(client)
        return client

    return original


async def test_the_sabotage_wrapper_logs_every_session_out() -> None:
    """The existing mode: the session is ended before the poll uses it."""
    clients: list[Any] = []
    ensure = _sabotaging_ensure(_original_ensure(clients))

    await ensure(None)
    await ensure(None)

    assert len(clients) == 2
    for client in clients:
        client.user.logout.assert_called_once()


async def test_the_mid_poll_wrapper_ends_the_first_session_after_the_endpoint() -> None:
    """`monitoring.status` answers, then the session is logged out, once."""
    clients: list[Any] = []
    ensure = _midpoll_ensure(_original_ensure(clients), {})

    first = await ensure(None)
    assert first.user.logout.call_count == 0  # nothing yet: it acts mid-poll
    assert first.monitoring.status() == "answered"
    first.user.logout.assert_called_once()

    second = await ensure(None)
    assert second.monitoring.status() == "answered"
    second.user.logout.assert_not_called()  # the retry's session is left alone


async def test_the_refusal_wrapper_raises_a_100003_on_the_first_session_only() -> None:
    """The simulated refusal is the library's own exception, once."""
    from huawei_lte_api.exceptions import ResponseErrorLoginRequiredException

    clients: list[Any] = []
    ensure = _refusal_ensure(_original_ensure(clients), {}, "net_mode", expire=False)

    first = await ensure(None)
    with pytest.raises(ResponseErrorLoginRequiredException) as caught:
        first.net.net_mode()
    assert str(caught.value.code) == "100003"
    first.user.logout.assert_not_called()  # the session stays live

    second = await ensure(None)
    assert second.net.net_mode() == "answered"


async def test_the_refusal_wrapper_can_end_the_session_with_the_refusal() -> None:
    """With `expire` the same refusal also logs the session out."""
    from huawei_lte_api.exceptions import ResponseErrorLoginRequiredException

    clients: list[Any] = []
    ensure = _refusal_ensure(_original_ensure(clients), {}, "net_mode", expire=True)

    first = await ensure(None)
    with pytest.raises(ResponseErrorLoginRequiredException):
        first.net.net_mode()

    first.user.logout.assert_called_once()


def test_every_refusable_endpoint_names_a_real_library_method() -> None:
    """The table the refusal mode reads must point at methods that exist."""
    from huawei_lte_api.Client import Client

    from scripts.diag_check import REFUSABLE

    for key, (group, method) in REFUSABLE.items():
        client_group = getattr(Client(MagicMock()), group)
        assert callable(getattr(client_group, method)), key


async def test_the_recording_wrapper_remembers_an_expiry_the_retry_clears() -> None:
    """The coordinator's retry clears the rejection, so the exception is the evidence."""
    from custom_components.huawei_router_5g.api import HuaweiAuthError

    seen: list[str] = []

    async def failing(_self: Any) -> Any:
        raise HuaweiAuthError("expired")

    async def working(_self: Any) -> Any:
        return {"ok": 1}

    with pytest.raises(HuaweiAuthError):
        await _recording_get_data(failing, seen)(None)
    assert await _recording_get_data(working, seen)(None) == {"ok": 1}
    assert seen == ["HuaweiAuthError"]


# ---------------------------------------------------------------------------
# The entry option
# ---------------------------------------------------------------------------

_ENTRIES = [
    {
        "domain": "other",
        "entry_id": "x",
        "title": "Other",
        "options": {"host": "other"},
        "data": {},
    },
    {
        "domain": "huawei_router_5g",
        "entry_id": "aaa111",
        "title": "Huawei H165",
        "options": {"host": "http://192.168.252.1", "password": "h165-secret-pw"},
        "data": {"mac": "aa:bb:cc:00:00:01"},
    },
    {
        "domain": "huawei_router_5g",
        "entry_id": "bbb222",
        "title": "Huawei B315",
        "options": {"host": "http://192.168.8.1", "password": "b315-secret-pw"},
        "data": {"mac": "aa:bb:cc:00:00:02"},
    },
]


def test_no_selector_takes_the_first_router_entry() -> None:
    """The behavior before the option existed is unchanged."""
    assert _select_entry(_ENTRIES, None)["entry_id"] == "aaa111"


@pytest.mark.parametrize("selector", ["bbb222", "huawei b315", "192.168.8"])
def test_a_selector_matches_an_id_a_title_or_part_of_a_host(selector: str) -> None:
    """Any of the three names picks the same entry."""
    assert _select_entry(_ENTRIES, selector)["entry_id"] == "bbb222"


def test_a_selector_that_matches_nothing_lists_what_is_configured() -> None:
    """No guess: the run stops and says which entries exist."""
    with pytest.raises(SystemExit) as stopped:
        _select_entry(_ENTRIES, "nonesuch")

    assert "Huawei H165" in str(stopped.value)
    assert "Huawei B315" in str(stopped.value)


def test_the_redaction_secrets_come_from_the_chosen_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checking the B315 must not look for the H165's password, or the reverse."""
    import json

    from scripts import diag_check

    path = tmp_path / "core.config_entries"
    path.write_text(json.dumps({"data": {"entries": _ENTRIES}}), encoding="utf-8")
    monkeypatch.setattr(diag_check, "CONFIG_ENTRIES", path)

    options, data, entry_id, _ = diag_check._credentials("B315")
    secrets = _secrets(options, data)

    assert entry_id == "bbb222"
    assert "b315-secret-pw" in secrets
    assert "h165-secret-pw" not in secrets
    assert "aa:bb:cc:00:00:02" in secrets


async def test_the_entry_option_reaches_both_produce_and_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`produce` builds the client and `main` draws the secrets, from one entry."""
    from scripts import diag_check

    selectors: list[str | None] = []

    class _HaltError(Exception):
        pass

    def credentials(selector: str | None = None) -> Any:
        selectors.append(selector)
        raise _HaltError

    monkeypatch.setattr(diag_check, "_credentials", credentials)

    with pytest.raises(_HaltError):
        await diag_check.produce("x", Report(), entry="H165")
    assert selectors == ["H165"]

    selectors.clear()
    monkeypatch.setattr(sys, "argv", ["diag_check.py", "--entry", "B315"])
    with pytest.raises(_HaltError):
        await diag_check.main()
    assert selectors == ["B315"]


# ---------------------------------------------------------------------------
# The login bound
# ---------------------------------------------------------------------------


def test_the_login_budget_counts_and_stops_at_its_bound() -> None:
    """Twelve logins, then the run ends before a thirteenth."""
    budget = LoginBudget(bound=3)
    create = budget.wrap(lambda _api: "connection")

    assert [create(None) for _ in range(3)] == ["connection"] * 3
    assert budget.count == 3
    with pytest.raises(RunStoppedError):
        create(None)
    assert budget.stopped is not None
    assert budget.count == 3


def test_the_login_budget_stops_at_the_first_already_logged_in() -> None:
    """The router saying it holds a session is the first sign of the lockout."""
    from huawei_lte_api.exceptions import LoginErrorAlreadyLoginException

    def refuse(_api: Any) -> Any:
        raise LoginErrorAlreadyLoginException("already", 108002)

    budget = LoginBudget()
    create = budget.wrap(refuse)

    with pytest.raises(LoginErrorAlreadyLoginException):
        create(None)
    assert budget.stopped is not None
    with pytest.raises(RunStoppedError):
        create(None)
    assert budget.count == 1  # the second attempt was never made


def test_the_default_login_bound_is_twelve() -> None:
    """The bound the plan states for one router."""
    assert LoginBudget().bound == 12 == LOGIN_BOUND


def test_a_run_stop_passes_through_the_librarys_exception_handlers() -> None:
    """`api.py` wraps login failures in `except Exception`, which must not catch this."""
    assert not issubclass(RunStoppedError, Exception)


# ---------------------------------------------------------------------------
# The checks of the three modes
# ---------------------------------------------------------------------------


def _endpoints_artefact(
    answered: list[str], extra: dict[str, Any] | None = None, **top: Any
) -> dict[str, Any]:
    artefact = _artefact(endpoints={key: {"outcome": "answered"} for key in answered})
    artefact["endpoints"].update(extra or {})
    artefact.update(top)
    return artefact


def test_the_mid_poll_check_needs_the_expiry_and_a_full_recovery() -> None:
    """Passes only if the session was met dead and nothing was lost."""
    baseline = _endpoints_artefact(["a", "b", "c"])

    good = _endpoints_artefact(["a", "b", "c"], _auth_errors=["HuaweiAuthError"])
    report = Report()
    check_mid_poll(good, baseline, report, "m")
    assert report.failed == 0

    no_expiry = _endpoints_artefact(["a", "b", "c"], _auth_errors=[])
    report = Report()
    check_mid_poll(no_expiry, baseline, report, "m")
    assert _passed(report, "the dead session was met") is False

    lost = _endpoints_artefact(["a", "b"], _auth_errors=["HuaweiAuthError"])
    report = Report()
    check_mid_poll(lost, baseline, report, "m")
    assert _passed(report, "every endpoint the clean pass answered") is False


def test_the_refusal_check_needs_the_judgment_the_premise_and_the_rest() -> None:
    """The recorded refusal, its judgment, the premise and the other endpoints."""
    baseline = _endpoints_artefact(["a", "b", "c"])
    good = _endpoints_artefact(
        ["a", "c"],
        {"b": {"outcome": "refused", "code": "100003", "judged": "live_session"}},
        premise={"outcome": "refused", "code": "100003"},
        _auth_errors=[],
    )

    report = Report()
    check_refusal(good, baseline, report, "r", "b")
    assert report.failed == 0

    for broken_key, broken in (
        ("judged", {"b": {"outcome": "refused", "code": "100003"}}),
        ("recorded refused", {"b": {"outcome": "answered"}}),
    ):
        artefact = dict(good)
        artefact["endpoints"] = {**good["endpoints"], **broken}
        report = Report()
        check_refusal(artefact, baseline, report, "r", "b")
        assert report.failed >= 1, broken_key

    no_premise = dict(good, premise={"outcome": "served", "code": None})
    report = Report()
    check_refusal(no_premise, baseline, report, "r", "b")
    assert _passed(report, "the premise check") is False

    lost = _endpoints_artefact(
        ["a"],
        {"b": {"outcome": "refused", "code": "100003", "judged": "live_session"}},
        premise={"outcome": "refused", "code": "100003"},
        _auth_errors=[],
    )
    report = Report()
    check_refusal(lost, baseline, report, "r", "b")
    assert _passed(report, "the rest of the poll answered") is False


def test_the_refusal_expired_check_needs_the_raise() -> None:
    """The same refusal with the session ended must raise `HuaweiAuthError`."""
    baseline = _endpoints_artefact(["a", "b"])
    good = _endpoints_artefact(
        ["a", "b"],
        premise={"outcome": "refused", "code": "100003"},
        _auth_errors=["HuaweiAuthError"],
    )

    report = Report()
    check_refusal_expired(good, baseline, report, "e")
    assert report.failed == 0

    silent = dict(good, _auth_errors=[])
    report = Report()
    check_refusal_expired(silent, baseline, report, "e")
    assert _passed(report, "raised HuaweiAuthError") is False


def test_the_health_check_needs_refused_endpoints_listed_as_not_served() -> None:
    """Every endpoint refused with a router code is `not_served`, none is degraded."""
    artefact = _endpoints_artefact(
        ["a"],
        {"sms_list": {"outcome": "refused", "code": "125003"}},
        _health={"not_served": ["SMS messages"], "degraded_capabilities": []},
    )
    report = Report()
    check_health(artefact, report, "h", 1)
    assert report.failed == 0

    degraded = dict(
        artefact,
        _health={
            "not_served": ["SMS messages"],
            "degraded_capabilities": ["SMS messages"],
        },
    )
    report = Report()
    check_health(degraded, report, "h", 1)
    assert _passed(report, "no refused endpoint is also degraded") is False

    unlisted = dict(artefact, _health={"not_served": [], "degraded_capabilities": []})
    report = Report()
    check_health(unlisted, report, "h", 1)
    assert _passed(report, "not_served lists the endpoints the router refuses") is False
    assert _passed(report, "not_served holds 1 endpoint") is False


def test_the_health_check_expects_none_on_a_router_that_refuses_nothing() -> None:
    """The reference unit: nothing refused, so nothing is `not_served`."""
    artefact = _endpoints_artefact(
        ["a", "b"], _health={"not_served": [], "degraded_capabilities": []}
    )
    report = Report()
    check_health(artefact, report, "h", 0)

    assert report.failed == 0


def test_the_health_timestamp_changing_is_not_instability() -> None:
    """`_health` carries `last_good_update`, the clock reading of the last poll.

    Two runs minutes apart always differ in it. Any other change in the health
    snapshot is still a difference.
    """
    first = _artefact()
    first["_health"] = {
        "severity": "ok",
        "last_good_update": "2026-10-06T09:00:00+00:00",
    }
    second = _artefact()
    second["_health"] = {
        "severity": "ok",
        "last_good_update": "2026-10-06T09:21:00+00:00",
    }

    report = Report()
    check_stability(first, second, report)
    assert _passed(report, "no stable value changed")

    second["_health"]["severity"] = "degraded"
    report = Report()
    check_stability(first, second, report)
    assert not _passed(report, "no stable value changed")
