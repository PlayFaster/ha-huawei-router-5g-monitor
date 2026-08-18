"""Constants for the Huawei Router 5G Monitor integration."""

DOMAIN = "huawei_router_5g"

DEFAULT_NAME = "Huawei 5G"
CONF_NAME = "name"

NAME = "Huawei Router 5G Monitor"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 180
CONF_STOP_POLLING = "stop_polling"
# Overall budget for one poll — all twenty-six endpoints together.
FETCH_TIMEOUT = 30

# Per-request transport timeout, passed to `Connection`. Deliberately well
# under FETCH_TIMEOUT: without it a single hung endpoint consumes the entire
# poll budget and fails the whole update, whereas a per-request timeout lets
# that one endpoint fail while the other fourteen still return. A dropped
# endpoint is no longer silent either — the Integration Health sensor reports
# it as a degraded capability once it persists.
REQUEST_TIMEOUT = 10

# Longest a caller will wait for the API lock before giving up.
#
# Unbounded acquisition is what turned a single wedged task into a permanent
# outage: every later poll and every button press queued behind a lock nobody
# would ever release, and the only symptom was a timeout thirty seconds later
# with nothing naming the cause.
#
# Sized above the longest legitimate hold, so a slow-but-working router is
# never failed by it. That hold is a full poll — twenty-six endpoints inside
# `FETCH_TIMEOUT` (30 s) — and a write may arrive the moment one starts, so the
# floor is 30 s and this carries 30 s of headroom on top. The network-mode
# settle (15 s) and its read-back are deliberately *not* in that arithmetic:
# since 2026-08-18 they run with the lock released.
LOCK_TIMEOUT = 60

# Seconds a liveness probe may take. One endpoint on a brand-new connection,
# so `REQUEST_TIMEOUT` plus the login round trip is the whole budget.
PROBE_TIMEOUT = 20

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
REPAIR_SELF_RECOVERED = "self_recovered"
REPAIR_NAMES: tuple[str, ...] = (
    REPAIR_AUTH_FAILED,
    REPAIR_CONN_ERROR,
    REPAIR_SELF_RECOVERED,
)

# --- Section 19: Integration Health ------------------------------------------
#
# `api.get_data()` fetches twenty-six endpoints and **silently omits** any optional
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
    # Added with the §T-4 entity set. Omitting these was an oversight: a block
    # absent from this map cannot be reported as a degraded capability, so the
    # endpoint could fail every poll and Section 19 would stay green.
    # `test_integration_health` now sweeps the fetch list against this map.
    "start_date": "Data plan",
    "converged_status": "SIM and country",
    "dial_up_profiles": "APN profiles",
    "dial_up_connection": "Connection settings",
    "antenna_type": "Antenna selection",
    "csps_state": "Network registration",
    "security_sip": "SIP ALG",
    "security_upnp": "UPnP",
    "voice_busy": "Voice line state",
    "voice_volte": "VoLTE status",
    "onekey_diag": "Router self-diagnosis",
}

# --- `monitoring/onekey_diag` -------------------------------------------------
#
# The router's own fault diagnosis: one verdict plus nine reasons.
#
# **`connection_status` is the verdict, and `2` means healthy** - it is not a
# boolean and `0` is not its good value. Decoded on 2026-08-15 by taking the
# data session down and reading the block in both states: `2` -> `8`, while
# `dialupswitch_off` went `0` -> `1` and `apnstatus` `0` -> `2`, correctly
# naming the cause. The other seven stayed `0`.
#
# **Only `2` and `8` have been observed**, which is why the check below is
# `!= "2"` rather than `== "8"`: `2` is confirmed good, so anything else is at
# minimum not-the-known-good value, whereas enumerating failure codes would be
# a guess about every code never seen.
DIAG_VERDICT_KEY = "connection_status"
DIAG_HEALTHY = "2"

# The nine reason fields, with the labels a user reads. `0` means nothing to
# report. **Only `dialupswitch_off` and `apnstatus` were observed changing**;
# the other seven labels are read from their field names and are the best
# available reading rather than a measured one.
DIAG_REASONS: dict[str, str] = {
    "signal_status": "Signal problem",
    "sim_status": "SIM problem",
    "dialupswitch_off": "Mobile data switched off",
    "datalimit_off": "Data limit reached",
    "roam_off": "Roaming disabled",
    "staticdns": "Static DNS problem",
    "apnstatus": "APN problem",
    "modemdialup_err": "Modem dial-up error",
    "speedLimitStatus": "Speed limited by the network",
}

# `device_information` is the one endpoint whose absence already raises, so it
# can never appear as "degraded" — the fetch fails outright instead.
CRITICAL_ENDPOINT = "device_information"

# Signal fields that a working `device_signal` response always carries at least
# one of. All of them absent while the block itself is non-empty is contract
# drift, not a weak signal — a firmware rename looks exactly like this.
SIGNAL_CONTRACT_KEYS: tuple[str, ...] = ("rsrp", "rsrq", "rssi", "sinr")

# Section 8: consecutive whole-fetch failures tolerated before entities are
# marked unavailable. Last known values are held until then.
FETCH_STRIKE_LIMIT = 3

