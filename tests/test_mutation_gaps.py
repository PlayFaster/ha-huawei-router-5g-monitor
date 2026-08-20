"""Assertions the first `sensor.py` / `helpers.py` mutation run showed were absent.

Every test here was written against a specific surviving mutant. The functions
below were all *covered* — each had tests, and the suite was at 100% line and
branch — but covered in the shape that executes a line without checking what it
produced.

Grouped by module, and each docstring names the mutation it kills rather than
restating the code.

**Two survivor classes are deliberately not chased**, per
`mutation_testing_setup.md` §7:

- **Equivalent mutants.** `str(msg.get("Smstat", None)) == "1"` and
  `str(msg.get("Smstat", "0")) == "1"` both evaluate false when the key is
  absent, so no test can separate them. Same for `.get(k, False)` → `.get(k)`.
- **Type-annotation strings.** `cast("dict[str, Any]", …)` mutated to
  `cast("DICT[STR, ANY]", …)` has no runtime effect at all — `cast` returns its
  second argument untouched.
"""

from unittest.mock import MagicMock

import pytest

from custom_components.huawei_router_5g.helpers import (
    _tracked_macs,
    build_device_info,
    parse_sms_list,
)
from custom_components.huawei_router_5g.sensor import (
    _current_apn_profile,
    _parse_nr_band_from_band,
)

# ---------------------------------------------------------------------------
# helpers.parse_sms_list — 16 survivors
# ---------------------------------------------------------------------------


def _sms(**over):
    """One well-formed message, overridable per test."""
    return {
        "Index": "7",
        "Phone": "+353871234567",
        "Content": "hello",
        "Date": "2026-08-15 10:00:00",
        "Smstat": "0",
        **over,
    }


def _payload(*messages):
    return {"Messages": {"Message": list(messages)}}


def test_a_message_index_is_read_from_its_own_field() -> None:
    """Kills `int(msg.get("Index", 1))`.

    The index is what `delete_sms` is given. A default that is not `0` means a
    message with no index silently becomes a request to delete message 1 —
    someone else's message.
    """
    assert parse_sms_list(_payload(_sms()))[0]["index"] == 7


def test_a_null_index_does_not_take_down_the_whole_list() -> None:
    """Reject a null index without losing the whole list.

    **This found a real defect, not just a missing assertion.**

    The comprehension admits any message where the `Index` **key** is present,
    and an empty `<Index/>` element arrives as `None`. A `.get` default only
    applies to a *missing* key, so `int(None)` raised `TypeError` — and because
    the raise happens inside the comprehension, one malformed message lost the
    entire inbox rather than itself. Fixed by `int(msg.get("Index") or 0)`.
    """
    assert parse_sms_list(_payload(_sms(Index=None)))[0]["index"] == 0


def test_a_message_with_no_index_key_is_filtered_out() -> None:
    """The filter is on the key, so a message without one is not a message."""
    stripped = _sms()
    del stripped["Index"]

    assert parse_sms_list(_payload(stripped)) == []


def test_the_read_flag_is_true_only_for_status_one() -> None:
    """Pins the one value that means *read*, against a field of many codes."""
    assert parse_sms_list(_payload(_sms(Smstat="1")))[0]["read"] is True
    assert parse_sms_list(_payload(_sms(Smstat="0")))[0]["read"] is False
    assert parse_sms_list(_payload(_sms(Smstat="2")))[0]["read"] is False


def test_a_single_real_message_is_not_mistaken_for_metadata() -> None:
    """Kills `len(messages_raw) >= 1` in the metadata-offset heuristic.

    Some firmwares return a metadata element first. The guard requires **more
    than one** element before treating the first as metadata — relaxed to `>= 1`
    it discards the only message in a one-message inbox.
    """
    assert len(parse_sms_list(_payload(_sms()))) == 1


