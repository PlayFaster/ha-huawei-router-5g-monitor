"""Section 22 — the targeted read-back and its three outcomes.

The whole value of this mechanism is in keeping *disagreed* and *could not be
read* apart. Collapsing them is the defect the section names, and it is an easy
one to reintroduce: both are "the read did not say yes", and one `if` treats
them the same.

These are mechanism tests. The coverage half — that every write path either
confirms or declares an exclusion — lives in `test_write_classification.py`.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.huawei_router_5g.api import READ_BACK_ENDPOINTS
from custom_components.huawei_router_5g.helpers import confirm_write


def _api(*results):
    """Build an API stub whose read_back answers each result in turn."""
    api = MagicMock()
    api.read_back = AsyncMock(side_effect=list(results))
    return api


@pytest.mark.asyncio
async def test_a_read_that_agrees_confirms_immediately() -> None:
    """The happy path costs exactly one read."""
    api = _api({"dataswitch": "1"})

    result = await confirm_write(
        api, "mobile_dataswitch", lambda b: b.get("dataswitch"), "1", label="test"
    )

    assert result is True
    assert api.read_back.await_count == 1


@pytest.mark.asyncio
async def test_a_read_that_disagrees_twice_is_a_refusal() -> None:
    """Two disagreeing reads mean the router declined the command."""
    api = _api({"dataswitch": "0"}, {"dataswitch": "0"})

    with patch("custom_components.huawei_router_5g.helpers.asyncio.sleep", AsyncMock()):
        result = await confirm_write(
            api, "mobile_dataswitch", lambda b: b.get("dataswitch"), "1", label="test"
        )

    assert result is False
    assert api.read_back.await_count == 2


@pytest.mark.asyncio
async def test_a_stale_first_read_is_not_a_refusal() -> None:
    """Accepted-then-applied must not be reported as declined.

    These routers commonly answer the first read after a write with the old
    value. Without the retry every such write would raise at the user, which
    is worse than the debounce the read-back replaced.
    """
    api = _api({"dataswitch": "0"}, {"dataswitch": "1"})

    with patch("custom_components.huawei_router_5g.helpers.asyncio.sleep", AsyncMock()):
        result = await confirm_write(
            api, "mobile_dataswitch", lambda b: b.get("dataswitch"), "1", label="test"
        )

    assert result is True
    assert api.read_back.await_count == 2


@pytest.mark.asyncio
async def test_a_failed_read_is_unverified_not_failed() -> None:
    """`None` from the API is the third outcome, and must stay distinct.

    This is the assertion that stops the collapse: `False` and `None` are both
    "not confirmed", and only one of them may reach the user as an error.
    """
    api = _api(None)

    result = await confirm_write(
        api, "mobile_dataswitch", lambda b: b.get("dataswitch"), "1", label="test"
    )

    assert result is None
    assert result is not False


@pytest.mark.asyncio
async def test_a_missing_key_is_unverified_not_failed() -> None:
    """A block that came back without the key proves nothing either way."""
    api = _api({"something_else": "1"})

    result = await confirm_write(
        api, "mobile_dataswitch", lambda b: b.get("dataswitch"), "1", label="test"
    )

    assert result is None


@pytest.mark.asyncio
async def test_an_unexpected_shape_is_unverified_not_failed() -> None:
    """An extractor that blows up on a strange payload must not fail the write.

    The guest-WiFi extractor walks a nested list. A firmware that reshapes
    that block would otherwise turn every guest toggle into a reported
    failure — while the toggle itself was working.
    """
    api = _api({"Ssids": "not the shape anyone expected"})

    def _explodes(block):
        return block["Ssids"]["Ssid"][0]["WifiEnable"]

    result = await confirm_write(
        api, "wlan_multi_basic_settings", _explodes, "1", label="test"
    )

    assert result is None


@pytest.mark.asyncio
async def test_comparison_is_on_strings() -> None:
    """`1` from a caller must match `"1"` from the router.

    The API returns strings throughout. A caller holding an int would
    otherwise see every write refused.
    """
    api = _api({"dataswitch": 1})

    result = await confirm_write(
        api, "mobile_dataswitch", lambda b: b.get("dataswitch"), "1", label="test"
    )

    assert result is True


def test_every_read_back_endpoint_is_a_real_one() -> None:
    """The read-back map may not name an endpoint the integration cannot poll.

    A typo here would surface only as a permanently unverified control — no
    error, no failure, just a mechanism that quietly never confirms anything.
    """
    from custom_components.huawei_router_5g.const import ENDPOINT_NAMES

    unknown = sorted(set(READ_BACK_ENDPOINTS) - set(ENDPOINT_NAMES))
    assert not unknown, f"read-back names endpoints that are never fetched: {unknown}"


def test_connection_affecting_writes_have_no_read_back_reader() -> None:
    """Section 22's exclusion, enforced rather than left as a comment.

    Anything that re-establishes the connection answers abnormally *while
    succeeding*, so a read-back reports a working command as failed. Network
    mode and Reconnect are this integration's two, and the protection is that
    no reader exists for the endpoints they would need.
    """
    assert "net_mode" not in READ_BACK_ENDPOINTS
    assert "dial_up_connection" not in READ_BACK_ENDPOINTS


# ---------------------------------------------------------------------------
# The API side of the read-back
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_back_returns_the_block_on_success() -> None:
    """A successful read hands the endpoint's block straight back."""
    from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI

    api = HuaweiRouter5GAPI("192.168.8.1", "admin", "pw")
    api._execute_with_retry = AsyncMock(return_value={"dataswitch": "1"})

    assert await api.read_back("mobile_dataswitch") == {"dataswitch": "1"}


