"""Tests for the Huawei Router 5G helpers module."""

from unittest.mock import MagicMock

import pytest

from custom_components.huawei_router_5g.const import DOMAIN
from custom_components.huawei_router_5g.helpers import (
    _parse_complex_float,
    _parse_complex_int,
    _safe_float,
    _safe_int,
    build_device_info,
    get_network_type_label,
    get_router_model,
    parse_signal_value,
    parse_sms_list,
)
from tests.conftest import assert_is_root, assert_links_to_parent

# ---------------------------------------------------------------------------
# get_router_model
# ---------------------------------------------------------------------------


def test_get_router_model_none():
    """Return default when called with None."""
    assert get_router_model(None) == "Huawei Router"


def test_get_router_model_empty():
    """Return default when called with empty dict."""
    assert get_router_model({}) == "Huawei Router"


def test_get_router_model_with_device_name():
    """Return DeviceName when it is present."""
    assert get_router_model({"DeviceName": "B535s-232"}) == "B535s-232"


def test_get_router_model_device_name_none():
    """Return default when DeviceName is None."""
    assert get_router_model({"DeviceName": None}) == "Huawei Router"


def test_get_router_model_device_name_empty_string():
    """Return default when DeviceName is empty string."""
    assert get_router_model({"DeviceName": ""}) == "Huawei Router"


# ---------------------------------------------------------------------------
# parse_signal_value
# ---------------------------------------------------------------------------


def test_parse_signal_value_none():
    """Return None for None input."""
    assert parse_signal_value(None) is None


def test_parse_signal_value_empty():
    """Return None for empty string."""
    assert parse_signal_value("") is None


def test_parse_signal_value_na():
    """Return None for N/A string."""
    assert parse_signal_value("N/A") is None


def test_parse_signal_value_double_dash():
    """Return None for '--' placeholder."""
    assert parse_signal_value("--") is None


def test_parse_signal_value_dbm():
    """Strip dBm unit and return float."""
    assert parse_signal_value("-95dBm") == -95.0


def test_parse_signal_value_db():
    """Strip dB unit and return float."""
    assert parse_signal_value("-12dB") == -12.0


def test_parse_signal_value_positive_db():
    """Handle positive dB value with unit."""
    assert parse_signal_value("6dB") == 6.0


def test_parse_signal_value_plain_number():
    """Handle plain numeric string without unit."""
    assert parse_signal_value("4") == 4.0


def test_parse_signal_value_int():
    """Handle integer input directly."""
    assert parse_signal_value(-95) == -95.0


def test_parse_signal_value_float():
    """Handle float input directly."""
    assert parse_signal_value(-12.5) == -12.5


def test_parse_signal_value_invalid():
    """Return None for non-numeric strings."""
    assert parse_signal_value("invalid") is None


def test_parse_signal_value_mhz():
    """Strip MHz unit."""
    assert parse_signal_value("20MHz") == 20.0


def test_parse_signal_value_bps_units():
    """Test various bits-per-second units."""
    assert parse_signal_value("100mbps") == 100.0
    assert parse_signal_value("50bps") == 50.0
    assert parse_signal_value("10s") == 10.0
    assert parse_signal_value("100b") == 100.0


# ---------------------------------------------------------------------------
# safe conversions
# ---------------------------------------------------------------------------


def test_safe_int():
    """Test _safe_int helper."""
    assert _safe_int("20MHz") == 20
    assert _safe_int("-95dBm") == -95
    assert _safe_int(None) is None
    assert _safe_int("N/A") is None


def test_safe_float():
    """Test _safe_float helper."""
    assert _safe_float("-12.5dB") == -12.5
    assert _safe_float(None) is None


# ---------------------------------------------------------------------------
# complex parsing
# ---------------------------------------------------------------------------


