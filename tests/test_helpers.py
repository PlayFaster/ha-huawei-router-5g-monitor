"""Tests for the Huawei Router 5G helpers module."""

from unittest.mock import MagicMock

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
    assert "via_device" not in info

    # Test Signal Group (non-system)
    info = build_device_info(coordinator, "signal")
    assert info["identifiers"] == {(DOMAIN, "001122334455_signal")}
    assert info["name"] == "My Router Signal"
    assert info["via_device"] == (DOMAIN, "001122334455_system")

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
