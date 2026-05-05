"""Sensor platform for Huawei Router 5G."""

import ipaddress
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfDataRate,
    UnitOfFrequency,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import (
    _parse_complex_float,
    _parse_complex_int,
    _safe_int,
    build_device_info,
    get_network_type_label,
    parse_signal_value,
    parse_sms_list,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


def _get_timestamp(seconds: Any) -> Any:
    """Convert seconds offset to a timestamp, rounded to the nearest minute."""
    sec = _safe_int(seconds)
    if sec is None or sec < 0:
        return None
    # Round to nearest minute (60s)
    rounded_sec = round(sec / 60) * 60
    return dt_util.now() - timedelta(seconds=rounded_sec)


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


def _get_signal_value(data: dict | None, key: str) -> Any:
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

SENSOR_TYPES: Final[tuple[HuaweiSensorEntityDescription, ...]] = (
    # --- System Sub-device ---
    HuaweiSensorEntityDescription(
        key="model_name",
        translation_key="model_name",
        icon="mdi:router-wireless",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("DeviceName") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sw_version",
        translation_key="sw_version",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("SoftwareVersion") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="last_updated",
        translation_key="last_updated",
        icon="mdi:update",
        device_class=SensorDeviceClass.TIMESTAMP,
        group="system",
        value_fn=lambda data: None,  # Handled by property
    ),
    HuaweiSensorEntityDescription(
        key="wan_ip",
        translation_key="wan_ip",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("WanIPAddress") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="wan_ipv6",
        translation_key="wan_ipv6",
        icon="mdi:ip-network-outline",
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
        device_class=SensorDeviceClass.DURATION,
        icon="mdi:clock-outline",
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
        icon="mdi:clock-check-outline",
        group="system",
        value_fn=lambda data: (
            _get_timestamp(data.get("device_information", {}).get("uptime"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="current_connection_duration",
        translation_key="current_connection_duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
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
        icon="mdi:link-variant",
        group="system",
        value_fn=lambda data: (
            _get_timestamp(data.get("traffic_statistics", {}).get("CurrentConnectTime"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="total_connection_time",
        translation_key="total_connection_time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
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
        icon="mdi:calendar-clock",
        group="system",
        value_fn=lambda data: (
            _get_timestamp(data.get("traffic_statistics", {}).get("TotalConnectTime"))
            if data
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="battery",
        translation_key="battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:wifi-check",
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
        icon="mdi:account-group",
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
        icon="mdi:lan-connect",
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
        icon="mdi:wifi-cog",
        group="wifi",
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
        icon="mdi:dns",
        group="system",
        value_fn=lambda data: (
            data.get("monitoring_status", {}).get("PrimaryDns") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="secondary_dns",
        translation_key="secondary_dns",
        icon="mdi:dns",
        group="system",
        value_fn=lambda data: (
            data.get("monitoring_status", {}).get("SecondaryDns") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="primary_ipv6_dns",
        translation_key="primary_ipv6_dns",
        icon="mdi:dns",
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
        icon="mdi:dns",
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
        icon="mdi:signal-variant",
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
        icon="mdi:tune",
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
        icon="mdi:antenna",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda data: (
            data.get("current_plmn", {}).get("FullName") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="plmn",
        translation_key="plmn",
        icon="mdi:barcode",
        group="signal",
        value_fn=lambda data: (
            data.get("current_plmn", {}).get("Numeric") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="operator_search_mode",
        translation_key="operator_search_mode",
        icon="mdi:magnify",
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
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
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
        icon="mdi:signal-variant",
        group="signal",
        min_limit=-50,
        max_limit=0,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "rsrq")),
    ),
    HuaweiSensorEntityDescription(
        key="rssi",
        translation_key="rssi",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
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
        icon="mdi:signal-variant",
        group="signal",
        min_limit=-30,
        max_limit=50,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "sinr")),
    ),
    HuaweiSensorEntityDescription(
        key="signal_bars",
        translation_key="signal_bars",
        icon="mdi:signal-cellular-outline",
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
        icon="mdi:signal-cellular-outline",
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
        icon="mdi:identifier",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "cell_id"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="pci",
        translation_key="pci",
        icon="mdi:identifier",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "pci"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="tac",
        translation_key="tac",
        icon="mdi:identifier",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "tac"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="band",
        translation_key="band",
        icon="mdi:radio-tower",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "band"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="mode",
        translation_key="mode",
        icon="mdi:signal-variant",
        group="signal",
        value_fn=lambda data: {"0": "2G", "2": "3G", "7": "4G"}.get(
            str(_get_signal_value(data, "mode"))
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="transmit_power",
        translation_key="transmit_power",
        icon="mdi:transmission-tower",
        group="signal",
        value_fn=lambda data: _parse_complex_float(_get_signal_value(data, "txpower")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="uplink_mcs",
        translation_key="uplink_mcs",
        icon="mdi:numeric",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "ul_mcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="downlink_mcs",
        translation_key="downlink_mcs",
        icon="mdi:numeric",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "dl_mcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="earfcn",
        translation_key="earfcn",
        icon="mdi:numeric",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "earfcn")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="rrc_status",
        translation_key="rrc_status",
        icon="mdi:state-machine",
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
        icon="mdi:phone-voip",
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
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radio-tower",
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
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radio-tower",
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
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transfer-up",
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
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transfer-down",
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
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radio-tower",
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
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radio-tower",
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
        icon="mdi:transit-connection-variant",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "transmode"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="enodeb_id",
        translation_key="enodeb_id",
        icon="mdi:identifier",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "enodeb_id")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="cqi_0",
        translation_key="cqi_0",
        icon="mdi:numeric",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "cqi0")),
    ),
    # 5G Entities
    HuaweiSensorEntityDescription(
        key="nr5g_band",
        translation_key="nr5g_band",
        icon="mdi:radio-tower",
        group="signal",
        value_fn=lambda data: _parse_nr_band_from_band(_get_signal_value(data, "band")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="nr_rsrp",
        translation_key="nr_rsrp",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal-5g",
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
        icon="mdi:signal-5g",
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
        icon="mdi:signal-5g",
        group="signal",
        min_limit=-30,
        max_limit=50,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "nrsinr")),
    ),
    HuaweiSensorEntityDescription(
        key="5g_uplink_bandwidth",
        translation_key="5g_uplink_bandwidth",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transfer-up",
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
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transfer-down",
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
        icon="mdi:numeric",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "nrulmcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_downlink_mcs",
        translation_key="5g_downlink_mcs",
        icon="mdi:numeric",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "nrdlmcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_transmit_power",
        translation_key="5g_transmit_power",
        icon="mdi:transmission-tower",
        group="signal",
        value_fn=lambda data: _parse_complex_float(
            _get_signal_value(data, "nrtxpower")
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_earfcn",
        translation_key="5g_earfcn",
        icon="mdi:numeric",
        group="signal",
        value_fn=lambda data: _parse_complex_int(_get_signal_value(data, "nrearfcn")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_block_error_rate",
        translation_key="5g_block_error_rate",
        icon="mdi:chart-bell-curve",
        group="signal",
        min_limit=0,
        value_fn=lambda data: parse_signal_value(_get_signal_value(data, "nrbler")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_rank",
        translation_key="5g_rank",
        icon="mdi:numeric",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=1,
        max_limit=4,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "nrrank")),
    ),
    HuaweiSensorEntityDescription(
        key="5g_cqi_0",
        translation_key="5g_cqi_0",
        icon="mdi:numeric",
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
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:arrow-down-bold-outline",
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
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:arrow-up-bold-outline",
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
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:arrow-up-down-bold-outline",
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
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arrow-down-bold-outline",
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
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arrow-up-bold-outline",
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
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arrow-down-bold-outline",
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
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arrow-up-bold-outline",
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
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:arrow-up-bold-outline",
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
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:arrow-down-bold-outline",
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
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:arrow-up-down-bold-outline",
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
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:arrow-down-bold-outline",
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
        state_class=SensorStateClass.TOTAL,
        icon="mdi:arrow-down-bold-outline",
        group="data",
        min_limit=0,
        max_limit=100000,
        value_fn=lambda data: (
            round(
                _safe_int(data.get("month_statistics", {}).get("CurrentMonthDownload"))
                / (1024**3),
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
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:arrow-up-bold-outline",
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
        state_class=SensorStateClass.TOTAL,
        icon="mdi:arrow-up-bold-outline",
        group="data",
        min_limit=0,
        max_limit=100000,
        value_fn=lambda data: (
            round(
                _safe_int(data.get("month_statistics", {}).get("CurrentMonthUpload"))
                / (1024**3),
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
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:arrow-up-down-bold-outline",
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
        icon="mdi:message-alert",
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
        icon="mdi:message-text",
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
        icon="mdi:message-text",
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
        icon="mdi:message-alert",
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
        icon="mdi:message-text",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:message-alert-outline",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:message-draw",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:message-minus",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:message-settings",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:message-alert-outline",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:message-text-outline",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:message-alert-outline",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:email-edit-outline",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:message-settings-outline",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:message-text-outline",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:message-plus",
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:message-text-clock",
        group="sms",
        value_fn=lambda data: None,  # Handled by property
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
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

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry,
        description: HuaweiSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.entity_description.key == "last_updated":
            return self.coordinator.last_update_success_time

        if self.entity_description.key == "last_sms":
            if not self.coordinator.data:
                return None
            messages = parse_sms_list(self.coordinator.data.get("sms_list"))
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
            if not self.coordinator.data:
                return {}
            messages = parse_sms_list(self.coordinator.data.get("sms_list"))
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
    def device_info(self):
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self.entity_description.group)