def test_parse_complex_int():
    """Test _parse_complex_int helper."""
    assert _parse_complex_int("20") == 20
    assert _parse_complex_int("20MHz") == 20
    assert _parse_complex_int("DL:500 UL:18500") == "DL:500 UL:18500"
    assert _parse_complex_int("1:2:3") == "1:2:3"
    assert _parse_complex_int(None) is None
    assert _parse_complex_int("invalid") == "invalid"


def test_parse_complex_float():
    """Test _parse_complex_float helper."""
    assert _parse_complex_float("-12.5") == -12.5
    assert _parse_complex_float("-12.5dB") == -12.5
    assert _parse_complex_float("DL:50.5 UL:18.5") == "DL:50.5 UL:18.5"
    assert _parse_complex_float("1:2.5:3") == "1:2.5:3"
    assert _parse_complex_float(None) is None
    assert _parse_complex_float("invalid") == "invalid"


# ---------------------------------------------------------------------------
# get_network_type_label
# ---------------------------------------------------------------------------


def test_get_network_type_label_none():
    """Return None for None input."""
    assert get_network_type_label(None) is None


def test_get_network_type_label_lte():
    """Map '19' to 'LTE'."""
    assert get_network_type_label("19") == "LTE"


def test_get_network_type_label_5g_nsa():
    """Map '51' to '5G NR NSA'."""
    assert get_network_type_label("51") == "5G NR NSA"


def test_get_network_type_label_5g_sa():
    """Map '52' to '5G NR SA'."""
    assert get_network_type_label("52") == "5G NR SA"


def test_get_network_type_label_unknown():
    """Return 'Unknown (code)' for unrecognised codes."""
    assert get_network_type_label("99") == "Unknown (99)"


def test_get_network_type_label_gsm():
    """Map '1' to 'GSM'."""
    assert get_network_type_label("1") == "GSM"


# ---------------------------------------------------------------------------
# build_device_info
# ---------------------------------------------------------------------------


def test_build_device_info():
    """Test standardized DeviceInfo construction."""
    coordinator = MagicMock()
    coordinator.entry.title = "My Router"
    coordinator.entry.options = {}
    coordinator.mac = "001122334455"
    coordinator.model = "H165-383"
    coordinator.sw_version = "1.0.1"
    coordinator.hw_version = "v1"
    coordinator.api.url = "http://192.168.8.1"

    # Test System Group
    info = build_device_info(coordinator, "system")
    assert info["identifiers"] == {(DOMAIN, "001122334455_system")}
    assert info["name"] == "My Router System"
    assert_is_root(info)

    # Test Signal Group (non-system)
    info = build_device_info(coordinator, "signal")
    assert info["identifiers"] == {(DOMAIN, "001122334455_signal")}
    assert info["name"] == "My Router Signal"
    assert_links_to_parent(info, "001122334455_system")

    # Test Fallback ID (no MAC)
    coordinator.mac = None
    coordinator.entry.options = {"host": "192.168.8.1"}
    info = build_device_info(coordinator, "system")
    assert info["identifiers"] == {(DOMAIN, "host_192.168.8.1_system")}


# ---------------------------------------------------------------------------
# parse_sms_list
# ---------------------------------------------------------------------------


def test_parse_sms_list_none():
    """Return empty list for None input."""
    assert parse_sms_list(None) == []


def test_parse_sms_list_empty():
    """Return empty list for empty dict or missing Messages."""
    assert parse_sms_list({}) == []
    assert parse_sms_list({"Messages": None}) == []
    assert parse_sms_list({"Messages": "not_a_dict"}) == []


def test_parse_sms_list_standard():
    """Parse standard SMS list."""
    data = {
        "Messages": {
            "Message": [
                {
                    "Index": "1",
                    "Phone": "123456",
                    "Content": "Hello",
                    "Date": "2023-01-01",
                    "Smstat": "1",
                },
                {
                    "Index": "2",
                    "Phone": "654321",
                    "Content": "World",
                    "Date": "2023-01-02",
                    "Smstat": "0",
                },
            ]
        }
    }
    sms = parse_sms_list(data)
    assert len(sms) == 2
    assert sms[0]["index"] == 1
    assert sms[0]["read"] is True
    assert sms[1]["index"] == 2
    assert sms[1]["read"] is False


