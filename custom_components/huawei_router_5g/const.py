"""Constants for the Huawei Router 5G Monitor integration."""

DOMAIN = "huawei_router_5g"

DEFAULT_NAME = "Huawei 5G"
CONF_NAME = "name"

NAME = "Huawei Router 5G Monitor"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 180
CONF_STOP_POLLING = "stop_polling"
FETCH_TIMEOUT = 30

# Repair issues this integration can raise. The registry keys on
# `(domain, issue_id)`, so each id is suffixed with the entry id — otherwise
# two routers share one slot and the healthy one's next successful poll deletes
# the failing one's repair.
#
# These names are also the `translation_key`s, which stay bare. **Never rename
# one**: `ir.async_delete_issue` looks up by id, so renaming while a repair is
# live orphans it permanently with no UI path to clear it.
REPAIR_AUTH_FAILED = "auth_failed"
REPAIR_CONN_ERROR = "conn_error"
REPAIR_NAMES: tuple[str, ...] = (REPAIR_AUTH_FAILED, REPAIR_CONN_ERROR)

# --- Section 19: Integration Health ------------------------------------------
#
# `api.get_data()` fetches fifteen endpoints and **silently omits** any optional
# one that fails — only `device_information` raises. So a poll can succeed with
# a whole capability missing and nothing anywhere says so. That is precisely the
# silent failure Section 19 exists to surface.
#
# Friendly names, because `degraded_capabilities` is read by users in the UI and
# in templates, not by developers.
ENDPOINT_NAMES: dict[str, str] = {
    "device_information": "Device information",
    "device_signal": "Signal metrics",
    "monitoring_status": "Connection status",
    "monitoring_check_notifications": "Notifications",
    "traffic_statistics": "Traffic statistics",
    "month_statistics": "Monthly data usage",
    "current_plmn": "Network operator",
    "net_mode": "Network mode",
    "sms_count": "SMS counters",
    "sms_list": "SMS messages",
    "mobile_dataswitch": "Mobile data switch",
    "lan_host_info": "Wired clients",
    "wlan_host_list": "WiFi clients",
    "wlan_wifi_feature_switch": "WiFi feature switch",
    "wlan_multi_basic_settings": "WiFi networks",
}

# `device_information` is the one endpoint whose absence already raises, so it
# can never appear as "degraded" — the fetch fails outright instead.
CRITICAL_ENDPOINT = "device_information"

# Signal fields that a working `device_signal` response always carries at least
# one of. All of them absent while the block itself is non-empty is contract
# drift, not a weak signal — a firmware rename looks exactly like this.
SIGNAL_CONTRACT_KEYS: tuple[str, ...] = ("rsrp", "rsrq", "rssi", "sinr")

# Section 19: require a condition to persist before flipping the sensor, so a
# single blip raises no alarm. Matches the Section 8 fetch strike budget.
HEALTH_STRIKE_LIMIT = 3
