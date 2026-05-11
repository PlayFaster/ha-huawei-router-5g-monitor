"""Shared helpers for the Huawei Router 5G Monitor integration."""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import HuaweiRouter5GDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

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
    "10": "EVDO rev. 0",
    "11": "EVDO rev. A",
    "12": "EVDO rev. B",
    "13": "1xRTT",
    "14": "UMB",
    "15": "1xEVDV",
    "16": "3xRTT",
    "17": "HSPA+ 64QAM",
    "18": "HSPA+ MIMO",
    "19": "LTE",
    "21": "IS95A",
    "22": "IS95B",
    "23": "CDMA1x",
    "24": "EVDO rev. 0",
    "25": "EVDO rev. A",
    "26": "EVDO rev. B",
    "27": "Hybrid CDMA1x",
    "28": "Hybrid EVDO rev. 0",
    "29": "Hybrid EVDO rev. A",
    "30": "Hybrid EVDO rev. B",
    "31": "eHRPD rev. 0",
    "32": "eHRPD rev. A",
    "33": "eHRPD rev. B",
    "34": "Hybrid eHRPD rev. 0",
    "35": "Hybrid eHRPD rev. A",
    "36": "Hybrid eHRPD rev. B",
    "41": "LTE-A",
    "51": "5G NR NSA",
    "52": "5G NR SA",
    "71": "LTE + 5G NR",
    "101": "5G",
}

# Network type codes that indicate active 5G NR connectivity
NR_NETWORK_TYPES: frozenset[str] = frozenset({"51", "52", "71", "101"})


def get_router_model(device_info: dict[str, Any] | None) -> str:
    """Extract the router model from device_information dict.

    Returns 'Huawei Router' if no model name is found.
    """
    if not device_info:
        return "Huawei Router"
    return (device_info.get("DeviceName") or "").strip() or "Huawei Router"


def parse_signal_value(val: Any) -> float | None:
    """Parse a signal value string to float, stripping unit suffixes.

    Handles values like '-95dBm', '-12dB', '6dB', or plain '6'.
    Returns None for empty, None, or unparsable values.
    """
    if val in (None, "", "N/A", "--"):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    s_lower = s.lower()
    for suffix in ("dbm", "db", "mhz", "khz", "ghz", "mbps", "bps", "s", "b"):
        if s_lower.endswith(suffix):
            s = s[: -len(suffix)].strip()
            break
    try:
        return float(s)
    except ValueError, TypeError:
        return None


def _safe_int(val: Any) -> int | None:
    """Safely convert value to int or return None."""
    f_val = parse_signal_value(val)
    return int(f_val) if f_val is not None else None


def _safe_float(val: Any) -> float | None:
    """Safely convert value to float or return None."""
    return parse_signal_value(val)


def _parse_complex_int(val: Any) -> Any:
    """Parse as int if simple number, otherwise return raw string."""
    if val in (None, "", "N/A", "--"):
        return None
    s_val = str(val).strip()
    # If it contains colons or multiple numbers, it's complex - return raw
    if ":" in s_val or len(s_val.split()) > 1:
        return s_val
    try:
        f_val = parse_signal_value(s_val)
        if f_val is not None:
            return int(f_val)
    except ValueError, TypeError:
        pass
    return s_val


def _parse_complex_float(val: Any) -> Any:
    """Parse as float if simple number, otherwise return raw string."""
    if val in (None, "", "N/A", "--"):
        return None
    s_val = str(val).strip()
    # If it contains colons or multiple numbers, it's complex - return raw
    if ":" in s_val or len(s_val.split()) > 1:
        return s_val
    f_val = parse_signal_value(s_val)
    return f_val if f_val is not None else s_val


def get_network_type_label(code: str | None) -> str | None:
    """Map a Huawei CurrentNetworkType code to a human-readable label."""
    if code is None:
        return None
    return _NETWORK_TYPE_MAP.get(str(code), f"Unknown ({code})")


def build_device_info(
    coordinator: HuaweiRouter5GDataUpdateCoordinator, group: str
) -> DeviceInfo:
    """Build standardized DeviceInfo dict for platforms."""
    group_names = {
        "system": "System",
        "signal": "Signal",
        "data": "Data",
        "sms": "SMS",
        "clients": "Clients",
        "wifi": "WiFi",
    }
    display_group = group_names.get(group, group.capitalize())
    sub_name = f"{coordinator.entry.title} {display_group}"

    mac = coordinator.mac
    # Fallback to host from options if MAC is missing (should be rare)
    from homeassistant.const import CONF_HOST

    host = coordinator.entry.options.get(CONF_HOST, "")
    sub_id_prefix = mac if mac else f"host_{host}"

    info = DeviceInfo(
        identifiers={(DOMAIN, f"{sub_id_prefix}_{group}")},
        name=sub_name,
        manufacturer="Huawei",
        model=coordinator.model,
        sw_version=coordinator.sw_version,
        hw_version=coordinator.hw_version,
        configuration_url=coordinator.api.url,
    )

    if group != "system":
        info["via_device"] = (DOMAIN, f"{sub_id_prefix}_system")

    return info


def parse_sms_list(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Parse get_sms_list response into a list of message dicts.

    Handles different response structures from different router models.
    """
    if not data:
        return []

    messages_container = data.get("Messages")
    if not messages_container:
        return []

    if not isinstance(messages_container, dict):
        _LOGGER.debug("Unexpected SMS container type: %s", type(messages_container))
        return []

    messages_raw = messages_container.get("Message")
    if not messages_raw:
        return []

    # Some routers return a list where the first element is metadata and the
    # actual messages start at index 1. Others return the list directly.
    if isinstance(messages_raw, list):
        if len(messages_raw) > 1 and not isinstance(messages_raw[0], dict):
            messages_raw = messages_raw[1:]
        elif (
            len(messages_raw) > 1
            and isinstance(messages_raw[0], dict)
            and "Index" not in messages_raw[0]
            and "Content" not in messages_raw[0]
        ):
            # First element is a dict but doesn't look like a message
            messages_raw = messages_raw[1:]
    elif isinstance(messages_raw, dict):
        # Single message returned as a dict
        messages_raw = [messages_raw]
    else:
        return []

    return [
        {
            "index": int(msg.get("Index", 0)),
            "phone": msg.get("Phone", ""),
            "content": msg.get("Content", ""),
            "date": msg.get("Date", ""),
            "read": str(msg.get("Smstat", "0")) == "1",
        }
        for msg in messages_raw
        if isinstance(msg, dict) and "Index" in msg
    ]


def find_ssid_by_path(
    ssids: list[dict[str, Any]], path_fragment: str
) -> dict[str, Any] | None:
    """Find an SSID dict based on its internal ID path fragment."""
    for ssid in ssids:
        if path_fragment in str(ssid.get("ID", "")):
            return ssid
    return None


def is_ssid_on(ssids: list[dict[str, Any]], path_fragment: str) -> bool | None:
    """Check if a specific radio path is enabled."""
    ssid = find_ssid_by_path(ssids, path_fragment)
    if ssid:
        return str(ssid.get("WifiEnable")) == "1"
    return None