def test_parse_sms_list_with_metadata_string():
    """Parse SMS list where index 0 is a metadata string."""
    data = {"Messages": {"Message": ["Count: 1", {"Index": "1", "Content": "Test"}]}}
    sms = parse_sms_list(data)
    assert len(sms) == 1
    assert sms[0]["index"] == 1


def test_parse_sms_list_with_metadata_dict():
    """Parse SMS list where index 0 is a metadata dict."""
    data = {
        "Messages": {"Message": [{"Count": "1"}, {"Index": "1", "Content": "Test"}]}
    }
    sms = parse_sms_list(data)
    assert len(sms) == 1
    assert sms[0]["index"] == 1


def test_parse_sms_list_single_dict():
    """Parse SMS list containing a single message dict."""
    data = {"Messages": {"Message": {"Index": "1", "Content": "Single"}}}
    sms = parse_sms_list(data)
    assert len(sms) == 1
    assert sms[0]["index"] == 1


def test_parse_sms_list_invalid_type():
    """Return empty list for invalid Message container type."""
    data = {"Messages": {"Message": 123}}
    assert parse_sms_list(data) == []


def test_parse_complex_int_error():
    """Test _parse_complex_int error branch."""
    # We need to trigger the except (ValueError, TypeError) block.
    # parse_signal_value returns None for "invalid", so it doesn't enter the
    # try block or returns None. To hit the catch, we'd need parse_signal_value
    # to return something that int() fails on, but parse_signal_value already
    # returns float or None. Actually, line 116-117 is hit if int(f_val) fails.
    # If f_val is 10.5, int(10.5) is 10 (no error).
    # If we pass a string that parse_signal_value returns as a float but
    # int() fails? Unlikely.
    # However, we can mock parse_signal_value inside the test to force the error.
    from unittest.mock import patch

    with patch(
        "custom_components.huawei_router_5g.helpers.parse_signal_value",
        return_value="not_an_int",
    ):
        assert _parse_complex_int("trigger_error") == "trigger_error"


def test_parse_sms_list_empty_messages():
    """Test parse_sms_list with empty Message field."""
    data = {"Messages": {"Message": []}}
    assert parse_sms_list(data) == []
    data = {"Messages": {"Message": None}}
    assert parse_sms_list(data) == []


# ---------------------------------------------------------------------------
# HuaweiAboutEntity — the `about` note mechanism
# ---------------------------------------------------------------------------


def test_an_entity_with_no_note_is_left_exactly_as_it_was():
    """No note means no key, not an empty one.

    An `about: None` that still emitted the key would put a null attribute on
    every entity that has not been given a note yet, which reads as a broken
    note rather than an absent one.
    """
    from custom_components.huawei_router_5g.helpers import HuaweiAboutEntity

    entity = HuaweiAboutEntity()

    assert entity._with_about({"ssid": "Home"}) == {"ssid": "Home"}
    assert entity._with_about(None) is None
    assert entity.extra_state_attributes is None


def test_the_note_is_read_from_the_description_when_there_is_no_class_override():
    """Both sources resolve, and `_attr_about` wins.

    Description-driven entities take the note from the description; the device
    tracker has no description at all and sets `_attr_about` instead. Both
    paths have to work, and the class-level value has to take precedence or
    the tracker would silently publish nothing.
    """
    from unittest.mock import MagicMock

    from custom_components.huawei_router_5g.helpers import HuaweiAboutEntity

    entity = HuaweiAboutEntity()
    entity.entity_description = MagicMock(about="From the description")
    assert entity.extra_state_attributes == {"about": "From the description"}

    entity._attr_about = "From the class"
    assert entity.extra_state_attributes == {"about": "From the class"}


