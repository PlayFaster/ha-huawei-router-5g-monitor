"""Shared helpers for the Huawei Router 5G Monitor integration."""

from __future__ import annotations

import logging
from calendar import monthrange
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo

from ._compat import via_device_link
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
    except (ValueError, TypeError):
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
    except (ValueError, TypeError):
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
    host = coordinator.entry.options.get(CONF_HOST, "")
    sub_id_prefix = mac or f"host_{host}"

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
        # The `via_device` tuple is deprecated in HA 2026.8 and removed in
        # 2027.8; `via_device_link` feature-detects and emits `via_device_id`
        # where available. The registry and entry id are resolved from the
        # coordinator so no new argument has to be threaded through every
        # entity call site.
        cast(dict[str, Any], info).update(
            via_device_link(
                coordinator.hass,
                DOMAIN,
                f"{sub_id_prefix}_system",
                coordinator.entry.entry_id,
            )
        )

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


def cycle_bounds(start_day: int, now: datetime) -> tuple[datetime, datetime, int]:
    """Return (start, end, length_in_days) of the billing cycle containing `now`.

    `start_day` is `monitoring/start_date`'s `StartDay` — the day of the month
    the router zeroes its monthly counters on. It is clamped to the length of
    each month it is applied to, so a start day of 31 lands on the 28th in
    February rather than being skipped: the router cannot reset on a date that
    does not exist, and skipping would silently merge two cycles into one.

    `now` must be timezone-aware and in the user's local zone. Cycle boundaries
    are local midnight — computing them in UTC would shift the reset day by up
    to a day for anyone not on UTC.

    Length is measured in **calendar days** rather than by dividing seconds, so
    a cycle spanning a DST transition is still 30 or 31 days rather than 30.04.

    Ported from `zte_router_5g`.
    """

    def _at(year: int, month: int) -> datetime:
        """Return local midnight on the start day of the given month."""
        last = monthrange(year, month)[1]
        return now.replace(
            year=year,
            month=month,
            day=min(start_day, last),
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    start = _at(now.year, now.month)
    if start > now:
        # The start day has not arrived yet this month, so the cycle in flight
        # began last month.
        prev_year, prev_month = (
            (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
        )
        start = _at(prev_year, prev_month)

    next_year, next_month = (
        (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    )
    end = _at(next_year, next_month)

    return start, end, (end.date() - start.date()).days


def project_cycle_usage(
    used: float,
    elapsed_days: float,
    cycle_length_days: int,
    prior_rate: float | None,
    credibility_days: float,
) -> float:
    """Project end-of-cycle usage from usage so far.

    The naive form — `used / elapsed * length` — divides by a number
    approaching zero, so its error early in a cycle is unbounded: half a
    gigabyte one second after a reset projects to over a million. Two things
    tame it.

    First, the denominator is floored at one day. That alone bounds the result
    without inventing a cap.

    Second, when a previous cycle is known, its daily rate is blended in — but
    **only into the unobserved remainder**. Blending the whole projection would
    be wrong: by day 20 most of the figure is a meter reading rather than a
    forecast, and shrinking observed bytes toward last cycle is meaningless.
    Applying it to the remainder alone makes the prior's influence decay
    structurally, because it is multiplied by a shrinking number of days. No
    clamp and no cliff: at day 20 of 30 the prior moves the answer by around one
    percent, and by day 28 it is noise.

    `credibility_days` sets how quickly this cycle's own rate displaces the
    prior — the weight reaches one half at that many days elapsed.

    **`elapsed_days` is wall-clock time since the cycle start, not the router's
    `MonthDuration`.** That field is *connected* time, which is the same thing
    only while the link never drops: `TotalConnectTime` is its lifetime
    equivalent and is plainly a connection counter. Feeding connected time in
    here while `cycle_length_days` stays wall-clock would inflate the rate by
    exactly the proportion of the cycle the router spent offline.

    Ported from `zte_router_5g`.
    """
    elapsed = max(elapsed_days, 0.0)
    remaining = max(cycle_length_days - elapsed, 0.0)

    current_rate = used / max(elapsed, 1.0)

    if prior_rate is None:
        rate = current_rate
    else:
        weight = elapsed / (elapsed + credibility_days)
        rate = weight * current_rate + (1.0 - weight) * prior_rate

    return used + remaining * rate
