"""A fake router at the HTTP transport, for tests that must drive a real poll.

**Why this exists.** Every other test in this suite replaces the API object, so
anything `api.py` *derives* is supplied by the fixture instead of computed. A
test written that way cannot fail when the derivation stops working — which is
the gap `dev_standards.md` §11 (1.32.0) closes and chore `C-021` adopts. Here
the payload is the only input: `huawei-lte-api` parses it, `api.py` classifies
it, `coordinator.py` accumulates it, and the assertion reads what was published.

**The seam is `requests`, not `aiohttp`.** The three sibling projects reach the
network through `async_get_clientsession` and fake it with `aioclient_mock`.
This one reaches it through `huawei-lte-api`, which holds its own
`requests.Session`, so the equivalent fixture is `requests_mock` — shipped by
`pytest-homeassistant-custom-component` exactly as `aioclient_mock` is, so no
dependency is added here either.

**What a fixture body has to be.** `huawei-lte-api` parses a response with
`xmltodict.parse` and then unwraps `data["response"]`, so a payload dictionary
becomes a wire body through `xmltodict.unparse({"response": payload})` and
nothing is written by hand. The same route serves faults: an `<error><code>`
body is mapped by the library onto its own exception types, so session expiry
and the rest are *served*, never patched.

**Faults are payloads or transport errors, never patches.** `arm()` takes one
of `FAULTS`. Everything the integration does in response — the strike budgets,
the health verdict, the repair issues — then runs for real.

Background, options considered, and the four bootstrap requests:
`.shared/issues/x_project/fault_injection_options.md` §3.
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests
import xmltodict

# Error codes the router answers with, from `ResponseCodeEnum` in the library.
# `api.py` treats 125002 and 125003 as session expiry and re-logs in; 100002 is
# how a router reports an endpoint it does not implement.
ERROR_NO_SUPPORT = 100002
ERROR_NO_RIGHTS = 100003
ERROR_SYSTEM_CSRF = 125002
ERROR_WRONG_SESSION_TOKEN = 125003

FAULTS = (
    "session_expired",
    "csrf_expired",
    "no_rights",
    "unreachable",
    "timeout",
    "endpoint_error",
    "endpoint_missing",
)

# **`session_expired` is 125003, not 125002, and the difference matters.**
# `huawei-lte-api` wraps every request in `_try_or_reload_and_retry`, which
# catches `ResponseErrorLoginCsrfException` — 125002 — reloads the session and
# retries once, inside the library. A test that serves 125002 therefore never
# reaches `api.py`'s own classification: the poll succeeds because the library
# recovered, and the assertion passes whatever `api.py` does with the code.
# 125003 is not retried there, so it is the one that exercises this project's
# session handling. `csrf_expired` is kept for driving the library's own path
# deliberately.

# Faults that represent the router being gone rather than answering badly.
# These reach the login exchange as well, because a router that cannot be
# reached cannot be logged into either.
_TRANSPORT_FAULTS = ("unreachable", "timeout")

# The login exchange. A payload-shaped fault deliberately does **not** apply
# here: the case being modeled is a session that lapses while the integration
# is polling, and the recovery under test is `api.py` logging in again. A fault
# that also failed the re-login would make every expiry unrecoverable and no
# test could tell the retry from its absence.
_BOOTSTRAP = ("user/state-login", "user/login")

# The homepage. Supplying both CSRF tokens here means the library never falls
# through to `webserver/token` or `webserver/SesTokInfo`, so the bootstrap is
# this plus the two login requests.
_HOMEPAGE = (
    '<html><head><meta name="csrf_token" content="token-one"/>'
    '<meta name="csrf_token" content="token-two"/></head><body></body></html>'
)

# `password_type` 0 selects base-64 encoding, which keeps `webserver/publickey`
# and the RSA path out of the exchange. `State` -1 means "not logged in", so
# `UserSession` performs the login rather than skipping it.
_STATE_LOGIN = {"State": "-1", "password_type": "0"}

# Enough of a router to drive a poll. `device_information` is the only endpoint
# `api.py` treats as critical; every other block is optional by design, and an
# endpoint absent from this map answers "no support", which is what a router
# that does not implement it does.
DEFAULT_PAYLOADS: dict[str, Any] = {
    "device/information": {
        "DeviceName": "B535-232",
        "SerialNumber": "TEST0000000001",
        "Imei": "000000000000000",
        "SoftwareVersion": "11.0.1.1",
        "HardwareVersion": "WL1B535FM",
        "MacAddress1": "00:11:22:AA:BB:CC",
        "WebUIVersion": "11.0.1.1",
        "Uptime": "3600",
    },
    "device/signal": {
        "rsrp": "-95dBm",
        "rsrq": "-11dB",
        "rssi": "-70dBm",
        "sinr": "12dB",
        "cell_id": "12345678",
        "band": "3",
        "mode": "7",
    },
    "monitoring/status": {
        "ConnectionStatus": "901",
        "SignalIcon": "4",
        "CurrentNetworkType": "19",
        "SimStatus": "1",
    },
    "monitoring/traffic-statistics": {
        "CurrentDownloadRate": "1024",
        "CurrentUploadRate": "512",
        "TotalDownload": "1048576",
        "TotalUpload": "524288",
        "CurrentConnectTime": "3600",
    },
    "monitoring/month_statistics": {
        "CurrentMonthDownload": "10485760",
        "CurrentMonthUpload": "5242880",
        "MonthDuration": "86400",
    },
    "net/current-plmn": {"FullName": "Test Network", "Numeric": "00101", "Rat": "7"},
    "net/net-mode": {"NetworkMode": "03", "NetworkBand": "3FFFFFFF"},
    "sms/sms-count": {"LocalInbox": "0", "LocalUnread": "0", "SimInbox": "0"},
    "dialup/mobile-dataswitch": {"dataswitch": "1"},
    "monitoring/check-notifications": {"UnreadMessage": "0", "SmsStorageFull": "0"},
    "lan/HostInfo": {
        "Hosts": {
            "Host": [
                {
                    "HostName": "wired-client",
                    "IpAddress": "192.168.8.100",
                    "MacAddress": "00:11:22:33:44:55",
                    "AssociatedSsid": "",
                }
            ]
        }
    },
    "wlan/host-list": {"Hosts": {"Host": []}},
    "wlan/wifi-feature-switch": {"wifi5g_enabled": "1", "wifienable": "1"},
    "wlan/multi-basic-settings": {
        "Ssids": {
            "Ssid": [
                {
                    "Index": "0",
                    "WifiSsid": "TestNet",
                    "WifiEnable": "1",
                    "ID": "Radio.1",
                }
            ]
        }
    },
    "sms/sms-list": {"Count": "0", "Messages": None},
    "monitoring/start_date": {"StartDay": "1", "DataLimit": "100GB"},
    "monitoring/converged-status": {"currentsimtype": "1", "curroaming": "0"},
    "dialup/profiles": {"CurrentProfile": "1", "Profiles": {"Profile": []}},
    "dialup/connection": {"RoamAutoConnectEnable": "1", "MaxIdelTime": "0"},
    "device/antenna_type": {"antennatype": "0"},
    "net/csps_state": {"cpsstate": "1"},
    "security/sip": {"Enabled": "1", "Port": "5060"},
    "security/upnp": {"UpnpStatus": "1"},
    # `voice_busy` answers with a bare string rather than a block, which is why
    # `api.py` handles it separately. The fixture has to be equally odd or the
    # difference is untested.
    "voice/voicebusy": "Idle",
    "voice/volte": {"VolteStatus": "1"},
    "monitoring/onekey_diag": {"DiagResult": "0"},
}

# The library builds `<url>/api/<endpoint>`, so this strips the prefix and
# leaves the endpoint as the map above keys it.
#
# **Matching is case-insensitive, and it has to be.** `requests_mock` lowercases
# `request.path`, so an endpoint the library spells `lan/HostInfo` arrives here
# as `lan/hostinfo` and a case-sensitive lookup silently answers "no support" —
# which reads as a router that does not implement the endpoint rather than as a
# fixture miss. The map keeps the library's spelling for readability and every
# comparison goes through `_key`.
_API_PATH = re.compile(r"^/api/(?P<endpoint>.+?)/?$")


def _key(endpoint: str) -> str:
    """Normalize an endpoint for lookup and comparison."""
    return endpoint.lower()


def _xml(payload: Any) -> str:
    """Render a payload as the response envelope the library parses."""
    return xmltodict.unparse({"response": payload})


def _error_xml(code: int) -> str:
    """Render the error envelope the library maps onto its exception types."""
    return xmltodict.unparse({"error": {"code": str(code), "message": ""}})


class RouterTransport:
    """A router that answers, and misbehaves when told to.

    Register it on a `requests_mock.Mocker` and drive the integration normally.
    The state it holds is deliberately per-instance rather than per-request, so
    a fault can be armed for a set number of polls and then clear itself, which
    is what makes recovery observable.
    """

    def __init__(self, mocker: Any, payloads: dict[str, Any] | None = None) -> None:
        """Register every route on `mocker`."""
        self.payloads = dict(DEFAULT_PAYLOADS if payloads is None else payloads)
        self.fault: str | None = None
        self.fault_endpoint: str | None = None
        self.answers_remaining: int | None = None
        self.request_count = 0
        # Faulted answers actually served. A test that arms a fault and then
        # asserts a recovery has to check this too: if nothing ever reached the
        # fault, the recovery assertion passes for the wrong reason.
        self.faults_served = 0
        # How long the `timeout` fault hangs for. A test using it shortens
        # `FETCH_TIMEOUT` to something below this.
        self.hang_seconds = 0.3

        mocker.get(re.compile(r"/$"), text=_HOMEPAGE)
        mocker.post(
            re.compile(r"/api/user/login$"),
            text=_xml("OK"),
            headers={"__RequestVerificationToken": "token-next"},
        )
        mocker.get(re.compile(r"/api/.*"), text=self._answer)
        # Some endpoints are POSTs with a request body — `sms/sms-list` is the
        # one a poll reaches. Answered by the same handler so an unregistered
        # POST does not become a silent warning in the middle of a fetch.
        mocker.post(re.compile(r"/api/(?!user/login).*"), text=self._answer)

    def arm(
        self, fault: str, *, endpoint: str | None = None, answers: int | None = None
    ) -> None:
        """Make the router misbehave.

        `endpoint` scopes the payload-shaped faults to one block, which is how
        a non-critical endpoint is failed without failing the whole fetch.

        `answers` clears the fault after that many **faulted answers**, so one
        test can cover the failure and the recovery. Counting answers rather
        than fetch cycles is what makes the budget hold whatever the fault
        does: a fault that stops the login exchange never reaches the endpoint
        a cycle would have been counted on, and a fault scoped to one endpoint
        is served once per cycle either way.
        """
        if fault not in FAULTS:
            msg = f"unknown fault {fault!r}; expected one of {FAULTS}"
            raise ValueError(msg)
        self.fault = fault
        self.fault_endpoint = endpoint
        self.answers_remaining = answers

    def clear(self) -> None:
        """Return the router to normal."""
        self.fault = None
        self.fault_endpoint = None
        self.answers_remaining = None

    def _current_fault(self, endpoint: str) -> str | None:
        """Return the fault that applies to this endpoint, if any."""
        if self.fault is None:
            return None
        if self.fault_endpoint is not None and _key(self.fault_endpoint) != endpoint:
            return None
        if endpoint in [_key(name) for name in _BOOTSTRAP] and (
            self.fault not in _TRANSPORT_FAULTS
        ):
            return None
        return self.fault

    def _count_answer(self) -> None:
        """Spend one of the fault's budget, clearing it when nothing is left.

        Called **after** the fault for the current request has been decided, so
        the answer that spends the last of the budget is still faulted and the
        one after it is not.
        """
        if self.answers_remaining is None:
            return
        self.answers_remaining -= 1
        if self.answers_remaining <= 0:
            self.clear()

    def _answer(self, request: Any, context: Any) -> str:
        """Answer one GET, applying whatever fault is armed."""
        match = _API_PATH.match(request.path)
        endpoint = _key(match.group("endpoint") if match else request.path)

        self.request_count += 1
        fault = self._current_fault(endpoint)
        if fault is not None:
            self.faults_served += 1
            self._count_answer()

        if fault == "unreachable":
            raise requests.ConnectionError("connection refused")
        if fault == "timeout":
            # A router that accepts the connection and then does not answer.
            # The coordinator's own `asyncio.timeout(FETCH_TIMEOUT)` is what
            # ends this, so a test using it shortens that constant rather than
            # waiting 30 seconds. `time.sleep` is correct here: the library is
            # synchronous and runs in a worker thread.
            #
            # Raising afterwards stops the orphaned worker walking the
            # remaining endpoints. The coordinator has already given up by
            # then — `asyncio.timeout` cancels the await, not the thread — so
            # without this one armed fault answers twenty-six times per cycle.
            time.sleep(self.hang_seconds)
            raise requests.Timeout("read timed out")
        if fault == "session_expired":
            return _error_xml(ERROR_WRONG_SESSION_TOKEN)
        if fault == "csrf_expired":
            return _error_xml(ERROR_SYSTEM_CSRF)
        if fault == "no_rights":
            return _error_xml(ERROR_NO_RIGHTS)
        if fault == "endpoint_error":
            return _error_xml(ERROR_NO_SUPPORT)
        if fault == "endpoint_missing":
            return _xml({})

        for name, payload in self.payloads.items():
            if _key(name) == endpoint:
                return _xml(payload)
        return _error_xml(ERROR_NO_SUPPORT)