def test_the_metadata_element_is_dropped_when_there_is_one() -> None:
    """Kills `len(messages_raw) > 2`.

    Two elements where the first is not a message: the heuristic must fire.
    """
    result = parse_sms_list(_payload("metadata-not-a-dict", _sms()))

    assert len(result) == 1
    assert result[0]["index"] == 7


def test_the_heuristic_inspects_the_first_element_not_the_second() -> None:
    """Kills `messages_raw[0]` → `messages_raw[1]` in both conditions.

    Reading the wrong element makes the decision on a message that is real,
    so a genuine two-message inbox loses its first message.
    """
    first, second = _sms(Index="1"), _sms(Index="2")

    result = parse_sms_list(_payload(first, second))

    assert [m["index"] for m in result] == [1, 2]


def test_the_heuristic_matches_the_content_key_exactly() -> None:
    """Kills the `"Content"` case and `XX`-wrapping mutants.

    The key is the router's spelling. Mutated, the condition is always true,
    and the first message of every multi-message inbox is discarded as
    metadata.
    """
    result = parse_sms_list(_payload(_sms(Index="1"), _sms(Index="2")))

    assert len(result) == 2


# ---------------------------------------------------------------------------
# helpers.build_device_info — 12 survivors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("group", "label"),
    [
        ("system", "System"),
        ("signal", "Signal"),
        ("data", "Data"),
        ("clients", "Clients"),
        ("sms", "SMS"),
        ("wifi", "WiFi"),
    ],
)
def test_each_sub_device_group_resolves_to_its_own_label(
    mock_coordinator, group: str, label: str
) -> None:
    """Kills every key mutation in the group → label map.

    A mutated key does not raise — the lookup misses and the sub-device is
    named by the fallback, so six devices called the same thing appear in the
    registry and every entity under them is filed together. Nothing errors.
    """
    info = build_device_info(mock_coordinator, group)

    assert info["name"].endswith(label), f"{group} resolved to {info['name']!r}"


# ---------------------------------------------------------------------------
# helpers._tracked_macs — 4 survivors
# ---------------------------------------------------------------------------


def test_tracked_macs_reads_both_host_lists() -> None:
    """Kills mutations dropping either block name from the loop.

    Wired and wireless clients arrive in different blocks. Losing one is
    invisible in a household where every device is on WiFi, and deletes every
    wired client's tracker the next time cleanup runs.
    """
    coordinator = MagicMock()
    coordinator.data = {
        "lan_host_info": {"Hosts": {"Host": [{"MacAddress": "WIRED"}]}},
        "wlan_host_list": {"Hosts": {"Host": [{"MacAddress": "WIFI"}]}},
    }

    assert _tracked_macs(coordinator) == {"WIRED", "WIFI"}


def test_tracked_macs_ignores_a_block_that_is_not_a_dict() -> None:
    """A failed optional endpoint omits its block; the shape is not guaranteed."""
    coordinator = MagicMock()
    coordinator.data = {
        "lan_host_info": "not a dict",
        "wlan_host_list": {"Hosts": {"Host": [{"MacAddress": "WIFI"}]}},
    }

    assert _tracked_macs(coordinator) == {"WIFI"}


# ---------------------------------------------------------------------------
# sensor._current_apn_profile — 14 survivors
# ---------------------------------------------------------------------------


def _apn(current="3"):
    return {
        "dial_up_profiles": {
            "CurrentProfile": current,
            "Profiles": {
                "Profile": [
                    {"Index": "1", "Name": "first"},
                    {"Index": "3", "Name": "third"},
                    {"Index": "2", "Name": "second"},
                ]
            },
        }
    }


def test_the_apn_profile_is_matched_on_index_not_position() -> None:
    """The router returned profiles ordered 1, 3, 2 — position is not index.

    Kills the `Index` default mutations: with a wrong default the comparison
    matches the wrong profile, and the APN Name sensor reports a profile the
    router is not using.
    """
    assert _current_apn_profile(_apn("3"))["Name"] == "third"
    assert _current_apn_profile(_apn("2"))["Name"] == "second"


