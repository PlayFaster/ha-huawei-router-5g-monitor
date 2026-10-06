"""A refused endpoint is told from an expired session, driven through a real poll.

Dev16 plan I1, issue 50. A router can answer 100003 to one optional endpoint
while the session is live, and the fetch loop used to read that as an expiry:
the setup then failed with `invalid_auth` although the login had worked. The
loop now separates the two with an anonymous premise check (does this router
refuse `device_information` without a login?) and a re-read of
`device_information` on the live session, and falls back to the history of the
run where the premise cannot be confirmed.

Every test builds a real `HuaweiRouter5GAPI` over the fake transport in
[`transport.py`](transport.py). The only things faked are the HTTP responses;
the premise check, the re-read and the history run for real. The router's own
refusal of a polled endpoint has not been observed on any router held, so the
refusal is served by the fake, and that is stated here and in the plan.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests_mock as requests_mock_module

from custom_components.huawei_router_5g import api as api_module
from custom_components.huawei_router_5g.api import HuaweiAuthError, HuaweiRouter5GAPI
from custom_components.huawei_router_5g.const import (
    ADJUDICATION_BUDGET,
    FETCH_TIMEOUT,
    PREMISE_TIMEOUT,
    REQUEST_TIMEOUT,
)

from .transport import (
    ERROR_NO_RIGHTS,
    ERROR_SYSTEM_CSRF,
    ERROR_WRONG_SESSION_TOKEN,
    RouterTransport,
)

ROUTER_URL = "http://192.168.8.1"

# Every non-critical key of the fetch list, with the path the fake router
# serves it on. `device_information` is the critical one and is not here.
NON_CRITICAL: dict[str, str] = {
    "device_signal": "device/signal",
    "monitoring_status": "monitoring/status",
    "monitoring_check_notifications": "monitoring/check-notifications",
    "traffic_statistics": "monitoring/traffic-statistics",
    "month_statistics": "monitoring/month_statistics",
    "current_plmn": "net/current-plmn",
    "net_mode": "net/net-mode",
    "sms_count": "sms/sms-count",
    "sms_list": "sms/sms-list",
    "mobile_dataswitch": "dialup/mobile-dataswitch",
    "lan_host_info": "lan/HostInfo",
    "wlan_host_list": "wlan/host-list",
    "wlan_wifi_feature_switch": "wlan/wifi-feature-switch",
    "wlan_multi_basic_settings": "wlan/multi-basic-settings",
    "start_date": "monitoring/start_date",
    "converged_status": "monitoring/converged-status",
    "dial_up_profiles": "dialup/profiles",
    "dial_up_connection": "dialup/connection",
    "antenna_type": "device/antenna_type",
    "csps_state": "net/csps_state",
    "security_sip": "security/sip",
    "security_upnp": "security/upnp",
    "voice_busy": "voice/voicebusy",
    "voice_volte": "voice/volte",
    "onekey_diag": "monitoring/onekey_diag",
}

CODES = (ERROR_NO_RIGHTS, ERROR_SYSTEM_CSRF, ERROR_WRONG_SESSION_TOKEN)


@pytest.fixture(name="transport")
def transport_fixture():
    """Serve a working router over the `requests` transport."""
    with requests_mock_module.Mocker() as mocker:
        yield RouterTransport(mocker)


async def _api() -> HuaweiRouter5GAPI:
    """Build a real API object and log it in against the fake router."""
    api = HuaweiRouter5GAPI(ROUTER_URL, "admin", "password")
    await api.login()
    return api


def _outcome(api: HuaweiRouter5GAPI, key: str) -> dict[str, Any]:
    return api.endpoint_outcomes[key]


@pytest.mark.asyncio
@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("key", sorted(NON_CRITICAL))
async def test_a_refused_endpoint_on_a_live_session_is_recorded_refused(
    transport, key, code
):
    """Each non-critical endpoint, each of the three codes, premise confirmed."""
    transport.refuse(NON_CRITICAL[key], code)
    api = await _api()

    data = await api.get_data()

    assert key not in data
    assert data["device_information"]["DeviceName"] == "B535-232"
    assert len(data) == len(NON_CRITICAL)  # every other block, plus the critical
    assert _outcome(api, key)["outcome"] == "refused"
    assert _outcome(api, key)["code"] == str(code)
    assert api.premise_result == {"outcome": "refused", "code": "100003"}
    assert api.last_rejection is not None
    assert api.last_rejection["verdict"] == "refused"


@pytest.mark.asyncio
@pytest.mark.parametrize("code", CODES)
async def test_a_signal_with_the_session_ended_raises_an_auth_error(transport, code):
    """The re-read raising one of the three codes is an expiry.

    The session ends after two authenticated answers, so the third endpoint is
    refused with the router's logged-out code, the premise confirms and the
    re-read of `device_information` is refused too.
    """
    transport.logged_out_code = code
    transport.expire_after = 2
    api = await _api()

    with pytest.raises(HuaweiAuthError):
        await api.get_data()

    assert transport.anonymous_info_reads == 1
    assert api._client is None


@pytest.mark.asyncio
async def test_the_re_read_is_made_at_most_once_per_poll(transport):
    """Two refused endpoints cost one premise check and one re-read."""
    transport.refuse(NON_CRITICAL["device_signal"])
    transport.refuse(NON_CRITICAL["net_mode"])
    api = await _api()

    data = await api.get_data()

    assert "device_signal" not in data
    assert "net_mode" not in data
    assert transport.anonymous_info_reads == 1
    # The poll's own read of `device_information` and the one re-read.
    assert transport.authenticated_info_reads == 2


@pytest.mark.asyncio
async def test_a_healthy_poll_makes_no_anonymous_connection(transport):
    """The premise check is made only when a signal occurs."""
    api = await _api()

    await api.get_data()

    assert transport.anonymous_info_reads == 0
    assert transport.authenticated_info_reads == 1
    assert api.premise_result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("code", CODES)
async def test_device_information_raising_a_signal_is_an_expiry_with_no_premise(
    transport, code
):
    """The critical read is never adjudicated: no premise check, no re-read."""
    transport.refuse("device/information", code)
    api = await _api()

    with pytest.raises(HuaweiAuthError):
        await api.get_data()

    assert transport.anonymous_info_reads == 0
    # The poll's own read. A 125002 is retried once inside the library after it
    # reloads the session, so that code is read twice; none is `api.py`'s
    # re-read, which is made only for a non-critical endpoint.
    assert transport.authenticated_info_reads == (2 if code == ERROR_SYSTEM_CSRF else 1)


@pytest.mark.asyncio
async def test_with_the_premise_answered_a_never_answered_endpoint_is_refused(
    transport,
):
    """A router that serves `device_information` anonymously cannot be tested.

    The premise reads `served`, so the history decides: the endpoint has never
    answered and is recorded refused, the poll returns its data, and no
    re-read is made.
    """
    transport.info_needs_login = False
    transport.refuse(NON_CRITICAL["device_signal"])
    api = await _api()

    data = await api.get_data()

    assert "device_signal" not in data
    assert _outcome(api, "device_signal")["outcome"] == "refused"
    assert api.premise_result == {"outcome": "served", "code": None}
    assert transport.authenticated_info_reads == 1


@pytest.mark.asyncio
async def test_with_the_premise_answered_an_endpoint_that_answered_earlier_raises(
    transport,
):
    """The history reads a signal from an endpoint that answered as an expiry."""
    transport.info_needs_login = False
    api = await _api()
    await api.get_data()
    assert "device_signal" in api.answered_endpoints
    transport.refuse(NON_CRITICAL["device_signal"])

    with pytest.raises(HuaweiAuthError):
        await api.get_data()

    assert transport.authenticated_info_reads == 2  # one per poll, no re-read


@pytest.mark.asyncio
async def test_a_premise_connection_error_leaves_it_unknown_and_is_checked_again(
    transport,
):
    """The premise is not kept after a failure, and the history decides."""
    transport.anonymous_error = True
    transport.refuse(NON_CRITICAL["device_signal"])
    transport.refuse(NON_CRITICAL["net_mode"])
    api = await _api()

    data = await api.get_data()

    assert "device_signal" not in data
    assert _outcome(api, "device_signal")["outcome"] == "refused"
    assert _outcome(api, "net_mode")["outcome"] == "refused"
    # Unknown is not kept, so each of the two signals made its own check.
    assert transport.anonymous_info_reads == 2
    assert transport.authenticated_info_reads == 1
    assert api.premise_result == {"outcome": "unknown", "code": None}

    transport.anonymous_error = False
    await api.get_data()

    assert transport.anonymous_info_reads == 3
    assert api.premise_result == {"outcome": "refused", "code": "100003"}


@pytest.mark.asyncio
async def test_a_premise_connection_error_does_not_excuse_an_answered_endpoint(
    transport,
):
    """With the premise unknown, an endpoint that answered earlier still raises."""
    transport.anonymous_error = True
    api = await _api()
    await api.get_data()
    transport.refuse(NON_CRITICAL["device_signal"])

    with pytest.raises(HuaweiAuthError):
        await api.get_data()


@pytest.mark.asyncio
async def test_with_the_premise_confirmed_an_answered_endpoint_is_refused_when_the_re_read_answers(
    transport,
):
    """An endpoint that answered earlier and now draws a signal on a live session."""
    api = await _api()
    await api.get_data()
    assert "device_signal" in api.answered_endpoints
    transport.refuse(NON_CRITICAL["device_signal"])

    data = await api.get_data()

    assert "device_signal" not in data
    assert data["device_information"]["DeviceName"] == "B535-232"
    assert _outcome(api, "device_signal")["outcome"] == "refused"


@pytest.mark.asyncio
async def test_a_reset_clears_the_premise_and_not_the_history(transport):
    """The premise is read again after a reset; the history survives it."""
    transport.refuse(NON_CRITICAL["device_signal"])
    api = await _api()
    await api.get_data()
    assert transport.anonymous_info_reads == 1
    answered = api.answered_endpoints
    assert "device_information" in answered

    api._reset_client()

    assert api._premise_cache is None
    assert api.answered_endpoints == answered
    await api.login()
    await api.get_data()
    assert transport.anonymous_info_reads == 2


@pytest.mark.asyncio
async def test_a_premise_is_kept_for_the_run(transport):
    """A second poll with a signal does not read the premise again."""
    transport.refuse(NON_CRITICAL["device_signal"])
    api = await _api()
    await api.get_data()
    await api.get_data()

    assert transport.anonymous_info_reads == 1


@pytest.mark.asyncio
async def test_with_the_adjudication_budget_spent_the_history_decides(transport):
    """Past the budget no premise read or re-read is made."""
    assert ADJUDICATION_BUDGET == 10
    assert ADJUDICATION_BUDGET == (
        FETCH_TIMEOUT - 3 * PREMISE_TIMEOUT - REQUEST_TIMEOUT - 1
    )
    transport.refuse(NON_CRITICAL["device_signal"])
    api = await _api()

    with patch.object(api_module, "ADJUDICATION_BUDGET", -1):
        data = await api.get_data()

    assert "device_signal" not in data
    assert transport.anonymous_info_reads == 0
    assert transport.authenticated_info_reads == 1

    # An endpoint that answered earlier is read as an expiry by the history.
    transport.refused.clear()
    await api.get_data()
    transport.refuse(NON_CRITICAL["device_signal"])
    reads = transport.anonymous_info_reads
    with (
        patch.object(api_module, "ADJUDICATION_BUDGET", -1),
        pytest.raises(HuaweiAuthError),
    ):
        await api.get_data()
    assert transport.anonymous_info_reads == reads


@pytest.mark.asyncio
async def test_the_premise_connection_is_closed_when_its_read_raises(transport):
    """The anonymous connection is closed on the failure path too."""
    api = await _api()
    conn = MagicMock()
    conn.get.side_effect = RuntimeError("boom")
    with patch.object(api_module, "Connection", return_value=conn):
        result = api._read_premise(api._generation)

    assert result is None
    conn.requests_session.close.assert_called_once()
    assert api.premise_result == {"outcome": "unknown", "code": None}


@pytest.mark.asyncio
async def test_the_recorded_premise_holds_no_payload(transport):
    """An anonymous answer carries identifiers, and none reaches the record."""
    transport.info_needs_login = False
    transport.refuse(NON_CRITICAL["device_signal"])
    api = await _api()

    await api.get_data()

    recorded = repr(api.premise_result)
    assert api.premise_result == {"outcome": "served", "code": None}
    assert "TEST0000000001" not in recorded
    assert "00:11:22:AA:BB:CC" not in recorded
    assert "TEST0000000001" not in repr(api.endpoint_outcomes)


@pytest.mark.asyncio
async def test_a_write_begun_before_a_reset_is_discarded(transport):
    """A worker thread orphaned across a reset cannot write the history.

    The reset happens inside the poll, while `device_signal` is being read, so
    the answers after it belong to a client generation that no longer exists.
    """
    api = await _api()

    def reset_during_signal(endpoint: str) -> None:
        if endpoint == "device/signal":
            api._reset_client()

    transport.on_request = reset_during_signal

    await api.get_data()

    assert api.answered_endpoints == frozenset({"device_information"})


@pytest.mark.asyncio
async def test_a_stale_premise_write_is_discarded(transport):
    """A premise read begun before a reset leaves no cache and no record."""
    api = await _api()
    stale = api._generation
    api._reset_client()

    api._read_premise(stale)

    assert api._premise_cache is None
    assert api.premise_result is None


@pytest.mark.asyncio
async def test_one_warning_per_endpoint_and_code(transport, caplog):
    """The log names the refusing endpoint once, not on every poll."""
    transport.refuse(NON_CRITICAL["device_signal"])
    api = await _api()

    with caplog.at_level("WARNING"):
        await api.get_data()
        await api.get_data()

    messages = [r.getMessage() for r in caplog.records if "refused" in r.getMessage()]
    named = [m for m in messages if "device_signal" in m and "100003" in m]
    assert len(named) == 1


@pytest.mark.asyncio
async def test_a_connection_that_cannot_be_built_leaves_the_premise_unknown(transport):
    """The premise check fails before it has a connection to close."""
    api = await _api()

    with patch.object(api_module, "Connection", side_effect=RuntimeError("boom")):
        result = api._read_premise(api._generation)

    assert result is None
    assert api.premise_result == {"outcome": "unknown", "code": None}


@pytest.mark.asyncio
async def test_a_re_read_that_fails_otherwise_fails_the_poll_as_a_connection_error(
    transport,
):
    """The re-read raising something other than a session signal is not an expiry.

    The router answers the re-read `100002`, which says nothing about the
    session, so the poll fails as a connection error and does not log in again.
    """
    from custom_components.huawei_router_5g.api import HuaweiConnectionError

    transport.refuse(NON_CRITICAL["device_signal"])

    def refuse_info_after_the_first_read(endpoint: str) -> None:
        if endpoint == "device/information" and transport.authenticated_info_reads == 1:
            transport.refuse("device/information", 100002)

    transport.on_request = refuse_info_after_the_first_read
    api = await _api()

    with pytest.raises(HuaweiConnectionError):
        await api.get_data()


@pytest.mark.asyncio
async def test_a_re_read_that_cannot_reach_the_router_fails_the_poll(transport):
    """A transport error on the re-read is a connection error, not an expiry."""
    import requests

    from custom_components.huawei_router_5g.api import HuaweiConnectionError

    transport.refuse(NON_CRITICAL["device_signal"])

    def drop_the_re_read(endpoint: str) -> None:
        if (
            endpoint == "device/information"
            and transport.authenticated_info_reads == 1
            and transport.anonymous_info_reads == 1
        ):
            raise requests.ConnectionError("reset")

    transport.on_request = drop_the_re_read
    api = await _api()

    with pytest.raises(HuaweiConnectionError):
        await api.get_data()