def test_a_binary_sensor_with_no_attributes_of_its_own_still_carries_the_note():
    """The mixin's default property is the path most entities take.

    Most entities in this component publish nothing but the note, so this is
    the common case rather than an edge one — and it is the case that breaks
    if the mixin is listed after `CoordinatorEntity` in the bases, because the
    platform's own `extra_state_attributes` then wins.
    """
    from unittest.mock import MagicMock

    from custom_components.huawei_router_5g.binary_sensor import (
        LTE_CA_DESCRIPTION,
        HuaweiBinarySensor,
    )

    coordinator = MagicMock()
    coordinator.data = {}
    sensor = HuaweiBinarySensor(coordinator, MagicMock(), LTE_CA_DESCRIPTION)

    assert sensor.extra_state_attributes == {"about": LTE_CA_DESCRIPTION.about}


# ---------------------------------------------------------------------------
# Mutation findings, recommendations_20260815.md
# ---------------------------------------------------------------------------


def _device_info_coordinator():
    """Build the coordinator stub `build_device_info` reads from."""
    coordinator = MagicMock()
    coordinator.entry.title = "My Router"
    coordinator.entry.options = {}
    coordinator.entry.entry_id = "entry-abc"
    coordinator.mac = "001122334455"
    coordinator.model = "H165-383"
    coordinator.sw_version = "1.0.1"
    coordinator.hw_version = "v1"
    coordinator.api.url = "http://192.168.8.1"
    return coordinator


def test_build_device_info_links_to_the_named_parent():
    """The parent link names a specific device, and nothing checked which.

    Covers finding ASSERT.1 from recommendations_20260815.md.

    `assert_links_to_parent()` asserts on HA 2026.8+ only that `via_device_id`
    is **truthy** — it never inspects the identifier it is passed. With a
    mocked device registry that id is truthy whatever arguments produced it,
    so `via_device_link(hass, None, None, None)` passed a dozen tests.

    Asserting at the call boundary is the proportionate fix: it is the one
    place a mocked registry cannot hide the arguments. The helper is
    deliberately left alone — resolving the id through the registry would need
    a real `hass` in every test that uses it.
    """
    from unittest.mock import patch

    coordinator = _device_info_coordinator()

    with patch(
        "custom_components.huawei_router_5g.helpers.via_device_link",
        return_value={"via_device_id": "resolved"},
    ) as link:
        build_device_info(coordinator, "signal")

    link.assert_called_once()
    args = link.call_args.args
    assert args[0] is coordinator.hass
    assert args[1] == DOMAIN
    assert args[2] == "001122334455_system"
    assert args[3] == "entry-abc"


def test_build_device_info_carries_the_hardware_identity():
    """Section 2: the registry must be right while the hardware is offline.

    Covers finding RETVAL.1 from recommendations_20260815.md. All three fields
    could be set to None, or dropped from the call entirely, with the suite
    green. Distinct sentinels, so a swap cannot pass either.
    """
    coordinator = _device_info_coordinator()
    coordinator.model = "MODEL-SENTINEL"
    coordinator.sw_version = "SW-SENTINEL"
    coordinator.hw_version = "HW-SENTINEL"

    info = build_device_info(coordinator, "data")

    assert info["model"] == "MODEL-SENTINEL"
    assert info["sw_version"] == "SW-SENTINEL"
    assert info["hw_version"] == "HW-SENTINEL"


def test_build_device_info_names_a_group_it_has_never_heard_of():
    """The group map is a display-name override, not a registration.

    Covers finding BVA.5 from recommendations_20260815.md. The
    `group.capitalize()` fallback is what makes a seventh sub-device degrade
    gracefully instead of being named "My Router None".
    """
    info = build_device_info(_device_info_coordinator(), "storage")

    assert info["name"] == "My Router Storage"