# Section 19: consecutive polls a capability must be missing before Integration
# Health reports it degraded, so a single blip raises no alarm.
#
# Deliberately a second constant rather than a reuse of the one above. They
# happen to share a value and measure different things — one counts failed
# polls, the other counts a missing block across successful polls — so either
# could move without the other. `unifi_network_monitor` and `wifi_ssid_monitor`
# split them the same way and use these names; this project held a single
# `HEALTH_STRIKE_LIMIT` doing both jobs until 2026-08-17.
HEALTH_DRIFT_STRIKE_LIMIT = 3

# Seconds to wait before the follow-up refresh a disruptive button schedules.
#
# Both controls take the router away and bring it back, so the reading straight
# afterwards is stale by definition and the entities would sit wrong until the
# next scheduled poll - twenty minutes by default. These are measured, not
# guessed: a reconnect was back inside five seconds on the reference B535, and
# a reboot takes well under a minute to start answering again. Both carry
# headroom.
#
# Both fire even while polling is paused - the follow-up is part of the button
# press, not background polling (Section 13). Neither fires when it would land
# after the next scheduled poll anyway - see `async_schedule_refresh`.
# --- Network mode -----------------------------------------------------------
#
# Code to label for `net_mode.NetworkMode`. **One table, used by both the select
# and the Preferred Network Mode sensor.** They previously held separate copies
# of this mapping in two modules, and both were missing `08` — so a router in 5G
# Only reported `unknown` twice, from one cause.
#
# `08` is 5G Only, established 2026-08-16 on a live H165-383: the web interface
# offers exactly three modes, `net.net_mode_list()` returns exactly three codes
# (`00`, `08`, `03`), and `00`/`03` were already known. The router reported `08`
# while its interface showed 5G Only. **The code list is authoritative; the name
# is inference** — `AccessList` publishes codes without names.
#
# `huawei-lte-api`'s `NetworkModeEnum` is the origin of the other seven and has
# no 5G member at all: it predates 5G. Copying its vocabulary is what left a 5G
# integration unable to name the mode its own hardware was in. The library does
# not constrain us — `set_net_mode` takes `networkmode` as a plain `str` and
# passes it through unvalidated.
NETWORK_MODE_LABELS: dict[str, str] = {
    "00": "Auto",
    "01": "2G Only",
    "02": "3G Only",
    "0201": "3G/2G Auto",
    "03": "4G Only",
    "0301": "4G/2G Auto",
    "0302": "4G/3G Auto",
    "030201": "4G/3G/2G Auto",
    "08": "5G Only",
}

# Offered when `net.net_mode_list()` cannot be read. Deliberately the pre-2026-08
# hardcoded set plus `08`: a device that will not publish its own list is one we
# know nothing about, so widening the offer there would invite refused writes.
NETWORK_MODE_FALLBACK: tuple[str, ...] = (
    "00",
    "030201",
    "0302",
    "0301",
    "03",
    "0201",
    "02",
    "01",
    "08",
)


def network_mode_label(code: str | None) -> str | None:
    """Return a display label for a raw NetworkMode code.

    An unrecognized code is rendered `Unknown (nn)` rather than dropped, the
    same way `network_type` handles a code with no known name. That choice is
    the whole lesson of `08`: for months the router sat in a valid mode this
    integration could not name, and because the unmapped case returned `None`
    both entities read `unknown` — indistinguishable from a dead endpoint.
    """
    if code in (None, ""):
        return None
    text = str(code)
    return NETWORK_MODE_LABELS.get(text, f"Unknown ({text})")


# Seconds to wait after a network-mode write before re-reading it.
#
# The router applies the change, drops the radio and re-registers, answering
# abnormally throughout — including answering the write itself with
# `-1: Unknown`. Reading back before the radio settles reports the old mode and
# looks exactly like a refusal. Matches the settle time `hardware_check.py` has
# used for the reconnect path, which exercises the same re-registration.
NET_MODE_SETTLE = 15

RECONNECT_REFRESH_DELAY = 20
REBOOT_REFRESH_DELAY = 60

# --- Data-usage projection tuning (status_plan §T-2) -------------------------
#
# PROJECTION_CREDIBILITY_DAYS is the point at which this cycle's own usage rate
# and the previous cycle's are weighted equally. Three days is deliberate:
# usage is bursty, and a heavy weekend is not a new baseline, but waiting a
# fortnight would leave the projection lagging exactly when a user most wants
# warning that they are on course to exceed their allowance.
#
# It matters less than it looks. The blend applies only to the *unobserved*
# remainder of the cycle (see `helpers.project_cycle_usage`), so the prior's
# influence decays with the days left rather than with this constant.
#
# Ported from zte_router_5g, which established the values.
PROJECTION_CREDIBILITY_DAYS = 3.0

# Confidence bands published as an attribute on the projection, expressed as
# thresholds on the credibility weight. The projection is always shown — an
# `unknown` on day one reads as a broken sensor, whereas a number carrying
# "confidence: low" is understood. The caveat belongs in the attributes, not in
# the state.
PROJECTION_CONFIDENCE_LOW = 0.4
PROJECTION_CONFIDENCE_MEDIUM = 0.75

# The one action that removes entities rather than commanding the router.
# Defaults to a dry run: a client that is merely powered off is still usually
# in the router's host list, but a router that has aged it out is
# indistinguishable from one that never saw it, so removal is always explicit.
SERVICE_CLEANUP = "cleanup_unused_entities"
