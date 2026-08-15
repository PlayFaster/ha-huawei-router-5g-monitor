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
)
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import (
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


def _projection(data: dict[str, Any] | None) -> _Projection | None:
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
    """Return the projected end-of-cycle byte count, or None."""
    result = _projection(data)
    return None if result is None else result.projected_bytes


SENSOR_TYPES: Final[tuple[HuaweiSensorEntityDescription, ...]] = (
    # --- System Sub-device ---
    HuaweiSensorEntityDescription(
        key="model_name",
        translation_key="model_name",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("DeviceName") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sw_version",
        translation_key="sw_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("SoftwareVersion") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="last_updated",
        translation_key="last_updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        group="system",
        value_fn=lambda data: None,  # Handled by property
    ),
    HuaweiSensorEntityDescription(
        key="wan_ip",
        translation_key="wan_ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("WanIPAddress") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="wan_ipv6",
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
        translation_key="uptime_timestamp",
        device_class=SensorDeviceClass.TIMESTAMP,
        group="system",
        value_fn=lambda data: data.get("system_boot_time") if data else None,
    ),
    HuaweiSensorEntityDescription(
        key="current_connection_duration",
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
        translation_key="current_connection_timestamp",
        device_class=SensorDeviceClass.TIMESTAMP,
        group="system",
        value_fn=lambda data: data.get("conn_start_time") if data else None,
    ),
    HuaweiSensorEntityDescription(
        key="total_connection_time",
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
        translation_key="total_connection_timestamp",
        device_class=SensorDeviceClass.TIMESTAMP,
        group="system",
        value_fn=lambda data: data.get("total_conn_start_time") if data else None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="battery",
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
        translation_key="primary_dns",
        group="system",
        value_fn=lambda data: (
            data.get("monitoring_status", {}).get("PrimaryDns") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="secondary_dns",
        translation_key="secondary_dns",
        group="system",
        value_fn=lambda data: (
            data.get("monitoring_status", {}).get("SecondaryDns") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="primary_ipv6_dns",
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
        translation_key="preferred_network_mode",
        group="signal",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            {
                "00": "Auto",
                "01": "2G Only",
                "02": "3G Only",
                "03": "4G Only",
                "0302": "4G/3G Auto",
                "0301": "4G/2G Auto",
                "0201": "3G/2G Auto",
                "030201": "4G/3G/2G Auto",
            }.get(str(data.get("net_mode", {}).get("NetworkMode")))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="operator",
        translation_key="operator",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda data: (
            data.get("current_plmn", {}).get("FullName") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="plmn",
        translation_key="plmn",
        group="signal",
        value_fn=lambda data: (
            data.get("current_plmn", {}).get("Numeric") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="operator_search_mode",
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
        translation_key="cell_id",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "cell_id"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="pci",
        translation_key="pci",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "pci"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="tac",
        translation_key="tac",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "tac"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="band",
        translation_key="band",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "band"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="mode",
        translation_key="mode",
        group="signal",
        value_fn=lambda data: {"0": "2G", "2": "3G", "7": "4G"}.get(
            str(_get_signal_value(data, "mode"))
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="transmit_power",
        translation_key="transmit_power",
        group="signal",
        # Documented in docs/value_min_max.md since the band was first written,
        # but never actually implemented. `_parse_complex_float` returns the raw
        # string for multi-carrier values ("PPusch:12dBm PPucch:5dBm"), and the
        # guard's float() raises and passes those through untouched — so the
        # band applies only to the simple-number case, which is the one an
        # implausible reading appears in.
        min_limit=-30,
        max_limit=40,
        value_fn=lambda data: _parse_complex_float(_get_signal_value(data, "txpower")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="uplink_mcs",
        translation_key="uplink_mcs",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "ul_mcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="downlink_mcs",
        translation_key="downlink_mcs",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "dl_mcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="earfcn",
        translation_key="earfcn",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "earfcn")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="rrc_status",
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
        translation_key="transmission_mode",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "transmode"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="enodeb_id",
        translation_key="enodeb_id",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "enodeb_id")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="cqi_0",
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
        translation_key="nr5g_band",
        group="signal",
        value_fn=lambda data: _parse_nr_band_from_band(_get_signal_value(data, "band")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="nr_rsrp",
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
        translation_key="5g_uplink_mcs",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "nrulmcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_downlink_mcs",
        translation_key="5g_downlink_mcs",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "nrdlmcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_transmit_power",
        translation_key="5g_transmit_power",
        group="signal",
        # See transmit_power — documented, never implemented.
        min_limit=-30,
        max_limit=40,
        value_fn=lambda data: _parse_complex_float(
            _get_signal_value(data, "nrtxpower")
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_earfcn",
        translation_key="5g_earfcn",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "nrearfcn")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_block_error_rate",
        translation_key="5g_block_error_rate",
        group="signal",
        min_limit=0,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "nrbler")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_rank",
        translation_key="5g_rank",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=1,
        max_limit=4,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "nrrank")),
    ),
    HuaweiSensorEntityDescription(
        key="5g_cqi_0",
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
        translation_key="imei",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "Imei"),
    ),
    HuaweiSensorEntityDescription(
        key="imsi",
        translation_key="imsi",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "Imsi"),
    ),
    HuaweiSensorEntityDescription(
        key="iccid",
        translation_key="iccid",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "Iccid"),
    ),
    HuaweiSensorEntityDescription(
        key="sim_number",
        translation_key="sim_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "Msisdn"),
    ),
    HuaweiSensorEntityDescription(
        key="serial_number",
        translation_key="serial_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "SerialNumber"),
    ),
    HuaweiSensorEntityDescription(
        key="mcc_mnc",
        translation_key="mcc_mnc",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _identifier(data, "Mccmnc"),
    ),
    # --- System information --------------------------------------------------
    HuaweiSensorEntityDescription(
        key="product_name",
        translation_key="product_name",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: _info(data, "spreadname_en"),
    ),
    HuaweiSensorEntityDescription(
        key="web_ui_version",
        translation_key="web_ui_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: _info(data, "WebUIVersion"),
    ),
    HuaweiSensorEntityDescription(
        key="carrier_build",
        translation_key="carrier_build",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: _info(data, "iniversion"),
    ),
    HuaweiSensorEntityDescription(
        key="supported_modes",
        translation_key="supported_modes",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _info(data, "supportmode"),
    ),
    HuaweiSensorEntityDescription(
        key="wan_dns",
        translation_key="wan_dns",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _info(data, "wan_dns_address"),
    ),
    HuaweiSensorEntityDescription(
        key="wan_dns_ipv6",
        translation_key="wan_dns_ipv6",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _info(data, "wan_ipv6_dns_address"),
    ),
    HuaweiSensorEntityDescription(
        key="country_code",
        translation_key="country_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: _block(data, "converged_status", "CountryCode"),
    ),
    HuaweiSensorEntityDescription(
        key="mtu",
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
        translation_key="apn",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (_current_apn_profile(data) or {}).get("ApnName"),
    ),
    HuaweiSensorEntityDescription(
        key="apn_profile",
        translation_key="apn_profile",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda data: (_current_apn_profile(data) or {}).get("Name"),
    ),
    # --- Signal ---------------------------------------------------------------
    HuaweiSensorEntityDescription(
        key="primary_band",
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
        translation_key="antenna_1",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda data: _antenna(data, "antenna1type"),
    ),
    HuaweiSensorEntityDescription(
        key="antenna_2",
        translation_key="antenna_2",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda data: _antenna(data, "antenna2type"),
    ),
    # --- Data ----------------------------------------------------------------
    HuaweiSensorEntityDescription(
        key="counters_last_reset",
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
        translation_key="billing_cycle_day",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="data",
        min_limit=1,
        max_limit=31,
        value_fn=lambda data: _safe_int(_block(data, "start_date", "StartDay")),
    ),
    HuaweiSensorEntityDescription(
        key="alert_threshold",
        translation_key="alert_threshold",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        group="data",
        min_limit=0,
        max_limit=100,
        value_fn=lambda data: _safe_int(_block(data, "start_date", "MonthThreshold")),
    ),
    HuaweiSensorEntityDescription(
        key="projected_usage",
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
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], SensorEntity
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
    _unrecorded_attributes = frozenset(
        {
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
        """Return extra state attributes."""
        if self.entity_description.key == "sms_total":
            data = self.coordinator.data
            if not data or not data.get("sms_count"):
                return {}
            counts = data.get("sms_count", {})
            try:
                return {
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
            except (ValueError, TypeError):
                return {}

        if self.entity_description.key == "last_sms":
            messages = self._get_messages()
            if not messages:
                return {}
            latest = messages[0]
            return {
                "phone": latest["phone"],
                "date": latest["date"],
                "index": latest["index"],
                "unread": not latest["read"],
            }

        return {}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self.entity_description.group)