def test_an_unknown_current_profile_matches_nothing() -> None:
    """Kills `.get("CurrentProfile", "XXXX")` and the `None` default.

    A default that happens to equal no index is correct; one that matches an
    index would report a profile chosen by the default rather than the router.
    """
    assert _current_apn_profile(_apn("99")) is None


def test_a_missing_profile_list_is_not_a_crash() -> None:
    """Kills `.get("Profiles", None)` and `.get("Profile", None)`.

    Both raise `AttributeError` or `TypeError` on a block the router returned
    without the nested list — which is what a firmware without APN profiles
    returns. That takes the whole sensor platform down, not one sensor.
    """
    assert _current_apn_profile({"dial_up_profiles": {"CurrentProfile": "1"}}) is None
    assert (
        _current_apn_profile(
            {"dial_up_profiles": {"CurrentProfile": "1", "Profiles": {}}}
        )
        is None
    )


# ---------------------------------------------------------------------------
# sensor._parse_nr_band_from_band — 8 survivors
# ---------------------------------------------------------------------------


def test_the_nr_band_is_taken_from_the_last_parenthesis_in_the_segment() -> None:
    """Kills `rfind` → `find` on both the opening and closing marker.

    The composite band string carries several parenthesised groups per
    segment. Searching forwards finds the first, which is the LTE anchor, so
    the 5G band sensor reports an LTE band and looks plausible.
    """
    band = "20MHz@500(B1) + 15MHz@1875(B3) + 10MHz@152690(N28)"

    assert _parse_nr_band_from_band(band) == "N28"


def test_a_band_string_with_no_nr_segment_returns_nothing() -> None:
    """Kills `start >= 0`, which treats "not found" as a match at position 0."""
    assert _parse_nr_band_from_band("20MHz@500(B1) + 15MHz@1875(B3)") is None


def test_a_non_string_band_is_rejected_rather_than_split() -> None:
    """Kills `not band and not isinstance(...)`.

    With `and`, a non-empty non-string reaches `.split()` and raises. The
    field is null on some firmwares, and a list on others.
    """
    assert _parse_nr_band_from_band(None) is None
    assert _parse_nr_band_from_band(12345) is None
    assert _parse_nr_band_from_band("") is None


def test_segments_are_split_on_the_plus_separator() -> None:
    """Kills `band.split(None)`, which splits on whitespace instead.

    Whitespace splitting breaks a segment in half, so the marker search runs
    over a fragment and the band is lost — silently, as `None`.
    """
    assert _parse_nr_band_from_band("10MHz@152690(N28) + 20MHz@500(B1)") == "N28"


# ---------------------------------------------------------------------------
# diagnostics — 9 survivors
#
# `mutation_testing_setup.md` §7.1 applies here and inverts the usual rule: on
# a module whose job is to *remove* something, a mutated key that is **read**
# is a leak, not a rename. A mutated `.get("XXipXX")` returns `None`, the guard
# goes falsy, the branch is skipped entirely — and the original value is left
# in the output.
# ---------------------------------------------------------------------------


def test_pseudonyms_are_numbered_from_one_and_ascend() -> None:
    """Kills `+ 1` → `- 1` and `+ 2`, and the `.get(prefix, 1)` default.

    The numbering is the whole value of a pseudonym: `mac-1` must mean the
    same device everywhere in one download, and two devices must not collide.
    A counter starting at 2, or descending, still produces stable-looking
    tokens — `mac--1`, `mac-2` — so nothing looks wrong in the output.
    """
    from custom_components.huawei_router_5g.diagnostics import _Tokenizer

    tok = _Tokenizer()

    assert tok.token("mac", "AA:BB:CC:DD:EE:01") == "mac-1"
    assert tok.token("mac", "AA:BB:CC:DD:EE:02") == "mac-2"
    assert tok.token("ip", "192.168.8.5") == "ip-1"


