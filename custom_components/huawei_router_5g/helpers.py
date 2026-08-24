"""Shared helpers for the Huawei Router 5G Monitor integration."""

from __future__ import annotations

import asyncio
import logging
import math
from calendar import monthrange
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from ._compat import via_device_link
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

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

READ_BACK_RETRY_DELAY = 1.0
"""Seconds between the two read-back attempts (Section 22).

These routers commonly answer the first read after a write with the *old*
value — the command is accepted and applied a moment later. One short pause
separates that from a genuine refusal. Long enough to matter, short enough
that a confirmed control still beats the ten-second debounce it replaces.
"""


def get_router_model(device_info: dict[str, Any] | None) -> str:
    """Extract the router model from device_information dict.

    Returns 'Huawei Router' if no model name is found.
    """
    if not device_info:
        return "Huawei Router"
    return (device_info.get("DeviceName") or "").strip() or "Huawei Router"


PARSE_PRECISION = 3
"""Decimal places kept by `parse_signal_value`.

Section 6 requires rounding at parse time. Three places is the standard's own
example and is far below the precision of anything this router reports — the
signal figures arrive as integers or one decimal, and the derived values are
unit conversions of byte counters. It exists to stop float artefacts of the
`0.30000000000000004` kind reaching the recorder, not to reduce real
precision.
"""


def _finite(val: float) -> float | None:
    """Return the value, or None if it is infinity or NaN."""
    return val if math.isfinite(val) else None


def parse_signal_value(val: Any) -> float | None:
    """Parse a signal value string to float, stripping unit suffixes.

    Handles values like '-95dBm', '-12dB', '6dB', or plain '6'.
    Returns None for empty, None, or unparsable values.

    **Rounds at parse time (Section 6).** This is the single point every
    numeric value in the component passes through — `_safe_int` and
    `_safe_float` both delegate here — so rounding here covers all of them.
    Rounding matters even though 27 entities set
    `suggested_display_precision`, because that setting only governs what the
    dashboard renders: the unrounded value is what reaches the recorder and
    long-term statistics, so without this the stored history carries precision
    the screen never shows and nothing ever looks wrong.

    **Non-finite values are unparsable, not values.** `float()` accepts
    `"inf"` and `"nan"`, so without the finite check they would leave here as
    numbers: `_safe_int` would then raise `OverflowError` on the first and
    `ValueError` on the second, from inside a `value_fn` that nothing catches,
    and `_safe_float` would publish infinity as a sensor state and carry it
    into long-term statistics, where it cannot be taken back. Returning None
    routes both to *unknown*, which is what the caller already handles.
    """
    if val in (None, "", "N/A", "--"):
        return None
    if isinstance(val, (int, float)):
        return _finite(round(float(val), PARSE_PRECISION))
    s = str(val).strip()
    s_lower = s.lower()
    for suffix in ("dbm", "db", "mhz", "khz", "ghz", "mbps", "bps", "s", "b"):
        if s_lower.endswith(suffix):
            s = s[: -len(suffix)].strip()
            break
    try:
        return _finite(round(float(s), PARSE_PRECISION))
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
    """Parse as int if simple number, otherwise return raw string.

    **No `try` around `int()`, deliberately.** `parse_signal_value` returns a
    finite float or None, so the conversion cannot raise — the guard that used
    to sit here existed for `"inf"` and `"nan"`, which are now rejected at the
    parser instead of caught at every caller.
    """
    if val in (None, "", "N/A", "--"):
        return None
    s_val = str(val).strip()
    # If it contains colons or multiple numbers, it's complex - return raw
    if ":" in s_val or len(s_val.split()) > 1:
        return s_val
    f_val = parse_signal_value(s_val)
    if f_val is not None:
        return int(f_val)
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


_GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
# The extension table. These are still GSM-7, but each costs two septets
# because it is sent as ESC + character, so they are counted separately by
# anything that cares about segment boundaries.
_GSM7_EXTENDED = "\f^{}\\[~]|€"

GSM7_CHARS = frozenset(_GSM7_BASIC + _GSM7_EXTENDED)


