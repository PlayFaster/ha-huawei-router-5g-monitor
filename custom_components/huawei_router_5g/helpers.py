"""Shared helpers for the Huawei Router 5G Monitor integration."""

from typing import Any

# Huawei CurrentNetworkType code → human-readable label
_NETWORK_TYPE_MAP: dict[str, str] = {
    "0": "No Service",
    "1": "GSM",
    "2": "GPRS",
    "3": "EDGE",
    "4": "WCDMA",
    "5": "HSDPA",
    "6": "HSUPA",
    "7": "HSPA",
    "8": "TD-SCDMA",
    "9": "HSPA+",
    "10": "EV-DO rev.0",
    "11": "EV-DO rev.A",
    "12": "EV-DO rev.B",
    "13": "1xRTT",
    "17": "HSPA+ 64QAM",
    "18": "HSPA+ MIMO",
    "19": "LTE",
    "41": "LTE-A",
    "51": "5G NR NSA",
    "52": "5G NR SA",
    "71": "LTE + 5G NR",
}

# Network type codes that indicate active 5G NR connectivity
NR_NETWORK_TYPES: frozenset[str] = frozenset({"51", "52", "71"})


def get_router_model(device_info: dict | None) -> str:
    """Extract the router model from device_information dict.

    Returns 'Huawei Router' if no model name is found.
    """
    if not device_info:
        return "Huawei Router"
    return (device_info.get("DeviceName") or "").strip() or "Huawei Router"


def parse_signal_value(val: Any) -> float | None:
    """Parse a signal value string to float, stripping unit suffixes.

    Handles values like '-95dBm', '-12dB', '6dB', or plain '6'.
    Returns None for empty, None, or unparseable values.
    """
    if val in (None, "", "N/A", "--"):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    for suffix in ("dBm", "dB", "MHz", "kHz", "Mbps", "bps"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
            break
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def get_network_type_label(code: str | None) -> str | None:
    """Map a Huawei CurrentNetworkType code to a human-readable label."""
    if code is None:
        return None
    return _NETWORK_TYPE_MAP.get(str(code), f"Unknown ({code})")
