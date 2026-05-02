"""Sensor platform for Huawei Router 5G."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfDataRate,
    UnitOfInformation,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HuaweiSensorEntityDescription(SensorEntityDescription):
    """Describes Huawei sensor entity."""

    value_fn: Callable[[Any], Any]


def _get_signal_value(data: dict, key: str) -> Any:
    """Get signal value from data."""
    signal = data.get("device_signal", {})
    return signal.get(key)


SENSORS: tuple[HuaweiSensorEntityDescription, ...] = (
    HuaweiSensorEntityDescription(
        key="rsrp",
        name="RSRP",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _get_signal_value(data, "rsrp"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="rsrq",
        name="RSRQ",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _get_signal_value(data, "rsrq"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="rssi",
        name="RSSI",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _get_signal_value(data, "rssi"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="sinr",
        name="SINR",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _get_signal_value(data, "sinr"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HuaweiSensorEntityDescription(
        key="network_type",
        name="Network Type",
        value_fn=lambda data: data.get("monitoring_status", {}).get(
            "CurrentNetworkType"
        ),
    ),
    HuaweiSensorEntityDescription(
        key="operator",
        name="Operator",
        value_fn=lambda data: data.get("current_plmn", {}).get("FullName"),
    ),
    HuaweiSensorEntityDescription(
        key="total_download",
        name="Total Download",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("traffic_statistics", {}).get("TotalDownload"),
    ),
    HuaweiSensorEntityDescription(
        key="total_upload",
        name="Total Upload",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("traffic_statistics", {}).get("TotalUpload"),
    ),
    HuaweiSensorEntityDescription(
        key="current_download_rate",
        name="Current Download Rate",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("traffic_statistics", {}).get(
            "CurrentDownloadRate"
        ),
    ),
    HuaweiSensorEntityDescription(
        key="current_upload_rate",
        name="Current Upload Rate",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("traffic_statistics", {}).get(
            "CurrentUploadRate"
        ),
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HuaweiRouterSensor(coordinator, description) for description in SENSORS
    )


class HuaweiRouterSensor(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], SensorEntity
):
    """Representation of a Huawei Router sensor."""

    entity_description: HuaweiSensorEntityDescription

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        description: HuaweiSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.unique_id)},
            "name": coordinator.entry.title,
            "manufacturer": "Huawei",
            "model": coordinator.model,
            "sw_version": coordinator.sw_version,
            "hw_version": coordinator.hw_version,
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)
