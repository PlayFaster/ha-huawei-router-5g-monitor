"""How each login failure is classified, and what the coordinator does with it.

The library raises a different exception for each login code. Before 1.2.4-dev1
`api.py` caught the wrong-username (108001) and wrong-password (108002) leaves
only, so a wrong pair (108006) and a lockout (108007) fell into the generic
handler and read as an unreachable router.

Plan `v124_dev1_plan.md` item I2 and decisions D16 and D17: the parent
credentials class raises `HuaweiAuthError`; 108007 raises `HuaweiLockoutError`,
which follows the strike rule of every other failure with no repair and no
reauth; and the coordinator retries only an expired session, so a rejected login
is tried once per poll.

The login is driven by patching `_create_connection_sync`, as the other login
tests do, because the fake transport's login always answers OK.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from huawei_lte_api.exceptions import (
    LoginErrorPasswordWrongException,
    LoginErrorUsernamePasswordOverrunException,
    LoginErrorUsernamePasswordWrongException,
    LoginErrorUsernameWrongException,
)
import pytest

from custom_components.huawei_router_5g.api import (
    HuaweiAuthError,
    HuaweiLockoutError,
    HuaweiRouter5GAPI,
    HuaweiSessionExpiredError,
)
from custom_components.huawei_router_5g.config_flow import (
    HuaweiRouter5GConfigFlow,
    HuaweiRouter5GOptionsFlow,
)
from custom_components.huawei_router_5g.const import FETCH_STRIKE_LIMIT
from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

GOOD = {"device_information": {"DeviceName": "H165-383"}}

CREDENTIAL_ERRORS = [
    pytest.param(
        LoginErrorUsernameWrongException("Wrong username", 108001), id="108001"
    ),
    pytest.param(
        LoginErrorPasswordWrongException("Wrong password", 108002), id="108002"
    ),
    pytest.param(
        LoginErrorUsernamePasswordWrongException("Wrong pair", 108006), id="108006"
    ),
]


def _lockout() -> LoginErrorUsernamePasswordOverrunException:
    return LoginErrorUsernamePasswordOverrunException("Password overrun", 108007)


def _api() -> HuaweiRouter5GAPI:
    return HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password")


# ---------------------------------------------------------------------------
# api.py: the classification of each code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("error", CREDENTIAL_ERRORS)
async def test_each_credentials_code_is_an_auth_error(error) -> None:
    """108001, 108002 and 108006 all raise `HuaweiAuthError` from both paths."""
    api = _api()
    with (
        patch.object(api, "_create_connection_sync", side_effect=error),
        pytest.raises(HuaweiAuthError) as raised,
    ):
        await api.login()
    assert not isinstance(raised.value, HuaweiSessionExpiredError)

    with (
        patch.object(api, "_create_connection_sync", side_effect=error),
        pytest.raises(HuaweiAuthError),
    ):
        await api._login_internal()
    assert api.login_metadata["result"] == "auth_failed"
    assert api._client is None


@pytest.mark.asyncio
async def test_the_lockout_has_its_own_error_and_record() -> None:
    """108007 raises `HuaweiLockoutError`, which is not an auth error."""
    api = _api()
    with (
        patch.object(api, "_create_connection_sync", side_effect=_lockout()),
        pytest.raises(HuaweiLockoutError) as raised,
    ):
        await api.login()
    assert not isinstance(raised.value, HuaweiAuthError)
    assert api._client is None

    with (
        patch.object(api, "_create_connection_sync", side_effect=_lockout()),
        pytest.raises(HuaweiLockoutError),
    ):
        await api._login_internal()
    assert api.login_metadata == {
        "result": "lockout",
        "username_configured": True,
        "error": "LoginErrorUsernamePasswordOverrunException",
    }
    assert api._client is None


# ---------------------------------------------------------------------------
# config_flow.py: the four steps that validate credentials
# ---------------------------------------------------------------------------

USER_INPUT = {
    CONF_HOST: "http://192.168.8.1",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "secret",
}


def _entry() -> MagicMock:
    entry = MagicMock()
    entry.title = "My Huawei Router"
    entry.options = dict(USER_INPUT)
    return entry


async def _run_step(step: str, user_input: dict) -> dict:
    """Run one flow step with the real credential validation."""
    if step == "user":
        flow = HuaweiRouter5GConfigFlow()
        flow.hass = MagicMock()
        flow.context = {}
        return await flow.async_step_user(dict(user_input))
    if step == "reauth_confirm":
        flow = HuaweiRouter5GConfigFlow()
        flow.hass = MagicMock()
        flow.context = {"entry_id": "entry-1"}
        flow._reauth_entry = _entry()
        return await flow.async_step_reauth_confirm(dict(user_input))
    if step == "reconfigure":
        flow = HuaweiRouter5GConfigFlow()
        flow.hass = MagicMock()
        flow.hass.config_entries.async_get_entry = MagicMock(return_value=_entry())
        flow.context = {"entry_id": "entry-1"}
        return await flow.async_step_reconfigure(dict(user_input))
    options = HuaweiRouter5GOptionsFlow(_entry())
    options.hass = MagicMock()
    return await options.async_step_init(dict(user_input))


STEPS = ["user", "reauth_confirm", "reconfigure", "init"]


@pytest.mark.asyncio
@pytest.mark.parametrize("step", STEPS)
@pytest.mark.parametrize("error", CREDENTIAL_ERRORS)
async def test_every_step_shows_invalid_auth_for_a_credentials_code(
    step, error
) -> None:
    """A wrong username, password or pair shows `invalid_auth` in every step."""
    with patch.object(HuaweiRouter5GAPI, "_create_connection_sync", side_effect=error):
        result = await _run_step(step, USER_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
@pytest.mark.parametrize("step", STEPS)
async def test_every_step_shows_the_lockout(step) -> None:
    """A lockout shows `login_attempts_exceeded`, not `cannot_connect`."""
    with patch.object(
        HuaweiRouter5GAPI, "_create_connection_sync", side_effect=_lockout()
    ):
        result = await _run_step(step, USER_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "login_attempts_exceeded"}


# ---------------------------------------------------------------------------
# coordinator.py: driven through repeated polls over a real API client
# ---------------------------------------------------------------------------


def _coordinator() -> HuaweiRouter5GDataUpdateCoordinator:
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.title = "My Huawei Router"
    entry.data = {}
    entry.options = {}
    return HuaweiRouter5GDataUpdateCoordinator(hass, entry, _api())


@pytest.mark.asyncio
@pytest.mark.parametrize("error", CREDENTIAL_ERRORS)
async def test_a_rejected_login_is_tried_once_per_poll(error) -> None:
    """Held for the strike budget, then reauth; one login attempt per poll.

    The coordinator's retry is for an expired session. Retrying a rejected login
    doubled the failed attempts per poll toward a lockout whose threshold is
    unmeasured.
    """
    coordinator = _coordinator()
    coordinator.data = GOOD
    with (
        patch.object(
            coordinator.api, "_create_connection_sync", side_effect=error
        ) as login,
        patch("custom_components.huawei_router_5g.coordinator.ir.async_create_issue"),
    ):
        for poll in range(1, FETCH_STRIKE_LIMIT + 1):
            assert await coordinator._async_update_data() == GOOD
            assert login.call_count == poll
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()
        assert login.call_count == FETCH_STRIKE_LIMIT + 1


@pytest.mark.asyncio
async def test_a_lockout_follows_the_strike_rule_with_no_repair(caplog) -> None:
    """Held for the strike budget, then unavailable naming the lockout.

    No connectivity repair, because the router is reachable, and no reauth,
    because the credentials may be right. One login attempt per poll.
    """
    coordinator = _coordinator()
    coordinator.data = GOOD
    with (
        patch.object(
            coordinator.api, "_create_connection_sync", side_effect=_lockout()
        ) as login,
        patch(
            "custom_components.huawei_router_5g.coordinator.ir.async_create_issue"
        ) as issue,
    ):
        for poll in range(1, FETCH_STRIKE_LIMIT + 1):
            assert await coordinator._async_update_data() == GOOD
            assert login.call_count == poll
        with pytest.raises(UpdateFailed, match="locked out"):
            await coordinator._async_update_data()
    assert login.call_count == FETCH_STRIKE_LIMIT + 1
    assert coordinator.consecutive_failures == FETCH_STRIKE_LIMIT + 1
    issue.assert_not_called()
    assert "Router login locked out (failure 1/3)" in caplog.text


@pytest.mark.asyncio
async def test_a_lockout_at_the_first_poll_is_unavailable_at_once() -> None:
    """With no values to hold, the first lockout fails the poll, still with no repair."""
    coordinator = _coordinator()
    coordinator.data = None
    with (
        patch.object(
            coordinator.api, "_create_connection_sync", side_effect=_lockout()
        ),
        patch(
            "custom_components.huawei_router_5g.coordinator.ir.async_create_issue"
        ) as issue,
        pytest.raises(UpdateFailed, match="locked out"),
    ):
        await coordinator._async_update_data()
    issue.assert_not_called()
    assert coordinator.health_snapshot.get("severity") == "error"


@pytest.mark.asyncio
async def test_an_expired_session_is_still_retried_once() -> None:
    """The retry the coordinator keeps: an expired session recovers silently."""
    coordinator = _coordinator()
    coordinator.data = GOOD
    calls: list[str] = []

    async def get_data() -> dict:
        calls.append("get_data")
        if len(calls) == 1:
            raise HuaweiSessionExpiredError("Session expired")
        return GOOD

    with patch.object(coordinator.api, "get_data", side_effect=get_data):
        assert await coordinator._async_update_data() == GOOD
    assert len(calls) == 2
    assert coordinator.consecutive_failures == 0
