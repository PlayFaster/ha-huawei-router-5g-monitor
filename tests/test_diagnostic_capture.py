"""Tests for the rejection and login captures the diagnostics download carries.

`coordinator.data` is `None` until the first successful poll, so an integration
that has never succeeded produces an empty `data` block — which is exactly when
a download is asked for. `api.last_rejection` and `api.login_metadata` carry
what was rejected and what the login saw.

**Aligned with `zte_router_5g`**, the reference implementation: same attribute
names, same `verdict` vocabulary, same clearing rule, and the same case names
where the case exists in both projects. Two of its cases have no counterpart
here and are absent rather than stubbed — a key presence map, because this
router states expiry through its own error codes rather than leaving it to be
inferred from which keys came back blank, and a body preview, because
`huaweiapi` parses the response and this wrapper never sees a raw body.

The assertions on the produced file live in `test_diagnostics_artefact.py`. A
capture can be correct on the API client and never reach the download; that is
a defect `zte_router_5g` shipped in `[3.3.9-dev5]` and found by hand two
releases later, and it is why the two files are separate.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from huawei_lte_api.exceptions import (
    LoginErrorPasswordWrongException,
    ResponseErrorException,
    ResponseErrorLoginRequiredException,
)
import pytest

from custom_components.huawei_router_5g.api import (
    HuaweiAuthError,
    HuaweiConnectionError,
    HuaweiRouter5GAPI,
)

# Distinctive so a substring search over the whole record is conclusive. The
# shared fixtures use "password", which appears in library text and in field
# names and so cannot prove absence.
SECRET = "sekrit_hunter2"


def _make_api() -> HuaweiRouter5GAPI:
    return HuaweiRouter5GAPI("http://192.168.8.1", "admin", SECRET)


def _error(code: str) -> ResponseErrorException:
    """Build the library's error carrying a router response code.

    The library takes the message and the code positionally, and every other
    suite in this project builds them the same way.
    """
    return ResponseErrorException("refused", code)


# ---------------------------------------------------------------------------
# _record_verdict — retention, clearing, and what a record carries
# ---------------------------------------------------------------------------


def test_a_new_client_holds_no_rejection() -> None:
    """Nothing has been rejected before anything has been asked."""
    api = _make_api()
    assert api.last_rejection is None
    assert api.login_metadata == {}


def test_a_rejected_response_is_retained_with_its_verdict() -> None:
    """The verdict, the router's code and the endpoint are all held."""
    api = _make_api()
    api._record_verdict("refused", code="100002", key="device_signal")

    assert api.last_rejection == {
        "verdict": "refused",
        "code": "100002",
        "key": "device_signal",
    }


def test_a_live_verdict_clears_a_previous_rejection() -> None:
    """A stale rejection must not outlive the fault that produced it."""
    api = _make_api()
    api._record_verdict("expired", code="125002")
    assert api.last_rejection is not None

    api._record_verdict("live")
    assert api.last_rejection is None


def test_only_the_most_recent_rejection_is_held() -> None:
    """The record is bounded to one, as in `zte_router_5g`."""
    api = _make_api()
    api._record_verdict("expired", code="125002", key="monitoring_status")
    api._record_verdict("refused", code="100002", key="device_signal")

    assert api.last_rejection is not None
    assert api.last_rejection["verdict"] == "refused"
    assert api.last_rejection["key"] == "device_signal"


def test_an_absent_code_is_omitted_rather_than_recorded_as_none() -> None:
    """A transport failure carries no router code, and says so by omission."""
    api = _make_api()
    api._record_verdict("unavailable", key="sms_list")

    assert api.last_rejection is not None
    assert "code" not in api.last_rejection


def test_the_retained_payload_is_copied_not_referenced() -> None:
    """A later mutation of the live payload must not rewrite the evidence."""
    api = _make_api()
    payload = {"device_information": {"DeviceName": "B535s-232"}}
    api._record_verdict("refused", code="100002", payload=payload)

    payload["device_information"] = {"DeviceName": "changed"}

    assert api.last_rejection is not None
    assert api.last_rejection["payload"]["device_information"] == {
        "DeviceName": "B535s-232"
    }


