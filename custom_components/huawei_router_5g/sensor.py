"""Sensor platform for Huawei Router 5G Monitor."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_HOST,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import get_network_type_label, parse_signal_value

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HuaweiSensorEntityDescription(SensorEntityDescription):
    """Describes a Huawei Router 5G sensor entity."""

    value_fn: Callable[[Any], Any]
    group: str = "system"
    min_limit: float | None = None
    max_limit: float | None = None


def _safe_int(val: Any) -> int | None:
    """Safely convert a value to int."""
    if val in (None, "", "N/A"):
        return None
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return None


def _safe_float(val: Any) -> float | None:
    """Safely convert a value to float."""
    if val in (None, "", "N/A"):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _bytes_to_gb(val: Any) -> float | None:
    """Convert a byte count to GB."""
    if val in (None, "", "N/A"):
        return None
    try:
        return round(float(val) / 1_073_741_824, 2)
    except (ValueError, TypeError):
        return None


def _get_total_sms(data: Any) -> int | None:
    """Sum all SMS storage counts to derive the total message count."""
    sms = data.get("sms_count") or {}
    keys = ["LocalRead", "LocalUnread", "LocalSent", "LocalDraft"]
    try:
        return sum(int(sms.get(k, 0)) for k in keys)
    except (ValueError, TypeError):
        return None


SENSOR_TYPES: Final[tuple[HuaweiSensorEntityDescription, ...]] = (
    # ------------------------------------------------------------------ System
    HuaweiSensorEntityDescription(
        key="model_name",
        name="Model Name",
        icon="mdi:router-wireless",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda d: (d.get("device_information") or {}).get("DeviceName"),
    ),
    HuaweiSensorEntityDescription(
        key="sw_version",
        name="Firmware Version",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda d: (d.get("device_information") or {}).get("SoftwareVersion"),
    ),
    HuaweiSensorEntityDescription(
        key="hw_version",
        name="Hardware Version",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda d: (d.get("device_information") or {}).get("HardwareVersion"),
    ),
    HuaweiSensorEntityDescription(
        key="imei",
        name="IMEI",
        icon="mdi:identifier",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="system",
        value_fn=lambda d: (d.get("device_information") or {}).get("Imei"),
    ),
    HuaweiSensorEntityDescription(
        key="wan_ip",
        name="WAN IP Address",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda d: (
            (d.get("monitoring_status") or {}).get("WanIPAddress")
            or (d.get("device_information") or {}).get("WanIPAddress")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="lan_ip",
        name="LAN IP Address",
        icon="mdi:ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda d: (d.get("device_information") or {}).get("LanIPAddress"),
    ),
    HuaweiSensorEntityDescription(
        key="last_updated",
        name="Last Updated",
        icon="mdi:update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda d: None,  # Handled in native_value property
    ),
    HuaweiSensorEntityDescription(
        key="total_connection_time",
        name="Total Connection Time",
        icon="mdi:clock-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        group="system",
        value_fn=lambda d: _safe_int(
            (d.get("traffic_statistics") or {}).get("TotalConnectTime")
        ),
    ),
    # ------------------------------------------------------------------ Signal
    HuaweiSensorEntityDescription(
        key="network_type",
        name="Network Type",
        icon="mdi:network",
        group="signal",
        value_fn=lambda d: get_network_type_label(
            (d.get("monitoring_status") or {}).get("CurrentNetworkType")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="signal_bars",
        name="Signal Bars",
        icon="mdi:signal-cellular-3",
        state_class=SensorStateClass.MEASUREMENT,
        group="signal",
        value_fn=lambda d: _safe_int(
            (d.get("monitoring_status") or {}).get("SignalIcon")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="rsrp",
        name="LTE RSRP",
        icon="mdi:signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        min_limit=-140,
        max_limit=-30,
        group="signal",
        value_fn=lambda d: parse_signal_value(
            (d.get("device_signal") or {}).get("rsrp")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="rsrq",
        name="LTE RSRQ",
        icon="mdi:signal",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dB",
        min_limit=-40,
        max_limit=0,
        group="signal",
        value_fn=lambda d: parse_signal_value(
            (d.get("device_signal") or {}).get("rsrq")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="rssi",
        name="LTE RSSI",
        icon="mdi:signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        min_limit=-120,
        max_limit=-20,
        group="signal",
        value_fn=lambda d: parse_signal_value(
            (d.get("device_signal") or {}).get("rssi")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="sinr",
        name="LTE SINR",
        icon="mdi:waveform",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dB",
        min_limit=-20,
        max_limit=50,
        group="signal",
        value_fn=lambda d: parse_signal_value(
            (d.get("device_signal") or {}).get("sinr")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="cell_id",
        name="Cell ID",
        icon="mdi:transmission-tower",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda d: (d.get("device_signal") or {}).get("cell_id"),
    ),
    HuaweiSensorEntityDescription(
        key="pci",
        name="LTE PCI",
        icon="mdi:transmission-tower",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda d: (d.get("device_signal") or {}).get("pci"),
    ),
    HuaweiSensorEntityDescription(
        key="lte_ca",
        name="Carrier Aggregation",
        icon="mdi:plus-network",
        group="signal",
        value_fn=lambda d: (
            "enabled"
            if (d.get("device_signal") or {}).get("lte_ca") == "1"
            else "disabled"
            if (d.get("device_signal") or {}).get("lte_ca") is not None
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="lte_band",
        name="LTE Band",
        icon="mdi:antenna",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda d: (d.get("device_signal") or {}).get("lte_bandwidth"),
    ),
    HuaweiSensorEntityDescription(
        key="lte_earfcn",
        name="LTE EARFCN",
        icon="mdi:numeric",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda d: _safe_int(
            (d.get("device_signal") or {}).get("ltedl_earfcn")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="nr5g_band",
        name="5G NR Band",
        icon="mdi:antenna",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda d: (d.get("device_signal") or {}).get("sc_band") or None,
    ),
    HuaweiSensorEntityDescription(
        key="nr5g_earfcn",
        name="5G NR EARFCN",
        icon="mdi:numeric",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda d: _safe_int(
            (d.get("device_signal") or {}).get("sc_earfcn")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="nr5g_cell_id",
        name="5G NR Cell ID",
        icon="mdi:transmission-tower",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="signal",
        value_fn=lambda d: (d.get("device_signal") or {}).get("sc_cellid") or None,
    ),
    HuaweiSensorEntityDescription(
        key="operator",
        name="Network Operator",
        icon="mdi:sim-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="signal",
        value_fn=lambda d: (d.get("current_plmn") or {}).get("FullName"),
    ),
    HuaweiSensorEntityDescription(
        key="plmn",
        name="PLMN (MCC/MNC)",
        icon="mdi:map-marker",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        group="signal",
        value_fn=lambda d: (d.get("current_plmn") or {}).get("Numeric"),
    ),
    # ------------------------------------------------------------------ Data
    HuaweiSensorEntityDescription(
        key="current_download_rate",
        name="Download Rate",
        icon="mdi:download-network",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        group="data",
        value_fn=lambda d: _safe_int(
            (d.get("traffic_statistics") or {}).get("CurrentDownloadRate")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="current_upload_rate",
        name="Upload Rate",
        icon="mdi:upload-network",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        group="data",
        value_fn=lambda d: _safe_int(
            (d.get("traffic_statistics") or {}).get("CurrentUploadRate")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="total_download",
        name="Total Download",
        icon="mdi:download-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        group="data",
        value_fn=lambda d: _safe_int(
            (d.get("traffic_statistics") or {}).get("TotalDownload")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="total_upload",
        name="Total Upload",
        icon="mdi:upload-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        group="data",
        value_fn=lambda d: _safe_int(
            (d.get("traffic_statistics") or {}).get("TotalUpload")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="total_data",
        name="Total Data",
        icon="mdi:network-outline",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        group="data",
        value_fn=lambda d: (
            _safe_int((d.get("traffic_statistics") or {}).get("TotalDownload", 0))
            + _safe_int((d.get("traffic_statistics") or {}).get("TotalUpload", 0))
            if (d.get("traffic_statistics") or {}).get("TotalDownload")
            and (d.get("traffic_statistics") or {}).get("TotalUpload")
            else None
        ),
    ),
    HuaweiSensorEntityDescription(
        key="month_download",
        name="Monthly Download",
        icon="mdi:download-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        group="data",
        value_fn=lambda d: _safe_int(
            (d.get("month_statistics") or {}).get("CurrentMonthDownload")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="month_upload",
        name="Monthly Upload",
        icon="mdi:upload-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        group="data",
        value_fn=lambda d: _safe_int(
            (d.get("month_statistics") or {}).get("CurrentMonthUpload")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="month_total",
        name="Monthly Total",
        icon="mdi:network-outline",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        group="data",
        value_fn=lambda d: (
            _safe_int(
                (d.get("month_statistics") or {}).get("CurrentMonthDownload", 0)
            )
            + _safe_int(
                (d.get("month_statistics") or {}).get("CurrentMonthUpload", 0)
            )
            if (d.get("month_statistics") or {}).get("CurrentMonthDownload")
            and (d.get("month_statistics") or {}).get("CurrentMonthUpload")
            else None
        ),
    ),
    # Legacy GB sensors (disabled by default, preserved for history)
    HuaweiSensorEntityDescription(
        key="month_download_gb",
        name="Monthly Download GB",
        icon="mdi:download-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        entity_registry_enabled_default=False,
        group="data",
        value_fn=lambda d: _bytes_to_gb(
            (d.get("month_statistics") or {}).get("CurrentMonthDownload")
        ),
    ),
    HuaweiSensorEntityDescription(
        key="month_upload_gb",
        name="Monthly Upload GB",
        icon="mdi:upload-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        entity_registry_enabled_default=False,
        group="data",
        value_fn=lambda d: _bytes_to_gb(
            (d.get("month_statistics") or {}).get("CurrentMonthUpload")
        ),
    ),
    # ------------------------------------------------------------------ SMS
    HuaweiSensorEntityDescription(
        key="sms_unread",
        name="Unread Messages",
        icon="mdi:email-mark-as-unread",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        value_fn=lambda d: (
            (_safe_int((d.get("sms_count") or {}).get("LocalUnread", 0)) or 0)
            + (_safe_int((d.get("sms_count") or {}).get("SimUnread", 0)) or 0)
        )
        if d.get("sms_count")
        else None,
    ),
    HuaweiSensorEntityDescription(
        key="sms_total",
        name="Total Messages",
        icon="mdi:email-multiple",
        state_class=SensorStateClass.MEASUREMENT,
        group="sms",
        value_fn=_get_total_sms,
    ),
    HuaweiSensorEntityDescription(
        key="sms_new",
        name="New Message Flag",
        icon="mdi:email-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        group="sms",
        value_fn=lambda d: _safe_int((d.get("sms_count") or {}).get("NewMsg")),
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            HuaweiRouterSensor(coordinator, entry, description)
            for description in SENSOR_TYPES
        ]
    )


class HuaweiRouterSensor(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], SensorEntity
):
    """Representation of a Huawei Router 5G sensor."""

    _attr_has_entity_name = True
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
    def native_value(self):
        """Return the sensor value."""
        if not self.coordinator.data:
            return None

        key = self.entity_description.key

        if key == "last_updated":
            return self.coordinator.last_update_success_time

        try:
            value = self.entity_description.value_fn(self.coordinator.data)
        except (KeyError, AttributeError):
            return None

        if value is None:
            return None

        if isinstance(value, (int, float)):
            if (
                self.entity_description.min_limit is not None
                and value < self.entity_description.min_limit
            ):
                return None
            if (
                self.entity_description.max_limit is not None
                and value > self.entity_description.max_limit
            ):
                return None

        return value

    @property
    def extra_state_attributes(self):
        """Return extra attributes for specific sensors."""
        data = self.coordinator.data
        if data is None:
            return {}

        key = self.entity_description.key

        if key == "sms_total":
            sms = data.get("sms_count") or {}
            try:
                return {
                    "local_unread": int(sms.get("LocalUnread", 0)),
                    "local_read": int(sms.get("LocalRead", 0)),
                    "local_sent": int(sms.get("LocalSent", 0)),
                    "local_draft": int(sms.get("LocalDraft", 0)),
                    "local_max": int(sms.get("LocalMax", 0)),
                    "sim_unread": int(sms.get("SimUnread", 0)),
                    "sim_read": int(sms.get("SimRead", 0)),
                    "sim_max": int(sms.get("SimMax", 0)),
                }
            except (ValueError, TypeError):
                return {}

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
