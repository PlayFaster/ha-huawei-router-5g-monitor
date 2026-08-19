"""Binary sensor platform for Huawei Router 5G Monitor."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

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

from .const import DIAG_HEALTHY, DIAG_REASONS, DIAG_VERDICT_KEY
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import (
    ABOUT_UNRECORDED,
    HuaweiAboutEntity,
    build_device_info,
    is_ssid_on,
    parse_signal_value,
)

# Section 22. `0` (unlimited) — this platform is read-only. Entities are
# coordinator-driven with no per-entity polling, so there is nothing to
# serialize.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HuaweiBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Huawei Router 5G binary sensor entity."""

    group: str = "signal"
    # Optional. When set, `HuaweiValueBinarySensor` reads the state from it and
    # no per-entity subclass is needed. The eleven original descriptions leave
    # it None and keep their own classes.
    value_fn: Callable[[dict[str, Any] | None], bool | None] | None = None
    # dev_standards Section 14 — the human-facing `about` note. Mandatory; a
    # sweep in `tests/test_entity_hygiene.py` fails when one is missing.
    about: str | None = None


BEST_CONN_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="best_connection",
    about=(
        "On when both the LTE anchor and the 5G leg are healthy at once - the "
        "state this hardware performs best in. Off does not mean a problem; "
        "it means the router is running on one of the two rather than both."
    ),
    translation_key="best_connection",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    group="signal",
)

SMS_STORAGE_FULL_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="sms_storage_full",
    about=(
        "On when message storage has no room left. A full store makes the "
        "network stop delivering new messages, and nothing else in the "
        "integration reports that - which is the whole reason this entity "
        "exists."
    ),
    translation_key="sms_storage_full",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    group="sms",
)

WIFI_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="wifi_status",
    about=(
        "Whether the router's WiFi is on overall. It follows the radio, not the "
        "individual SSID flags: with the radio off, the per-SSID settings still read "
        "as enabled and mean nothing."
    ),
    translation_key="wifi_status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="wifi",
)

WIFI_24G_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="wifi24g_status",
    about=(
        "Whether the 2.4 GHz radio is broadcasting. Off while WiFi Status is "
        "on means that band alone has been disabled."
    ),
    translation_key="wifi24g_status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="wifi",
)

WIFI_5G_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="wifi5g_status",
    about=(
        "Whether the 5 GHz radio is broadcasting. The lookup deliberately "
        "steps past the guest network when matching, because a guest SSID on "
        "the same radio would otherwise be mistaken for the main one."
    ),
    translation_key="wifi5g_status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="wifi",
)

MOBILE_CONN_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="mobile_connection",
    about=(
        "On when the mobile data connection is established. This is the "
        "router's link to the operator, not the router's link to the local "
        "network - the LAN keeps working while this is off."
    ),
    translation_key="mobile_connection",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
)

LTE_CA_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="lte_ca",
    about=(
        "On when LTE carrier aggregation is combining more than one carrier. "
        "LTE Band lists which; Primary Band names only the anchor."
    ),
    translation_key="lte_ca",
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
)

ENDC_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="endc_status",
    about=(
        "On when EN-DC is active, meaning the router has a 5G leg attached "
        "alongside its LTE anchor. This is what 'connected to 5G' means on a "
        "non-standalone network."
    ),
    translation_key="endc_status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    group="signal",
)

ENDC_RESTRICTED_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="endc_restricted",
    about=(
        "On when the network is withholding 5G from this router. It is a network-side "
        "restriction rather than a fault at this end, and it is the usual explanation "
        "for good signal with no 5G leg."
    ),
    translation_key="endc_restricted",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
)

SINGLE_SSID_MODE_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="single_ssid_mode",
    about=(
        "On when both bands share one network name, so clients pick a band "
        "themselves. Convenient, but it removes the ability to pin a device "
        "to 2.4 GHz for range."
    ),
    translation_key="single_ssid_mode",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="wifi",
)

ROAMING_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="roaming",
    about=(
        "On when the router is registered to a network other than the SIM's "
        "home operator. Compare MCC MNC with Operator Code to see which "
        "network that is."
    ),
    translation_key="roaming",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
)

