"""Outcomes driven through a real poll, with the transport faked.

`dev_standards.md` §11 (1.32.0), chore `C-021`. Every test here builds a real
`HuaweiRouter5GAPI` and a real coordinator, and the only thing faked is the
HTTP response. `huawei-lte-api` parses it, `api.py` classifies it,
`coordinator.py` accumulates it. Nothing patches a method of the code under
test, and no fixture supplies a value the code is supposed to derive.

**What this reaches that the rest of the suite cannot.** The strike budgets are
accumulation behavior: `FETCH_STRIKE_LIMIT`, `HEALTH_DRIFT_STRIKE_LIMIT` and
`REPAIR_CONN_STRIKE_LIMIT` are all crossed by consecutive polls, and setting a
counter by hand proves the comparison rather than that the code can reach it.
Both repair issues are raised from those paths, so both are driven here from a
poll rather than asserted at their call site.

The fake router and the faults it can be armed with are in
[`transport.py`](transport.py); the design record is
`.shared/issues/x_project/fault_injection_options.md` §3.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests_mock as requests_mock_module
from homeassistant.helpers import issue_registry as ir

from custom_components.huawei_router_5g import coordinator as coordinator_module
from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI
from custom_components.huawei_router_5g.const import (
    DOMAIN,
    FETCH_STRIKE_LIMIT,
    HEALTH_DRIFT_STRIKE_LIMIT,
    REPAIR_AUTH_FAILED,
    REPAIR_CONN_ERROR,
    REPAIR_CONN_STRIKE_LIMIT,
)
from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)

from .transport import RouterTransport

ROUTER_URL = "http://192.168.8.1"


@pytest.fixture(name="transport")
def transport_fixture():
    """Serve a working router over the `requests` transport."""
    with requests_mock_module.Mocker() as mocker:
        yield RouterTransport(mocker)


@pytest.fixture(name="short_fetch_timeout")
def short_fetch_timeout_fixture(monkeypatch):
    """Shorten the fetch deadline so the `timeout` fault can reach it.

    The deadline is a **constant**, not behavior: the code path under test is
    the coordinator's own `asyncio.timeout`, which still runs and still decides
    what happens. Waiting the real 30 seconds ten times over would put a single
    test at five minutes.
    """
    monkeypatch.setattr(coordinator_module, "FETCH_TIMEOUT", 0.1)


def _coordinator(hass, entry) -> HuaweiRouter5GDataUpdateCoordinator:
    """Build a coordinator over a real API client.

    The entry is added to `hass` because a successful poll writes hardware
    metadata back to it through `async_update_entry`, which an entry the
    registry has never seen rejects.
    """
    entry.add_to_hass(hass)
    api = HuaweiRouter5GAPI(ROUTER_URL, "admin", "password")
    return HuaweiRouter5GDataUpdateCoordinator(hass, entry, api)


async def _poll(
    coordinator: HuaweiRouter5GDataUpdateCoordinator, transport: Any = None
) -> Any:
    """Drive one poll through the public entry point and return the data held.

    `async_refresh` rather than `_async_update_data`: it is what Home Assistant
    calls, it keeps `data` and `last_update_success` for the next cycle to
    accumulate on, and a failed poll is then observed the way the user does —
    stale data held, or entities unavailable — rather than as an exception.

    Pass `transport` when the fault is `timeout`. `asyncio.timeout` cancels the
    await but cannot cancel the worker thread, which is the behavior `api.py`
    documents and compensates for with `invalidate()`. That thread is still
    inside the fake transport holding its lock, so the next request blocks
    until it finishes. Waiting for it here keeps one test's leftovers out of
    the next one.
    """
    await coordinator.async_refresh()
    if transport is not None:
        await asyncio.sleep(transport.hang_seconds)
    return coordinator.data


async def test_a_working_router_produces_derived_values(
    hass, mock_config_entry, transport
):
    """The payload is the only input, and everything else is derived.

    Asserts fields the fixture does not state: the model comes from
    `get_router_model` reading `DeviceName`, and the signal values reach the
    coordinator having been through the library's XML parse and `api.py`.
    """
    coordinator = _coordinator(hass, mock_config_entry)

    data = await _poll(coordinator)

    assert data["device_information"]["DeviceName"] == "B535-232"
    assert data["device_signal"]["rsrp"] == "-95dBm"
    assert coordinator.model == "B535-232"
    assert coordinator.health_snapshot["severity"] == "ok"
    assert coordinator.consecutive_failures == 0


async def test_an_endpoint_the_router_does_not_implement_is_not_a_failure(
    hass, mock_config_entry, transport
):
    """A non-critical endpoint answering an error leaves the poll healthy.

    The distinction being asserted is the one `api.py` makes per endpoint:
    only `device_information` is critical, so every other block may be absent
    without the fetch failing. Driving it through the transport is what proves
    the classification, because the error arrives as a router response rather
    than as an exception a test raised.
    """
    transport.arm("endpoint_error", endpoint="device/signal")
    coordinator = _coordinator(hass, mock_config_entry)

    data = await _poll(coordinator)

    assert "device_signal" not in data
    assert data["device_information"]["DeviceName"] == "B535-232"
    assert coordinator.consecutive_failures == 0


async def test_a_critical_endpoint_failing_fails_the_poll(
    hass, mock_config_entry, transport
):
    """`device_information` failing is the one that takes the fetch with it."""
    transport.arm("endpoint_error", endpoint="device/information")
    coordinator = _coordinator(hass, mock_config_entry)

    await _poll(coordinator)

    assert coordinator.last_update_success is False
    assert coordinator.consecutive_failures == 1


async def test_the_fetch_strike_budget_holds_then_releases(
    hass, mock_config_entry, transport
):
    """Last-known values are held for three failures and dropped on the fourth.

    This is `FETCH_STRIKE_LIMIT` driven rather than asserted: each cycle is a
    real poll against an unreachable router, and the transition is the one the
    user sees as entities going unavailable.
    """
    coordinator = _coordinator(hass, mock_config_entry)
    good = await _poll(coordinator)

    transport.arm("unreachable")
    for expected in range(1, FETCH_STRIKE_LIMIT + 1):
        held = await _poll(coordinator)
        assert held == good
        assert coordinator.last_update_success is True
        assert coordinator.consecutive_failures == expected

    await _poll(coordinator)

    assert coordinator.last_update_success is False
    assert coordinator.consecutive_failures == FETCH_STRIKE_LIMIT + 1
    assert coordinator.health_snapshot["severity"] == "error"


async def test_the_conn_error_repair_is_raised_only_once_the_budget_is_spent(
    hass, mock_config_entry, transport, short_fetch_timeout
):
    """`conn_error` waits for `REPAIR_CONN_STRIKE_LIMIT` consecutive failures.

    The gate is ten polls, which is why nothing in the suite had reached it.
    Asserts the issue is absent at nine and present at ten, because a repair
    raised early is the defect this constant exists to prevent.

    Driven with the `timeout` fault; the refused-connection branch reaches the
    same gate and is covered by
    `test_a_router_that_refuses_the_connection_raises_the_repair`.
    """

    registry = ir.async_get(hass)
    issue_id = f"{REPAIR_CONN_ERROR}_{mock_config_entry.entry_id}"

    coordinator = _coordinator(hass, mock_config_entry)
    await _poll(coordinator)

    transport.arm("timeout")
    for _ in range(REPAIR_CONN_STRIKE_LIMIT - 1):
        await _poll(coordinator, transport)

    assert coordinator.consecutive_failures == REPAIR_CONN_STRIKE_LIMIT - 1
    assert registry.async_get_issue(DOMAIN, issue_id) is None

    await _poll(coordinator, transport)

    assert coordinator.consecutive_failures == REPAIR_CONN_STRIKE_LIMIT
    assert registry.async_get_issue(DOMAIN, issue_id) is not None


async def test_a_recovered_router_clears_the_repair_in_the_same_cycle(
    hass, mock_config_entry, transport, monkeypatch
):
    """Recovery deletes the issue on the poll that succeeds, not a later one.

    Section 19 requires a success to clear the verdict in the same cycle, so
    the assertion is made on the poll that recovers rather than after it.
    """

    registry = ir.async_get(hass)
    issue_id = f"{REPAIR_CONN_ERROR}_{mock_config_entry.entry_id}"

    coordinator = _coordinator(hass, mock_config_entry)
    await _poll(coordinator)

    # Shortened only while the router is expected to hang. The recovering poll
    # below runs against the real deadline: under coverage instrumentation a
    # healthy poll can take longer than a tenth of a second, and the recovery
    # would then time out and the test would report a failure to clear that
    # the code had not made.
    monkeypatch.setattr(coordinator_module, "FETCH_TIMEOUT", 0.1)
    transport.arm("timeout")
    for _ in range(REPAIR_CONN_STRIKE_LIMIT):
        await _poll(coordinator, transport)

    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    monkeypatch.undo()
    transport.clear()
    await _poll(coordinator)

    assert registry.async_get_issue(DOMAIN, issue_id) is None
    assert coordinator.consecutive_failures == 0
    assert coordinator.health_snapshot["severity"] == "ok"


async def test_a_capability_is_reported_degraded_only_after_the_drift_budget(
    hass, mock_config_entry, transport
):
    """A missing block is tolerated twice and reported degraded on the third.

    `HEALTH_DRIFT_STRIKE_LIMIT` counts a capability missing across *successful*
    polls, which is a different budget from the failed-poll one and is why the
    two constants are separate. Nothing had driven it: the endpoint has to go
    missing three times in a row while the fetch keeps working.
    """
    coordinator = _coordinator(hass, mock_config_entry)
    await _poll(coordinator)

    transport.arm("endpoint_error", endpoint="device/signal")
    for _ in range(HEALTH_DRIFT_STRIKE_LIMIT - 1):
        await _poll(coordinator)
        assert coordinator.health_snapshot["degraded_capabilities"] == []
        assert coordinator.health_snapshot["severity"] == "ok"

    await _poll(coordinator)

    assert coordinator.health_snapshot["degraded_capabilities"] != []
    assert coordinator.health_snapshot["severity"] == "degraded"

    transport.clear()
    await _poll(coordinator)

    assert coordinator.health_snapshot["degraded_capabilities"] == []
    assert coordinator.health_snapshot["severity"] == "ok"


async def test_a_signal_block_with_no_known_field_is_reported_as_drift(
    hass, mock_config_entry, transport
):
    """A renamed firmware field is `warning`, and outranks a missing block.

    The distinction being asserted is the one Section 19 draws between
    `degraded` and `warning`: a block that is absent is a lost capability, a
    block that arrives carrying none of its contract keys means the readings
    cannot be trusted. Driven through the transport because the check reads
    what `api.py` actually collected.
    """
    payloads = dict(transport.payloads)
    payloads["device/signal"] = {"unexpected_field": "-95dBm"}
    transport.payloads = payloads

    coordinator = _coordinator(hass, mock_config_entry)
    await _poll(coordinator)

    assert coordinator.health_snapshot["drift"] != []
    assert coordinator.health_snapshot["severity"] == "warning"


async def test_a_router_that_refuses_the_connection_raises_the_repair(
    hass, mock_config_entry, transport
):
    """A refused connection reaches the repair, exactly as a timeout does.

    **This is the most ordinary failure the integration has.** A router that
    is powered off, unplugged or moved to a new address answers with a refused
    connection, not a timeout. Until 2026-08-23 the repair and the fault probe
    sat on the `TimeoutError` branch alone, so this path could fail every poll
    for ever and never raise the card whose own text asks the user to check
    that the router is powered on and reachable.

    Asserted at the gate rather than past it, because a repair raised early
    tells the user nothing they were not told four polls ago by every entity
    going unavailable.
    """
    registry = ir.async_get(hass)
    issue_id = f"{REPAIR_CONN_ERROR}_{mock_config_entry.entry_id}"

    coordinator = _coordinator(hass, mock_config_entry)
    await _poll(coordinator)

    transport.arm("unreachable")
    for _ in range(REPAIR_CONN_STRIKE_LIMIT - 1):
        await _poll(coordinator)

    assert coordinator.consecutive_failures == REPAIR_CONN_STRIKE_LIMIT - 1
    assert registry.async_get_issue(DOMAIN, issue_id) is None

    await _poll(coordinator)

    assert coordinator.consecutive_failures == REPAIR_CONN_STRIKE_LIMIT
    assert coordinator.health_snapshot["severity"] == "error"
    assert registry.async_get_issue(DOMAIN, issue_id) is not None


async def test_a_session_that_expires_mid_fetch_is_retried_and_recovers(
    hass, mock_config_entry, transport
):
    """A 125002 body re-logs in and the poll succeeds, raising no repair.

    This is the path that most needs the real transport: the router reports an
    expired session as an ordinary error body, `huawei-lte-api` maps it onto
    `ResponseErrorException`, and `api.py` reads the code to tell expiry from
    a genuine failure. Nothing here patches an exception into place.
    """

    registry = ir.async_get(hass)
    coordinator = _coordinator(hass, mock_config_entry)

    transport.arm("session_expired", endpoint="device/information", answers=1)
    data = await _poll(coordinator)

    # The fault has to have been served, or the poll below succeeded because
    # nothing ever expired and the retry was never exercised.
    assert transport.faults_served == 1
    assert data["device_information"]["DeviceName"] == "B535-232"
    assert coordinator.consecutive_failures == 0
    assert (
        registry.async_get_issue(
            DOMAIN, f"{REPAIR_AUTH_FAILED}_{mock_config_entry.entry_id}"
        )
        is None
    )


async def test_a_session_that_cannot_be_re_established_raises_the_auth_repair(
    hass, mock_config_entry, transport
):
    """Expiry that survives the retry raises `auth_failed` and stops the entry.

    The second declared outcome, driven from a poll. `is_persistent` is
    asserted because an auth repair that vanishes on restart leaves the user
    with no working entities and no card explaining why.
    """

    registry = ir.async_get(hass)
    coordinator = _coordinator(hass, mock_config_entry)

    transport.arm("session_expired")
    with patch.object(
        type(mock_config_entry), "async_start_reauth_if_available", MagicMock()
    ) as start_reauth:
        await _poll(coordinator)
        # The reauth flow is started from a task rather than inline, so
        # asserting straight after the poll is a race that only shows up on a
        # slower run.
        await hass.async_block_till_done()

    # `ConfigEntryAuthFailed` is how the coordinator asks Home Assistant for a
    # reauth flow, and asserting it here is what keeps the patch honest: it
    # stands in for the flow rather than hiding it. Left unpatched, the flow
    # outlives the test and fails at teardown looking for an integration that
    # is not installed in the test environment.
    start_reauth.assert_called_once()
    assert coordinator.last_update_success is False
    issue = registry.async_get_issue(
        DOMAIN, f"{REPAIR_AUTH_FAILED}_{mock_config_entry.entry_id}"
    )
    assert issue is not None
    assert issue.is_persistent is True
    assert issue.severity is ir.IssueSeverity.ERROR
