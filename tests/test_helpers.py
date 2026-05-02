"""Tests for the Huawei Router 5G helpers module."""

from custom_components.huawei_router_5g.helpers import (
    get_network_type_label,
    get_router_model,
    parse_signal_value,
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
