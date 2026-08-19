"""Sensor platform for Huawei Router 5G."""

import ipaddress
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfDataRate,
    UnitOfFrequency,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    PROJECTION_CONFIDENCE_LOW,
    PROJECTION_CONFIDENCE_MEDIUM,
    PROJECTION_CREDIBILITY_DAYS,
    network_mode_label,
)
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import (
    ABOUT_UNRECORDED,
    HuaweiAboutEntity,
    _parse_complex_float,
    _parse_complex_int,
    _safe_int,
    build_device_info,
    cycle_bounds,
    get_network_type_label,
    parse_signal_value,
    parse_sms_list,
    project_cycle_usage,
)

_LOGGER = logging.getLogger(__name__)

# Section 22. `0` (unlimited) — this platform is read-only. Entities are
# coordinator-driven with no per-entity polling, so there is nothing to
# serialize.
PARALLEL_UPDATES = 0


def format_ipv6(value: Any) -> Any:
    """Format an IPv6 address."""
    try:
        return str(ipaddress.IPv6Address(str(value)))
    except ValueError:
        return value


def format_freq_mhz(value: Any) -> float | None:
    """Format frequency in MHz from lteulfreq/ltedlfreq API fields.

    The Huawei API returns these fields in 10ths of MHz (e.g. raw 19700 → 1970.0 MHz).
    WARNING: Using /100 gives a 10x too-low result (197.0 MHz — looks like a valid
    frequency but is wrong). Using /1000 gives 19.7 MHz (obviously wrong). Only /10
    is correct for this router series.
    """
    f_val = parse_signal_value(value)
    return f_val / 10 if f_val is not None else None


def format_khz_to_mhz(value: Any) -> float | None:
    """Convert frequency from kHz to MHz (÷1000) for ulfrequency/dlfrequency fields.

    NOTE: Do NOT use this for LTE channel bandwidth. LTE bandwidth comes from
    ulbandwidth/dlbandwidth fields which are already in MHz and need no scaling.
    The ulfrequency/dlfrequency fields are carrier frequencies in kHz (e.g. 1970000 kHz
    → 1970.0 MHz); applying /1000 here gives the correct MHz value.
    WARNING: If ulfrequency/dlfrequency were mistakenly used for the bandwidth sensors,
    /1000 would give ~1970 MHz instead of the correct ~20 MHz.
    """
    f_val = parse_signal_value(value)
    return f_val / 1000 if f_val is not None else None


def _get_signal_value(data: dict[str, Any] | None, key: str) -> Any:
    """Get signal value from data."""
    if data is None:
        return None
    return data.get("device_signal", {}).get(key)


def _parse_nr_band_from_band(band: str | None) -> str | None:
    """Parse 5G NR band label from composite band string, e.g. returns 'N28'."""
    if not band or not isinstance(band, str):
        return None
    for segment in band.split("+"):
        seg = segment.strip()
        if "(N" in seg:
            start = seg.rfind("(N") + 1
            end = seg.rfind(")")
            if start > 0 and end > start:
                return seg[start:end]
    return None


@dataclass(frozen=True, kw_only=True)
class HuaweiSensorEntityDescription(SensorEntityDescription):
    """Describes Huawei sensor entity."""

    value_fn: Callable[[Any], Any]
    group: str = "system"
    min_limit: float | None = None
    max_limit: float | None = None
    # dev_standards Section 14 — the human-facing `about` note. Mandatory: a
    # sweep in `tests/test_entity_hygiene.py` fails when a description ships
    # without one, which is the only thing that keeps the set from decaying.
    about: str | None = None


# --- Guard Bands & Range Validation ---
# The following ranges are used to filter out invalid or outlier values:
# LTE RSRP: -140 to -44 dBm
# LTE RSRQ: -50 to 0 dB
# LTE RSSI: -120 to -25 dBm
# LTE SINR: -30 to 40 dB
# 5G RSRP: -150 to -30 dBm
# 5G RSRQ: -50 to 0 dB
# 5G SINR: -30 to 40 dB

# --- §T-4 value helpers ------------------------------------------------------


def _info(data: dict[str, Any] | None, key: str) -> Any:
    """Return a `device_information` key, or None."""
    return data.get("device_information", {}).get(key) if data else None


def _block(data: dict[str, Any] | None, block: str, key: str) -> Any:
    """Return a key from any top-level block, or None."""
    return data.get(block, {}).get(key) if data else None


# Identifiers are digits that are not quantities. Returned as `str` with no
# unit, no device class and no display precision — see the LTS note in
# `SENSOR_TYPES` — because any of those makes Home Assistant coerce the value,
# and `01` becomes `1` while a 15-digit IMEI becomes scientific notation.
def _identifier(data: dict[str, Any] | None, key: str) -> str | None:
    """Return an identifier verbatim, or None when absent or blank."""
    raw = _info(data, key)
    return None if raw in (None, "") else str(raw)


# Antenna type codes, decoded by controlled change against a live B535 on
# 2026-08-15: the GUI was moved from External to Internal and both fields
# followed. `Mix` needs no code of its own — it is the two per-antenna fields
# disagreeing, which two separate sensors express directly.
_ANTENNA_TYPES: Final[dict[str, str]] = {"0": "Internal", "1": "External"}


def _antenna(data: dict[str, Any] | None, key: str) -> str | None:
    """Return the antenna in use, or the raw code if it is not known.

    Passing an unmapped code through unchanged is deliberate: a firmware
    revision inventing a third value should show as itself rather than be
    forced into the wrong word.
    """
    raw = _block(data, "antenna_type", key)
    if raw in (None, ""):
        return None
    return _ANTENNA_TYPES.get(str(raw), str(raw))


