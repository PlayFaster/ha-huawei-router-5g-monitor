"""Diagnostics support for Huawei Router 5G Monitor.

A diagnostics download must be safe to attach to a public issue **without the
user hand-editing it** (dev_standards Section 20).

**Key-name redaction alone is not enough, and this module used to be exactly
that**: a twenty-name `TO_REDACT` set handed to `async_redact_data`, with the
whole of `coordinator.data` poured through it. `async_redact_data` matches on
key name, so anything the firmware returned under a key not on that list was
published verbatim — and the list can never be complete, because new firmware
adds keys. The failure mode is silent and gets worse over time.

The precedent is exact: `unifi_network_monitor` held `diagnostics: done` across
**two full IQS scans** while leaking device MACs, user-assigned device names,
internal IPs, the subscriber's ISP and third-party SSIDs. Every gap sat next to
a correctly-redacted field, and reading the code is what produced both clean
verdicts.

This integration is more exposed than its siblings for two reasons that no
sibling shares:

* It has a **`device_tracker` platform**, so `lan_host_info` and
  `wlan_host_list` carry the MAC, hostname and IP of **every device on the
  user's network** — people who never consented to appear in a bug report.
* It has **SMS**, so the payload carries message bodies and sender numbers.

The approach is therefore layered, and applied **recursively** — Huawei's
payload is nested dicts and lists, not the flat map ZTE's shim was written for:

* **Blank** values with no referential role — credentials and subscriber
  identifiers.
* **Pseudonymize** values worth cross-referencing — IPs, MACs, hostnames, SSIDs
  and cell identifiers become stable tokens (`ip-1`, `mac-1`), so a maintainer
  can still see "these two fields refer to the same thing".
* **Summarize** free text — an SMS body is reduced to its length, which is what
  an SMS-handling bug actually turns on.
* **Sweep** every remaining string for anything IP- or MAC-shaped, as a
  structural backstop for keys this module does not enumerate. This is the part
  that survives a firmware update.

Everything diagnostically useful is deliberately preserved: model, firmware and
hardware version, every signal metric, band and channel, byte counters, uptime,
connection status and failure counts.

**Verified against a real download on 2026-08-14** — a live B535 capture, read
field by field. That audit found four leaks that reading this module had not,
and they are worth naming because they are the general shapes, not one-offs:

* **The same value under a second key name.** `Mccmnc` was published in full
  while `current_plmn.Numeric` — the identical operator code — was redacted
  beside it.
* **A key listed in the wrong case.** `spn` was on the carrier list; the router
  sends `Spn`. It was null in the capture, so the output looked clean.
* **One member of a class covered, its siblings not.** `cell_id` and `pci` were
  tokenized while `tac` and `scc_pci` went out whole.
* **Fields that are null on this router but not on others.** Every WiFi key
  field, `WifiWpapsk` included, was unlisted and empty. Null was a property of
  that firmware and auth level, not of the schema.

The first three were invisible to a code reading because each sat immediately
next to a correctly-handled field — the same shape as the `unifi` precedent
above. A capture from one router is evidence about one firmware; the shape
sweep, not this key list, is what covers the rest.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import HuaweiRouter5GDataUpdateCoordinator

REDACTED = "**REDACTED**"

# Values with no cross-reference worth preserving — blanked outright.
# Subscriber identifiers uniquely identify a person to their carrier.
TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "Password",
    "Username",
    "Imei",
    "Imsi",
    "Iccid",
    "SimIccid",
    "Msisdn",
    "SubscriberNumber",
    "Serial",
    "SerialNumber",
    # WiFi key material. Every one of these was null in the 2026-08-14 B535
    # capture, which is why a code reading passed them over — but null is a
    # property of that router's firmware and auth level, not of the schema.
    # `WifiWpapsk` is the WPA pre-shared key: the household's WiFi password.
    "WifiWpapsk",
    "MixWifiWpapsk",
    "WifiRadiusKey",
    "WifiWepKey1",
    "WifiWepKey2",
    "WifiWepKey3",
    "WifiWepKey4",
    "WifiWep128Key1",
    "WifiWep128Key2",
    "WifiWep128Key3",
    "WifiWep128Key4",
}

# Carrier and network-operator identity. Together with a cell id these place
# the subscriber geographically, and none of it helps diagnose a fault here.
#
# `Mccmnc` is the same value as `current_plmn.Numeric` reached by another key,
# and was published in full while `Numeric` beside it was redacted. `Spn` was
# listed as lowercase `spn`, which the router never sends — a silent miss.
CARRIER_KEYS = {"FullName", "ShortName", "Numeric", "Rat", "Spn", "spn", "Mccmnc"}

# Tokenized rather than blanked — seeing that two fields hold the same address
# is diagnostic, seeing the address itself is not.
IP_KEYS = {
    "WanIPAddress",
    "WanIPv6Address",
    "LanIPAddress",
    "IpAddress",
    "IPv4Address",
    "IPv6Address",
    "PrimaryDns",
    "SecondaryDns",
    "PrimaryIpv6Dns",
    "SecondaryIpv6Dns",
}
MAC_KEYS = {
    "mac",
    "MacAddress",
    "MacAddress1",
    "MacAddress2",
    "WanMacAddress",
    "wan_mac_address",
    "WifiMac",
    "BSSID",
}
# A user-assigned device name is often a person's name ("Sam's iPhone"), and an
# SSID identifies a household and frequently its neighbors too.
NAME_KEYS = {"HostName", "DeviceNameFromHost", "ActualName"}
SSID_KEYS = {"Ssid", "WifiSsid", "AssociatedSsid", "SsidName"}
# Cell, area and neighbor identifiers. A serving cell id plus a tracking area
# plus an operator resolves to a mast in open databases, so these are treated
# as one class regardless of radio technology.
#
# The last six were added after the 2026-08-14 B535 capture. `tac` and
# `scc_pci` were published in full alongside the four already listed, and `sc`
# was covered only under the name `sc_cellid`, which the router never sends.
# The 3G and GSM entries (`sc`, `rac`, `lac`, `bsic`) were null on an LTE/NR
# attach and would have appeared on a fallback network.
CELL_KEYS = {
    "cell_id",
    "enodeb_id",
    "pci",
    "sc_cellid",
    "nrcellid",
    "plmn",
    "tac",
    "lac",
    "rac",
    "sc",
    "bsic",
    "scc_pci",
    "nei_cellid",
}

# Third-party content: an SMS is data about someone who never consented to
# appear in a bug report.
TEXT_KEYS = {"content", "Content", "message"}
PHONE_KEYS = {"phone", "Phone", "SmsNumber", "Number", "target"}

# Keys whose values are known never to be addresses, and which the shape sweep
# would otherwise corrupt. Both entries below were found by test, not by
# reasoning — a first-draft sweep rewrote `11.0.1.1(H192SP1C983)` as
# `ip-1(H192SP1C983)` and `2026-08-09 10:00:00` as `2026-08-09 ip6-1`.
#
# The rules were narrowed as well (see the regexes), but a firmware version
# that happens to be four dotted numbers is genuinely indistinguishable from an
# IPv4 address by shape alone. Where the ambiguity is real, naming the key is
# the honest fix — an invented pattern that "usually" tells them apart would
# silently corrupt some other router's version string instead.
NEVER_SWEPT_KEYS = {
    "SoftwareVersion",
    "HardwareVersion",
    "WebUIVersion",
    "iniversion",
    "Date",
    "date",
    "DeviceName",
    # The same two versions again, under the names `ConfigEntry.data` stores
    # them (Section 2's Flat Identity pattern). The router's spellings were
    # listed when the four-part-version false positive was first found in
    # Phase 2a; the entry's were not, and `11.0.1.1` was being published as
    # `ip-1` in every download since. Found by a test written for a mutation
    # finding, not by review — the third time on this module that a key was
    # covered under one spelling and missed under another.
    "sw_version",
    "hw_version",
}

# Each octet bounded to 0-255, and not adjacent to a word character, `.` or `(`
# — so a dotted version string carrying a suffix is not mistaken for an address.
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
_IPV4_RE = re.compile(
    rf"(?<![\w.])(?:{_OCTET}\.){{3}}{_OCTET}(?![\w.(])",
)
_MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
# Requires either a `::` elision or the full eight-group form. Anything looser
# matches a `HH:MM:SS` timestamp, which has three hex-looking colon groups.
_IPV6_RE = re.compile(
    r"\b(?:[0-9A-Fa-f]{1,4}:){1,7}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4})*)?"
    r"|\b(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}\b"
)


class _Tokenizer:
    """Assigns stable pseudonyms to identifier values.

    Section 20: twenty identical `**REDACTED**` strings destroy the file's
    usefulness; twenty stable tokens preserve it. The same input always yields
    the same token *within one download*, and tokens are allocated in
    first-seen order, so nothing about the real value survives.
    """

    def __init__(self) -> None:
        """Initialize an empty token map."""
        self._tokens: dict[tuple[str, str], str] = {}
        self._counts: dict[str, int] = {}

    def token(self, prefix: str, value: str) -> str:
        """Return a stable token for this value under this prefix."""
        key = (prefix, value)
        if key not in self._tokens:
            self._counts[prefix] = self._counts.get(prefix, 0) + 1
            self._tokens[key] = f"{prefix}-{self._counts[prefix]}"
        return self._tokens[key]


def _sweep(value: str, tokenizer: _Tokenizer) -> str:
    """Replace anything address-shaped anywhere in a string.

    The structural backstop for keys this module does not enumerate — which is
    every key a future firmware invents. Matched on **shape only**, never
    against a list of real values: that would put PII in the source tree and
    would not work for anybody else's router.

    MACs are swept before IPv6 because the two shapes overlap.
    """
    value = _MAC_RE.sub(lambda m: tokenizer.token("mac", m.group(0)), value)
    value = _IPV4_RE.sub(lambda m: tokenizer.token("ip", m.group(0)), value)
    return _IPV6_RE.sub(lambda m: tokenizer.token("ip6", m.group(0)), value)


def _sanitize(value: Any, tokenizer: _Tokenizer, key: str = "") -> Any:
    """Recursively sanitize a payload node.

    Recursion is the point. The previous implementation flattened nothing and
    matched nothing below the top level, so `lan_host_info → Hosts → Host → […]`
    — the list holding every client's MAC, hostname and IP — passed through
    untouched.
    """
    if isinstance(value, dict):
        return {k: _sanitize(v, tokenizer, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v, tokenizer, key) for v in value]

    if key in TO_REDACT or key in CARRIER_KEYS:
        return REDACTED if value not in (None, "") else value

    if not isinstance(value, str) or not value:
        return value

    if key in TEXT_KEYS:
        return f"<{key}: {len(value)} chars>"
    if key in PHONE_KEYS:
        return tokenizer.token("phone", value)
    if key in IP_KEYS:
        # Huawei returns several addresses in one field, semicolon-separated.
        return ";".join(
            tokenizer.token("ip", part.strip()) if part.strip() else part
            for part in value.split(";")
        )
    if key in MAC_KEYS:
        return tokenizer.token("mac", value)
    if key in NAME_KEYS:
        return tokenizer.token("name", value)
    if key in SSID_KEYS:
        return tokenizer.token("ssid", value)
    if key in CELL_KEYS:
        return tokenizer.token("cell", value)
    if key in NEVER_SWEPT_KEYS:
        return value

    return _sweep(value, tokenizer)


def _sanitize_rejection(
    rejection: dict[str, Any] | None, tokenizer: _Tokenizer
) -> dict[str, Any] | None:
    """Sanitize a retained rejection, payload included.

    The verdict, the router's error code and the endpoint name are names and
    codes only and pass through untouched; the payload is walked exactly as
    `coordinator.data` is.

    Mirrors `zte_router_5g._sanitize_rejection`. That project also sweeps a
    `body_preview`, which has no counterpart here: `huaweiapi` parses the
    response and this integration never sees a raw body, so there is no
    unparsable verdict to carry one.
    """
    # `isinstance`, not truthiness: diagnostics must survive a coordinator
    # whose api is a stand-in, and must never put a non-serializable object
    # into a file the user is about to attach to an issue.
    if not isinstance(rejection, dict):
        return None
    out = deepcopy(rejection)
    if "payload" in out:
        out["payload"] = _sanitize(out["payload"], tokenizer)
    return out


def _entity_resolution(payload: dict[str, Any]) -> dict[str, Any]:
    """Report which entity descriptions this payload populates, and which it does not.

    **This is the question a support case actually asks.** A reporter with an
    unfamiliar Huawei router says half their entities read `unknown`; the
    payload above says what the router sent, and the entity list says what this
    integration offers, but matching one against the other is manual work over
    a hundred-odd descriptions. This does that matching in the file.

    Three outcomes, and they are different findings:

    - **`resolved`** — the description produced a value from this payload.
    - **`no_value`** — it produced `None`. The firmware does not report what
      that entity reads, and its entity will be `unknown` on this device. This
      is the list a supporter wants.
    - **`raised`** — the description's own `value_fn` threw against this
      payload. That is a defect in **this integration**, not in the firmware,
      and it is invisible today: the entity simply shows nothing.

    Covers the description-driven platforms only. Switches, buttons, numbers
    and selects derive their state from entity properties and write paths
    rather than from a payload function, so there is nothing here to evaluate
    for them and a stub row would imply otherwise.

    **Evaluated against the raw payload, deliberately.** Sanitizing first would
    change what the descriptions see — a tokenized address is still a value, but
    a redacted one is not — and the answer must be what the entity would really
    produce. Nothing leaks by doing so: only description keys and counts are
    recorded, never a value.
    """
    # Imported here rather than at module scope: `diagnostics` is loaded on
    # demand for a download, and pulling in every platform module at import
    # time would make a rarely-used path a startup cost.
    from .binary_sensor import VALUE_BINARY_SENSORS
    from .sensor import SENSOR_TYPES

    tables: tuple[tuple[str, Any], ...] = (
        ("sensor", SENSOR_TYPES),
        ("binary_sensor", VALUE_BINARY_SENSORS),
    )

    out: dict[str, Any] = {}
    for platform, descriptions in tables:
        resolved: list[str] = []
        no_value: list[str] = []
        raised: dict[str, str] = {}
        for description in descriptions:
            try:
                value = description.value_fn(payload)
            except Exception as err:  # noqa: BLE001 - see `raised` above
                # A description that throws is the finding. Naming the type
                # would suppress every other kind, and the whole point is that
                # nobody knows what unfamiliar firmware provokes.
                raised[description.key] = type(err).__name__
                continue
            (resolved if value is not None else no_value).append(description.key)

        out[platform] = {
            "total": len(resolved) + len(no_value) + len(raised),
            "resolved": len(resolved),
            "no_value": sorted(no_value),
            "raised": raised,
        }
    return out


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[HuaweiRouter5GDataUpdateCoordinator]
) -> dict[str, Any]:
    """Return sanitized diagnostics for a config entry."""
    coordinator = entry.runtime_data
    tokenizer = _Tokenizer()

    # deepcopy first — diagnostics is a read path and must never mutate the
    # live coordinator payload the entities are serving from (Section 20).
    raw = deepcopy(coordinator.data) if coordinator.data else {}

    # Probed here rather than inside the mapping below, because it is the one
    # part of this document that talks to the router. A failure sweeping the
    # probes must not cost the reporter the rest of the file.
    try:
        probes = await coordinator.api.probe_diagnostic_endpoints()
    except Exception as err:  # noqa: BLE001 - the download outranks the probe
        probes = {"error": type(err).__name__}

    return {
        "entry": {
            "title": entry.title,
            "data": _sanitize(deepcopy(dict(entry.data)), tokenizer),
            "options": _sanitize(deepcopy(dict(entry.options)), tokenizer),
        },
        "coordinator": {
            "consecutive_failures": coordinator.consecutive_failures,
            "last_update_success": coordinator.last_update_success,
            "last_update_success_time": (
                coordinator.last_update_success_time.isoformat()
                if coordinator.last_update_success_time
                else None
            ),
            "data_available": coordinator.data is not None,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        # The three boot-time latches and the counter-drift picture behind
        # them. Nothing here is device data and nothing needs redacting:
        # counters, rates and timestamps. It is in the download because the
        # constants in the latch were set from a single device, and a report
        # that carries no rate leaves a recorder extraction as the only route
        # to one.
        "uptime": coordinator.uptime_state,
        "data": _sanitize(raw, tokenizer),
        # `data` is empty until the first successful poll, which is exactly
        # the case this file is usually requested for. These two carry the
        # evidence that would otherwise be reachable only from raw logs.
        #
        # The rejected payload goes through the same walker as `data`, so it
        # is no more revealing than an accepted one. `login` carries an
        # outcome only and never a credential — see
        # `api.HuaweiRouter5GAPI._record_login_metadata`.
        "last_rejection": _sanitize_rejection(
            coordinator.api.last_rejection, tokenizer
        ),
        "login": (
            deepcopy(coordinator.api.login_metadata)
            if isinstance(coordinator.api.login_metadata, dict)
            else {}
        ),
        # What each endpoint of the most recent poll did. Names, outcomes and
        # the router's own codes — no values, so nothing here needs sanitizing
        # beyond the guard that it is a mapping at all.
        #
        # This is what makes an absence readable. Without it, an endpoint
        # missing from `data` above could have been refused, skipped at the
        # fetch deadline, or failed in a handler that logs and continues, and
        # a reader could not tell which — which is the whole question when the
        # download comes from a router nobody here has seen.
        # Endpoints this integration does not poll, called once for this
        # download. An entry reading `refused` with a code is the router
        # stating it does not serve that endpoint; `answered` with key names
        # is a capability this device has and the integration does not read.
        # Names and counts only — see `api.probe_diagnostic_endpoints`.
        "probes": probes,
        # How the refusal-or-expiry question was settled on this router
        # (dev16 plan I1): whether it refuses `device_information` without a
        # login, which is what lets a 100003 from an optional endpoint be read as
        # a refusal and not as an expired session. Outcome and code only, never
        # the payload. `not_made` means no endpoint has drawn a session signal
        # since the integration started, so the question never arose.
        "premise": (
            deepcopy(coordinator.api.premise_result)
            if isinstance(coordinator.api.premise_result, dict)
            else {"outcome": "not_made", "code": None}
        ),
        # Sessions the probe sweep found lost and replaced. Zero where none was,
        # which says the probe outcomes above were read on one live session.
        "probe_sessions_lost": (
            coordinator.api.sweep_sessions_lost
            if isinstance(coordinator.api.sweep_sessions_lost, int)
            else 0
        ),
        # Which of this integration's entity descriptions the payload above
        # populates. The endpoint map says what the router served; this says
        # what that means for the entities a reporter is looking at.
        "entity_resolution": _entity_resolution(raw),
        "endpoints": (
            deepcopy(coordinator.api.endpoint_outcomes)
            if isinstance(coordinator.api.endpoint_outcomes, dict)
            else {}
        ),
    }