@pytest.mark.asyncio
async def test_read_back_swallows_the_error_and_answers_none() -> None:
    """A failed read is unverified, so it must not raise into the write path.

    This is the contract `confirm_write` depends on. If `read_back` raised,
    the exception would escape the entity's confirmation step and report a
    write that had already succeeded as a failure.
    """
    from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI

    api = HuaweiRouter5GAPI("192.168.8.1", "admin", "pw")
    api._execute_with_retry = AsyncMock(side_effect=Exception("router busy"))

    assert await api.read_back("mobile_dataswitch") is None


@pytest.mark.asyncio
async def test_read_back_treats_a_non_dict_answer_as_unreadable() -> None:
    """Some endpoints answer with a bare string; that proves nothing here."""
    from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI

    api = HuaweiRouter5GAPI("192.168.8.1", "admin", "pw")
    api._execute_with_retry = AsyncMock(return_value="Idle")

    assert await api.read_back("mobile_dataswitch") is None


@pytest.mark.asyncio
async def test_read_back_refuses_an_endpoint_with_no_reader() -> None:
    """An unlisted endpoint is a programming error, not a runtime outcome.

    Raising rather than returning None on purpose: a typo must fail loudly at
    the first press, not degrade into a control that silently never confirms.
    """
    from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI

    api = HuaweiRouter5GAPI("192.168.8.1", "admin", "pw")

    with pytest.raises(ValueError, match="no read-back reader"):
        await api.read_back("net_mode")


# ---------------------------------------------------------------------------
# The entity side — how a switch acts on each outcome
# ---------------------------------------------------------------------------


def _switch(read_back_result):
    from custom_components.huawei_router_5g.switch import (
        MOBILE_DATA_DESCRIPTION,
        HuaweiMobileDataSwitch,
    )

    coordinator = MagicMock()
    coordinator.api.set_mobile_data = AsyncMock()
    coordinator.api.read_back = AsyncMock(return_value=read_back_result)
    coordinator.async_force_refresh = AsyncMock()
    entry = MagicMock()
    entry.unique_id = "abc"
    entry.title = "Router"
    switch = HuaweiMobileDataSwitch(coordinator, entry, MOBILE_DATA_DESCRIPTION)
    switch.hass = MagicMock()
    switch.async_write_ha_state = MagicMock()
    return switch, coordinator


@pytest.mark.asyncio
async def test_a_refused_write_raises_a_translated_error() -> None:
    """The user must be told, and told in their own language.

    A raw f-string here would show English to everyone; Section 12 requires
    the `exceptions` block, and this asserts the entity actually uses it.
    """
    from homeassistant.exceptions import HomeAssistantError

    switch, _ = _switch({"dataswitch": "0"})

    with (
        patch("custom_components.huawei_router_5g.helpers.asyncio.sleep", AsyncMock()),
        pytest.raises(HomeAssistantError) as caught,
    ):
        await switch.async_turn_on()

    assert caught.value.translation_key == "write_not_confirmed"
    switch.async_write_ha_state.assert_not_called()


@pytest.mark.asyncio
async def test_a_confirmed_write_publishes_without_a_refresh() -> None:
    """Confirmation is the point: publish now, do not wait for the debounce."""
    switch, coordinator = _switch({"dataswitch": "1"})

    await switch.async_turn_on()

    switch.async_write_ha_state.assert_called_once()
    coordinator.async_force_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unverified_write_falls_back_to_a_refresh() -> None:
    """Unverified publishes nothing as fact and leaves it to the next poll."""
    switch, coordinator = _switch(None)

    await switch.async_turn_on()

    switch.async_write_ha_state.assert_not_called()
    coordinator.async_force_refresh.assert_awaited_once()


# ---------------------------------------------------------------------------
# The guest-SSID extractor
# ---------------------------------------------------------------------------


def test_the_guest_extractor_finds_the_guest_by_flag_not_position() -> None:
    """The guest network is identified by `wifiisguestnetwork`, not by index.

    The router does not guarantee an order — the APN profile lookup learned
    this when the router returned profiles 1, 3, 2. Putting the guest second
    here is what makes the test meaningful.
    """
    from custom_components.huawei_router_5g.switch import _guest_enable_flag

    block = {
        "Ssids": {
            "Ssid": [
                {"wifiisguestnetwork": "0", "WifiEnable": "1"},
                {"wifiisguestnetwork": "1", "WifiEnable": "0"},
            ]
        }
    }

    assert _guest_enable_flag(block) == "0"


def test_the_guest_extractor_accepts_a_single_ssid_as_a_dict() -> None:
    """A router with one SSID returns a bare dict, not a one-element list.

    This API does that throughout. Without the coercion the extractor would
    iterate the dict's *keys* and silently find no guest network — reporting
    every guest toggle as unverified on exactly the routers that have only
    one SSID configured.
    """
    from custom_components.huawei_router_5g.switch import _guest_enable_flag

    block = {"Ssids": {"Ssid": {"wifiisguestnetwork": "1", "WifiEnable": "1"}}}

    assert _guest_enable_flag(block) == "1"


def test_the_guest_extractor_returns_none_when_there_is_no_guest_network() -> None:
    """No guest SSID means unverified, which is the safe outcome.

    `confirm_write` turns this into `None` — the write is left for the next
    poll rather than reported as refused.
    """
    from custom_components.huawei_router_5g.switch import _guest_enable_flag

    assert _guest_enable_flag({"Ssids": {"Ssid": []}}) is None
    assert _guest_enable_flag({}) is None