def is_gsm7(text: str) -> bool:
    """Return True when every character is in the GSM 03.38 alphabet.

    False means at least one character forces UCS-2 for the whole message — a
    single emoji or curly quote is enough, which is why the Unicode ceiling is
    so much lower than the plain-text one.

    Ported from `zte_router_5g`, which established the table.
    """
    return all(char in GSM7_CHARS for char in text)


def get_network_type_label(code: str | None) -> str | None:
    """Map a Huawei CurrentNetworkType code to a human-readable label."""
    if code is None:
        return None
    return _NETWORK_TYPE_MAP.get(str(code), f"Unknown ({code})")


# The single `about` attribute name, and the frozenset that carries it into
# `_unrecorded_attributes`. Public on purpose: Home Assistant resolves
# `_unrecorded_attributes` by ordinary attribute lookup and does **not** union
# it across bases, so every entity class that declares its own set has to start
# from this one. Reaching for `HuaweiAboutEntity._unrecorded_attributes`
# instead would be a private access at six call sites.
ABOUT_ATTRIBUTE = "about"
ABOUT_UNRECORDED: frozenset[str] = frozenset({ABOUT_ATTRIBUTE})


class HuaweiAboutEntity:
    """Mixin exposing a static, human-facing ``about`` note as an attribute.

    Ported from ``zte_router_5g`` (which took it from ``unifi_network_monitor``
    and ``wifi_ssid_monitor``); keep the implementations interchangeable. Set the
    text via an ``about`` field on the entity description — every description in
    this component carries one and a sweep enforces it — or via ``_attr_about``
    at class level for an entity that has no description.

    The note shows in Tools and the More Info dialog but is listed in
    ``_unrecorded_attributes``, so the recorder never writes it to history. That
    is what makes it free: the text is identical on every state change, and
    recording it would cost one copy per change forever
    (``dev_standards`` Section 14).

    **List this mixin FIRST in an entity's bases** so its
    ``extra_state_attributes`` wins over the platform default. An entity that
    defines its own ``extra_state_attributes`` must route the result through
    ``_with_about``, or the note silently disappears for that entity only —
    which is the one failure mode here that no type checker sees.

    The text is hardcoded rather than translated. There is no HA-native
    "entity description" field, and this is a pragmatic use of the attribute
    channel rather than a translation surface.
    """

    _unrecorded_attributes = ABOUT_UNRECORDED
    _attr_about: str | None = None

    @property
    def _about_text(self) -> str | None:
        """Resolve the note from ``_attr_about`` or the entity description."""
        if self._attr_about is not None:
            return self._attr_about
        description = getattr(self, "entity_description", None)
        return getattr(description, "about", None) if description is not None else None

    def _with_about(self, attrs: dict[str, Any] | None) -> dict[str, Any] | None:
        """Merge the ``about`` note into an entity's own attribute dict."""
        about = self._about_text
        if about is None:
            return attrs
        return {ABOUT_ATTRIBUTE: about, **(attrs or {})}

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Default: expose only the ``about`` note when one is set."""
        return self._with_about(None)


SUB_DEVICE_LABELS: dict[str, str] = {
    "system": "System",
    "signal": "Signal",
    "data": "Data",
    "sms": "SMS",
    "clients": "Clients",
    "wifi": "WiFi",
}
"""Display label for each sub-device group.

Module level rather than local so a test can reconcile it against the groups
the entity descriptions actually use. That reconciliation is necessary because
`build_device_info` falls back to `group.capitalize()`, which produces **the
identical string** for `system`, `signal`, `data` and `clients` — so a mistyped
key in this map is invisible to every behavioral test, and four mutations of
it survive mutation testing by construction.

