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
    CONF_HOST,
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

from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import (
    build_device_info,
    get_network_type_label,
    parse_signal_value,
    parse_sms_list,
)

_LOGGER = logging.getLogger(__name__)


def _safe_int(val: Any) -> int | None:
    """Safely convert value to int or return None."""
    f_val = parse_signal_value(val)
    return int(f_val) if f_val is not None else None


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
    """Format frequency in MHz (input is in tenths of MHz)."""
    f_val = parse_signal_value(value)
    return f_val / 10 if f_val is not None else None


def _get_signal_value(data: dict | None, key: str) -> Any:
    """Get signal value from data."""
    if data is None:
        return None
    return data.get("device_signal", {}).get(key)


def _get_network_type(data: dict | None) -> str | None:
    """Map numeric network type to human-readable string."""
    if data is None:
        return None
    type_code = data.get("monitoring_status", {}).get("CurrentNetworkType")
    return get_network_type_label(type_code)


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
        name="Model Name",
        icon="mdi:router-wireless",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("DeviceName") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sw_version",
        name="Software Version",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("SoftwareVersion") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="last_updated",
        name="Last Updated",
        icon="mdi:update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: None,  # Handled by property
    ),
    HuaweiSensorEntityDescription(
        key="wan_ip",
        name="WAN IP Address",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda data: (
            data.get("device_information", {}).get("WanIPAddress") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="wan_ipv6",
        name="WAN IPv6 Address",
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
        name="Uptime Duration",
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
        name="Uptime",
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
        name="Current Connection Duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
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
        name="Current Connection Uptime",
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
        name="Total Connection Duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
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
        name="Total Connection Uptime",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-clock",
        group="system",
        value_fn=lambda data: (
            _get_timestamp(data.get("traffic_statistics", {}).get("TotalConnectTime"))
            if data
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="battery",
        name="Battery",
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
        name="WiFi Users Connected",
        icon="mdi:wifi-check",
        state_class=SensorStateClass.MEASUREMENT,
        group="system",
        min_limit=0,
        max_limit=255,
        value_fn=lambda data: (
            _safe_int(data.get("monitoring_status", {}).get("CurrentWifiUser"))
            if data
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="primary_dns",
        name="Primary DNS Server",
        icon="mdi:dns",
        group="system",
        value_fn=lambda data: (
            data.get("monitoring_status", {}).get("PrimaryDns") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="secondary_dns",
        name="Secondary DNS Server",
        icon="mdi:dns",
        group="system",
        value_fn=lambda data: (
            data.get("monitoring_status", {}).get("SecondaryDns") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # --- Signal Sub-device ---
    HuaweiSensorEntityDescription(
        key="network_type",
        name="Network Type",
        icon="mdi:signal-variant",
        group="signal",
        value_fn=_get_network_type,
    ),
    HuaweiSensorEntityDescription(
        key="operator",
        name="Operator",
        icon="mdi:antenna",
        group="signal",
        value_fn=lambda data: (
            data.get("current_plmn", {}).get("FullName") if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="plmn",
        name="Operator Code",
        icon="mdi:barcode",
        group="signal",
        value_fn=lambda data: (
            data.get("current_plmn", {}).get("Numeric") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="operator_search_mode",
        name="Operator Search Mode",
        icon="mdi:magnify",
        group="signal",
        value_fn=lambda data: (
            data.get("current_plmn", {}).get("State") if data else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="rsrp",
        name="LTE RSRP",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-150,
        max_limit=-30,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "rsrp")),
    ),
    HuaweiSensorEntityDescription(
        key="rsrq",
        name="LTE RSRQ",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-50,
        max_limit=0,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "rsrq")),
    ),
    HuaweiSensorEntityDescription(
        key="rssi",
        name="LTE RSSI",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-120,
        max_limit=-20,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "rssi")),
    ),
    HuaweiSensorEntityDescription(
        key="sinr",
        name="LTE SINR",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-30,
        max_limit=50,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "sinr")),
    ),
    HuaweiSensorEntityDescription(
        key="signal_bars",
        name="Signal Bars",
        icon="mdi:signal-cellular-outline",
        group="signal",
        min_limit=0,
        max_limit=5,
        value_fn=lambda data: (
            _safe_int(data.get("monitoring_status", {}).get("SignalIcon"))
            if data
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="cell_id",
        name="LTE Cell ID",
        icon="mdi:identifier",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "cell_id"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="pci",
        name="LTE PCI",
        icon="mdi:identifier",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "pci"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="tac",
        name="LTE TAC",
        icon="mdi:identifier",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "tac"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="band",
        name="LTE Band",
        icon="mdi:broadcasting",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "band"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="lte_ca",
        name="LTE Carrier Aggregation",
        icon="mdi:plus-network",
        group="signal",
        value_fn=lambda data: (
            "enabled" if str(_get_signal_value(data, "lte_ca")) == "1" else "disabled"
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="mode",
        name="LTE Mode",
        icon="mdi:signal",
        group="signal",
        value_fn=lambda data: {"0": "2G", "2": "3G", "7": "4G"}.get(
            str(_get_signal_value(data, "mode"))
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="transmit_power",
        name="LTE Transmit Power",
        group="signal",
        min_limit=-30,
        max_limit=40,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "txpower")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="uplink_mcs",
        name="LTE Uplink MCS",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "ul_mcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="downlink_mcs",
        name="LTE Downlink MCS",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "dl_mcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="earfcn",
        name="LTE EARFCN",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "earfcn")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="rrc_status",
        name="LTE RRC Status",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "rrc_status"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="ims",
        name="IMS Status",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "ims"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="lte_uplink_frequency",
        name="LTE Uplink Frequency",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        min_limit=0,
        value_fn=lambda data: format_freq_mhz(_get_signal_value(data, "lteulfreq")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="lte_downlink_frequency",
        name="LTE Downlink Frequency",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        min_limit=0,
        value_fn=lambda data: format_freq_mhz(_get_signal_value(data, "ltedlfreq")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="transmission_mode",
        name="LTE Transmission Mode",
        group="signal",
        value_fn=lambda data: _get_signal_value(data, "transmode"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="enodeb_id",
        name="eNodeB ID",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "enodeb_id")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="cqi_0",
        name="LTE CQI 0",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "cqi0")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="uplink_frequency",
        name="LTE Uplink Frequency (Secondary)",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        min_limit=0,
        value_fn=lambda data: format_freq_mhz(_get_signal_value(data, "ulfrequency")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="downlink_frequency",
        name="LTE Downlink Frequency (Secondary)",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        group="signal",
        min_limit=0,
        value_fn=lambda data: format_freq_mhz(_get_signal_value(data, "dlfrequency")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # 5G Entities
    HuaweiSensorEntityDescription(
        key="nr5g_band",
        name="5G NR Band",
        icon="mdi:broadcasting",
        group="signal",
        value_fn=lambda data: v if (v := _get_signal_value(data, "sc_band")) else None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="nr_rsrp",
        name="5G RSRP",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-150,
        max_limit=-30,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "nrrsrp")),
    ),
    HuaweiSensorEntityDescription(
        key="nr_rsrq",
        name="5G RSRQ",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-50,
        max_limit=0,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "nrrsrq")),
    ),
    HuaweiSensorEntityDescription(
        key="nr_sinr",
        name="5G SINR",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        min_limit=-30,
        max_limit=50,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "nrsinr")),
    ),
    HuaweiSensorEntityDescription(
        key="5g_uplink_bandwidth",
        name="5G Uplink Bandwidth",
        native_unit_of_measurement="MHz",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "nrulbandwidth")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_downlink_bandwidth",
        name="5G Downlink Bandwidth",
        native_unit_of_measurement="MHz",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "nrdlbandwidth")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_uplink_mcs",
        name="5G Uplink MCS",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "nrulmcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_downlink_mcs",
        name="5G Downlink MCS",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "nrdlmcs")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_transmit_power",
        name="5G Transmit Power",
        group="signal",
        min_limit=-30,
        max_limit=40,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "nrtxpower")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_earfcn",
        name="5G EARFCN",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "nrearfcn")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_block_error_rate",
        name="5G Block Error Rate",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_float(_get_signal_value(data, "nrbler")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_rank",
        name="5G Rank",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "nrrank")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="5g_cqi_0",
        name="5G CQI 0",
        group="signal",
        min_limit=0,
        value_fn=lambda data: _safe_int(_get_signal_value(data, "nrcqi0")),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # --- Data Sub-device ---
    HuaweiSensorEntityDescription(
        key="total_download",
        name="Total Download",
        native_unit_of_measurement=UnitOfInformation.BYTES,
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
        name="Total Upload",
        native_unit_of_measurement=UnitOfInformation.BYTES,
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
        name="Total Data",
        native_unit_of_measurement=UnitOfInformation.BYTES,
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
        name="Download Rate",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
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
        name="Upload Rate",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
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
        name="Max Download Rate",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        group="data",
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
        name="Max Upload Rate",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        group="data",
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
        name="Connection Upload",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
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
        name="Connection Download",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
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
        name="Day Used",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
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
        name="Month Download",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
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
        name="Month Download (GB)",
        native_unit_of_measurement="GB",
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
        name="Month Upload",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
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
        name="Month Upload (GB)",
        native_unit_of_measurement="GB",
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
        name="Month Total",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
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
        name="SMS Unread",
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
        key="sms_total",
        name="SMS Total (Device)",
        icon="mdi:message-text",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            (_safe_int(data.get("sms_count", {}).get("LocalUnread")) or 0)
            + (_safe_int(data.get("sms_count", {}).get("LocalRead")) or 0)
            + (_safe_int(data.get("sms_count", {}).get("LocalSent")) or 0)
            + (_safe_int(data.get("sms_count", {}).get("LocalDraft")) or 0)
            if data and data.get("sms_count")
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_unread_device",
        name="SMS Unread (Device)",
        icon="mdi:message-alert",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalUnread")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_inbox_device",
        name="SMS Inbox (Device)",
        icon="mdi:message-text",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalInbox")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_outbox_device",
        name="SMS Outbox (Device)",
        icon="mdi:message-send",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalOutbox")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_drafts_device",
        name="SMS Drafts (Device)",
        icon="mdi:message-draw",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalDraft")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_deleted_device",
        name="SMS Deleted (Device)",
        icon="mdi:message-minus",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalDeleted")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_capacity_device",
        name="SMS Capacity (Device)",
        icon="mdi:message-settings",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("LocalMax")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_unread_sim",
        name="SMS Unread (SIM)",
        icon="mdi:message-alert-outline",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimUnread")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_inbox_sim",
        name="SMS Inbox (SIM)",
        icon="mdi:message-text-outline",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimInbox")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_outbox_sim",
        name="SMS Outbox (SIM)",
        icon="mdi:message-send-outline",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimOutbox")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_drafts_sim",
        name="SMS Drafts (SIM)",
        icon="mdi:message-draw-outline",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimDraft")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_capacity_sim",
        name="SMS Capacity (SIM)",
        icon="mdi:message-settings-outline",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimMax")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_messages_sim",
        name="SMS Messages (SIM)",
        icon="mdi:message-text-outline",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("SimUsed")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sms_new",
        name="SMS New",
        icon="mdi:message-plus",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        min_limit=0,
        max_limit=10000,
        value_fn=lambda data: (
            _safe_int(data.get("sms_count", {}).get("NewMsg")) if data else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="last_sms",
        name="Last SMS",
        icon="mdi:message-text-clock",
        group="sms",
        value_fn=lambda data: None,  # Handled by property
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
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
        host = self._entry.options[CONF_HOST]
        group = self.entity_description.group

        group_names = {
            "system": "System",
            "signal": "Signal",
            "data": "Data",
            "sms": "SMS",
        }
        display_group = group_names.get(group, group.capitalize())
        sub_name = f"{self._entry.title} {display_group}"

        mac = self.coordinator.mac
        sub_id_prefix = mac if mac else f"host_{host}"

        info = {
            "identifiers": {(DOMAIN, f"{sub_id_prefix}_{group}")},
            "name": sub_name,
            "manufacturer": "Huawei",
            "model": self.coordinator.model,
            "sw_version": self.coordinator.sw_version,
            "hw_version": self.coordinator.hw_version,
            "configuration_url": f"http://{host}",
        }

        if group != "system":
            info["via_device"] = (DOMAIN, f"{sub_id_prefix}_system")

        return info