@pytest.mark.parametrize("sentinel", ["", "N/A", "--", None])
def test_the_routers_no_value_sentinels_parse_to_none(sentinel):
    """`"--"` must reach a sensor as unknown, not as the string `"--"`.

    Covers finding ERR.3 from recommendations_20260815.md.

    The guard is decorative in `parse_signal_value`, whose fall-through hits
    `float()` and returns None anyway — but load-bearing in these two, where
    the fall-through returns the raw string. Without it a numeric sensor
    publishes the literal `"--"` as its state.
    """
    assert _parse_complex_int(sentinel) is None
    assert _parse_complex_float(sentinel) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1970000khz", 1970000.0),
        ("1970000KHz", 1970000.0),
        ("3.5ghz", 3.5),
        ("3.5GHz", 3.5),
    ],
)
def test_khz_and_ghz_suffixes_are_stripped(raw, expected):
    """Two of the nine unit suffixes were never exercised.

    Covers finding ERR.4 from recommendations_20260815.md. The other seven had
    their mutants killed, so this was a precise gap rather than a thin area.
    `khz` is the one that matters: the router reports `ulfrequency` and
    `dlfrequency` in kHz, and an unparsed value takes four sensors to unknown.

    The mixed-case forms are included because the comparison runs on a
    lower-cased copy and nothing proved that.
    """
    assert parse_signal_value(raw) == expected


def test_a_message_missing_every_optional_field_takes_the_defaults():
    """A firmware that omits a field must not take the SMS sensors down.

    Covers finding ERR.2 from recommendations_20260815.md. Every message dict
    in the suite carried every field, so no default was ever taken — and one
    of them raises when absent: `int(msg.get("Index", None))` is `int(None)`,
    a TypeError that propagates out of the parser.
    """
    parsed = parse_sms_list({"Messages": {"Message": [{"Index": "7"}]}})

    assert len(parsed) == 1
    assert parsed[0]["index"] == 7
    assert parsed[0]["phone"] == ""
    assert parsed[0]["content"] == ""
    assert parsed[0]["date"] == ""
    assert parsed[0]["read"] is False


def test_entries_that_are_not_messages_are_dropped_rather_than_parsed():
    """The filter is `isinstance` **and** `"Index" in msg`, not either.

    Covers finding ERR.2 from recommendations_20260815.md. Under `or`, a bare
    string reaches `msg.get` and raises; a dict with no `Index` is parsed as
    though it were a message.
    """
    parsed = parse_sms_list(
        {
            "Messages": {
                "Message": [
                    {"Index": "1", "Content": "real"},
                    {"Content": "no index — metadata, not a message"},
                    "not a dict at all",
                ]
            }
        }
    )

    assert len(parsed) == 1
    assert parsed[0]["index"] == 1


@pytest.mark.parametrize(
    ("messages", "expected_indexes"),
    [
        # One real message must be kept — this is what `> 1` decides.
        ([{"Index": "5", "Content": "only"}], [5]),
        # A leading metadata element carries neither key, and is dropped.
        ([{"Count": "2"}, {"Index": "9", "Content": "real"}], [9]),
        # Two real messages: neither is metadata, so neither is dropped.
        (
            [{"Index": "1", "Content": "a"}, {"Index": "2", "Content": "b"}],
            [1, 2],
        ),
    ],
)
def test_the_metadata_offset_heuristic_at_its_edges(messages, expected_indexes):
    """Some firmware prefixes the list with a count element.

    Covers finding BVA.4 from recommendations_20260815.md. The suite only ever
    supplied well-formed multi-message lists whose first element was a real
    message, so neither edge of the length test nor either side of the
    metadata test was exercised — including a straight inversion of the
    condition.

    The indexes are asserted, not just the count: on count alone the
    single-message and metadata cases are indistinguishable.
    """
    parsed = parse_sms_list({"Messages": {"Message": messages}})

    assert [m["index"] for m in parsed] == expected_indexes