def test_a_repeated_value_keeps_the_same_pseudonym() -> None:
    """Stability is the point — the same MAC twice must read as one device."""
    from custom_components.huawei_router_5g.diagnostics import _Tokenizer

    tok = _Tokenizer()
    first = tok.token("mac", "AA:BB:CC:DD:EE:01")

    assert tok.token("mac", "AA:BB:CC:DD:EE:01") == first
    assert tok.token("mac", "AA:BB:CC:DD:EE:02") != first


def test_the_sweep_tokenizes_the_matched_text_not_none() -> None:
    """Kills `tokenizer.token("mac", None)` and the IPv4 equivalent.

    Passing `None` instead of `m.group(0)` makes every match share one key, so
    **every MAC in the download collapses to a single pseudonym** — three
    different clients all read as `mac-1`. The output still looks sanitised,
    which is what makes it dangerous: nothing is obviously wrong, and the
    distinctness the pseudonyms exist to provide is gone.
    """
    from custom_components.huawei_router_5g.diagnostics import _sweep, _Tokenizer

    tok = _Tokenizer()
    swept = _sweep("AA:BB:CC:DD:EE:01 and AA:BB:CC:DD:EE:02", tok)

    assert "AA:BB:CC:DD:EE:01" not in swept
    assert "AA:BB:CC:DD:EE:02" not in swept
    assert "mac-1" in swept and "mac-2" in swept


def test_the_sweep_distinguishes_two_addresses_in_one_string() -> None:
    """The IPv4 half of the same defect."""
    from custom_components.huawei_router_5g.diagnostics import _sweep, _Tokenizer

    swept = _sweep("192.168.8.1 -> 192.168.8.99", _Tokenizer())

    assert "192.168.8.1" not in swept
    assert "192.168.8.99" not in swept
    assert "ip-1" in swept and "ip-2" in swept


# ---------------------------------------------------------------------------
# The survivors the first triage pass aimed at and missed
#
# Written after the verification run, which showed the earlier tests had been
# aimed partly at mutants that cannot be killed. These are the ones that were
# killable and were not covered.
# ---------------------------------------------------------------------------


def test_tracked_macs_survives_a_block_with_no_hosts_key() -> None:
    """Kills `block.get("Hosts", None)` and `block.get("Hosts", )`.

    Both raise `AttributeError` on a block the router returned without the
    nested `Hosts` wrapper — which is what an empty client list looks like on
    some firmwares. That takes the whole poll down, and the poll is what every
    entity depends on.
    """
    coordinator = MagicMock()
    coordinator.data = {
        "lan_host_info": {},
        "wlan_host_list": {"Hosts": {"Host": [{"MacAddress": "WIFI"}]}},
    }

    assert _tracked_macs(coordinator) == {"WIFI"}


def test_the_sub_device_group_map_matches_the_groups_actually_used() -> None:
    """The map and the entity descriptions must name the same groups.

    **This check exists because the `group.capitalize()` fallback hides
    typos.** A mistyped key does not raise — the lookup misses and the
    fallback produces a near-identical label, and for `system`, `signal`,
    `data` and `clients` it produces exactly the same string. Those four
    entries are invisible to any behavioural test, which is why four
    mutations of them survive mutation testing and always will.

    The fallback is kept on purpose: a `KeyError` would fail entity setup over
    a typo, which is worse than a slightly wrong label. This is what makes the
    typo visible instead.

    Both directions, because each catches a different mistake: a group with no
    entry gets the fallback silently, and an entry no group uses is dead
    weight that outlives whatever it was for.
    """
    import pathlib
    import re

    import custom_components.huawei_router_5g as component
    from custom_components.huawei_router_5g.helpers import SUB_DEVICE_LABELS

    source = "".join(
        p.read_text(encoding="utf-8")
        for p in sorted(pathlib.Path(component.__path__[0]).glob("*.py"))
    )
    used = set(re.findall(r'group="([a-z_]+)"', source))
    used |= set(re.findall(r'build_device_info\(\s*[\w.]+,\s*"([a-z_]+)"', source))

    assert used, "no group literals found in source — the pattern has drifted"
    assert used == set(SUB_DEVICE_LABELS), (
        f"groups used but unmapped: {sorted(used - set(SUB_DEVICE_LABELS))}; "
        f"mapped but unused: {sorted(set(SUB_DEVICE_LABELS) - used)}"
    )