def _current_apn_profile(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the profile `CurrentProfile` selects, or None.

    Matched on the `Index` field, never on list position: the router returned
    its three profiles ordered 1, 3, 2 on 2026-08-15, so indexing the list
    would name the wrong APN.
    """
    block = data.get("dial_up_profiles") if data else None
    if not block:
        return None
    current = str(block.get("CurrentProfile", "")).strip()
    profiles = block.get("Profiles", {}).get("Profile", [])
    if isinstance(profiles, dict):
        profiles = [profiles]
    for profile in profiles:
        if str(profile.get("Index", "")).strip() == current:
            return cast("dict[str, Any]", profile)
    return None


@dataclass(frozen=True)
class _Projection:
    """A projected end-of-cycle figure and the context needed to judge it."""

    bytes_used: int
    projected_bytes: int
    cycle_start: datetime
    cycle_length_days: int
    elapsed_days: float
    weight: float
    basis: str

    @property
    def confidence(self) -> str:
        """Return how much of this figure rests on observed data."""
        if self.weight < PROJECTION_CONFIDENCE_LOW:
            return "low"
        if self.weight < PROJECTION_CONFIDENCE_MEDIUM:
            return "medium"
        return "high"


def _month_used_bytes(data: dict[str, Any] | None) -> int | None:
    """Sum this cycle's download and upload counters."""
    down = _safe_int(_block(data, "month_statistics", "CurrentMonthDownload"))
    up = _safe_int(_block(data, "month_statistics", "CurrentMonthUpload"))
    if down is None and up is None:
        return None
    return (down or 0) + (up or 0)


def _projection(coordinator: Any) -> _Projection | None:
    """Return this entry's projection, computing it at most once per poll.

    Memoised on the **coordinator**, not on this module. Both consumers — the
    sensor's value and its `confidence` attribute — run on the same state
    write, so an uncached call does the whole calculation twice to produce two
    halves of one answer.

    A module-level slot looked equivalent and was not: it is shared by every
    config entry, so with two routers each poll replaces the other's entry and
    the memo never hits. It degrades to no memo at all, silently, on exactly
    the installs that poll most. It also persisted between tests.

    See `coordinator.projection_cache` for why the key is identity and why
    holding the payload is what makes that safe.
    """
    data = coordinator.data
    cached = coordinator.projection_cache
    if cached is not None and cached[0] is data:
        return cast("_Projection | None", cached[1])
    result = _compute_projection(data)
    coordinator.projection_cache = (data, result)
    return result


def _compute_projection(data: dict[str, Any] | None) -> _Projection | None:
    """Project this cycle's usage to its end, or None if it cannot be.

    Returns None only when the router's monthly package is switched off, because
    then the counters never roll over and there is genuinely no cycle to project
    against. Everything else — including the first minute of a new cycle —
    produces a figure, because a sensor showing `unknown` reads as broken.

    **The disabled check accepts several spellings on purpose.** `zte_router_5g`
    tested `== "off"` exactly, so `"0"` and `"OFF"` read as *enabled* and it
    projected against a cycle the router was not keeping. Huawei reports
    `SetMonthData` as `"0"`/`"1"`, but casing is not guaranteed anywhere in this
    API and an exact match on one spelling is the same trap.
    """
    enabled = str(_block(data, "start_date", "SetMonthData") or "").strip().lower()
    if enabled in ("0", "off", "false", ""):
        return None

    start_day = _safe_int(_block(data, "start_date", "StartDay"))
    if start_day is None or not 1 <= start_day <= 31:
        return None

    used = _month_used_bytes(data)
    if used is None:
        return None

    now = dt_util.now()
    start, _end, length = cycle_bounds(start_day, now)
    elapsed = (now - start).total_seconds() / 86400.0

    # No cycle history is stored yet, so the prior-cycle rate is unavailable and
    # the denominator floor inside `project_cycle_usage` carries the whole job.
    prior_rate: float | None = None

    projected = project_cycle_usage(
        used=used,
        elapsed_days=elapsed,
        cycle_length_days=length,
        prior_rate=prior_rate,
        credibility_days=PROJECTION_CREDIBILITY_DAYS,
    )

    return _Projection(
        bytes_used=used,
        projected_bytes=int(projected),
        cycle_start=start,
        cycle_length_days=length,
        elapsed_days=elapsed,
        weight=elapsed / (elapsed + PROJECTION_CREDIBILITY_DAYS),
        basis="run_rate_only" if prior_rate is None else "blended",
    )


def _projected_bytes(data: dict[str, Any] | None) -> int | None:
    """Return the projected end-of-cycle byte count, or None.

    Uncached, and **not** the path the entity uses — `native_value` reads the
    memoised projection off the coordinator, because a `value_fn` receives
    only the payload and cannot reach it. Kept as the description's `value_fn`
    so the sweeps that require one still see it, and so the calculation stays
    testable from a bare payload.
    """
    result = _compute_projection(data)
    return None if result is None else result.projected_bytes


SENSOR_TYPES: Final[tuple[HuaweiSensorEntityDescription, ...]] = (
    # --- System Sub-device ---
    HuaweiSensorEntityDescription(
        key="model_name",
        about=(
            "The router's model as it reports it. Read once at setup and stored "
            "on the config entry, so it stays correct even when the router is "
            "unreachable."
        ),
        translation_key="model_name",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("DeviceName") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sw_version",
        about=(
            "Firmware version running on the router. Huawei ships the firmware "
            "and the web interface separately, so this and Web UI Version move "
            "independently and disagreeing versions are not a fault."
        ),
        translation_key="sw_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("SoftwareVersion") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="last_updated",
        about=(
            "When this integration last completed a successful poll. It reports "
            "the **integration's** health rather than the router's: a value going "
            "stale means polling has stopped, whatever the individual sensors "
            "still show."
        ),
        translation_key="last_updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        group="system",
        value_fn=lambda data: None,  # Handled by property
    ),
    HuaweiSensorEntityDescription(
        key="wan_ip",
        about=(
            "The IPv4 address the operator has assigned to the router's WAN. "
            "Usually a carrier-grade NAT address rather than a publicly reachable "
            "one."
        ),
        translation_key="wan_ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("WanIPAddress") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="wan_ipv6",
        about=(
            "The IPv6 address assigned to the router's WAN, where the operator "
            "provides IPv6 at all."
        ),
        translation_key="wan_ipv6",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            format_ipv6(data.get("device_information", {}).get("WanIPv6Address"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="uptime",
        about=(
            "How long the router has been powered on, in seconds. Disabled by "
            "default because Uptime, which expresses the same fact as a "
            "timestamp, is the better one to display."
        ),
        translation_key="uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        min_limit=0,
        value_fn=lambda data: (
            _safe_int(data.get("device_information", {}).get("uptime"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="uptime_timestamp",
        about=(
            "The moment the router last started, derived by subtracting its "
            "uptime from the current time. A timestamp rather than a counter, so "
            "it stays still while the router runs instead of ticking - which is "
            "what makes it readable in history."
        ),
        translation_key="uptime_timestamp",
        device_class=SensorDeviceClass.TIMESTAMP,
        group="system",
        value_fn=lambda data: data.get("system_boot_time") if data else None,
    ),
    HuaweiSensorEntityDescription(
        key="current_connection_duration",
        about=(
            "How long the current mobile data session has been up, in seconds. "
            "Disabled by default in favor of Connection Uptime, which says the "
            "same thing as a fixed point in time."
        ),
        translation_key="current_connection_duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        min_limit=0,
        value_fn=lambda data: (
            _safe_int(data.get("traffic_statistics", {}).get("CurrentConnectTime"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="current_connection_timestamp",
        about=(
            "The moment the current mobile data session was established. A reset "
            "here without a router restart means the data connection dropped and "
            "came back - the router itself stayed up."
        ),
        translation_key="current_connection_timestamp",
        device_class=SensorDeviceClass.TIMESTAMP,
        group="system",
        value_fn=lambda data: data.get("conn_start_time") if data else None,
    ),
    HuaweiSensorEntityDescription(
        key="total_connection_time",
        about=(
            "Lifetime total of all connected time, in seconds, as the router "
            "counts it. **Connected time, not elapsed time**: it does not advance "
            "while the link is down. Disabled by default."
        ),
        translation_key="total_connection_time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        min_limit=0,
        value_fn=lambda data: (
            _safe_int(data.get("traffic_statistics", {}).get("TotalConnectTime"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="total_connection_timestamp",
        about=(
            "Total Duration expressed as a point in time. It is not the date the "
            "router was first used - it is now minus the accumulated connected "
            "time, so any offline period shifts it forward."
        ),
        translation_key="total_connection_timestamp",
        device_class=SensorDeviceClass.TIMESTAMP,
        group="system",
        value_fn=lambda data: data.get("total_conn_start_time") if data else None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="battery",
        about=(
            "Battery charge, on the models that have one. This router family is "
            "mains-powered in most variants, so the entity is disabled by default "
            "and stays unavailable where there is no battery."
        ),
        translation_key="battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        entity_registry_enabled_default=False,
        group="system",
        min_limit=0,
        max_limit=100,
        value_fn=lambda data: (
            _safe_int(data.get("monitoring_status", {}).get("BatteryPercent"))
            if data
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="wifi_users",
        about=(
            "Clients currently associated over WiFi, across all radios and SSIDs "
            "including the guest network."
        ),
        translation_key="wifi_users",
        state_class=SensorStateClass.MEASUREMENT,
        group="clients",
        min_limit=0,
        max_limit=255,
        value_fn=lambda data: (
            _safe_int(data.get("monitoring_status", {}).get("CurrentWifiUser"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="total_connected",
        about=(
            "Every client the router currently reports as connected, wired and "
            "wireless together. WiFi Connected and Wired Connected are its two "
            "halves."
        ),
        translation_key="total_connected",
        state_class=SensorStateClass.MEASUREMENT,
        group="clients",
        min_limit=0,
        max_limit=512,
        value_fn=lambda data: (
            len(
                [
                    h
                    for h in (
                        data.get("lan_host_info", {}).get("Hosts", {}).get("Host", [])
                    )
                    if isinstance(h, dict) and str(h.get("Active")) == "1"
                ]
            )
            if data and data.get("lan_host_info")
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="wired_connected",
        about=(
            "Clients currently connected over the wired LAN ports. Together with "
            "WiFi Connected it accounts for Total Connected, so a difference "
            "between the three is a client the router classifies as neither."
        ),
        translation_key="wired_connected",
        state_class=SensorStateClass.MEASUREMENT,
        group="clients",
        min_limit=0,
        max_limit=512,
        value_fn=lambda data: (
            len(
                [
                    h
                    for h in (
                        data.get("lan_host_info", {}).get("Hosts", {}).get("Host", [])
                    )
                    if isinstance(h, dict)
                    and str(h.get("Active")) == "1"
                    and "Wireless" not in str(h.get("InterfaceType", ""))
                ]
            )
            if data and data.get("lan_host_info")
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="wifi_capacity",
        about=(
            "The maximum number of WiFi clients the router will admit. A firmware "
            "limit, not a license - reaching it means new clients are refused."
        ),
        translation_key="wifi_capacity",
        group="wifi",
        entity_registry_enabled_default=False,
        min_limit=0,
        max_limit=512,
        value_fn=lambda data: (
            _safe_int(data.get("monitoring_status", {}).get("TotalWifiUser"))
            if data
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="primary_dns",
        about=(
            "First IPv4 DNS server the operator handed the router. Devices on the "
            "LAN are usually pointed at the router itself, which forwards here, "
            "so this is what resolves names in practice unless something "
            "overrides it."
        ),
        translation_key="primary_dns",
        group="system",
        value_fn=lambda data: (
            data.get("monitoring_status", {}).get("PrimaryDns") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="secondary_dns",
        about=(
            "Second IPv4 DNS server the operator handed the router, used when the "
            "first does not answer. A blank value is common and is not a fault."
        ),
        translation_key="secondary_dns",
        group="system",
        value_fn=lambda data: (
            data.get("monitoring_status", {}).get("SecondaryDns") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="primary_ipv6_dns",
        about=(
            "First IPv6 DNS server the operator handed the router. Blank wherever "
            "the operator provides no IPv6 service, which is the usual case on a "
            "mobile data plan."
        ),
        translation_key="primary_ipv6_dns",
        group="system",
        value_fn=lambda data: (
            format_ipv6(data.get("monitoring_status", {}).get("PrimaryIPv6Dns"))
            if data
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="secondary_ipv6_dns",
        about=(
            "Second IPv6 DNS server the operator handed the router, used when the "
            "first does not answer. Blank wherever there is no IPv6 service."
        ),
        translation_key="secondary_ipv6_dns",
        group="system",
        value_fn=lambda data: (
            format_ipv6(data.get("monitoring_status", {}).get("SecondaryIPv6Dns"))
            if data
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # --- Signal Sub-device ---
    HuaweiSensorEntityDescription(
        key="network_type",
        about=(
            "The radio access technology currently in use, decoded from the "
            "router's numeric code - `19` becomes `LTE`, `51` becomes `5G NR "
            "NSA`. A code with no known name is published as `Unknown (n)` rather "
            "than hidden, so an unfamiliar reading is information and not a bug."
        ),
        translation_key="network_type",
        group="signal",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            get_network_type_label(
                data.get("monitoring_status", {}).get("CurrentNetworkType")
            )
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="preferred_network_mode",
        about=(
            "The network mode the router reports as being in force. The Preferred "
            "Network Mode control writes it; this sensor reads it back, so a "
            "disagreement between the two means the router refused or altered the "
            "request."
        ),
        translation_key="preferred_network_mode",
        group="signal",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            network_mode_label(data.get("net_mode", {}).get("NetworkMode"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="operator",
        about=(
            "Name of the mobile network the router is registered to, as the "
            "network reports it."
        ),
        translation_key="operator",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda data: (
            data.get("current_plmn", {}).get("FullName") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="plmn",
        about=(
            "The numeric operator code (MCC plus MNC) of the registered network - "
            "the machine-readable twin of Operator. Useful when a network changes "
            "its display name but not its identity."
        ),
        translation_key="plmn",
        group="signal",
        value_fn=lambda data: (
            data.get("current_plmn", {}).get("Numeric") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="operator_search_mode",
        about=(
            "Whether the router chooses its network automatically or has been "
            "pinned to one manually."
        ),
        translation_key="operator_search_mode",
        group="signal",
        value_fn=lambda data: (
            {"0": "Auto", "1": "Manual"}.get(
                str(data.get("current_plmn", {}).get("State"))
            )
            if data
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="rsrp",
        about=(
            "LTE Reference Signal Received Power, in dBm: how strong the serving "
            "cell's reference signal is at the router. This is the primary 'how "
            "good is my signal' figure. Better than -80 is excellent, worse than "
            "-100 is weak. Readings outside -150 to -30 dBm are discarded as "
            "implausible rather than published, so a gap here is a rejected "
            "reading, not a dead radio."
        ),
        translation_key="rsrp",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-150,
        max_limit=-30,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "rsrp")),
    ),
    HuaweiSensorEntityDescription(
        key="rsrq",
        about=(
            "LTE Reference Signal Received Quality, in dB: reference signal power "
            "relative to everything else the router hears on the channel. It "
            "falls as the cell gets busier even when RSRP has not moved, so it "
            "answers a different question from RSRP and is read alongside it, not "
            "instead."
        ),
        translation_key="rsrq",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-50,
        max_limit=0,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "rsrq")),
    ),
    HuaweiSensorEntityDescription(
        key="rssi",
        about=(
            "Total received power across the whole LTE channel in dBm, including "
            "noise and other cells. Higher is not automatically better: a strong "
            "RSSI beside a weak RSRP means most of what the router hears is not "
            "its own cell."
        ),
        translation_key="rssi",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-120,
        max_limit=-20,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "rssi")),
    ),
    HuaweiSensorEntityDescription(
        key="sinr",
        about=(
            "LTE Signal to Interference plus Noise Ratio, in dB, and the single "
            "best predictor of achievable throughput. Above 20 dB is excellent; "
            "below 0 dB the wanted signal is quieter than everything competing "
            "with it."
        ),
        translation_key="sinr",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-30,
        max_limit=50,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "sinr")),
    ),
    HuaweiSensorEntityDescription(
        key="signal_bars",
        about=(
            "The LTE signal bars the router's own web interface shows, 0 to 5. It "
            "is the router's summarized verdict rather than a measurement, so it "
            "is stable and readable but too coarse to trend. Use LTE RSRP, RSRQ "
            "and SINR when comparing over time."
        ),
        translation_key="signal_bars",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=0,
        max_limit=5,
        value_fn=lambda data: (
            _safe_int(data.get("monitoring_status", {}).get("SignalIcon"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="signal_bars_nr",
        about=(
            "The 5G signal bars the router's own web interface shows, 0 to 5. As "
            "with Signal Bars this is a summarized verdict, not a measurement."
        ),
        translation_key="signal_bars_nr",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=0,
        max_limit=5,
        value_fn=lambda data: (
            _safe_int(data.get("monitoring_status", {}).get("SignalIconNr"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="cell_id",
        about=(
            "Identifier of the LTE cell the router is attached to. An identifier, "
            "not a measurement: a change means the router moved to a different "
            "cell, and the number itself has no ordering."
        ),
        translation_key="cell_id",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "cell_id"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="pci",
        about=(
            "Physical Cell Identity of the serving LTE cell, 0 to 503. The short "
            "identifier the radio uses to tell neighboring cells apart. It is "
            "not a quality figure and neighboring cells reuse the numbers."
        ),
        translation_key="pci",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "pci"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="tac",
        about=(
            "Tracking Area Code of the current LTE cell - the group of cells the "
            "network pages the router within. It changes only when the router "
            "moves between tracking areas, so it is far more stable than LTE Cell "
            "ID."
        ),
        translation_key="tac",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "tac"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="band",
        about=(
            "The full set of LTE carriers in use, including every aggregated "
            "secondary carrier. Primary Band reports only the anchor carrier, so "
            "the two reading differently is expected whenever carrier aggregation "
            "is active - it is not a contradiction."
        ),
        translation_key="band",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "band"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="mode",
        about=(
            "The radio access technology in use, as the router's own signal block "
            "names it. Network Type answers the same question from a different "
            "field and with a fuller vocabulary."
        ),
        translation_key="mode",
        group="signal",
        value_fn=lambda data: {"0": "2G", "2": "3G", "7": "4G"}.get(
            str(_get_signal_value(data, "mode"))
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="transmit_power",
        about=(
            "The router's own LTE transmit power. High values mean the router is "
            "shouting to be heard, so this reflects distance and obstruction on "
            "the **uplink** and says nothing about downlink quality. This "
            "hardware reports a compound string naming each channel "
            "(`PPusch:10dBm PPucch:11dBm ...`), passed through unparsed rather "
            "than half-parsed."
        ),
        translation_key="transmit_power",
        group="signal",
        # This is a compound text sensor not a power number sensor
        # It deliberatley has No guard band
        value_fn=lambda data: _parse_complex_float(_get_signal_value(data, "txpower")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="uplink_mcs",
        about=(
            "Modulation and Coding Scheme index chosen for the LTE uplink. As "
            "with the downlink figure it is a scheduler decision, not a "
            "measurement."
        ),
        translation_key="uplink_mcs",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "ul_mcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="downlink_mcs",
        about=(
            "Modulation and Coding Scheme index chosen for the LTE downlink. A "
            "scheduler decision rather than a measurement: it rises as the "
            "channel improves, and is the closest single number to 'bits per "
            "symbol currently in use'."
        ),
        translation_key="downlink_mcs",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "dl_mcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="earfcn",
        about=(
            "The E-ARFCN channel number of the LTE carrier: where in the spectrum "
            "the carrier sits. An identifier, so arithmetic on it means nothing."
        ),
        translation_key="earfcn",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "earfcn")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="rrc_status",
        about=(
            "Whether the LTE radio connection is `Connected` (actively exchanging "
            "data) or `Idle` (attached but dormant). Idle is normal when nothing "
            "is being transferred and is not a fault."
        ),
        translation_key="rrc_status",
        group="signal",
        value_fn=lambda data: (
            {"0": "Idle", "1": "Connected"}.get(
                str(_get_signal_value(data, "rrc_status"))
            )
            if data
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="ims",
        about=(
            "Whether the router is registered with the operator's IMS core, which "
            "is what carries VoLTE and SMS over LTE. `Unregistered` is expected "
            "on a data-only plan and is not a fault by itself."
        ),
        translation_key="ims",
        group="signal",
        value_fn=lambda data: (
            {"0": "Unregistered", "1": "Registered"}.get(
                str(_get_signal_value(data, "ims"))
            )
            if data
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="lte_uplink_frequency",
        about=(
            "Center frequency of the LTE uplink carrier, converted to MHz from "
            "the raw value the router reports."
        ),
        translation_key="lte_uplink_frequency",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        min_limit=0,
        max_limit=3800,
        value_fn=lambda data: format_freq_mhz(_get_signal_value(data, "lteulfreq")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="lte_downlink_frequency",
        about=(
            "Center frequency of the LTE downlink carrier, converted to MHz from "
            "the raw value the router reports."
        ),
        translation_key="lte_downlink_frequency",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        min_limit=0,
        max_limit=3800,
        value_fn=lambda data: format_freq_mhz(_get_signal_value(data, "ltedlfreq")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="lte_uplink_bandwidth",
        about=(
            "Width of the LTE uplink carrier in MHz - the capacity available "
            "upward, not the rate in use."
        ),
        translation_key="lte_uplink_bandwidth",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        entity_category=EntityCategory.DIAGNOSTIC,
        min_limit=0,
        max_limit=20,
        # ulbandwidth reports LTE channel bandwidth directly in MHz (e.g. 20.0).
        # WARNING: ulfrequency is the carrier frequency in kHz — using it here with
        # /1000 produces ~1970 MHz instead of the correct ~20 MHz.
        value_fn=lambda data: parse_signal_value(
            _get_signal_value(data, "ulbandwidth")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="lte_downlink_bandwidth",
        about=(
            "Width of the LTE downlink carrier in MHz. A capacity figure, not a "
            "speed: a wide carrier with poor signal can be slower than a narrow "
            "one with good signal."
        ),
        translation_key="lte_downlink_bandwidth",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        entity_category=EntityCategory.DIAGNOSTIC,
        min_limit=0,
        max_limit=20,
        # dlbandwidth reports LTE channel bandwidth directly in MHz (e.g. 20.0).
        # WARNING: dlfrequency is the carrier frequency in kHz — using it here with
        # /1000 produces ~2160 MHz instead of the correct ~20 MHz.
        value_fn=lambda data: parse_signal_value(
            _get_signal_value(data, "dlbandwidth")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="5g_uplink_frequency",
        about=(
            "Center frequency of the 5G uplink carrier in MHz. On a paired band "
            "it sits a fixed distance from the downlink frequency; on a shared "
            "one the two are the same."
        ),
        translation_key="5g_uplink_frequency",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        min_limit=0,
        max_limit=7125,
        # ulfrequency reports carrier uplink frequency in kHz; divide by 1000 for MHz.
        # e.g. raw 1970000 kHz -> 1970.0 MHz.
        value_fn=lambda data: format_khz_to_mhz(_get_signal_value(data, "ulfrequency")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_downlink_frequency",
        about=(
            "Center frequency of the 5G downlink carrier in MHz. Which band it "
            "falls in decides the trade-off in play: low frequencies travel and "
            "penetrate, high ones carry more."
        ),
        translation_key="5g_downlink_frequency",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        min_limit=0,
        max_limit=7125,
        # dlfrequency reports carrier downlink frequency in kHz; divide by 1000 for MHz.
        # e.g. raw 2160000 kHz -> 2160.0 MHz.
        value_fn=lambda data: format_khz_to_mhz(_get_signal_value(data, "dlfrequency")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="transmission_mode",
        about=(
            "The LTE MIMO transmission mode the network has assigned. It is the "
            "network's choice, not a setting on the router."
        ),
        translation_key="transmission_mode",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "transmode"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="enodeb_id",
        about=(
            "Identifier of the LTE base station hosting the current cell, derived "
            "from the cell ID. Several cells usually share one base station, so "
            "this changes less often than LTE Cell ID and is the better one to "
            "watch for 'has the router moved sites'."
        ),
        translation_key="enodeb_id",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "enodeb_id")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="cqi_0",
        about=(
            "LTE Channel Quality Indicator for the first codeword. The modem's "
            "own summary of how much data the channel can carry, so it moves with "
            "interference as well as with signal strength. Higher is better; it "
            "is not a percentage."
        ),
        translation_key="cqi_0",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=0,
        # Aligned with `5g_cqi_0`, which has carried [0, 16] since it shipped.
        # The two are the same quantity on different radios and disagreed only
        # because nobody had compared them.
        max_limit=16,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "cqi0")),
    ),
    # 5G Entities
    HuaweiSensorEntityDescription(
        key="nr5g_band",
        about=(
            "The 5G NR band or bands the router is using. Blank or unavailable "
            "when no 5G leg is attached, which is normal on an LTE-only "
            "connection."
        ),
        translation_key="nr5g_band",
        group="signal",
        value_fn=lambda data: _parse_nr_band_from_band(_get_signal_value(data, "band")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="nr_rsrp",
        about=(
            "The 5G NR equivalent of LTE RSRP, in dBm. On a non-standalone "
            "network the 5G leg carries the data while LTE remains the anchor, so "
            "this and LTE RSRP describe two live radio links, not one."
        ),
        translation_key="nr_rsrp",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-150,
        max_limit=-30,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "nrrsrp")),
    ),
    HuaweiSensorEntityDescription(
        key="nr_rsrq",
        about=(
            "The 5G NR equivalent of LTE RSRQ, in dB: 5G reference signal power "
            "relative to the total power on the 5G carrier."
        ),
        translation_key="nr_rsrq",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-50,
        max_limit=0,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "nrrsrq")),
    ),
    HuaweiSensorEntityDescription(
        key="nr_sinr",
        about=(
            "The 5G NR equivalent of LTE SINR, in dB. On a non-standalone "
            "connection this is usually the figure that decides 5G throughput, "
            "with LTE SINR governing the anchor."
        ),
        translation_key="nr_sinr",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-30,
        max_limit=50,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "nrsinr")),
    ),
    HuaweiSensorEntityDescription(
        key="5g_uplink_bandwidth",
        about=(
            "Width of the 5G uplink carrier in MHz. Capacity upward, not the rate "
            "in use, and typically much narrower than the downlink."
        ),
        translation_key="5g_uplink_bandwidth",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        min_limit=0,
        max_limit=100,
        value_fn=lambda data: parse_signal_value(
            _get_signal_value(data, "nrulbandwidth")
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_downlink_bandwidth",
        about=("Width of the 5G downlink carrier in MHz. Capacity, not speed."),
        translation_key="5g_downlink_bandwidth",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        min_limit=0,
        max_limit=100,
        value_fn=lambda data: parse_signal_value(
            _get_signal_value(data, "nrdlbandwidth")
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_uplink_mcs",
        about=("Modulation and Coding Scheme index chosen for the 5G uplink."),
        translation_key="5g_uplink_mcs",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "nrulmcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_downlink_mcs",
        about=(
            "Modulation and Coding Scheme index chosen for the 5G downlink - the "
            "network's judgment of how densely it can encode, given the channel."
        ),
        translation_key="5g_downlink_mcs",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "nrdlmcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_transmit_power",
        about=(
            "The router's own 5G transmit power, with the same reading as LTE "
            "Transmit Power: it describes the uplink effort, not the downlink, "
            "and is reported as a compound per-channel string."
        ),
        translation_key="5g_transmit_power",
        group="signal",
        # No guard band, for the same reason as `transmit_power` above.
        value_fn=lambda data: _parse_complex_float(
            _get_signal_value(data, "nrtxpower")
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_earfcn",
        about=(
            "The NR-ARFCN channel number of the 5G carrier. An identifier for a "
            "position in the spectrum, not a quantity."
        ),
        translation_key="5g_earfcn",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "nrearfcn")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_block_error_rate",
        about=(
            "The share of 5G transport blocks that failed and had to be resent. "
            "Low single figures are normal. A persistently high value means the "
            "link is being pushed harder than it can carry, which signal strength "
            "alone does not reveal."
        ),
        translation_key="5g_block_error_rate",
        group="signal",
        min_limit=0,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "nrbler")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_rank",
        about=(
            "Number of independent 5G MIMO layers in use, 1 to 4. Two or more "
            "means the antennas are receiving genuinely different paths and the "
            "link can carry proportionally more; rank 1 is common on a very clean "
            "line of sight, where there is nothing to separate."
        ),
        translation_key="5g_rank",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=1,
        max_limit=4,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "nrrank")),
    ),
    HuaweiSensorEntityDescription(
        key="5g_cqi_0",
        about=(
            "The 5G Channel Quality Indicator for the first codeword - the "
            "modem's own summary of how much the 5G channel can carry. Higher is "
            "better and it is not a percentage."
        ),
        translation_key="5g_cqi_0",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=0,
        max_limit=16,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "nrcqi0")),
    ),
    # --- Data Sub-device ---
    HuaweiSensorEntityDescription(
        key="total_download",
        about=(
            "Lifetime bytes downloaded, as counted since the router's traffic "
            "statistics were last cleared - not since manufacture."
        ),
        translation_key="total_download",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        group="data",
        min_limit=0,
        max_limit=109951162777600,
        value_fn=lambda data: (
            _safe_int(data.get("traffic_statistics", {}).get("TotalDownload"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="total_upload",
        about=(
            "Lifetime bytes uploaded since the traffic statistics were last cleared."
        ),
        translation_key="total_upload",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        group="data",
        min_limit=0,
        max_limit=109951162777600,
        value_fn=lambda data: (
            _safe_int(data.get("traffic_statistics", {}).get("TotalUpload"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="total_data",
        about=(
            "Lifetime download plus upload since the traffic statistics were last "
            "cleared. The Clear Traffic Statistics button is what resets it."
        ),
        translation_key="total_data",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        group="data",
        min_limit=0,
        max_limit=109951162777600,
        value_fn=lambda data: (
            (_safe_int(data.get("traffic_statistics", {}).get("TotalDownload")) or 0)
            + (_safe_int(data.get("traffic_statistics", {}).get("TotalUpload")) or 0)
            if data
            and (
                data.get("traffic_statistics", {}).get("TotalDownload")
                or data.get("traffic_statistics", {}).get("TotalUpload")
            )
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="current_download_rate",
        about=(
            "Instantaneous download rate as the router reports it at the moment "
            "of the poll. It is a sample, not an average, so between polls it "
            "sees nothing - short bursts of traffic can pass entirely unrecorded."
        ),
        translation_key="current_download_rate",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.DATA_RATE,
        group="data",
        min_limit=0,
        max_limit=1250000000,
        value_fn=lambda data: (
            _safe_int(data.get("traffic_statistics", {}).get("CurrentDownloadRate"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="current_upload_rate",
        about=(
            "Instantaneous upload rate sampled at the moment of the poll. As with "
            "the download rate, traffic between polls is not seen."
        ),
        translation_key="current_upload_rate",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.DATA_RATE,
        group="data",
        min_limit=0,
        max_limit=1250000000,
        value_fn=lambda data: (
            _safe_int(data.get("traffic_statistics", {}).get("CurrentUploadRate"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="max_download_rate",
        about=(
            "The highest download rate the router has recorded. Not populated by "
            "the H165-383 firmware, which is why the entity is disabled by "
            "default rather than removed."
        ),
        translation_key="max_download_rate",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.DATA_RATE,
        group="data",
        entity_registry_enabled_default=False,
        min_limit=0,
        max_limit=1250000000,
        value_fn=lambda data: (
            _safe_int(data.get("traffic_statistics", {}).get("MaxDownloadRate"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="max_upload_rate",
        about=(
            "The highest upload rate the router has recorded. Like Max Download "
            "Rate it is unpopulated on current firmware and disabled by default."
        ),
        translation_key="max_upload_rate",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.DATA_RATE,
        group="data",
        entity_registry_enabled_default=False,
        min_limit=0,
        max_limit=1250000000,
        value_fn=lambda data: (
            _safe_int(data.get("traffic_statistics", {}).get("MaxUploadRate"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="current_connection_upload",
        about=(
            "Bytes uploaded during the current data session, resetting with each "
            "reconnection."
        ),
        translation_key="current_connection_upload",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.DATA_SIZE,
        group="data",
        min_limit=0,
        max_limit=109951162777600,
        value_fn=lambda data: (
            _safe_int(data.get("traffic_statistics", {}).get("CurrentUpload"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="current_connection_download",
        about=(
            "Bytes downloaded during the current data session. It resets whenever "
            "the connection drops and reconnects, which is more often than the "
            "monthly counters reset."
        ),
        translation_key="current_connection_download",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.DATA_SIZE,
        group="data",
        min_limit=0,
        max_limit=109951162777600,
        value_fn=lambda data: (
            _safe_int(data.get("traffic_statistics", {}).get("CurrentDownload"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="current_day_used",
        about=(
            "Total bytes used today, as the router counts a day. Recorded as a "
            "`total_increasing` counter so its daily reset is understood as a "
            "rollover rather than as a large negative step."
        ),
        translation_key="current_day_used",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.DATA_SIZE,
        # A daily counter is a resetting counter by definition. Under plain
        # TOTAL, HA recognizes a reset only from a `last_reset` attribute this
        # integration does not publish, so every rollover was recorded as a
        # large negative delta and walked the long-term statistics sum
        # backwards. See docs/changelog_local.md [1.1.3-dev10].
        state_class=SensorStateClass.TOTAL_INCREASING,
        group="data",
        min_limit=0,
        max_limit=109951162777600,
        value_fn=lambda data: (
            _safe_int(data.get("month_statistics", {}).get("CurrentDayUsed"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="month_download",
        about=(
            "Bytes downloaded in the current billing cycle, counted by the router "
            "against the cycle start day it has been configured with - not "
            "against the calendar month."
        ),
        translation_key="month_download",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.DATA_SIZE,
        # Monthly counter — resets on the billing rollover. See current_day_used.
        state_class=SensorStateClass.TOTAL_INCREASING,
        group="data",
        min_limit=0,
        max_limit=109951162777600,
        value_fn=lambda data: (
            _safe_int(data.get("month_statistics", {}).get("CurrentMonthDownload"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="month_download_gb",
        about=(
            "Month Download expressed in GB for convenience. The same underlying "
            "counter as Month Download, rounded - not a second measurement, so "
            "the two can never disagree by more than the rounding."
        ),
        translation_key="month_download_gb",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        group="data",
        entity_registry_enabled_default=False,
        min_limit=0,
        max_limit=100000,
        value_fn=lambda data: (
            round(
                (
                    _safe_int(
                        data.get("month_statistics", {}).get("CurrentMonthDownload")
                    )
                    or 0
                )
                / 1_000_000_000,
                2,
            )
            if data and data.get("month_statistics", {}).get("CurrentMonthDownload")
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="month_upload",
        about=(
            "Bytes uploaded in the current billing cycle, counted by the router "
            "against its configured cycle start day rather than the calendar "
            "month."
        ),
        translation_key="month_upload",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.DATA_SIZE,
        # Monthly counter — resets on the billing rollover. See current_day_used.
        state_class=SensorStateClass.TOTAL_INCREASING,
        group="data",
        min_limit=0,
        max_limit=109951162777600,
        value_fn=lambda data: (
            _safe_int(data.get("month_statistics", {}).get("CurrentMonthUpload"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="month_upload_gb",
        about=(
            "Month Upload expressed in GB. The same counter as Month Upload, rounded."
        ),
        translation_key="month_upload_gb",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        group="data",
        entity_registry_enabled_default=False,
        min_limit=0,
        max_limit=100000,
        value_fn=lambda data: (
            round(
                (
                    _safe_int(
                        data.get("month_statistics", {}).get("CurrentMonthUpload")
                    )
                    or 0
                )
                / 1_000_000_000,
                2,
            )
            if data and data.get("month_statistics", {}).get("CurrentMonthUpload")
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="month_total",
        about=(
            "Download plus upload for the current billing cycle. This is the "
            "figure a data allowance is usually measured against, and it is the "
            "input to Projected Usage."
        ),
        translation_key="month_total",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.DATA_SIZE,
        # Monthly counter — resets on the billing rollover. See current_day_used.
        state_class=SensorStateClass.TOTAL_INCREASING,
        group="data",
        min_limit=0,
        max_limit=109951162777600,
        value_fn=lambda data: (
            (
                _safe_int(data.get("month_statistics", {}).get("CurrentMonthDownload"))
                or 0
            )
            + (
                _safe_int(data.get("month_statistics", {}).get("CurrentMonthUpload"))
                or 0
            )
            if data
            and (
                data.get("month_statistics", {}).get("CurrentMonthDownload")
                or data.get("month_statistics", {}).get("CurrentMonthUpload")
            )
            else None
        ),
    ),
    # --- SMS Sub-device ---
    HuaweiSensorEntityDescription(
        key="sms_unread",
        about=(
            "Unread messages across both the device and the SIM. The two "
            "per-location entities add up to this one."
        ),
        translation_key="sms_unread",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            (_safe_int(data.get("sms_count", {}).get("LocalUnread")) or 0)
            + (_safe_int(data.get("sms_count", {}).get("SimUnread")) or 0)
            if data and data.get("sms_count")
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_total_msg",
        about=(
            "Every message in every storage location - inbox, outbox and drafts, "
            "on both the device and the SIM. The widest of the SMS counts."
        ),
        translation_key="sms_total_msg",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            (_safe_int(data.get("sms_count", {}).get("LocalInbox")) or 0)
            + (_safe_int(data.get("sms_count", {}).get("LocalOutbox")) or 0)
            + (_safe_int(data.get("sms_count", {}).get("LocalDraft")) or 0)
            + (_safe_int(data.get("sms_count", {}).get("SimUsed")) or 0)
            if data and data.get("sms_count")
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_total",
        about=(
            "Messages stored in the router's own memory. Its attributes break the "
            "same storage down by read, unread, sent, outbox and draft, which is "
            "what makes a filling mailbox diagnosable before it is full."
        ),
        translation_key="sms_total",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            (_safe_int(data.get("sms_count", {}).get("LocalInbox")) or 0)
            + (_safe_int(data.get("sms_count", {}).get("LocalOutbox")) or 0)
            + (_safe_int(data.get("sms_count", {}).get("LocalDraft")) or 0)
            if data and data.get("sms_count")
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_unread_device",
        about=(
            "Unread messages stored in the router's own memory. Part of the "
            "Unread Msg total, which adds this to the SIM-side count."
        ),
        translation_key="sms_unread_device",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalUnread")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_inbox_device",
        about=(
            "Received messages held in the router's own memory, read and unread "
            "together. Unread (Device) is the subset still waiting to be looked "
            "at."
        ),
        translation_key="sms_inbox_device",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalInbox")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_outbox_device",
        about=(
            "Sent messages retained in the router's memory. These occupy the same "
            "storage as received ones, so a full outbox blocks incoming messages "
            "just as effectively."
        ),
        translation_key="sms_outbox_device",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalOutbox")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_drafts_device",
        about=(
            "Unsent drafts held in the router's memory. They occupy the same "
            "storage as received messages, so drafts left behind reduce the room "
            "available for incoming ones."
        ),
        translation_key="sms_drafts_device",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalDraft")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_deleted_device",
        about=(
            "Messages marked deleted but not yet purged from the router's memory. "
            "They can still occupy storage until the router reclaims it."
        ),
        translation_key="sms_deleted_device",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalDeleted")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_capacity_device",
        about=(
            "How many messages the router's own memory can hold. Compare with "
            "Total (Device): reaching it is what makes SMS Storage Full turn on, "
            "and a full store silently drops incoming messages."
        ),
        translation_key="sms_capacity_device",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalMax")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_unread_sim",
        about=(
            "Unread messages stored on the SIM card. Part of the Unread Msg "
            "total, which adds this to the device-side count."
        ),
        translation_key="sms_unread_sim",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimUnread")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_inbox_sim",
        about=(
            "Received messages held on the SIM card, read and unread together. "
            "Where a message lands depends on the router's storage preference, "
            "not on the sender."
        ),
        translation_key="sms_inbox_sim",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimInbox")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_outbox_sim",
        about=(
            "Sent messages retained on the SIM card. Retained copies occupy the "
            "same limited storage as received messages, so an unpruned outbox can "
            "block delivery."
        ),
        translation_key="sms_outbox_sim",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimOutbox")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_drafts_sim",
        about=(
            "Unsent drafts held on the SIM card. As with the device store, drafts "
            "consume the same space that incoming messages need."
        ),
        translation_key="sms_drafts_sim",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimDraft")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_capacity_sim",
        about=(
            "How many messages the SIM card can hold. SIM storage is typically an "
            "order of magnitude smaller than the router's own, so it fills first "
            "and is usually what triggers SMS Storage Full."
        ),
        translation_key="sms_capacity_sim",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimMax")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_messages_sim",
        about=(
            "Messages stored on the SIM card across every folder - inbox, outbox "
            "and drafts. The SIM-side counterpart to Total (Device)."
        ),
        translation_key="sms_messages_sim",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimUsed")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sms_new",
        about=(
            "Messages the router reports as newly arrived and not yet filed. A "
            "transient count that normally settles to zero within a poll or two - "
            "it is not the same as Unread Msg, which persists until the message "
            "is read."
        ),
        translation_key="sms_new",
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("NewMsg")) if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="last_sms",
        about=(
            "The text of the most recent message. Its sender, timestamp and index "
            "are attributes, all excluded from the recorder: republishing a phone "
            "number on every poll is both a storage cost and a privacy one."
        ),
        translation_key="last_sms",
        group="sms",
        value_fn=lambda data: None,  # Handled by property
    ),
    # === §T-4: added 2026-08-15 ==============================================
    #
    # LONG-TERM STATISTICS. Every description below deliberately carries **no
    # `state_class`**, which is what keeps it out of LTS — `device_class` does
    # not control that, and omitting it alone would not be enough. The
    # identifiers additionally carry no `device_class`, no unit and no
    # `suggested_display_precision`, because any one of those makes Home
    # Assistant treat the state as a number: `01` becomes `1`, and a 15-digit
    # IMEI becomes scientific notation. `tests/test_entity_hygiene.py` sweeps
    # this rather than trusting the comment.
    #
    # --- Identity (System, diagnostic, disabled by default) ------------------
    HuaweiSensorEntityDescription(
        key="imei",
        about=(
            "The modem's IMEI - the identifier of the radio hardware, not of the "
            "SIM. Deliberately declared as text: given a unit or a device class, "
            "fifteen digits become scientific notation."
        ),
        translation_key="imei",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "Imei"),
    ),
    HuaweiSensorEntityDescription(
        key="imsi",
        about=(
            "The subscriber identity stored on the SIM. It identifies the "
            "**subscription**, unlike IMEI which identifies the hardware. "
            "Disabled by default and redacted from diagnostics downloads."
        ),
        translation_key="imsi",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "Imsi"),
    ),
    HuaweiSensorEntityDescription(
        key="iccid",
        about=(
            "The SIM card's own serial number, which stays with the card when it "
            "moves between routers. Disabled by default and redacted from "
            "diagnostics."
        ),
        translation_key="iccid",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "Iccid"),
    ),
    HuaweiSensorEntityDescription(
        key="sim_number",
        about=(
            "The phone number the SIM reports, where the operator has written one "
            "to the card. Many data SIMs leave this blank, which is not a fault."
        ),
        translation_key="sim_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "Msisdn"),
    ),
    HuaweiSensorEntityDescription(
        key="serial_number",
        about=(
            "The router's hardware serial number. An identifier: it carries no "
            "unit, no device class and no display precision, deliberately, "
            "because any one of those makes Home Assistant treat the digits as a "
            "quantity and reformat them."
        ),
        translation_key="serial_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "SerialNumber"),
    ),
    HuaweiSensorEntityDescription(
        key="mcc_mnc",
        about=(
            "The mobile country and network codes of the SIM's home operator. "
            "This is the SIM's home network, which is not necessarily the network "
            "the router is registered to right now - compare with Operator Code "
            "to see roaming."
        ),
        translation_key="mcc_mnc",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "Mccmnc"),
    ),
    # --- System information --------------------------------------------------
    HuaweiSensorEntityDescription(
        key="product_name",
        about=(
            "The marketing product name the firmware carries, which is often "
            "longer and friendlier than Model Name and occasionally disagrees "
            "with it."
        ),
        translation_key="product_name",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: _info(data, "spreadname_en"),
    ),
    HuaweiSensorEntityDescription(
        key="web_ui_version",
        about=(
            "Version of the router's own web interface, which Huawei ships and "
            "updates separately from the firmware - the two versions moving "
            "independently is normal."
        ),
        translation_key="web_ui_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: _info(data, "WebUIVersion"),
    ),
    HuaweiSensorEntityDescription(
        key="carrier_build",
        about=(
            "The operator-specific build identifier baked into the firmware. It "
            "identifies which carrier customization is loaded, which is what "
            "decides whether a given feature or endpoint exists at all."
        ),
        translation_key="carrier_build",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: _info(data, "iniversion"),
    ),
    HuaweiSensorEntityDescription(
        key="supported_modes",
        about=(
            "The radio modes this hardware and firmware combination can offer. It "
            "is the ceiling on what Preferred Network Mode can be set to, not a "
            "statement of what is in use."
        ),
        translation_key="supported_modes",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _info(data, "supportmode"),
    ),
    HuaweiSensorEntityDescription(
        key="wan_dns",
        about=(
            "The full IPv4 DNS server list as the WAN block reports it. Primary "
            "and Secondary DNS Server split the same information into two "
            "readable entities; this one is the unsplit source."
        ),
        translation_key="wan_dns",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _info(data, "wan_dns_address"),
    ),
    HuaweiSensorEntityDescription(
        key="wan_dns_ipv6",
        about=(
            "The full IPv6 DNS server list as the WAN block reports it - the "
            "unsplit source behind the two IPv6 DNS entities."
        ),
        translation_key="wan_dns_ipv6",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _info(data, "wan_ipv6_dns_address"),
    ),
    HuaweiSensorEntityDescription(
        key="country_code",
        about=(
            "The country the router believes it is operating in, which governs "
            "which radio and WiFi channels it will use."
        ),
        translation_key="country_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _block(data, "converged_status", "CountryCode"),
    ),
    HuaweiSensorEntityDescription(
        key="mtu",
        about=(
            "Maximum transmission unit of the mobile data connection. Relevant "
            "when tunneling or when large packets stall; the operator usually "
            "sets it."
        ),
        translation_key="mtu",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        min_limit=68,
        max_limit=9000,
        value_fn=lambda data: _safe_int(_block(data, "dial_up_connection", "MTU")),
    ),
    HuaweiSensorEntityDescription(
        key="apn",
        about=(
            "The access point name the active data profile is dialing. Different "
            "APNs on the same SIM can mean different addressing and different "
            "traffic treatment."
        ),
        translation_key="apn",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (_current_apn_profile(data) or {}).get("ApnName"),
    ),
    HuaweiSensorEntityDescription(
        key="apn_profile",
        about=(
            "The name of the dial-up profile the APN comes from. The router "
            "returns its profiles out of order, so the active one is resolved by "
            "matching its index rather than by list position."
        ),
        translation_key="apn_profile",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: (_current_apn_profile(data) or {}).get("Name"),
    ),
    # --- Signal ---------------------------------------------------------------
    HuaweiSensorEntityDescription(
        key="primary_band",
        about=(
            "The primary LTE carrier on its own. LTE Band carries the full "
            "aggregation, so `B1` here beside `B1+B3+B7` there is the same radio "
            "state described at two levels of detail."
        ),
        translation_key="primary_band",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="signal",
        # Deliberately narrower than the `band` sensor, which carries the whole
        # carrier aggregation. Disabled by default so the two do not sit side by
        # side reading as a contradiction.
        value_fn=lambda data: _get_signal_value(data, "bandInfo"),
    ),
    HuaweiSensorEntityDescription(
        key="secondary_cell_pci",
        about=(
            "Physical Cell Identity of the aggregated secondary cell. **An "
            "identifier, not a measurement**, despite reading as a small integer: "
            "a rise or fall means a different cell, not a better or worse one. It "
            "deliberately carries no unit and no state class so Home Assistant "
            "keeps it out of long-term statistics."
        ),
        translation_key="secondary_cell_pci",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="signal",
        # An identifier, not a measurement, despite reading as a small integer
        # — which is exactly why it needs the same treatment as the IMEI.
        value_fn=lambda data: (
            None
            if _get_signal_value(data, "scc_pci") in (None, "")
            else str(_get_signal_value(data, "scc_pci"))
        ),
    ),
    HuaweiSensorEntityDescription(
        key="antenna_1",
        about=(
            "Whether antenna port 1 is using the `Internal` or an `External` "
            "antenna. Reported per port, so this and Antenna 2 disagreeing is how "
            "a mixed setup shows itself - there is deliberately no third 'Mix' "
            "value. An unrecognized code is passed through raw rather than "
            "guessed at."
        ),
        translation_key="antenna_1",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda data: _antenna(data, "antenna1type"),
    ),
    HuaweiSensorEntityDescription(
        key="antenna_2",
        about=(
            "Whether antenna port 2 is using the `Internal` or an `External` "
            "antenna. See Antenna 1: the pair is what expresses a mixed setup."
        ),
        translation_key="antenna_2",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda data: _antenna(data, "antenna2type"),
    ),
    # --- Data ----------------------------------------------------------------
    HuaweiSensorEntityDescription(
        key="counters_last_reset",
        about=(
            "When the traffic counters were last cleared **manually**. This is "
            "not the billing boundary - Billing Cycle Day is - and a date here "
            "months old alongside a monthly counter days old is the normal state, "
            "not a contradiction."
        ),
        translation_key="counters_last_reset",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="data",
        # The date the counters were last cleared BY HAND. It is not the billing
        # boundary — `billing_cycle_day` is — and the name says so, because the
        # two were confused during the field review.
        value_fn=lambda data: _block(data, "month_statistics", "MonthLastClearTime"),
    ),
    HuaweiSensorEntityDescription(
        key="month_connected_time",
        about=(
            "**Connected** time this billing cycle, not elapsed time. It stops "
            "advancing while the link is down, so it is not the denominator "
            "behind Projected Usage - that uses wall-clock time from the cycle "
            "start. The two agree only on a connection that never drops."
        ),
        translation_key="month_connected_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="data",
        min_limit=0,
        max_limit=3_000_000,
        # CONNECTED time this cycle, not elapsed wall time. The projection uses
        # wall clock from the cycle start instead — see `project_cycle_usage`.
        value_fn=lambda data: _safe_int(
            _block(data, "month_statistics", "MonthDuration")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="day_connected_time",
        about=(
            "Connected time so far today. Like Month Connected Time it counts "
            "link-up seconds, not elapsed seconds."
        ),
        translation_key="day_connected_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="data",
        min_limit=0,
        max_limit=86_400,
        value_fn=lambda data: _safe_int(
            _block(data, "month_statistics", "CurrentDayDuration")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="data_allowance",
        about=(
            "The monthly data allowance configured **on the router**, in bytes. "
            "It is whatever was typed into the router's own data-plan page, not "
            "anything the operator confirms, so it is only as accurate as that "
            "entry."
        ),
        translation_key="data_allowance",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        group="data",
        min_limit=0,
        # `trafficmaxlimit`, not `DataLimit`: the same figure already in bytes,
        # so there is no `'2000GB'` string to parse and no GB/GiB ambiguity.
        value_fn=lambda data: _safe_int(_block(data, "start_date", "trafficmaxlimit")),
    ),
    HuaweiSensorEntityDescription(
        key="billing_cycle_day",
        about=(
            "Day of the month the router rolls its monthly counters over. This is "
            "the **billing boundary**; Counters Last Reset is the separate, "
            "manual clear and the two are routinely months apart."
        ),
        translation_key="billing_cycle_day",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="data",
        min_limit=1,
        max_limit=31,
        value_fn=lambda data: _safe_int(_block(data, "start_date", "StartDay")),
    ),
    HuaweiSensorEntityDescription(
        key="alert_threshold",
        about=(
            "The percentage of the allowance at which the router raises its own "
            "usage warning. A router-side setting; it does not affect this "
            "integration's entities."
        ),
        translation_key="alert_threshold",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        group="data",
        min_limit=0,
        max_limit=100,
        value_fn=lambda data: _safe_int(_block(data, "start_date", "MonthThreshold")),
    ),
    HuaweiSensorEntityDescription(
        key="line_state",
        about=(
            "The voice subsystem's own status string, read from the router's "
            "`voicebusy` block. `Idle` means no call is in progress. This is the "
            "one block in the payload that returns a bare string rather than a "
            "record."
        ),
        translation_key="line_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        # `voice.voicebusy()` returns a BARE STRING ("Idle"), not a dict - the
        # only block in this payload that does. An earlier pass concluded this
        # API offered no call state at all; that came from a bulk sweep which
        # had corrupted its own session, and it was wrong.
        value_fn=lambda data: (data or {}).get("voice_busy") or None,
    ),
    HuaweiSensorEntityDescription(
        key="projected_usage",
        about=(
            "An estimate of where this cycle's usage will finish, not a "
            "measurement. Early in a cycle it rests mostly on the previous "
            "cycle's rate and later mostly on this one's - the `confidence` "
            "attribute is how to judge which. It deliberately carries **no state "
            "class**, so nothing about a forecast enters long-term statistics; "
            "the usage behind it is already there via Month Total."
        ),
        translation_key="projected_usage",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=1,
        group="data",
        min_limit=0,
        # NO `state_class`, deliberately. The projection is an estimate, and the
        # usage it derives from is already in long-term statistics via the month
        # total — recording the forecast as well stores a second series that is
        # a re-derivation of the first and changes retroactively as the cycle
        # fills. `test_projection_has_no_state_class` holds this.
        value_fn=_projected_bytes,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            HuaweiRouterSensor(coordinator, entry, description)
            for description in SENSOR_TYPES
        ]
    )


class HuaweiRouterSensor(
    HuaweiAboutEntity,
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator],
    SensorEntity,
):
    """Representation of a Huawei Router sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description: HuaweiSensorEntityDescription

    # dev_standards Section 14. Without this, every attribute below is written
    # to the recorder on every state change — and `last_sms` republishes the
    # sender's phone number and the message metadata each poll, which is both
    # a database-growth problem and a privacy one. None of these is useful as
    # history: they are a snapshot that only makes sense alongside the current
    # state.
    #
    # `_unrecorded_attributes` is looked up by normal MRO and is NOT unioned
    # across bases by Home Assistant, so a subclass that redeclares it shadows
    # the mixin's `{"about"}` entirely. Every declaration in this component
    # therefore starts from `ABOUT_UNRECORDED`; a test
    # holds that.
    _unrecorded_attributes = ABOUT_UNRECORDED | frozenset(
        {
            # projected_usage
            "confidence",
            "cycle_start",
            "cycle_length_days",
            "elapsed_days",
            "basis",
            # sms_total
            "local_unread",
            "local_read",
            "local_sent",
            "local_outbox",
            "local_draft",
            "local_max",
            "sim_unread",
            "sim_read",
            "sim_max",
            # last_sms
            "phone",
            "date",
            "index",
            "unread",
        }
    )

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry: ConfigEntry,
        description: HuaweiSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

    def _get_messages(self) -> list[dict[str, Any]]:
        """Return parsed SMS messages from coordinator data."""
        if not self.coordinator.data:
            return []
        return parse_sms_list(self.coordinator.data.get("sms_list"))

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.entity_description.key == "last_updated":
            return self.coordinator.last_update_success_time

        if self.entity_description.key == "last_sms":
            messages = self._get_messages()
            return messages[0]["content"] if messages else None

        if self.entity_description.key == "projected_usage":
            # Read the memoised projection rather than calling the `value_fn`,
            # which takes only the payload and so cannot reach the cache. This
            # is the half that makes the memo pay: without it the value and
            # the `confidence` attribute each compute the projection in full,
            # on every state write.
            result = _projection(self.coordinator)
            return None if result is None else result.projected_bytes

        val = self.entity_description.value_fn(self.coordinator.data)

        # Apply guard bands
        min_limit = self.entity_description.min_limit
        max_limit = self.entity_description.max_limit

        if val is not None and (min_limit is not None or max_limit is not None):
            try:
                num_val = float(val)
                if min_limit is not None and num_val < min_limit:
                    return None
                if max_limit is not None and num_val > max_limit:
                    return None
            except (ValueError, TypeError):
                pass

        return val

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes.

        **Every return path goes through `_with_about`.** A bare `return {}`
        here would drop the note for that entity only, which no type checker
        and no per-entity test would notice.
        """
        if self.entity_description.key == "projected_usage":
            # Documented in `docs/all_sensors.md` and the README since the
            # sensor shipped, and computed by `_Projection` since then — but
            # never actually published. `confidence` is the whole basis on
            # which a user is meant to judge an estimate, so a figure without
            # it is a number with no way to weigh it.
            result = _projection(self.coordinator)
            if result is None:
                return self._with_about(None) or {}
            return (
                self._with_about(
                    {
                        "confidence": result.confidence,
                        "cycle_start": result.cycle_start.isoformat(),
                        "cycle_length_days": result.cycle_length_days,
                        "elapsed_days": round(result.elapsed_days, 2),
                        "basis": result.basis,
                    }
                )
                or {}
            )

        if self.entity_description.key == "sms_total":
            data = self.coordinator.data
            if not data or not data.get("sms_count"):
                return self._with_about(None) or {}
            counts = data.get("sms_count", {})
            try:
                return (
                    self._with_about(
                        {
                            "local_unread": int(counts.get("LocalUnread", 0)),
                            "local_read": int(counts.get("LocalRead", 0)),
                            "local_sent": int(counts.get("LocalSent", 0)),
                            "local_outbox": int(counts.get("LocalOutbox", 0)),
                            "local_draft": int(counts.get("LocalDraft", 0)),
                            "local_max": int(counts.get("LocalMax", 0)),
                            "sim_unread": int(counts.get("SimUnread", 0)),
                            "sim_read": int(counts.get("SimRead", 0)),
                            "sim_max": int(counts.get("SimMax", 0)),
                        }
                    )
                    or {}
                )
            except (ValueError, TypeError):
                return self._with_about(None) or {}

        if self.entity_description.key == "last_sms":
            messages = self._get_messages()
            if not messages:
                return self._with_about(None) or {}
            latest = messages[0]
            return (
                self._with_about(
                    {
                        "phone": latest["phone"],
                        "date": latest["date"],
                        "index": latest["index"],
                        "unread": not latest["read"],
                    }
                )
                or {}
            )

        return self._with_about(None) or {}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self.entity_description.group)
