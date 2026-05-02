"""Binary sensor platform for Huawei Router 5G Monitor."""

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class HuaweiBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Huawei Router 5G binary sensor entity."""

    group: str = "signal"


BEST_CONN_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="best_connection",
    translation_key="best_connection",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
)

SMS_STORAGE_FULL_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="sms_storage_full",
    translation_key="sms_storage_full",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="sms",
)

WIFI_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="wifi_status",
    name="WiFi Status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="system",
)

WIFI_24G_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="wifi24g_status",
    name="WiFi 2.4GHz Status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="system",
)

WIFI_5G_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="wifi5g_status",
    name="WiFi 5GHz Status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="system",
)

MOBILE_CONN_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="mobile_connection",
    name="Mobile Connection",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the binary sensor platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            HuaweiBestConnectionSensor(coordinator, entry, BEST_CONN_DESCRIPTION),
            HuaweiSmsStorageFullSensor(
                coordinator, entry, SMS_STORAGE_FULL_DESCRIPTION
            ),
            HuaweiWifiStatusSensor(coordinator, entry, WIFI_STATUS_DESCRIPTION),
            HuaweiWifi24GStatusSensor(coordinator, entry, WIFI_24G_STATUS_DESCRIPTION),
            HuaweiWifi5GStatusSensor(coordinator, entry, WIFI_5G_STATUS_DESCRIPTION),
            HuaweiMobileConnectionSensor(coordinator, entry, MOBILE_CONN_DESCRIPTION),
        ]
    )


class HuaweiBinarySensor(
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator], BinarySensorEntity
):
    """Base class for Huawei Router 5G binary sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description: HuaweiBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry,
        description: HuaweiBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

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


class HuaweiBestConnectionSensor(HuaweiBinarySensor):
    """Binary sensor that is True when 5G NR is actively in use."""

    @property
    def is_on(self) -> bool:
        """Return True if 5G NR band is active."""
        data = self.coordinator.data
        if not data:
            return False
        signal = data.get("device_signal") or {}
        nr_band = signal.get("sc_band", "")
        # 5G NR is active when a non-empty NR band is reported
        return bool(nr_band and nr_band not in ("", "N/A", "0"))

    @property
    def icon(self) -> str:
        """Return icon based on connection quality."""
        return "mdi:signal-5g" if self.is_on else "mdi:signal-cellular-1"


class HuaweiSmsStorageFullSensor(HuaweiBinarySensor):
    """Binary sensor that is True when SMS storage is full."""

    @property
    def is_on(self) -> bool | None:
        """Return True if SMS storage full flag is set."""
        data = self.coordinator.data
        if not data:
            return None
        status = data.get("monitoring_status") or {}
        flag = status.get("SmsStorageFull")
        if flag is None:
            return None
        return str(flag) == "1"


class HuaweiWifiStatusSensor(HuaweiBinarySensor):
    """Binary sensor that is True when WiFi is on."""

    @property
    def is_on(self) -> bool | None:
        """Return True if WiFi is on."""
        data = self.coordinator.data
        if not data:
            return None
        status = data.get("monitoring_status") or {}
        flag = status.get("WifiStatus")
        if flag is None:
            return None
        return str(flag) == "1"


class HuaweiWifi24GStatusSensor(HuaweiBinarySensor):
    """Binary sensor that is True when 2.4GHz WiFi is on."""

    @property
    def is_on(self) -> bool | None:
        """Return True if 2.4GHz WiFi is on."""
        data = self.coordinator.data
        if not data:
            return None
        status = data.get("wlan_wifi_feature_switch") or {}
        flag = status.get("wifi24g_switch_enable")
        if flag is None:
            return None
        return str(flag) == "1"


class HuaweiWifi5GStatusSensor(HuaweiBinarySensor):
    """Binary sensor that is True when 5GHz WiFi is on."""

    @property
    def is_on(self) -> bool | None:
        """Return True if 5GHz WiFi is on."""
        data = self.coordinator.data
        if not data:
            return None
        status = data.get("wlan_wifi_feature_switch") or {}
        flag = status.get("wifi5g_enabled")
        if flag is None:
            return None
        return str(flag) == "1"


class HuaweiMobileConnectionSensor(HuaweiBinarySensor):
    """Binary sensor that is True when mobile connection is active."""

    @property
    def is_on(self) -> bool | None:
        """Return True if mobile connection is active."""
        data = self.coordinator.data
        if not data:
            return None
        status = data.get("monitoring_status") or {}
        # 901 is connected
        return status.get("ConnectionStatus") == "901"