# ---------------------------------------------------------------------------
# Capture at the point of rejection, not the point of raising
# ---------------------------------------------------------------------------


async def test_an_expiry_is_recorded_before_the_retry_that_recovers_it() -> None:
    """The evidence survives a recovery.

    `_execute_with_retry` re-logs in and retries, so recording at the raise
    would leave nothing behind in the common case where the retry succeeds.
    """
    api = _make_api()
    client = MagicMock()
    calls: list[int] = []

    def _func(_client):
        calls.append(1)
        if len(calls) == 1:
            raise ResponseErrorLoginRequiredException("Login required", "100001")
        return {"ok": True}

    with (
        patch.object(api, "_ensure_client", return_value=client),
        patch.object(api, "_reset_client"),
    ):
        result = await api._execute_with_retry(_func)

    assert result == {"ok": True}
    # `ResponseErrorLoginRequiredException` subclasses `ResponseErrorException`
    # and so carries a code of its own, which is retained rather than discarded
    # because the classification did not need it.
    assert api.last_rejection == {"verdict": "expired", "code": "100001"}


@pytest.mark.parametrize("code", ["125002", "125003", "100003"])
async def test_each_expiry_code_is_recorded_as_expired(code: str) -> None:
    """The three codes this router uses for expiry all read as one verdict."""
    api = _make_api()
    client = MagicMock()
    calls: list[int] = []

    def _func(_client):
        calls.append(1)
        if len(calls) == 1:
            raise _error(code)
        return {"ok": True}

    with (
        patch.object(api, "_ensure_client", return_value=client),
        patch.object(api, "_reset_client"),
    ):
        await api._execute_with_retry(_func)

    assert api.last_rejection is not None
    assert api.last_rejection["verdict"] == "expired"
    assert api.last_rejection["code"] == code


async def test_a_non_expiry_error_is_recorded_as_refused_and_still_raises() -> None:
    """A code the router owns is evidence; it does not become a retry."""
    api = _make_api()
    client = MagicMock()

    def _func(_client):
        raise _error("100002")

    with (
        patch.object(api, "_ensure_client", return_value=client),
        pytest.raises(ResponseErrorException),
    ):
        await api._execute_with_retry(_func)

    assert api.last_rejection == {"verdict": "refused", "code": "100002"}


# ---------------------------------------------------------------------------
# _record_login_metadata — outcome only, never a credential
# ---------------------------------------------------------------------------


async def test_login_metadata_records_a_successful_login() -> None:
    """A login that produced a client records the outcome and nothing else."""
    api = _make_api()
    with patch.object(
        api, "_create_connection_sync", return_value=(MagicMock(), MagicMock())
    ):
        await api._login_internal()

    assert api.login_metadata == {
        "result": "ok",
        "username_configured": True,
        "error": None,
    }


async def test_login_metadata_records_a_rejected_credential() -> None:
    """The exception's class is recorded; its message never is."""
    api = _make_api()
    with (
        patch.object(
            api,
            "_create_connection_sync",
            side_effect=LoginErrorPasswordWrongException("Wrong password", "108003"),
        ),
        pytest.raises(HuaweiAuthError),
    ):
        await api._login_internal()

    assert api.login_metadata["result"] == "auth_failed"
    assert api.login_metadata["error"] == "LoginErrorPasswordWrongException"


async def test_login_metadata_records_an_unreachable_router() -> None:
    """A transport failure is a different outcome from a refused credential."""
    api = _make_api()
    with (
        patch.object(
            api, "_create_connection_sync", side_effect=OSError("no route to host")
        ),
        pytest.raises(HuaweiConnectionError),
    ):
        await api._login_internal()

    assert api.login_metadata["result"] == "connection_failed"
    assert api.login_metadata["error"] == "OSError"