INTEGRATION_HEALTH_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="integration_health",
    about=(
        "Reports the health of the integration itself, flagging when polling succeeds "
        "but specific capabilities or endpoints are missing or degraded. Provides "
        "`severity`, `issues`, `degraded_capabilities`, `drift`, and "
        "`last_good_update` attributes, and never goes unavailable."
    ),
    translation_key="integration_health",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="system",
)

SIM_STATUS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="sim_status",
    about=(
        "On when the SIM is not usable - missing, locked out, or failing to "
        "initialize. It is a problem sensor, so on means something is wrong; that is "
        "deliberately the opposite polarity to reading it as 'SIM present'."
    ),
    translation_key="sim_status",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="system",
)


# --- §T-4: added 2026-08-15 --------------------------------------------------
#
# These are declared as descriptions with a `value_fn` rather than as one class
# each, which is how the eleven above are written. Nine more subclasses whose
# only content is a two-line `is_on` would be boilerplate, and boilerplate is
# where a copy-paste error hides. `HuaweiValueBinarySensor` below reads the
# `value_fn` and is the only class any of these needs.
#
# Binary sensors carry no `state_class` and never enter long-term statistics,
# so none of them appears in the §T-4f exclusion lists.


def _flag(data: dict[str, Any] | None, block: str, key: str) -> bool | None:
    """Return a router `0`/`1` flag as a bool, or None when absent.

    **The `0` means off mapping is an assumption for the two signal flags.**
    Both `poorSignalStatus` and `speedLimitStatus` have only ever been observed
    reading `0`, which is the expected resting state and consistent with the
    field names, but neither has been seen in the other state. If either ever
    reports a problem that is not happening, this is the line to revisit.
    """
    if not data:
        return None
    raw = (data.get(block) or {}).get(key)
    if raw in (None, ""):
        return None
    return str(raw).strip().lower() not in ("0", "off", "false")


POOR_SIGNAL_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="poor_signal",
    about=(
        "The router's own verdict that its signal is poor, from a single "
        "firmware flag rather than computed here. The threshold it uses is "
        "not published, so read it as a hint - judge signal by LTE RSRP and "
        "SINR."
    ),
    translation_key="poor_signal",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
    value_fn=lambda data: _flag(data, "monitoring_status", "poorSignalStatus"),
)

SPEED_LIMITED_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="speed_limited",
    about=(
        "The router's own flag saying its throughput is being capped. The "
        "conditions it uses are not published, so it is a hint rather than a "
        "measurement."
    ),
    translation_key="speed_limited",
    # Deliberately no device class: throughput being limited is a state the
    # carrier chose, not a fault, and PROBLEM would render it as one.
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    group="signal",
    value_fn=lambda data: _flag(data, "monitoring_status", "speedLimitStatus"),
)

DATA_SERVICE_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="data_service",
    about=(
        "Whether the packet-switched (data) side of the network registration "
        "is attached. Voice Service reports the circuit-switched side, and on "
        "a data-only plan the two differ permanently."
    ),
    translation_key="data_service",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="signal",
    # `psstate` is packet-switched registration - the half that carries data.
    value_fn=lambda data: _flag(data, "csps_state", "psstate"),
)

VOICE_SERVICE_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="voice_service",
    about=(
        "Whether the circuit-switched (voice) side of the network "
        "registration is attached. Off on a data-only plan is expected, not a "
        "fault."
    ),
    translation_key="voice_service",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    group="signal",
    # `csstate` is circuit-switched registration - voice network attachment.
    # It says nothing about a call being in progress; no endpoint on this
    # hardware does.
    value_fn=lambda data: _flag(data, "csps_state", "csstate"),
)

DATA_PLAN_ENABLED_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="data_plan_enabled",
    about=(
        "Whether the router's monthly data plan is switched on. With it off "
        "the monthly counters never roll over, so Projected Usage reports "
        "nothing rather than projecting against a cycle the router is not "
        "keeping."
    ),
    translation_key="data_plan_enabled",
    entity_category=EntityCategory.DIAGNOSTIC,
    group="data",
    # Enabled by default because it is the switch that decides whether Data
    # Allowance, Alert Threshold and the projection mean anything at all.
    value_fn=lambda data: _flag(data, "start_date", "SetMonthData"),
)

