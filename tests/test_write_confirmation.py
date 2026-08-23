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
    succeeding*, so an **immediate** read-back reports a working command as
    failed. Reconnect is this integration's one, and the protection is that no
    reader exists for the endpoint it would need.

    Network mode was here too, and the distinction that removed it is worth
    keeping: re-registering the radio makes the router's answers unreliable
    *for a while*, not permanently. Where the resulting state is readable once
    things settle — as the mode is, and a dial is not — the right answer is to
    wait and read, not to give up on confirming.
    """
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
        await api.read_back("dial_up_connection")


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
async def test_an_unverified_write_does_nothing_and_waits() -> None:
    """Unverified publishes nothing, raises nothing, and forces no refresh.

    The refresh assertion is the load-bearing one. Forcing a poll here would
    fetch all 26 endpoints to re-ask a question the router has just failed to
    answer — costing two reads *and* a full poll in the transient case, which
    is more work than the debounced refresh this mechanism replaced and lands
    precisely when the router is already struggling.
    """
    switch, coordinator = _switch(None)

    await switch.async_turn_on()

    switch.async_write_ha_state.assert_not_called()
    coordinator.async_force_refresh.assert_not_awaited()


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


# ---------------------------------------------------------------------------
# The translated message
# ---------------------------------------------------------------------------


def test_the_refusal_message_renders_its_placeholder() -> None:
    """`{action}` must actually substitute, in both translation files.

    The message text and the `translation_placeholders` dict were written
    separately and nothing had ever brought them together. A mismatch is
    invisible in code review and invisible at runtime to everyone except the
    user, who is shown a raw `{action}` in the error dialog.

    Renders the shipped string with the placeholder the entity actually
    passes, and asserts both that the substitution happened and that no
    unfilled placeholder is left behind.
    """
    import json
    import pathlib
    import re

    import custom_components.huawei_router_5g as component

    for name in ("strings.json", "translations/en.json"):
        path = pathlib.Path(component.__path__[0]) / name
        message = json.loads(path.read_text(encoding="utf-8"))["exceptions"][
            "write_not_confirmed"
        ]["message"]

        # The placeholder set the entity supplies. Named here rather than
        # imported so a rename on either side fails this test rather than
        # quietly agreeing with itself.
        rendered = message.format(action="Enable mobile data")

        assert "Enable mobile data" in rendered, f"{name}: placeholder not substituted"
        assert not re.search(r"\{\w+\}", rendered), (
            f"{name}: unfilled placeholder left in the rendered message: {rendered}"
        )


def test_the_entity_passes_the_placeholder_the_message_expects() -> None:
    """The names in the message and in the code must be the same names.

    The test above proves `{action}` renders. This proves the entity supplies
    `action` and not something else — together they close the loop, and
    neither does it alone.
    """
    import json
    import pathlib
    import re

    import custom_components.huawei_router_5g as component

    path = pathlib.Path(component.__path__[0]) / "strings.json"
    message = json.loads(path.read_text(encoding="utf-8"))["exceptions"][
        "write_not_confirmed"
    ]["message"]
    expected = set(re.findall(r"\{(\w+)\}", message))

    source = (pathlib.Path(component.__path__[0]) / "switch.py").read_text(
        encoding="utf-8"
    )
    block = re.search(
        r'translation_key="write_not_confirmed".*?translation_placeholders='
        r"\{(.*?)\}",
        source,
        re.DOTALL,
    )
    assert block, "the raise site has moved — this test can no longer see it"
    supplied = set(re.findall(r'"(\w+)":', block.group(1)))

    assert expected == supplied, (
        f"message expects {sorted(expected)}, entity supplies {sorted(supplied)}"
    )


# ---------------------------------------------------------------------------
# Section 22 — the exclusion, declared on the entity rather than inferred
# ---------------------------------------------------------------------------


def _write_descriptions():
    """Return every write-capable entity description, with its module."""
    from custom_components.huawei_router_5g import button, select, switch

    found = []
    for module in (button, select, switch):
        for name, obj in vars(module).items():
            if name.startswith("_"):
                continue
            candidates = obj if isinstance(obj, tuple) else (obj,)
            found.extend(
                (module.__name__.rsplit(".", 1)[-1], item)
                for item in candidates
                if hasattr(item, "key") and hasattr(item, "no_confirmation")
            )
    return found


def test_the_write_platforms_all_carry_the_exclusion_field() -> None:
    """Guard the guard: the sweep below is worthless if the field is absent.

    A platform whose description class lacks `no_confirmation` contributes no
    entries at all, so the exclusion sweep would pass over an empty set.
    """
    modules = {module for module, _ in _write_descriptions()}

    assert {"button", "select", "switch"} <= modules
    assert len(_write_descriptions()) >= 8


def test_only_connection_affecting_writes_declare_an_exclusion() -> None:
    """The declared set must match the set that genuinely cannot confirm.

    Section 22 asks for the exclusion to be visible **on the entity**, not
    left as an unwritten rule — a reviewer reading `select.py` should see why
    that write is never confirmed without going to `api.py` to notice a reader
    is missing.

    Reconnect is the only one. It re-establishes the connection, so the router
    answers abnormally *while succeeding*, and nothing it reports afterwards
    distinguishes a dial that worked from one that did not.

    **Network mode was on this list and no longer is.** It re-registers the
    radio for the same reason, but it differs in the way that matters: the mode
    it ends up in is readable. Confirmed live on 2026-08-16 — the write answers
    `-1: Unknown` and applies anyway — so `api.set_net_mode` settles for the
    radio and re-reads `net_mode`. Adding a fourth exclusion is a reviewable
    act; this fails when one appears.
    """
    declared = {item.key for _, item in _write_descriptions() if item.no_confirmation}

    assert declared == {"reconnect"}


def test_every_declared_exclusion_states_a_reason() -> None:
    """A bare flag records the decision without the reasoning behind it.

    The next reader has to know *why* this write cannot be confirmed, or the
    exclusion looks like an omission and gets removed.
    """
    for module, item in _write_descriptions():
        if item.no_confirmation is None:
            continue
        assert len(item.no_confirmation) >= 60, (
            f"{module}.{item.key} declares an exclusion with no real reason"
        )


def test_no_excluded_write_has_a_read_back_reader() -> None:
    """The declaration and the structural protection must agree.

    Two mechanisms guard the same rule — the field here and the absence of a
    reader in `READ_BACK_ENDPOINTS`. They can drift apart silently: adding a
    reader for an excluded write would re-enable confirmation on a control
    that cannot confirm, while the entity still claims it is excluded.

    **`net_mode` was on this list and now has a reader, deliberately.** It was
    excluded on the belief that the router's answer could not be trusted; that
    is true of the write's own response, which returns `-1: Unknown` while
    succeeding, and false of a read taken after the radio settles. Reconnect
    stays excluded because nothing it reports afterwards separates a dial that
    worked from one that did not.
    """
    excluded_endpoints = {"dial_up_connection", "dial_up_profiles"}

    assert not (excluded_endpoints & set(READ_BACK_ENDPOINTS))


@pytest.mark.asyncio
async def test_a_confirmed_write_publishes_the_new_position() -> None:
    """The latch is stored before the publish, and the publish carries it.

    The rest of this file stubs `async_write_ha_state` with a bare
    `MagicMock`, so it can show that a publish happened and not what it
    carried. That is the gap `stubbed_publish_tests.md` was written about, and
    the defect it describes is exactly this entity's: `is_on` reads the latch
    while the coordinator payload is still pre-write, so publishing before the
    latch is stored re-stamps the old position over the frontend's optimistic
    toggle and the switch springs back.
    """
    switch, _ = _switch({"dataswitch": "1"})
    published: list[bool | None] = []
    switch.async_write_ha_state = MagicMock(
        side_effect=lambda: published.append(switch.is_on)
    )

    await switch.async_turn_on()

    assert published == [True]