async def test_login_metadata_never_carries_the_credential() -> None:
    """The password must not appear anywhere in the record, on any outcome.

    Asserted over the whole structure rather than key by key, following
    `zte_router_5g.test_login_metadata_never_carries_a_cookie_value`: a
    key-by-key assertion only finds the leaks somebody already thought of.
    The library's own message is made to carry the credential here, because
    interpolating it into the exception text is how it would escape.
    """
    api = _make_api()
    with (
        patch.object(
            api,
            "_create_connection_sync",
            side_effect=LoginErrorPasswordWrongException(
                f"rejected {SECRET}", "108003"
            ),
        ),
        pytest.raises(HuaweiAuthError),
    ):
        await api._login_internal()

    assert SECRET not in str(api.login_metadata)


# ---------------------------------------------------------------------------
# _record_endpoint — every endpoint's outcome, so an absence can be read
# ---------------------------------------------------------------------------


def test_a_new_client_holds_no_endpoint_outcomes() -> None:
    """Nothing has been polled before anything has been asked."""
    assert _make_api().endpoint_outcomes == {}


def test_an_outcome_carries_its_code_when_the_router_gave_one() -> None:
    """Names and codes only — no values reach this map."""
    api = _make_api()
    api._record_endpoint("security_sip", "refused", "100002")

    assert api.endpoint_outcomes == {
        "security_sip": {"outcome": "refused", "code": "100002"}
    }


def test_an_outcome_without_a_code_omits_the_field() -> None:
    """A transport failure has no router code, and says so by omission."""
    api = _make_api()
    api._record_endpoint("sms_list", "unavailable")

    assert api.endpoint_outcomes == {"sms_list": {"outcome": "unavailable"}}


def test_a_second_poll_replaces_the_map_rather_than_accumulating() -> None:
    """The map describes one pass. A union of two passes describes neither."""
    api = _make_api()
    api._record_endpoint("security_sip", "refused", "100002")
    api.endpoint_outcomes = {}
    api._record_endpoint("device_signal", "answered", result={"a": "1"})

    assert api.endpoint_outcomes == {
        "device_signal": {
            "outcome": "answered",
            "type": "dict",
            "keys": 1,
            "populated": 1,
        }
    }


def test_an_answered_endpoint_reports_how_much_it_actually_returned() -> None:
    """`answered` alone cannot tell a full block from an empty one.

    Firmware that knows an endpoint, answers it politely and populates nothing
    is the common case on a model this integration has not seen, and it is
    indistinguishable from a healthy read without these counts.
    """
    api = _make_api()
    api._record_endpoint(
        "device_signal", "answered", result={"rsrp": "-95", "nrrsrp": "", "sinr": None}
    )

    assert api.endpoint_outcomes["device_signal"] == {
        "outcome": "answered",
        "type": "dict",
        "keys": 3,
        "populated": 1,
    }


def test_an_endpoint_returning_something_other_than_a_mapping_says_so() -> None:
    """Measured on the reference H165: `voice_busy` answers the string `Idle`.

    A router returning a scalar where this integration expects a mapping is a
    real shape difference, and the type is the only thing that names it.
    """
    api = _make_api()
    api._record_endpoint("voice_busy", "answered", result="Idle")

    assert api.endpoint_outcomes["voice_busy"] == {
        "outcome": "answered",
        "type": "str",
    }


# ---------------------------------------------------------------------------
# probe_diagnostic_endpoints — the sweep over endpoints the poll never touches
# ---------------------------------------------------------------------------