SIM_LOCKED_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="sim_locked",
    about=(
        "Whether SIM lock is enabled on the router. A configuration state, "
        "not an alarm: it says the router will demand a PIN, not that it is "
        "currently blocked."
    ),
    translation_key="sim_locked",
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    group="system",
    # Supersedes `monitoring_status.simlockStatus`, which is an undecodable
    # code. This one is a plain flag.
    value_fn=lambda data: _flag(data, "converged_status", "SimLockEnable"),
)

ROAMING_AUTO_CONNECT_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="roaming_auto_connect",
    about=(
        "Whether the router will bring up data automatically while roaming. A "
        "setting on the router, and the one that decides whether roaming "
        "charges can be incurred without anyone acting."
    ),
    translation_key="roaming_auto_connect",
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    group="system",
    value_fn=lambda data: _flag(data, "dial_up_connection", "RoamAutoConnectEnable"),
)

SIP_ALG_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="sip_alg",
    about=(
        "Whether the router's SIP application-layer gateway is enabled. It "
        "rewrites VoIP signaling in transit, which helps some phone systems "
        "and breaks others; there is no universally right setting."
    ),
    translation_key="sip_alg",
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    group="system",
    # The firewall's SIP helper, not VoIP status. It is the commonest cause of
    # one-way audio behind a CPE, which is why its state is worth knowing even
    # though it never changes on its own.
    value_fn=lambda data: _flag(data, "security_sip", "SipStatus"),
)

ROUTER_DIAGNOSTICS_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="router_diagnostics",
    about=(
        "The router's built-in connection diagnostic. Reports whether the router can reach the mobile network, with specific failure causes listed in the `reasons` attribute. Compare with Integration Health to distinguish router-level outages from integration polling issues."
    ),
    translation_key="router_diagnostics",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    group="system",
)

VOLTE_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="volte",
    about=(
        "Whether VoLTE - voice carried over the LTE data channel - is "
        "available. It depends on the operator provisioning it as well as on "
        "the router supporting it, so off can be entirely correct."
    ),
    translation_key="volte",
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    group="system",
    # Real VoLTE state, unlike the SIP ALG flag which is a firewall setting.
    value_fn=lambda data: _flag(data, "voice_volte", "volte_enable"),
)

UPNP_DESCRIPTION = HuaweiBinarySensorEntityDescription(
    key="upnp",
    about=(
        "Whether UPnP port forwarding is enabled, letting devices on the LAN "
        "open inbound ports without being asked. Convenient for games and "
        "consoles, and a real attack surface."
    ),
    translation_key="upnp",
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    group="system",
    value_fn=lambda data: _flag(data, "security_upnp", "UpnpStatus"),
)

VALUE_BINARY_SENSORS: Final[tuple[HuaweiBinarySensorEntityDescription, ...]] = (
    POOR_SIGNAL_DESCRIPTION,
    SPEED_LIMITED_DESCRIPTION,
    DATA_SERVICE_DESCRIPTION,
    VOICE_SERVICE_DESCRIPTION,
    DATA_PLAN_ENABLED_DESCRIPTION,
    SIM_LOCKED_DESCRIPTION,
    ROAMING_AUTO_CONNECT_DESCRIPTION,
    SIP_ALG_DESCRIPTION,
    UPNP_DESCRIPTION,
    VOLTE_DESCRIPTION,
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
            HuaweiIntegrationHealthSensor(
                coordinator, entry, INTEGRATION_HEALTH_DESCRIPTION
            ),
            HuaweiRouterDiagnosticsSensor(
                coordinator, entry, ROUTER_DIAGNOSTICS_DESCRIPTION
            ),
            *(
                HuaweiValueBinarySensor(coordinator, entry, description)
                for description in VALUE_BINARY_SENSORS
            ),
        ]
    )


class HuaweiBinarySensor(
    HuaweiAboutEntity,
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator],
    BinarySensorEntity,
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
        return str(value) == "901"


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