The fallback is kept deliberately: a `KeyError` here would fail entity setup
for a typo, which is a worse outcome than a slightly wrong label. The test is
what makes the typo visible.
"""


def build_device_info(
    coordinator: HuaweiRouter5GDataUpdateCoordinator, group: str
) -> DeviceInfo:
    """Build standardized DeviceInfo dict for platforms."""
    display_group = SUB_DEVICE_LABELS.get(group, group.capitalize())
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
            # `or 0`, not a `.get` default: the filter below admits a message
            # whose `Index` key is present but null, which an empty `<Index/>`
            # element becomes. A default only applies to a missing key, so
            # `int(None)` raised and took the whole list down rather than one
            # message. Found by a mutation test on 2026-08-15.
            "index": int(msg.get("Index") or 0),
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


async def confirm_write(
    api: Any,
    endpoint: str,
    extract: Callable[[dict[str, Any]], Any],
    expected: str,
    *,
    label: str,
) -> bool | None:
    """Re-read one key after a write and say whether the device agrees.

    Section 22's three outcomes, kept distinct:

    | Return | Meaning | Caller |
    | :-- | :-- | :-- |
    | `True` | The read agrees | Publish immediately |
    | `False` | The read disagrees, twice | Raise a translated error |
    | `None` | The read failed or omitted the key | **Unverified, not failed** |

    **`None` is the row that matters.** Collapsing it into `False` reports a
    successful write as a failure whenever the router is briefly busy, and
    invites the user to repeat a command that has already taken effect. The
    integration previously had no read-back at all and confirmed writes with a
    debounced full refresh instead — up to ten seconds during which the
    frontend's optimistic toggle reverts and then corrects itself.

    The single retry exists because these routers commonly answer the first
    read after a write with the *old* value: the command is accepted and
    applied a moment later. One retry distinguishes that from a genuine
    refusal; more would just be waiting.

    Comparison is on `str`, because the API returns `"1"` where a caller
    naturally holds `1` and a mismatch there would read as a refusal.
    """
    raw: Any = None
    for attempt in (1, 2):
        block = await api.read_back(endpoint)
        if block is None:
            return None

        try:
            raw = extract(block)
        except (AttributeError, KeyError, IndexError, TypeError):
            # A shape the extractor did not expect is unverified, not refused.
            # The write may well have succeeded; nothing here can tell.
            _LOGGER.debug(
                "%s: read-back of %s had an unexpected shape",
                label,
                endpoint,
                exc_info=True,
            )
            return None

        if raw is None:
            _LOGGER.debug("%s: read-back of %s omitted the key", label, endpoint)
            return None

        if str(raw).strip() == expected:
            return True

        if attempt == 1:
            # Accepted-then-applied, not refused. Pause and read once more
            # before calling it a refusal.
            await asyncio.sleep(READ_BACK_RETRY_DELAY)

    _LOGGER.warning(
        "%s: the router still reports %r from %s after the write; expected %r",
        label,
        raw,
        endpoint,
        expected,
    )
    return False


# ---------------------------------------------------------------------------
# Client-tracker cleanup
#
# Lives here rather than in `__init__.py` because it now has two callers: the
# `cleanup_unused_entities` action, which sweeps every config entry, and the
# Clients button, which cleans only its own. A platform module importing from
# the package `__init__` would be a circular import.
# ---------------------------------------------------------------------------


def _tracked_macs(coordinator: HuaweiRouter5GDataUpdateCoordinator) -> set[str]:
    """Return every MAC the router currently reports, from both host lists."""
    data = coordinator.data or {}
    macs: set[str] = set()
    for key in ("lan_host_info", "wlan_host_list"):
        block = data.get(key)
        if not isinstance(block, dict):
            continue
        for host in block.get("Hosts", {}).get("Host", []) or []:
            if isinstance(host, dict) and (mac := host.get("MacAddress")):
                macs.add(mac)
    return macs


def _stale_tracker_entities(
    hass: HomeAssistant, entry: ConfigEntry
) -> list[er.RegistryEntry]:
    """Return device_tracker entities for clients the router no longer lists.

    A tracker is created for every client ever seen and nothing removes it, so
    a guest's phone seen once leaves a permanent entity. With two routers
    configured that accumulation stops being cosmetic.

    **Nothing is removed while the coordinator has no data.** An empty payload
    during an outage would otherwise make every client look stale and delete
    the lot — the failure mode this guard exists for.
    """
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None or not coordinator.data:
        return []

    live = _tracked_macs(coordinator)
    if not live:
        return []

    prefix = f"{entry.unique_id}_"
    registry = er.async_get(hass)
    return [
        item
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        if item.domain == Platform.DEVICE_TRACKER
        and item.unique_id.startswith(prefix)
        and item.unique_id[len(prefix) :] not in live
    ]
