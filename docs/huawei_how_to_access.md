<!-- markdownlint-disable MD033 -->

# Huawei Router Access Reference 🔗

This document details how this integration reaches the Huawei HiLink API — which endpoints exist, which are polled, which are readable but unused, which the hardware refuses, and what the data behind each is actually worth as a Home Assistant entity.

Everything below was measured against a live **B535 / H165-383**, firmware `4.4.0.1(H1600SP2C1632)`, on 2026-08-14 and 2026-08-15. Values quoted are real readings. Where a conclusion rests on an assumption rather than an observation, that is said.

---

## 📐 The shape of this API — read this first

The three sibling projects reach their devices in three different ways, and the difference decides how each of these documents is organised:

| Project | Interface | Document organised by |
| :-- | :-- | :-- |
| `unifi_network_monitor` | REST, one URL per resource | URL |
| `zte_router_5g` | Two `goform` endpoints, resource named in a `cmd=` parameter | `cmd` / `goformId` name |
| **`huawei_router_5g`** | **A third-party library over a documented-by-reverse-engineering XML API** | **Library endpoint** |

**This integration does not speak HTTP to the router at all.** Every call goes through [`huawei-lte-api`](https://pypi.org/project/huawei-lte-api/), pinned at **1.11.0**, which owns the URL construction, the XML parsing, the CSRF token handling and the session cookie. So the unit that corresponds to "an endpoint" here is **a library method** — `client.monitoring.status()`, `client.device.signal()` — and this document is organised that way.

Three consequences worth knowing before debugging:

- **You cannot fix a URL problem in this codebase.** If the library builds a request wrongly, the fix is a library version bump, not a patch here. This is why `tests/test_library_contract.py` exists — it checks every method this integration calls against the installed package, so a rename surfaces as a red suite rather than a runtime `AttributeError`.
- **A method existing in the library says nothing about the hardware supporting it.** The library covers the whole Huawei HiLink family. This model refuses a third of it. See [Not supported on this hardware](#-not-supported-on-this-hardware).
- **The library is synchronous.** Every call is wrapped in `asyncio.to_thread` in `api.py`. This is also why the IQS `async-dependency` and `inject-websession` rules sit at `todo` — there is no async interface to adopt and no `aiohttp` session to inject.

Base URL is normalised by `_normalize_router_url` in `api.py`; a bare host such as `192.168.8.1` gains `http://`, because the library's `Connection` rejects a schemeless URL outright.

---

## 🔧 Authentication

### One login, and most reads do not need it

The router accepts a single username and password — **there is no separate `admin` account or elevated tier**. `Connection(url, username=..., password=...)` logs in during construction; passing `username=None` produces an **anonymous** session, which is what this integration does today, because the config entry stores an empty username.

**Anonymous is enough for everything the integration polls.** Device information, signal, monitoring, traffic, SMS, connected clients and WiFi settings all answer without credentials on this firmware.

Roughly **90 of the library's ~240 read methods answer `100003: No rights (needs login)`** — the configuration surface: WiFi security settings, MAC filters, VPN, USB storage, voice/SIP account details, firmware update controls. Supplying the stored password as `admin` was tested and made **no difference to any of them**, so they are not a credential problem — they need a session this API grants differently, or the model does not permit them at all.

### Error codes worth recognising

| Code | Meaning | What to do |
| :-- | :-- | :-- |
| `100002: No support` | The hardware or firmware does not implement it | Nothing. Do not retry, do not add a sensor |
| `100003: No rights (needs login)` | Requires a session this connection does not have | Not a bug to fix in this integration |
| `108003` / `108006` | Wrong username / password | Surfaces as `HuaweiAuthError` → `ConfigEntryAuthFailed` → reauth flow |

### Logout — the failure that hid for a whole release line

`api.py` calls **`client.user.logout()`**. It previously called `Connection.logout()`, **a method that has never existed in this library**, hidden behind a `# type: ignore[attr-defined]`. Every unload and every reload leaked a session, silently, because a failed logout is deliberately swallowed — an unload must not be blocked by it.

**The lesson generalises:** a `type: ignore[attr-defined]` on a library call is a *claim about that library*, and this project made that claim falsely twice. `tests/test_entity_hygiene.py` now sweeps every suppression against a reviewed allow-list for exactly this reason.

### The session degrades under sustained bulk querying

**Measured 2026-08-15, and it will mislead anyone who tries to inventory this API by brute force.** A sweep calling ~240 read methods back to back returns `100003: No rights` for endpoints that demonstrably work — `wlan.multi_basic_settings` and `wlan.host_list` both failed in the sweep and both succeeded immediately afterwards on a fresh connection, and both are polled successfully in production every cycle.

So: **probe endpoints in small batches, and re-verify any negative result on a fresh session before believing it.** A single `100003` in a long run is not evidence.

---

## 📥 What the integration polls today

Fifteen read endpoints per cycle, all in `api.py::get_data`, merged into one flat dictionary keyed by block name.

| Endpoint | Block key | Feeds |
| :-- | :-- | :-- |
| `device.information` | `device_information` | Model, firmware, hardware, WAN IP, DNS, uptime |
| `device.signal` | `device_signal` | 55 keys — RSRP/RSRQ/SINR/RSSI, LTE and NR, bands, cell IDs |
| `monitoring.status` | `monitoring_status` | Connection status, network type, roaming, WiFi user counts |
| `monitoring.traffic_statistics` | `traffic_statistics` | Session and lifetime byte counters, current rates |
| `monitoring.month_statistics` | `month_statistics` | Monthly and daily usage, durations |
| `monitoring.check_notifications` | `monitoring_check_notifications` | Unread SMS, update status |
| `net.current_plmn` | `current_plmn` | Operator name and numeric |
| `net.net_mode` | `net_mode` | Preferred network mode and band masks |
| `dial_up.mobile_dataswitch` | `mobile_dataswitch` | Mobile data on/off |
| `sms.sms_count` | `sms_count` | Inbox/outbox/unread counts |
| `sms.get_sms_list` | `sms_list` | Message list |
| `lan.host_info` | `lan_host_info` | Connected clients — **the `device_tracker` source** |
| `wlan.host_list` | `wlan_host_list` | WiFi clients |
| `wlan.multi_basic_settings` | `wlan_multi_basic_settings` | SSIDs, guest network state |
| `wlan.wifi_feature_switch` | `wlan_wifi_feature_switch` | 49 WiFi capability flags |

`lan_host_info` and `wlan_host_list` carry the MAC, hostname and IP of every device on the user's network. That is a privacy surface no sibling project has, and it is why `diagnostics.py` recurses and pseudonymises rather than redacting by key name.

---

## 📤 Writes

Eight, all serialised behind one `asyncio.Lock` and routed through `_execute_with_retry`.

| Endpoint | Action | Register tier |
| :-- | :-- | :-- |
| `user.logout` | End the session | SAFE |
| `device.set_control(REBOOT)` | Reboot | ATTENDED |
| `monitoring.set_clear_traffic` | Zero the byte counters | ATTENDED |
| `dial_up.set_mobile_dataswitch` | Mobile data on/off | ATTENDED |
| `net.set_net_mode` | Preferred network mode | ATTENDED |
| `wlan._session.post_set` | Guest WiFi on/off | ATTENDED |
| `sms.send_sms` | Send a message | ATTENDED |
| `sms.delete_sms` | Delete a message | ATTENDED |

Every one is classified in `scripts/write_classification.py`; `tests/test_write_classification.py` fails on an unclassified write.

### Two spellings that matter

**`device.set_control(ControlModeEnum.REBOOT)`, not `device.reboot()`.** Both exist in 1.11.0, but **2.0.0 removes `reboot()` and `control()`** and keeps only `set_control`. The current spelling is correct on both, so the library bump needs no change here.

**`monitoring.set_clear_traffic()`, not `Monitoring.clear_traffic()`.** The latter has never existed. The Clear Traffic button could not have worked in any release; its test asserted the wrong name against a bare `MagicMock`, so nothing caught it.

### Guest WiFi deliberately bypasses the public setter

`set_guest_wifi` posts to `wlan/multi-basic-settings` through `client.wlan._session.post_set` under a reasoned `# noqa: SLF001`, **not** through `client.wlan.set_multi_basic_settings()`.

The public setter builds its own payload — `{'Ssids': {...}, 'WifiRestart': 1}` — and **discards every other top-level key**. Probed on a live B535, `multi_basic_settings()` returns `Ssids`, `DbhoEnable` and `modify_guest_ssid`, so the public setter would silently drop band-steering and guest-SSID state on every toggle. Full reasoning in `docs/DEVELOPMENT.md`.

---

## 🔍 Readable, not polled

Confirmed working on this hardware and **not** currently fetched. Verdicts are from the field review recorded in `.notes/info/extra_fields/`.

### Agreed for adoption

| Endpoint | Keys of interest | Live value | Why |
| :-- | :-- | :-- | :-- |
| `monitoring.start_date` | `StartDay`, `trafficmaxlimit`, `MonthThreshold`, `SetMonthData` | `1`, `2147483648000`, `80`, `1` | **The data-plan block.** Cycle day and allowance — the inputs a usage projection needs |
| `dial_up.profiles` | `CurrentProfile`, `Profiles.Profile[]` | `3`, three APNs | APN name and profile |
| `device.antenna_type` | `antenna1type`, `antenna2type` | `0` / `0` | `0` = Internal, `1` = External |
| `net.csps_state` | `psstate`, `csstate` | `1`, `1` | Data and voice network registration |
| `monitoring.converged_status` | `CountryCode`, `SimLockEnable` | `IE`, `0` | Country, SIM PIN lock |
| `dial_up.connection` | `MTU`, `RoamAutoConnectEnable` | `1500`, `1` | MTU diagnosis; roaming auto-connect |
| `security.sip` | `SipStatus` | `1` | SIP ALG — the classic cause of one-way VoIP audio |
| `security.upnp` | `UpnpStatus` | `0` | UPnP on/off |

### Readable, reviewed, not adopted

| Endpoint | Returns | Why not |
| :-- | :-- | :-- |
| `device.boot_time` | `04:48:35` | **Duplicate of `device_information.uptime`.** Read together they matched exactly (17,315 s); this is the same figure formatted `HH:MM:SS` |
| `wlan.wlandbho` | `DbhoEnable`, `MloEnable` | Band steering and Wi-Fi 7 MLO. Both are *settings the owner set*, not state — and `DbhoEnable` already arrives in `wlan_multi_basic_settings` |
| `net.cell_info` | `cellinfo`, `lac` | `cell_id` and `pci` are already exposed from `device_signal` |
| `s_ntp.timeinfo` | Timezone, sync status, servers | Router clock. Nothing acts on it |
| `dhcp.settings` | DHCP range, lease, `homerouter.cpe` | Static configuration, not state |
| `device.device_feature_switch` | `onekeydiag_enabled` etc. | Capability flags. Matters as a **precondition check**, not as a sensor |
| `net.net_feature_switch` | 9 capability flags | Same |
| `wlan.wifi_feature_switch` | 49 keys, 47 unread | Polled, but almost entirely firmware **capability** flags rather than state |
| `config_statistic.config` | 60+ keys | A firmware config template — dated `2012`, values are defaults. Mirrors `start_date` but is not live state |

### Readable, never reviewed

Found by the endpoint sweep and **not** assessed. Recorded so the next person starts here rather than re-running the probe.

| Endpoint | Keys | Note |
| :-- | :-- | :-- |
| `global_.module_switch` | 94 | The largest capability block on the device |
| `security.get_firewall_switch` | 11 | Firewall toggles |
| `security.nat`, `.dmz`, `.virtual_servers`, `.mac_filter`, `.url_filter` | 1–3 each | Firewall and forwarding configuration |
| `diagnosis.diagnose_ping`, `.diagnose_traceroute` | 11, 6 | **The router will run a ping or traceroute on request.** Interesting and unexplored |
| `diagnosis.time_reboot` | 4 | **Scheduled reboot, and it is ENABLED on the reference unit.** `enable='1'`, `dayinterval='7'`, `begintime='60'`, `endtime='300'` — a reboot every 7 days in a window that reads as 01:00–05:00 if the times are minutes past midnight, which is **inference from the values fitting, not measurement**. Worth knowing even if never exposed: it explains a weekly uptime reset, and it interacts with reboot detection. `zte_router_5g` exposes an equivalent |
| `online_update.status`, `.configuration`, `.autoupdate_config` | 8, 4, 2 | Firmware update state — may decode `monitoring_status.OnlineUpdateStatus`, which was rejected as an unknown code |
| `system.deviceinfoex` | 14 | Extended device information |
| `sms.config` | 16 | SMS behaviour settings |
| `net.net_mode_list` | 3 | The modes this device will accept — could validate the Network Mode select |
| `led.appctrlled` | 3 | LED control |
| `redirection.homepage`, `staticroute.wanpath`, `dhcp.static_addr_info` | 1–2 | Minor configuration |

---

## ❌ Not supported on this hardware

Returned `100002: No support`. **Do not add, do not retry.**

`monitoring.daily_data_limit` · `monitoring.month_statistics_wlan` · `wlan.station_information` · `wlan.basic_settings` · `ntwk.celllock` · `system.deviceinfo` · `statistic.feature_roam_statistic` · `user.remember_pwd`

`wlan.station_information` is the notable loss — it would give per-client WiFi signal strength, which nothing else provides.

---

## 🔤 Field formats and traps

**`DataLimit` is a display string, `trafficmaxlimit` is bytes.** `'2000GB'` needs parsing and carries a GB/GiB ambiguity; `2147483648000` is the same figure as an integer (2000 × 1024³). **Use `trafficmaxlimit`.**

**The router's statistics page is GiB, not GB.** The GUI's "156.96 GB" is `CurrentMonthDownload + CurrentMonthUpload` divided by 1024³, matching to the byte. Its "GB" and "TB" labels mean GiB and TiB throughout.

**`MonthDuration` counts from the billing cycle start, not from the last manual clear.** Measured 1,202,664 s = 13.92 days against a `StartDay` of 1, on 14 August. `MonthLastClearTime` (`2026-04-18`) is the *manual counter reset* and is unrelated — four months of separation between the two is what proves they measure different things.

**`workmode` reports the LTE anchor, not the aggregate.** It reads `LTE` while `EndcStatus=1` and `SignalIconNr=5` show the modem is attached to 5G NSA. Do not present it as "current network type".

**`device_signal.band` is the full carrier aggregation; `bandInfo` is only the primary.** `band` returns `20MHz@500(B1) + 15MHz@1875(B3) + ...` while `bandInfo` returns `B1`. Two sensors showing these side by side read as a contradiction unless one explains itself.

**`dial_up.profiles` returns profiles out of order.** The list came back indexed 1, 3, 2. Resolve `CurrentProfile` by matching the `Index` field, never by list position.

**`ImeiSvn` is the IMEI Software Version Number**, a two-digit manufacturer revision counter (`01`). There is no public table to decode it further, and `SoftwareVersion` already says the same thing readably.

**Identifiers are digits that are not quantities.** `Imei`, `Imsi`, `Iccid`, `Msisdn`, `SerialNumber`, `Mccmnc`, `scc_pci` must carry no `state_class`, no `device_class`, no unit and no display precision — set any of them and Home Assistant coerces the value, turning `01` into `1` and a 15-digit IMEI into scientific notation.

**Several status fields are undecodable codes.** `SimState=257`, `CurrentNetworkTypeEx=1011`, `CurrentServiceDomain=3`, `OnlineUpdateStatus=14`, `cellroam=2`. The library ships enums only for `NetworkMode`, `NetworkBand`, SMS box types and `SaveMode` — nothing covers these, and Huawei publishes no specification. **Prefer a typed endpoint over guessing**: `net.csps_state` supersedes `CurrentServiceDomain`, and `converged_status.SimLockEnable` supersedes `simlockStatus`.

---

## 🆕 What 2.0.1 added, and what a proper scan found

**Method: a full surface diff, not a probe.** 1.11.0 was unpacked alongside 2.0.1 and both enumerated — every group, every method signature, every enum member, every exception. That is the only way to answer "what is new" without guessing, and it is what the earlier field-level scans could not do.

**The surface barely moved.** 70 groups and 336 methods → 70 groups and 340 methods. No new groups, no enum changes, no exception changes. Most signature diffs are `Dict[str, Any]` → `dict[str, Any]` typing modernisation.

### Six methods added

| Method | Live value | Worth |
| :-- | :-- | :-- |
| **`monitoring.onekey_diag()`** | Ten fields — `connection_status`, `signal_status`, `sim_status`, `dialupswitch_off`, `datalimit_off`, `roam_off`, `staticdns`, `apnstatus`, `modemdialup_err`, `speedLimitStatus` | **The router's own self-diagnosis.** This is `status_plan` §S-6's target, and it now exists |
| **`voice.volte()`** | `volte_enable='1'`, `ui_display_ims='1'` | Real VoLTE state, which the SIP ALG flag is not |
| `wlan.guesttime_setting()` | `isvalidtime='1'`, `remaintime='0'`, `extendtime='30'` | Guest-WiFi time limit |
| `security.acl()` | `https_enable='1'`, `icmp_enable='0'`, `acs_enable='0'` | Remote-management access control |
| `user.rule()` | Password-length and complexity policy | Low |
| `diagnosis.wan_service_name()` | `'INTERNET'` | Low |

`onekey_diag`'s `speedLimitStatus` reads `0`, matching `monitoring_status.speedLimitStatus` — the two blocks cross-validate.

### Two methods removed — and both were already handled

`device.control` and `device.reboot` are gone. This integration calls `device.set_control(ControlModeEnum.REBOOT)`, chosen in `[1.1.3-dev10]` precisely because it survives 2.0.0. **No change was needed.**

### A correction the scan forced: the voice group IS readable

An earlier pass concluded there was "no registration status, no call state, no line status — nothing that changes when a call happens". **That was wrong**, and it came from the bulk sweep that had corrupted its own session. Re-probed in small batches on fresh connections:

| Method | Live value |
| :-- | :-- |
| **`voice.voicebusy()`** | **`Idle`** — the line state. It is exactly the live call state the earlier pass said did not exist |
| `voice.sipaccount()` | SIP proxy and register server addresses, **plus an account password field** |
| `voice.sipserver()` | Server profile, IP type, secondary server |
| `voice.voiperstatus()` | `voiper_enable='1'` |
| `voice.voiceadvance()` | `dtmfmethod='InBand'`, `EchoCancellationEnable='1'` |
| `voice.featureswitch()`, `.functioncode()`, `.speeddial()` | Readable; thin or empty here |

Only `voice.codec()` refuses.

> [!WARNING]
>
> **`voice.sipaccount()` returns a password.** If it is ever added to the fetch set, the key must go into `diagnostics.py`'s `TO_REDACT` in the same change — the diagnostics download dumps `coordinator.data` wholesale.

**The method lesson, since this is the second time it has bitten.** Probe in **small batches on fresh sessions** and re-verify every negative. A single bulk sweep of this API produces false `100003` results that read exactly like a genuine permission boundary, and both the "no VoIP state" and the "`wlan.multi_basic_settings` needs login" conclusions came from one.

### Still unmeasured

`online_update.status()` returns `CurrentComponentStatus='14'` — the same `14` that `monitoring_status.OnlineUpdateStatus` reports and that was rejected as an undecodable code. It now has a context that might decode it; not pursued.

---

## 📚 Related documents

- `ha-zte-router-5g-monitor/docs/zte_how_to_access.md` — the ZTE companion, organised by `cmd` name because that interface is two endpoints with a parameter.
- `ha-unifi-network-monitor/docs/api_endpoints.md` — the UniFi companion, organised by URL.
- `.notes/info/extra_fields/extra_fields_decide_202608.md` — the field-by-field review this document's verdicts are drawn from, with sub-device, category and default decisions.
- `.notes/info/extra_fields/extra_fields_202608.md` — the raw working notes and evidence trail behind it.
- `docs/all_sensors.md` — which entity each polled field becomes.
- `docs/DEVELOPMENT.md` — architecture, and the reasoning behind the guest-WiFi write path.
- `docs/ha_compatibility.md` — Home Assistant deprecations this integration absorbs.