class HuaweiIntegrationHealthSensor(HuaweiBinarySensor):
    """Section 19: the integration's own self-diagnosis.

    Surfaces the failure Home Assistant does **not** catch — a poll that
    succeeds while the data is wrong or a whole capability is quietly missing.
    `api.get_data()` silently omits any optional endpoint that fails, so
    "successful poll, absent capability" is this integration's characteristic
    silent failure.
    """

    # The detail belongs in attributes, and none of it is a time series — a
    # list of current issues has no meaning as history (Section 14).
    _unrecorded_attributes = ABOUT_UNRECORDED | frozenset(
        {
            "severity",
            "issues",
            "degraded_capabilities",
            "drift",
            "last_good_update",
        }
    )

    @property
    def available(self) -> bool:
        """Always available — that is the whole point of this entity.

        The inherited `CoordinatorEntity.available` returns
        `last_update_success`, which takes this sensor down at exactly the
        moment it has something to say. A user reads `unavailable` as "this
        sensor is broken", not "my router is down", so a health sensor that
        disappears during an outage is worse than none: its silence is
        indistinguishable from health.
        """
        return True

    @property
    def is_on(self) -> bool:
        """Return True when the integration has a problem to report."""
        return bool(self.coordinator.health_snapshot.get("issues"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the Section 19 attribute contract.

        **These spellings are normative.** Users write templates against them,
        so a project that spells one differently silently breaks every example
        written for a sibling. `checks_failed`, `degraded` and `last_good_scan`
        are prior spellings found in the field and are not valid.
        """
        snapshot = self.coordinator.health_snapshot
        return (
            self._with_about(
                {
                    "severity": snapshot.get("severity"),
                    "issues": list(snapshot.get("issues", [])),
                    "degraded_capabilities": list(
                        snapshot.get("degraded_capabilities", [])
                    ),
                    "drift": list(snapshot.get("drift", [])),
                    "last_good_update": snapshot.get("last_good_update"),
                }
            )
            or {}
        )


class HuaweiValueBinarySensor(HuaweiBinarySensor):
    """A binary sensor whose state comes from its description's `value_fn`.

    Covers every §T-4 binary sensor. The eleven older ones each carry their own
    subclass because their logic is genuinely per-entity; these read one flag
    from one block, so a shared class is both shorter and harder to get wrong.
    """

    @property
    def is_on(self) -> bool | None:
        """Return the flag this description reads, or None when unavailable."""
        value_fn = self.entity_description.value_fn
        if value_fn is None:
            # Unreachable for every description in VALUE_BINARY_SENSORS, and
            # covered by a test rather than a pragma: a description that
            # forgot its value_fn should report unavailable, not raise.
            return None
        return value_fn(self.coordinator.data)


class HuaweiRouterDiagnosticsSensor(HuaweiBinarySensor):
    """The router's own verdict on its connection, with the reasons attached.

    **Distinct from Integration Health, deliberately.** That sensor answers "is
    this integration working"; this one answers "does the router think its
    connection is working". Folding one into the other would make a single green
    light mean two different things, and they can disagree — a perfectly healthy
    integration faithfully reporting a router that cannot reach the network.

    One entity rather than ten. Nine of the ten fields read `0` permanently on a
    healthy router, so ten binary sensors would be nine pieces of furniture and
    one signal.
    """

    # Section 14: the reason list changes only when something is wrong, but the
    # raw block is republished every poll and none of it is a time series.
    _unrecorded_attributes = ABOUT_UNRECORDED | frozenset({"reasons", "raw", "verdict"})

    @property
    def is_on(self) -> bool | None:
        """Return True when the router reports its connection as unhealthy.

        `!= DIAG_HEALTHY`, not `== "8"`. Only `2` (healthy) and `8` (down) have
        been observed, so treating anything that is not the known-good value as
        a problem is sound, while enumerating failure codes would be a guess
        about every code never seen.
        """
        block = (self.coordinator.data or {}).get("onekey_diag") or {}
        verdict = block.get(DIAG_VERDICT_KEY)
        if verdict in (None, ""):
            return None
        return str(verdict) != DIAG_HEALTHY

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the reasons the router gives, plus the raw block.

        The raw block is published because seven of the nine reason labels are
        read from their field names rather than measured — a reader who
        disagrees with a label can see the field that produced it.
        """
        block = (self.coordinator.data or {}).get("onekey_diag") or {}
        if not block:
            return self._with_about(None) or {}
        reasons = [
            label
            for key, label in DIAG_REASONS.items()
            if str(block.get(key, "0")) not in ("0", "")
        ]
        return (
            self._with_about(
                {
                    "verdict": block.get(DIAG_VERDICT_KEY),
                    "reasons": reasons,
                    "raw": dict(block),
                }
            )
            or {}
        )
