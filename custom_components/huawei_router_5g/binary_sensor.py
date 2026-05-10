"""Binary sensor platform for Huawei Router 5G Monitor."""

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import build_device_info, is_ssid_on, parse_signal_value

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HuaweiBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Huawei Router 5G binary sensor entity."""

    group: str = "signal"


BEST_CONN_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="best_connection",
    translation_key="best_connection",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    group="signal",
)

SMS_STORAGE_FULL_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="sms_storage_full",
    translation_key="sms_storage_full",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    group="sms",
)

WIFI_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="wifi_status",
    translation_key="wifi_status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="wifi",
)

WIFI_24G_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="wifi24g_status",
    translation_key="wifi24g_status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="wifi",
)

WIFI_5G_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="wifi5g_status",
    translation_key="wifi5g_status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="wifi",
)

MOBILE_CONN_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="mobile_connection",
    translation_key="mobile_connection",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
)

LTE_CA_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="lte_ca",
    translation_key="lte_ca",
    icon="mdi:plus-network",
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
)

ENDC_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="endc_status",
    translation_key="endc_status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    group="signal",
)

ENDC_RESTRICTED_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="endc_restricted",
    translation_key="endc_restricted",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
)

SINGLE_SSID_MODE_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="single_ssid_mode",
    translation_key="single_ssid_mode",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="wifi",
)

ROAMING_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="roaming",
    translation_key="roaming",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
)

SIM_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="sim_status",
    translation_key="sim_status",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="system",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = entry.runtime_data
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
            HuaweiLteCaSensor(coordinator, entry, LTE_CA_DESCRIPTION),
            HuaweiEndcStatusSensor(coordinator, entry, ENDC_STATUS_DESCRIPTION),
            HuaweiEndcRestrictedSensor(coordinator, entry, ENDC_RESTRICTED_DESCRIPTION),
            HuaweiSingleSsidModeSensor(
                coordinator, entry, SINGLE_SSID_MODE_DESCRIPTION
            ),
            HuaweiRoamingSensor(coordinator, entry, ROAMING_DESCRIPTION),
            HuaweiSimStatusSensor(coordinator, entry, SIM_STATUS_DESCRIPTION),
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
        entry: ConfigEntry,
        description: HuaweiBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._group = description.group

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self._group)


class HuaweiBestConnectionSensor(HuaweiBinarySensor):
    """Binary sensor: True when NSA 5G is present.

    Active when both LTE anchor and 5G leg are healthy.
    """

    @property
    def is_on(self) -> bool | None:
        """Return True when all three quality gates pass.

        Stage 1 — NR band assignment present in composite band string.
        Stage 2 — LTE anchor: rsrp > -100 OR sinr > 15 OR rsrq > -12.
        Stage 3 — 5G leg: nr_rsrp > -105 OR nr_sinr > 10 OR nr_rsrq > -12
                           OR 5g_cqi >= 7 OR bler < 10%.
        """
        data = self.coordinator.data
        if not data:
            return None
        signal = data.get("device_signal") or {}

        # Stage 1: NR band label present in composite band string (e.g. "(N28)")
        band = signal.get("band") or ""
        if "(N" not in str(band):
            return False

        # Stage 2: LTE anchor health
        rsrp = parse_signal_value(signal.get("rsrp"))
        rsrq = parse_signal_value(signal.get("rsrq"))
        sinr = parse_signal_value(signal.get("sinr"))
        lte_ok = (
            (rsrp is not None and rsrp > -100)
            or (sinr is not None and sinr > 15)
            or (rsrq is not None and rsrq > -12)
        )
        if not lte_ok:
            return False

        # Stage 3: 5G leg health
        nr_rsrp = parse_signal_value(signal.get("nrrsrp"))
        nr_rsrq = parse_signal_value(signal.get("nrrsrq"))
        nr_sinr = parse_signal_value(signal.get("nrsinr"))
        nr_bler = parse_signal_value(signal.get("nrbler"))
        nr_cqi = parse_signal_value(signal.get("nrcqi0"))
        return (
            (nr_rsrp is not None and nr_rsrp > -105)
            or (nr_sinr is not None and nr_sinr > 10)
            or (nr_rsrq is not None and nr_rsrq > -12)
            or (nr_cqi is not None and nr_cqi >= 7)
            or (nr_bler is not None and nr_bler < 10)
        )

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
        status = data.get("monitoring_check_notifications") or {}
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
        multi_settings = data.get("wlan_multi_basic_settings") or {}
        ssids = multi_settings.get("Ssids", {}).get("Ssid", [])
        if isinstance(ssids, dict):
            ssids = [ssids]

        # Priority 1: ID path (Dynamic mapping)
        res = is_ssid_on(ssids, "Radio.1.Ssid.1")
        if res is not None:
            return res

        # Fallback to Index 0
        for ssid in ssids:
            if (
                str(ssid.get("Index")) == "0"
                and str(ssid.get("wifiisguestnetwork")) != "1"
            ):
                return str(ssid.get("WifiEnable")) == "1"
        return None


class HuaweiWifi5GStatusSensor(HuaweiBinarySensor):
    """Binary sensor that is True when 5GHz WiFi is on."""

    @property
    def is_on(self) -> bool | None:
        """Return True if 5GHz WiFi is on."""
        data = self.coordinator.data
        if not data:
            return None
        multi_settings = data.get("wlan_multi_basic_settings") or {}
        ssids = multi_settings.get("Ssids", {}).get("Ssid", [])
        if isinstance(ssids, dict):
            ssids = [ssids]

        # Priority 0: ID path (Dynamic mapping)
        res = is_ssid_on(ssids, "Radio.2.Ssid.1")
        if res is not None:
            return res

        # Fallback 1: SSID specifically named with '5G' but not '2.4G', and not guest
        for ssid in ssids:
            if str(ssid.get("wifiisguestnetwork")) != "1":
                name = str(ssid.get("WifiSsid", "")).upper()
                if "5G" in name and "2.4G" not in name:
                    return str(ssid.get("WifiEnable")) == "1"

        # Fallback 2: Index 1 (standard for 5GHz on many models)
        for ssid in ssids:
            if (
                str(ssid.get("Index")) == "1"
                and str(ssid.get("wifiisguestnetwork")) != "1"
            ):
                return str(ssid.get("WifiEnable")) == "1"

        # Fallback 3: Index 5 (H165-383)
        for ssid in ssids:
            if (
                str(ssid.get("Index")) == "5"
                and str(ssid.get("wifiisguestnetwork")) != "1"
            ):
                return str(ssid.get("WifiEnable")) == "1"

        # Fallback 4: First non-guest SSID that is NOT Index 0
        for ssid in ssids:
            if (
                str(ssid.get("Index")) != "0"
                and str(ssid.get("wifiisguestnetwork")) != "1"
            ):
                return str(ssid.get("WifiEnable")) == "1"

        return None


class HuaweiEndcStatusSensor(HuaweiBinarySensor):
    """Binary sensor: True when ENDC (LTE+5G Dual Connectivity) is active."""

    @property
    def is_on(self) -> bool | None:
        """Return True if ENDC is active."""
        data = self.coordinator.data
        if not data:
            return None
        status = data.get("monitoring_status") or {}
        value = status.get("EndcStatus")
        if value is None:
            return None
        return str(value) == "1"


class HuaweiEndcRestrictedSensor(HuaweiBinarySensor):
    """Binary sensor: True if 5G access is restricted by the carrier."""

    @property
    def is_on(self) -> bool | None:
        """Return True if 5G is restricted."""
        data = self.coordinator.data
        if not data:
            return None
        status = data.get("monitoring_status") or {}
        return str(status.get("endcRestrictedStatus")) == "1"


class HuaweiSingleSsidModeSensor(HuaweiBinarySensor):
    """Binary sensor: True if WiFi Single SSID (Band Steering) mode is enabled."""

    @property
    def is_on(self) -> bool | None:
        """Return True if Single SSID mode is active."""
        data = self.coordinator.data
        if not data:
            return None
        # DBHO (Dual-Band Handover) is the definitive flag for this router model
        multi_settings = data.get("wlan_multi_basic_settings") or {}
        if str(multi_settings.get("DbhoEnable")) == "1":
            return True

        # Fallback to feature switches for older models
        feature_switch = data.get("wlan_wifi_feature_switch") or {}
        return (
            feature_switch.get("stafrequenceenable") == "1"
            or feature_switch.get("wifi_dbdc_enable") == "1"
        )


class HuaweiRoamingSensor(HuaweiBinarySensor):
    """Binary sensor: True if the device is currently roaming."""

    @property
    def is_on(self) -> bool | None:
        """Return True if roaming is active."""
        data = self.coordinator.data
        if not data:
            return None
        status = data.get("monitoring_status") or {}
        value = status.get("RoamingStatus")
        if value is None:
            return None
        return str(value) == "1"


class HuaweiSimStatusSensor(HuaweiBinarySensor):
    """Binary sensor: True if there is a problem with the SIM card."""

    @property
    def is_on(self) -> bool | None:
        """Return True if SIM status is NOT '1' (Ready)."""
        data = self.coordinator.data
        if not data:
            return None
        status = data.get("monitoring_status") or {}
        sim_status = status.get("SimStatus")
        if sim_status is None:
            return None
        # 1 is Normal/Ready
        return str(sim_status) != "1"


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
        value = status.get("ConnectionStatus")
        if value is None:
            return None
        return value == "901"


class HuaweiLteCaSensor(HuaweiBinarySensor):
    """Binary sensor that is True when LTE Carrier Aggregation is active."""

    @property
    def is_on(self) -> bool | None:
        """Return True when multiple LTE carriers are aggregated."""
        data = self.coordinator.data
        if not data:
            return None
        band = (data.get("device_signal") or {}).get("band")
        if not band or not isinstance(band, str):
            return None
        return "+" in band