def test_the_sub_device_identifier_falls_back_to_the_host_without_a_mac() -> None:
    """Kills the `CONF_HOST` default mutations in `build_device_info`.

    The host is only read when the MAC is missing, so with a MAC present every
    mutation of that default is unobservable. Without one it becomes the
    device identifier — and an identifier of `host_None` or `host_` collides
    across every entry that also lacks a MAC, merging two routers into one
    device.
    """
    from homeassistant.const import CONF_HOST

    from custom_components.huawei_router_5g.const import DOMAIN
    from custom_components.huawei_router_5g.helpers import build_device_info

    coordinator = MagicMock()
    coordinator.entry.title = "Router"
    coordinator.entry.options = {CONF_HOST: "192.168.8.1"}
    coordinator.mac = None

    info = build_device_info(coordinator, "system")

    assert info["identifiers"] == {(DOMAIN, "host_192.168.8.1_system")}


def test_the_identifier_is_stable_when_neither_mac_nor_host_is_known() -> None:
    """The empty-string default is the deliberate one, and it is load-bearing.

    `None` would produce `host_None`; the empty default produces `host_`,
    which is at least consistent with itself across a restart.
    """
    from custom_components.huawei_router_5g.const import DOMAIN
    from custom_components.huawei_router_5g.helpers import build_device_info

    coordinator = MagicMock()
    coordinator.entry.title = "Router"
    coordinator.entry.options = {}
    coordinator.mac = None

    info = build_device_info(coordinator, "system")

    assert info["identifiers"] == {(DOMAIN, "host__system")}


@pytest.mark.asyncio
async def test_trackers_are_added_with_update_before_add() -> None:
    """Kills the `async_add_entities(new_entities, True)` flag mutations.

    `update_before_add=True` is what gives a newly discovered client a state
    immediately rather than at the next poll. Mutated to `False`, a tracker
    appears as `unknown` for a full interval — which on a three-minute poll is
    long enough to look broken and short enough never to be reported.
    """
    from unittest.mock import AsyncMock as _AsyncMock

    from custom_components.huawei_router_5g.device_tracker import async_setup_entry

    coordinator = MagicMock()
    coordinator.data = {
        "lan_host_info": {"Hosts": {"Host": [{"MacAddress": "AA:BB:CC:DD:EE:01"}]}},
    }
    coordinator.entry.unique_id = "dc7196112233"
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.unique_id = "dc7196112233"
    add = MagicMock()

    await async_setup_entry(_AsyncMock(), entry, add)

    add.assert_called_once()
    assert add.call_args[0][1] is True, "trackers added without update_before_add"


@pytest.mark.asyncio
async def test_a_tracker_is_built_against_the_real_coordinator() -> None:
    """Kills `HuaweiRouterDeviceTracker(None, mac)`.

    A tracker holding `None` cannot read the host list, so it can never report
    `home` — and the failure is per-entity and silent, not a setup error.
    """
    from unittest.mock import AsyncMock as _AsyncMock

    from custom_components.huawei_router_5g.device_tracker import async_setup_entry

    coordinator = MagicMock()
    coordinator.data = {
        "lan_host_info": {"Hosts": {"Host": [{"MacAddress": "AA:BB:CC:DD:EE:01"}]}},
    }
    coordinator.entry.unique_id = "dc7196112233"
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.unique_id = "dc7196112233"
    add = MagicMock()

    await async_setup_entry(_AsyncMock(), entry, add)

    created = add.call_args[0][0]
    assert created, "no tracker was created"
    assert all(t.coordinator is coordinator for t in created)