async def test_the_sweep_calls_every_probe_on_one_session() -> None:
    """One login for the whole sweep, and no re-login on a failure.

    This is the property the sweep exists to hold. Routed through
    `_execute_with_retry`, a `100003` costs a second login, and a 42-endpoint
    sweep accumulated enough churn on the reference H165 to leave the router
    refusing connections — measured 2026-09-07 and recorded in
    `docs/huawei_how_to_access.md`.
    """
    api = _make_api()
    logins = {"n": 0}

    async def counting() -> Any:
        logins["n"] += 1
        return MagicMock()

    with (
        patch.object(api, "_ensure_client", side_effect=counting),
        patch.object(
            type(api),
            "DIAGNOSTIC_PROBES",
            (
                ("a", lambda _c: {"x": "1"}),
                ("b", lambda _c: (_ for _ in ()).throw(_error("100003"))),
                ("c", lambda _c: {"y": "2"}),
            ),
        ),
    ):
        result = await api.probe_diagnostic_endpoints()

    assert logins["n"] == 1
    assert sorted(result) == ["a", "b", "c"]


async def test_a_refused_probe_carries_the_routers_code() -> None:
    """A refusal is the finding, recorded with the code the router gave."""
    api = _make_api()
    with (
        patch.object(api, "_ensure_client", return_value=MagicMock()),
        patch.object(
            type(api),
            "DIAGNOSTIC_PROBES",
            (("refused_one", lambda _c: (_ for _ in ()).throw(_error("100002"))),),
        ),
    ):
        result = await api.probe_diagnostic_endpoints()

    assert result["refused_one"] == {"outcome": "refused", "code": "100002"}


async def test_one_failure_never_stops_the_sweep() -> None:
    """The shape of the set of failures is the point, not the first one."""
    api = _make_api()
    with (
        patch.object(api, "_ensure_client", return_value=MagicMock()),
        patch.object(
            type(api),
            "DIAGNOSTIC_PROBES",
            (
                ("first", lambda _c: (_ for _ in ()).throw(OSError("gone"))),
                ("second", lambda _c: {"k": "v"}),
            ),
        ),
    ):
        result = await api.probe_diagnostic_endpoints()

    assert result["first"] == {"outcome": "unavailable", "error": "OSError"}
    assert result["second"]["outcome"] == "answered"


async def test_a_probe_publishes_key_names_but_never_values() -> None:
    """Names are a property of the firmware; values are the household's.

    A value from an endpoint nobody here has seen has no entry in
    `diagnostics.py`'s key lists and would be published intact by a sanitizer
    that matches on exact key names.
    """
    api = _make_api()
    with (
        patch.object(api, "_ensure_client", return_value=MagicMock()),
        patch.object(
            type(api),
            "DIAGNOSTIC_PROBES",
            (("block", lambda _c: {"Ssid": "TheSmiths-5G", "Empty": ""}),),
        ),
    ):
        result = await api.probe_diagnostic_endpoints()

    assert result["block"]["keys"] == ["Empty", "Ssid"]
    assert result["block"]["populated"] == 1
    assert "TheSmiths-5G" not in str(result)


async def test_a_probe_returning_a_scalar_reports_its_type() -> None:
    """Measured on the reference H165: `voice_busy` answers the string `Idle`."""
    api = _make_api()
    with (
        patch.object(api, "_ensure_client", return_value=MagicMock()),
        patch.object(type(api), "DIAGNOSTIC_PROBES", (("scalar", lambda _c: "Idle"),)),
    ):
        result = await api.probe_diagnostic_endpoints()

    assert result["scalar"]["type"] == "str"
    assert "keys" not in result["scalar"]


def test_the_excluded_probes_name_their_reason() -> None:
    """An endpoint left out on purpose says why, so nobody adds it back blind."""
    excluded = dict(_make_api().PROBES_EXCLUDED)

    assert "system.onlinestate" in excluded
    assert all(reason for reason in excluded.values())


def test_no_excluded_endpoint_is_also_probed() -> None:
    """The two lists must not disagree about the same endpoint."""
    api = _make_api()
    probed = {key for key, _ in api.DIAGNOSTIC_PROBES}
    excluded = {name.replace(".", "_") for name, _ in api.PROBES_EXCLUDED}

    assert not probed & excluded
