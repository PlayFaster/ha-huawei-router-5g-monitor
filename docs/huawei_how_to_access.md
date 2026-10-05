<!-- markdownlint-disable MD033 -->

# Huawei Router Access Reference 🔗

This document details how this integration reaches the Huawei HiLink API — which endpoints exist, which are polled, which are readable but unused, which the hardware refuses, and what the data behind each is actually worth as a Home Assistant entity.

Everything below was measured against a live **B535 / H165-383**, firmware `4.4.0.1(H1600SP2C1632)`, on 2026-08-14 and 2026-08-15. Values quoted are real readings. Where a conclusion rests on an assumption rather than an observation, that is said.

---

## 📐 The shape of this API — read this first

The three sibling projects reach their devices in three different ways, and the difference decides how each of these documents is organized:

| Project | Interface | Document organized by |
| :-- | :-- | :-- |
| `unifi_network_monitor` | REST, one URL per resource | URL |
| `zte_router_5g` | Two `goform` endpoints, resource named in a `cmd=` parameter | `cmd` / `goformId` name |
| **`huawei_router_5g`** | **A third-party library over a documented-by-reverse-engineering XML API** | **Library endpoint** |

**This integration does not speak HTTP to the router at all.** Every call goes through [`huawei-lte-api`](https://pypi.org/project/huawei-lte-api/), pinned at **2.0.1** in `manifest.json`, which owns the URL construction, the XML parsing, the CSRF token handling and the session cookie. So the unit that corresponds to "an endpoint" here is **a library method** — `client.monitoring.status()`, `client.device.signal()` — and this document is organized that way.

Three consequences worth knowing before debugging:

- **You cannot fix a URL problem in this codebase.** If the library builds a request wrongly, the fix is a library version bump, not a patch here. This is why `tests/test_library_contract.py` exists — it checks every method this integration calls against the installed package, so a rename surfaces as a red suite rather than a runtime `AttributeError`.
- **A method existing in the library says nothing about the hardware supporting it.** The library covers the whole Huawei HiLink family. This model refuses a third of it. See [Not supported on this hardware](#-not-supported-on-this-hardware).
- **The library is synchronous.** Every call is wrapped in `asyncio.to_thread` in `api.py`. This is also why the IQS `async-dependency` and `inject-websession` rules sit at `todo` — there is no async interface to adopt and no `aiohttp` session to inject.

Base URL is normalized by `_normalize_router_url` in `api.py`; a bare host such as `192.168.8.1` gains `http://`, because the library's `Connection` rejects a schemeless URL outright.

---

## 🔧 Authentication

### One login — and it is required

The router accepts a single username and password — **there is no separate `admin` account or elevated tier.** One credential is the whole authentication model; the evidence for that is at the end of this section.

`Connection(url, username=..., password=...)` logs in during construction. The config entry stores an **empty username with a real password**, and the library authenticates on the password alone — so this is an **authenticated session, not an anonymous one**.

> [!IMPORTANT]
>
> **The stored password is load-bearing. Clearing it breaks the integration outright.**
>
> `device.information` — the `CRITICAL_ENDPOINT`, whose failure aborts the whole fetch — returns **`100003: No rights (needs login)`** on an anonymous session. Verified 2026-08-16 as a sole call on a fresh connection, so it is not the bulk-sweep artefact described below.
>
> An earlier revision of this document claimed the integration ran anonymously and that "anonymous is enough for everything the integration polls". **Both statements were wrong.** Had they been true, every poll would have aborted on the critical endpoint.

Some reads _do_ answer anonymously — `device.basic_information`, `device.vendorname` and `system.deviceinfoex` all did on the same probe. That is what made the wrong claim plausible. It does not generalize, and `device.information` is the counter-example that matters.

Roughly **90 of the library's ~240 read methods answer `100003: No rights (needs login)`** — the configuration surface: WiFi security settings, MAC filters, VPN, USB storage, voice/SIP account details, firmware update controls. Supplying the stored password as `admin` was tested and made **no difference to any of them**, so they are not a credential problem — they need a session this API grants differently, or the model does not permit them at all.

**Four that were probed individually and stayed refused**, so they are not artefacts of the bulk-sweep problem described below:

| Endpoint | What is behind it | Consequence |
| :-- | :-- | :-- |
| `device.antenna_status` | The **configured** antenna mode — Auto / Internal / External / Mix | Only the resulting state is readable, from `device.antenna_type`. See the antenna note in Field formats |
| `dial_up.auto_apn` | Automatic APN selection | The APN itself is readable from `dial_up.profiles`, which is polled |
| `led.nightmode` | LED night-mode schedule | No route to LED state at all |
| `monitoring.wifi_month_setting` | Per-WiFi monthly data plan | The WAN-side plan is readable from `monitoring.start_date` |

Re-verify any of these on a fresh session before treating a refusal as permanent — that is the rule the next section exists for. These four have been.

### Error codes worth recognizing

| Code | Meaning | What to do |
| :-- | :-- | :-- |
| `100002: No support` | The hardware or firmware does not implement it | Nothing. Do not retry, do not add a sensor |
| `100003: No rights (needs login)` | Either the router refuses this one read, or the session has ended | `api.py` tells the two apart; see [Telling a refusal from an expiry](#telling-a-refusal-from-an-expiry--the-rule-as-built-123-dev16) |
| `108003` / `108006` | Wrong username / password | Surfaces as `HuaweiAuthError` → `ConfigEntryAuthFailed` → reauth flow |
| `-1: Unknown` | **Ambiguous — never treat it as a refusal on its own** | Read the state back and let that decide. See below |

> [!IMPORTANT]
>
> **`-1` is the router's answer both when it refuses a command and when it applies one it cannot answer for.** Two writes hit it, and they mean opposite things:
>
> - **`net.reconnect()`** — a genuine refusal. This hardware does not implement it; `dialup/dial` is used instead.
> - **`net.set_net_mode()`** — **applied, and answered badly.** Verified 2026-08-16: from `03`, a write of `00` raised `-1`, and the router's own web interface showed Auto immediately afterwards. The radio is re-registering, so the response to the POST is as unreliable as an immediate read-back would be.
>
> `api.set_net_mode` therefore waits `NET_MODE_SETTLE` and re-reads `net_mode`; that read is the only thing that separates the two cases.
>
> **`net_mode.NetworkMode` is confirmed present.** The hardware check reads it back on every run (`read-back net_mode.NetworkMode`), so a firmware rename of the key that `confirm_write` compares would surface immediately instead of turning every network-mode write into a permanent _unverified_.
>
> **`-1` is occasional, not guaranteed.** On 2026-08-19 the hardware check wrote `03` from `00` and the router accepted it outright. The 2026-08-16 observation was the other direction. What decides it has not been isolated, so code must handle both and no run should be assumed to have exercised the `-1` path. A refused mode change answers `-1` as well and is caught by the same read-back disagreeing.

### Logout — the failure that hid for a whole release line

`api.py` calls **`client.user.logout()`**. It previously called `Connection.logout()`, **a method that has never existed in this library**, hidden behind a `# type: ignore[attr-defined]`. Every unload and every reload leaked a session, silently, because a failed logout is deliberately swallowed — an unload must not be blocked by it.

**The lesson generalizes:** a `type: ignore[attr-defined]` on a library call is a _claim about that library_, and this project made that claim falsely twice. `tests/test_entity_hygiene.py` now sweeps every suppression against a reviewed allow-list for exactly this reason.

### The session degrades under sustained bulk querying

**Measured 2026-08-15, and it will mislead anyone who tries to inventory this API by brute force.** A sweep calling ~240 read methods back to back returns `100003: No rights` for endpoints that demonstrably work — `wlan.multi_basic_settings` and `wlan.host_list` both failed in the sweep and both succeeded immediately afterwards on a fresh connection, and both are polled successfully in production every cycle.

So: **probe endpoints in small batches, and re-verify any negative result on a fresh session before believing it.** A single `100003` in a long run is not evidence.

---

## 📥 What the integration polls today

**Twenty-six** read endpoints per cycle, all in `api.py::get_data`, merged into one flat dictionary keyed by block name. Every block key must also appear in `const.py::ENDPOINT_NAMES`; a block missing from that map cannot be reported as a degraded capability, so its endpoint can fail every poll while Integration Health stays green.

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
| `monitoring.start_date` | `start_date` | Data plan — allowance, cycle start day, threshold |
| `monitoring.converged_status` | `converged_status` | SIM and country |
| `dial_up.profiles` | `dial_up_profiles` | APN profiles — matched on `Index`, never list position |
| `dial_up.connection` | `dial_up_connection` | Connection settings |
| `device.antenna_type` | `antenna_type` | Antenna selection |
| `net.csps_state` | `csps_state` | Network registration |
| `security.sip` | `security_sip` | SIP ALG |
| `security.upnp` | `security_upnp` | UPnP |
| `voice.voicebusy` | `voice_busy` | Line state — returns a bare string (`Idle`), not a dict |
| `voice.volte` | `voice_volte` | VoLTE status |
| `monitoring.onekey_diag` | `onekey_diag` | Router self-diagnosis — see the decode below |

**One further endpoint is read but not polled.** `net.net_mode_list()` is fetched **once, after login**, and its `AccessList.Access` — `["00", "08", "03"]` on this hardware, exactly the three modes the web interface offers — becomes the Network Mode select's option list. It is static configuration that changes only with a firmware update, so polling it would be waste. It sat under _Readable, never reviewed_ in this document for weeks with the note "could validate the Network Mode select"; adopting it is what surfaced `08`.

`lan_host_info` and `wlan_host_list` carry the MAC, hostname and IP of every device on the user's network. That is a privacy surface no sibling project has, and it is why `diagnostics.py` recurses and pseudonymises rather than redacting by key name.

---

## 📤 Writes

**Ten**, all serialized behind one `asyncio.Lock` and routed through `_execute_with_retry`.

| Endpoint                        | Action                 | Register tier |
| :------------------------------ | :--------------------- | :------------ |
| `user.logout`                   | End the session        | SAFE          |
| `device.set_control(REBOOT)`    | Reboot                 | ATTENDED      |
| `monitoring.set_clear_traffic`  | Zero the byte counters | ATTENDED      |
| `dial_up.set_mobile_dataswitch` | Mobile data on/off     | ATTENDED      |
| `dial_up._session.post_set`     | Reconnect              | ATTENDED      |
| `wlan._session.post_set`        | Master WiFi on/off     | ATTENDED      |
| `net.set_net_mode`              | Preferred network mode | ATTENDED      |
| `wlan._session.post_set`        | Guest WiFi on/off      | ATTENDED      |
| `sms.send_sms`                  | Send a message         | ATTENDED      |
| `sms.delete_sms`                | Delete a message       | ATTENDED      |

Every one is classified in `scripts/write_classification.py`; `tests/test_write_classification.py` fails on an unclassified write.

### `set_net_mode` takes bands as well, and they come from the router

`net/net-mode` sets mode, LTE band mask and network band mask **together** — a mode change cannot omit the bands. This used to send `LTEBandEnum.ALL` and `NetworkBandEnum.ALL`, library constants never checked against the device. On this hardware that is harmless because the router clamps: after writing `ALL` it reports `LTEBand=7A0880800D5`, its own supported mask, and a `NetworkBand` matching neither the value sent nor anything in its published `BandList`. A model that took the value literally would have had its band selection reset on every mode change, so the current bands are now read and handed straight back.

**`08` is 5G Only.** The library's `NetworkModeEnum` ends at `MODE_4G_3G_AUTO` and has **no 5G member at all** — it predates 5G — so a table copied from it cannot name the mode this hardware sits in. The library does not constrain the write: `networkmode` is a plain `str`, passed through unvalidated.

### A mode change holds the session, and leaves half-closed sockets behind

**A network-mode write occupies the router for `NET_MODE_SETTLE` (15 s) plus a read-back**, because the router answers the write itself with `-1` and only a re-read after the radio settles can say whether the mode took. On a device that permits one login, that is the longest any single command holds the session, and nothing else can talk to the router while it does.

**The router closes its end during radio re-registration.** Sockets left over from before the change sit in `CLOSE_WAIT` until something closes them — three connections to the router were open during the 2026-08-17 lockup, two already half-closed. A `requests.Session` that is only dereferenced does not close them, and its pool will hand a dead one back out. Anything that discards a connection here must call `session.close()`, which is what `_reset_client()` now does.

### Outgoing SMS length is capped at four segments

The router's web interface states both ceilings: **612 ASCII characters, 268 UCS2**. Both divide exactly by one segment — 612 = 4 × 153, 268 = 4 × 67 — so this hardware concatenates at most **four** segments. `zte_router_5g` allows five.

**Which one applies is decided by the content.** A single emoji or curly quote forces UCS-2 for the whole message, so the same text that fits as plain ASCII can be refused once one special character is added.

**Read from the GUI, not measured from the API.** `sms.config` is the block most likely to publish these values and has not been probed. Behavior past four segments is untested — the integration refuses rather than finding out.

### Three spellings that matter

**`device.set_control(ControlModeEnum.REBOOT)`, not `device.reboot()`.** Both exist in 1.11.0, but **2.0.0 removes `reboot()` and `control()`** and keeps only `set_control`. The current spelling is correct on both, so the library bump needs no change here.

**`monitoring.set_clear_traffic()`, not `Monitoring.clear_traffic()`.** The latter has never existed. The Clear Traffic button could not have worked in any release; its test asserted the wrong name against a bare `MagicMock`, so nothing caught it.

**`dialup/dial`, not `net.reconnect()`.** The library exposes `net.reconnect()` and the router advertises the feature, but this hardware **refuses it with `-1: Unknown`**. Reconnect posts `dialup/dial` with `Action: 0` and then `Action: 1` through `client.dial_up._session.post_set`, then resets the client. Verified live: `CurrentConnectTime` 135 → 5, and confirmed from the UI by the owner on 2026-08-15.

### The master WiFi switch works at the RADIO level, not the SSID level

**The per-SSID flags in `wlan/multi-basic-settings` are gated by the radio.** Writing them while the radio is off changes nothing observable, which is why an earlier attempt at this control could not be made to work. The radio state lives in `wlan/status-switch-settings`, as `wifienable` per radio, and turning WiFi on or off means writing that block back whole. Verified `0,0 → 1,1 → 0,0` on a live B535.

**The library's own `wlan.wifi_network_switch()` answers `100005: Request format error`** on this hardware, so it is not an alternative.

Current WiFi state is readable from `monitoring_status.WifiStatus`, which is already polled — reading the radio block for it would be a second round trip for the same fact.

### Guest WiFi deliberately bypasses the public setter

**The library's public setter is unusable for this write.** `client.wlan.set_multi_basic_settings()` builds its own payload — `{'Ssids': {...}, 'WifiRestart': 1}` — and **discards every other top-level key**. Probed on a live B535, `multi_basic_settings()` returns three: `Ssids`, `DbhoEnable` and `modify_guest_ssid`. Using the public setter would therefore drop band-steering and guest-SSID state on every guest toggle, silently, because the router accepts the truncated block without complaint.

The guest write goes to `wlan/multi-basic-settings` through `client.wlan._session.post_set` instead, preserving the keys it did not set. The code-side decision and its test guard are in [`DEVELOPMENT.md`](DEVELOPMENT.md).

---

## 🔍 Readable — the review of everything else

This section is the record of a survey, not a list of what is currently unpolled. The first table below was adopted; the two after it were not.

Confirmed working on this hardware and **not** currently fetched. Verdicts are from the field review recorded in `.notes/info/extra_fields/`.

### Agreed for adoption — **all eight were adopted in `[1.2.0-dev11]` and are polled today**

They are listed here as the record of the decision and the live values it was made on. **They are no longer "not polled"** — every one appears in the polled table above and in `ENDPOINT_NAMES`. The only endpoint in the sections below that is also polled is `wlan.wifi_feature_switch`, listed under **reviewed, not adopted** — correctly, because it is polled but almost entirely unread.

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
| `wlan.wlandbho` | `DbhoEnable`, `MloEnable` | Band steering and Wi-Fi 7 MLO. Both are _settings the owner set_, not state — and `DbhoEnable` already arrives in `wlan_multi_basic_settings` |
| `net.cell_info` | `cellinfo`, `lac` | `cell_id` and `pci` are already exposed from `device_signal` |
| `s_ntp.timeinfo` | Timezone, sync status, servers | Router clock. Nothing acts on it |
| `dhcp.settings` | DHCP range, lease, `homerouter.cpe` | Static configuration, not state |
| `device.device_feature_switch` | `onekeydiag_enabled` etc. | Capability flags. Matters as a **precondition check**, not as a sensor |
| `net.net_feature_switch` | 9 capability flags | Same |
| `wlan.wifi_feature_switch` | 49 keys, 47 unread | Polled, but almost entirely firmware **capability** flags rather than state |
| `config_statistic.config` | 60+ keys | A firmware config template — dated `2012`, values are defaults. Mirrors `start_date` but is not live state |
| `device.vendorname` | `version_name='ZOWEE'` | The **ODM**, not the brand. See the trap in Field formats |
| `device.basic_information` | `classify='cpe'`, `devicename`, `spreadname_en` | Every field duplicates `device_information`. HA Core reads it as a fallback for models where `device.information` is thin; unnecessary here, where that endpoint answers every poll |
| `system.deviceinfoex` | `UpTime`, `custinfo`, `devcap` | `UpTime` duplicates `device_information.uptime`; the rest are capability flags and `devcap.Vendor` is empty |

### Readable, never reviewed

Found by the endpoint sweep and **not** assessed. Recorded so the next person starts here rather than re-running the probe.

> [!NOTE]
>
> **Five of these are now called on every diagnostics download**, and their live shape on this hardware is recorded in the rows below — measured 2026-09-07 by `api.DIAGNOSTIC_PROBES`. They are still unassessed as _entity candidates_; what has changed is that a download now says whether a given model serves them, so the next assessment starts from evidence rather than from a probe run by hand. `sms.config` is the one that answered the open question in this table.

| Endpoint | Keys | Note |
| :-- | :-- | :-- |
| `global_.module_switch` | 94 | The largest capability block on the device. **Probed:** answers 94 keys, all populated |
| `security.get_firewall_switch` | 11 | Firewall toggles. **Probed:** answers 11 keys, all populated |
| `security.nat`, `.dmz`, `.virtual_servers`, `.mac_filter`, `.url_filter` | 1–3 each | Firewall and forwarding configuration |
| `diagnosis.diagnose_ping`, `.diagnose_traceroute` | 11, 6 | **The router will run a ping or traceroute on request.** Interesting and unexplored |
| `diagnosis.time_reboot` | 4 | **Scheduled reboot, and it is ENABLED on the reference unit.** `enable='1'`, `dayinterval='7'`, `begintime='60'`, `endtime='300'` — a reboot every 7 days in a window that reads as 01:00–05:00 if the times are minutes past midnight, which is **inference from the values fitting, not measurement**. Worth knowing even if never exposed: it explains a weekly uptime reset, and it interacts with reboot detection. `zte_router_5g` exposes an equivalent. **Probed:** answers `enable`, `dayinterval`, `begintime`, `endtime` — the four keys, all populated |
| `online_update.status`, `.configuration`, `.autoupdate_config` | 8, 4, 2 | Firmware update state — may decode `monitoring_status.OnlineUpdateStatus`, which was rejected as an unknown code. **Probed:** `status` answers 8 keys, all populated |
| `sms.config` | 16 | SMS behavior settings. **Probed 2026-09-07: 16 keys, 14 populated, and the length ceilings are not among them.** The keys are `SaveMode`, `Sca`, `SendType`, `UseSReport`, `Validity`, `country_number`, `import_enabled`, `maxphone`, `pagesize`, `phone_number`, `sms_center_number_editabled`, `sms_forward_enable`, `smscharlang`, `smsisusepdu`, `switch_enable`, `url_enabled`. `smscharlang` and `smsisusepdu` bear on GSM-7 versus UCS-2 selection and are worth a look; nothing here supplies a character limit, so the web-interface figures stand |
| `led.appctrlled` | 3 | LED control. **Probed:** answers 3 keys, all populated |
| `redirection.homepage`, `staticroute.wanpath`, `dhcp.static_addr_info` | 1–2 | Minor configuration |

---

## ❌ Not supported on this hardware

Returned `100002: No support`. **Do not add, do not retry.**

> [!NOTE]
>
> **This list is now measured on every diagnostics download.** `api.DIAGNOSTIC_PROBES` calls 46 unpolled endpoints once per download and records each as answered, refused with the router's own code, or unavailable. On this hardware, 2026-09-07: **31 answered, 15 refused, none unavailable** — eleven `100002` and four `100003`. The point is not this device, which is already understood, but a report from a model nobody here has seen: an endpoint missing from the payload now says which of those it was.

`monitoring.daily_data_limit` · `monitoring.month_statistics_wlan` · `wlan.station_information` · `wlan.basic_settings` · `ntwk.celllock` · `system.deviceinfo` · `statistic.feature_roam_statistic` · `user.remember_pwd`

`wlan.station_information` is the notable loss — it would give per-client WiFi signal strength, which nothing else provides.

### Why a bulk sweep produces false `100003` results — the mechanism

The Authentication section already records the rule: **probe in small batches on fresh sessions, and re-verify every negative**, because a bulk sweep produces `100003` results that read exactly like a permission boundary. What follows is the cause, measured on 2026-09-07, and it is in this integration rather than in the router.

`ResponseErrorLoginRequiredException` is raised by `huawei-lte-api` for `100003` **and for no other code** — `125002` and `125003` map to `ResponseErrorLoginCsrfException` and `ResponseErrorWrongSessionToken` (`Session.py:189`). `api.py:_execute_with_retry` opens its handler with `isinstance(err, ResponseErrorLoginRequiredException)`, so a `100003` discards the client and logs in again before the code list below it is ever consulted.

Measured logins per call through that wrapper:

| Call                 | Logins |
| :------------------- | -----: |
| A read that answers  |      1 |
| `100002: No support` |      1 |
| `100003: No rights`  |  **2** |

So every refusal in a sweep costs a logout and a login. A 42-endpoint sweep on 2026-09-07 accumulated enough churn that the router began answering `LoginErrorAlreadyLoginException` and then refused connections for the rest of the run — after which the remaining endpoints reported failures that were artefacts, not findings. **The same 42 calls on one session, called directly without the retry wrapper, completed in about 900 ms with every endpoint returning a real outcome.**

Two consequences:

- **Anything sweeping endpoints outside the polled set must bypass `_execute_with_retry`** and call on a single established session. That is the whole fix, and it needs no delays between calls.
- **`100003` does not end the session on this firmware.** A read on the same session immediately afterwards answers normally, and a _fresh_ session returns `100003` from the same endpoints every time.

### Telling a refusal from an expiry — the rule as built (1.2.3-dev16)

**The ambiguity.** `100003` is the router's answer to a read it refuses on a live session, and it is also the answer to every login-only read once a session has ended. Until 1.2.3-dev16 the fetch loop in `api.py` treated a `100003`, `125002` or `125003` from any endpoint as an expired session. A router that refused one optional endpoint therefore failed the whole poll, and at setup the config flow reported `invalid_auth` although the login had worked. That is issue 50: a B529s-23a branded for Magenta Austria, firmware 11.182.63.00.1409. The report names neither the endpoint nor the code, so the three codes are handled alike.

**The rule.** `device_information` is the critical endpoint, and a session signal from it is always an expiry, as before. A non-critical endpoint that raises one of the three codes is adjudicated:

| Step | What `api.py` does | Result |
| :-- | :-- | :-- |
| 1. Premise | A new `Connection` with no credentials reads `device.information`. It opens no session and makes no login attempt | `100003` confirms the premise that this router refuses `device_information` without a login. An answer means the router serves it anonymously, and any other failure leaves the premise unknown, which is not kept |
| 2. Re-read | With the premise confirmed, `device_information` is read again on the session, at most once per poll | An answer means the session is live: the endpoint is recorded `refused` with `judged: live_session` and the poll continues. One of the three codes means the session has ended, and `HuaweiAuthError` is raised as before |
| 3. History | With the premise not confirmed, or with more than 10 s of the poll's 30 s used, the history of the run decides | An endpoint that has never answered is recorded `refused` with `judged: history`. An endpoint that answered earlier in the run raises `HuaweiAuthError` |

**Why `device_information`.** It is the one polled read that needs a login on both routers measured, and it is read every poll. A read that answers without a login cannot show a dead session, and a read the router refuses on a live session cannot show a live one. The reads that answer without a login are in the per-model tables below.

**Bounds.** Each request of the premise check is allowed `PREMISE_TIMEOUT`, 3 s. The premise check and the re-read are made only while the poll has used at most `ADJUDICATION_BUDGET`, 10 s of the 30 s, so that the adjudication cannot reach the coordinator's `asyncio.timeout`. The premise is kept for the run and cleared whenever the client is reset, so a router restarted by a firmware update is checked again. The recorded premise result holds an outcome and a code and never the payload, because a router that serves `device_information` anonymously returns identifiers in it. The history and the premise are written only if the client generation is unchanged since the read began, so a worker thread orphaned by a timeout cannot write after a reset.

**The history is `HuaweiRouter5GAPI.answered_endpoints`**, the endpoint names that have answered since the object was created. It lives on the API object and not on the library client, so a reset does not clear it, and it is held in memory only.

**Integration Health.** An endpoint refused with a router code on a poll, and never answered in the run, is not a lost capability. It is listed under the `not_served` attribute of the Integration Health sensor and takes no strike, so severity stays `ok`. An endpoint that answered earlier and now refuses still accrues strikes and reads `degraded`, and a timeout is not a router code.

**The probe sweep of the diagnostics download** holds the API lock for its duration and reads `device_information` after any probe that does not answer. A `100003` from that read is a lost session: the sweep logs in once through `_login_internal`, which does not take the lock, and repeats the probe, at most twice per sweep. A connection error from the read is unknown and causes no login. The sweep stops at 20 s, after a failed login, after a third loss, or if the client was reset under it, and marks the remaining probes `not_run`. The download records the premise result and the number of sessions lost.

**Reads that start something.** `net.plmn_list` starts a network scan. On the H165-383 it timed out in a read sweep and was followed by a brief data-connection restart on two runs, so it is the likely cause. It is not among the 46 `DIAGNOSTIC_PROBES`, and a read sweep of the library excludes it, together with `net.reconnect`, `accept`, `compress`, `operate` and `toggle` methods.

**Known limits.**

- **The router's own refusal of a polled endpoint has not been observed.** No router held refuses one. The refusal path is verified by unit tests built from the report and by a simulated refusal on two routers, in which the premise check and the re-read are real. The first evidence from a B529s is the author's diagnostics download.
- **The premise is measured on two routers and assumed on the B529s.** Where it does not hold there, the history decides.
- **The history fallback is more permissive than failing closed.** It reads a signal from an endpoint that has never answered as a refusal, so a session lost before any endpoint answered reads as a refusal. It is to be reviewed against the author's download, as the task `tighten_premise_failure_fallback_after_ops_download` records.
- **A refusal can follow the router's state.** The B315s-22 answers the SMS list with `125003` when it has no SIM and answers it with one. An endpoint that answered earlier and later draws such a code is an expiry under the history fallback.
- **The never-answered history is in memory.** A capability lost while Home Assistant is not running reads as never served after the next start. The task `persist_never_answered_endpoint_history` records the persisted set.
- **`_execute_with_retry` still treats `100003` as an expiry**, so a control the router refuses costs a login. The task `relogin_on_100003_in_execute_with_retry` records the change, which affects controls and not setup.

---

## 📏 Per-model measurements, 2026-10-05

Measured from the development container with `huawei-lte-api` 2.0.1, for the rule above. The H165-383 is the reference unit and the owner's main router. The B315s-22 is an older unit, software 21.329.01.00.25 and web UI 17.100.09.00.03, set up for comparison, and the author of issue 50 owns a B529s-23a that has not been measured. The routers were read and logged in; no reboot was made on the H165-383 and no write was made on either.

### Reads by class

| Measure | H165-383 | B315s-22, no SIM |
| :-- | :-- | :-- |
| Reads tried, taking no required argument | 243 | 251 |
| Answered when logged in | 149 | 86 |
| Answered both anonymously and logged in | 46 | 76 |
| `100002` when logged in | 51, of which 13 were also `100002` anonymously | 106, of which 81 were also `100002` anonymously |
| `100003` on a live session | 38, and a read of `device.information` answered after each | 0 |
| Refused `100003` anonymously and answered logged in | 103 | 32 |
| `125003` on a live session | 0, and one read returned `125003`, ended the session and answered `100002` on a fresh one | 3: two SMS reads and `vpn.toggle_status` |
| Polled reads mapped | 23 of 26 | 23 of 26 |
| Polled reads that need a login | 14 | 6 |
| Polled reads that answer without a login | 9 | 11, of which 5 answer `100002` and `sms.get_sms_list` answers `125003` |
| Polled reads refused on a live session | None | None |

The 14 polled reads that need a login on the H165-383 are `device.information`, `net.net_mode`, `sms.sms_count`, `sms.get_sms_list`, `lan.host_info`, `wlan.host_list`, `wlan.multi_basic_settings`, `dial_up.profiles`, `device.antenna_type`, `net.csps_state`, `security.sip`, `security.upnp`, `voice.voicebusy` and `voice.volte`. The 6 on the B315s-22 are `device.information`, `wlan.host_list`, `wlan.multi_basic_settings`, `dial_up.profiles`, `security.sip` and `security.upnp`.

### How an expiry presents, and what does not end a session

| Test | H165-383 | B315s-22 |
| :-- | :-- | :-- |
| Logout, then `device.information` and two login-only reads | `100003` on all three, twice | `100003` on all three, twice |
| Cleared cookies, the same reads | `100003` on all three, twice | `100003` on all three, twice |
| Garbage token, and an emptied token list | All three reads answered | All three reads answered |
| A second login, the first session read for 30 s | Answered throughout | Answered throughout |

An expiry therefore presents as `100003` on every login-only read at once, and the token is not what carries the session. Two sessions coexist on both routers, so a login made by the sweep after a lost session does not end the session of another client.

### Reboot timeline

On the B315s-22 the router was unreachable from about 18 s to 44 s after the reboot command, the old session read `100003` at 46 s, a new login answered, and the integration logged one fetch failure and raised no repair. The H165-383 was not rebooted, by the owner's direction.

### `net.current_plmn` and the SIM state

| State | B315s-22 |
| :-- | :-- |
| No SIM, Ethernet WAN | `net.current_plmn` returns the string `FAILED`, with and without a login. `sms.get_sms_list` called with no argument answers `125003` on a live session |
| SIM fitted and registered on LTE, 5 signal bars, operator code 27205 | `net.current_plmn` returns a dictionary. `sms.get_sms_list` answers and needs a login. 6 of 243 reads differ between the two states |

On the B315s-22 the Integration Health sensor read `warning` with six degraded capabilities and a signal-block drift without a SIM, and `degraded` with five degraded capabilities and no drift with one. The sensor code does not expect the string `FAILED`; the task `current_plmn_failed_string_crashes_sensors` records the three sensor sites. A router with its WAN on Ethernet shows an empty signal block, a `FAILED` operator string and 53 of 124 entities unknown, and the integration has not been tested in that mode, which is a roadmap item.

### The diagnostic probe list with a canary

| Router | Probes | Outcomes | Sessions ended |
| :-- | :-- | :-- | :-- |
| H165-383 | 46 in 1.6 s | 31 answered, 10 answered `100002`, 5 answered `100003` on a live session | None shown |
| B315s-22, with a SIM | 46 in 2.2 s | 22 answered, 23 answered `100002`, 1 answered `103005` | None |

The five `100003` probes on the H165-383 are `device_autorun_version`, `device_antenna_status`, `device_antenna_settings`, `monitoring_wifi_month_setting` and `dial_up_auto_apn`, each followed by a read of `device.information` that answered, except the last. After the last probe that read raised a connection error and not a `100003`, so the session was not shown to be dead, and the connect time of 9793 s afterwards shows the sweep did not restart the data connection. A canary that raises a connection error is therefore treated as unknown.

On the B315s-22, four connection errors in a read matrix coincided with the integration's own poll, and whether load or the SIM caused them is not established. Overlapping requests made it drop connections, so checks against it pause the integration's polling first.

---

## 🔤 Field formats and traps

**`DataLimit` is a display string, `trafficmaxlimit` is bytes.** `'2000GB'` needs parsing and carries a GB/GiB ambiguity; `2147483648000` is the same figure as an integer (2000 × 1024³). **Use `trafficmaxlimit`.**

**The router's statistics page is GiB, not GB.** The GUI's "156.96 GB" is `CurrentMonthDownload + CurrentMonthUpload` divided by 1024³, matching to the byte. Its "GB" and "TB" labels mean GiB and TiB throughout.

**`MonthDuration` counts from the billing cycle start, not from the last manual clear.** Measured 1,202,664 s = 13.92 days against a `StartDay` of 1, on 14 August. `MonthLastClearTime` (`2026-04-18`) is the _manual counter reset_ and is unrelated — four months of separation between the two is what proves they measure different things.

**`workmode` reports the LTE anchor, not the aggregate.** It reads `LTE` while `EndcStatus=1` and `SignalIconNr=5` show the modem is attached to 5G NSA. Do not present it as "current network type".

**`device_signal.band` is the full carrier aggregation; `bandInfo` is only the primary.** `band` returns `20MHz@500(B1) + 15MHz@1875(B3) + ...` while `bandInfo` returns `B1`. Two sensors showing these side by side read as a contradiction unless one explains itself.

**`dial_up.profiles` returns profiles out of order.** The list came back indexed 1, 3, 2. Resolve `CurrentProfile` by matching the `Index` field, never by list position.

**`device.vendorname` returns the ODM, not the brand.** It answers `{"version_name": "ZOWEE"}` on the reference unit — Zowee Technology, the contract manufacturer. Wiring it into the device registry's `manufacturer` would replace a correct "Huawei" with a name the owner has never heard of. **`manufacturer` is therefore a hardcoded `"Huawei"` in `helpers.py` and `__init__.py`, deliberately.**

There is **no brand field anywhere on this hardware**. Probed 2026-08-16: `device.information` has none, `device.basic_information` gives only `classify: cpe` and `devicename`, and `system.deviceinfoex` carries `devcap.Vendor` — the one field actually named for it — as an **empty string**. Brovi and SoyeaLink units will therefore also show as "Huawei"; the README says so under Compatibility. Anything better would have to be asked of the user in the config flow, not sniffed from the payload.

**`antenna1type` / `antenna2type` report the antenna in use, not the setting.** Decoded 2026-08-15 by a controlled change: `0` = Internal, `1` = External, both antennas moving together with the GUI. Under **Auto** they read `1` — the router had _chosen_ External — so the field answers "which antenna is the radio on right now", which is the more useful half and the only half available, since the configured mode sits behind `device.antenna_status` and is refused. **Mix needs no third code**: the value is reported per antenna, so Mix is simply the two disagreeing.

**`antenna1insertstatus` / `antenna2insertstatus` carry no information on this hardware.** Both stayed `1` across every antenna setting, so the field is **not** "an external antenna is plugged in". An earlier proposal to expose `insertstatus` and drop `type` was exactly backwards.

**`ImeiSvn` is not part of the IMEI, and is not redacted.** It is the IMEI **Software Version** Number — a two-digit manufacturer revision counter, `01` on this unit. There is no public table to decode it further, and `SoftwareVersion` already says the same thing readably, so no entity exposes it.

A 2026-08-15 review listed it for `diagnostics.py`'s `TO_REDACT` as "the one identifier of the seven not redacted". **That is withdrawn.** It was grouped with the identifiers on the strength of `Imei` appearing in its name; on inspection it carries no subscriber or device identity, and `SoftwareVersion` and `iniversion` — both published in full — are strictly more revealing about the same build. Redacting `01` would hide nothing while adding another `**REDACTED**` to a document whose usefulness depends on not being full of them.

**`maxsignal` is the bar-scale denominator.** It reads `5` alongside `SignalIcon = 4`, so the pair means four bars of five. It is constant, which is why it is not exposed on its own — but it is what makes `SignalIcon` interpretable.

**`WifiMacAddrWl0` / `WifiMacAddrWl1` are the 2.4 GHz and 5 GHz radio MACs**, and they are already present as `WifiMac` inside the SSID list. Static, and a second source for a fact the polled block already carries.

**`scc_pci` is a secondary carrier's physical cell ID.** Under carrier aggregation the modem holds a primary cell plus secondaries; `pci` identifies the primary and `scc_pci` one of the secondaries, which is why it is populated on a link showing four aggregated carriers. Useful for explaining a throughput change when the primary cell has not moved.

**Identifiers are digits that are not quantities.** `Imei`, `Imsi`, `Iccid`, `Msisdn`, `SerialNumber`, `Mccmnc`, `scc_pci` must carry no `state_class`, no `device_class`, no unit and no display precision — set any of them and Home Assistant coerces the value, turning `01` into `1` and a 15-digit IMEI into scientific notation.

**Several status fields are undecodable codes.** `SimState=257`, `CurrentNetworkTypeEx=1011`, `CurrentServiceDomain=3`, `OnlineUpdateStatus=14`, `cellroam=2`. The library ships enums only for `NetworkMode`, `NetworkBand`, SMS box types and `SaveMode` — nothing covers these, and Huawei publishes no specification. **Prefer a typed endpoint over guessing**: `net.csps_state` supersedes `CurrentServiceDomain`, and `converged_status.SimLockEnable` supersedes `simlockStatus`.

---

## 🆕 API Library version 2.0.1 and interoperability

**This integration runs on either 1.11.0 or 2.0.1.** Home Assistant core pins 1.11.0 for its own `huawei_lte` integration, so the methods below that exist only from 2.0.1, `voice.volte` and `monitoring.onekey_diag`, are skipped on 1.11.0 and their entities read unknown. Which version runs, what each does, and why both are supported are in `docs/library_versions.md`.

**Method: a full surface diff, not a probe.** 1.11.0 was unpacked alongside 2.0.1 and both enumerated — every group, every method signature, every enum member, every exception. That is the only way to answer "what is new" without guessing, and it is what the earlier field-level scans could not do.

**The surface barely moved.** 70 groups and 336 methods → 70 groups and 340 methods. No new groups, no enum changes, no exception changes. Most signature diffs are `Dict[str, Any]` → `dict[str, Any]` typing modernization.

### Six methods added

| Method | Live value | Worth |
| :-- | :-- | :-- |
| **`monitoring.onekey_diag()`** | Ten fields — decoded below | **The router's own self-diagnosis.** `status_plan` §S-6's target |
| **`voice.volte()`** | `volte_enable='1'`, `ui_display_ims='1'` | Real VoLTE state, which the SIP ALG flag is not |
| `wlan.guesttime_setting()` | `isvalidtime='1'`, `remaintime='0'`, `extendtime='30'` | Guest-WiFi time limit |
| `security.acl()` | `https_enable='1'`, `icmp_enable='0'`, `acs_enable='0'` | Remote-management access control |
| `user.rule()` | Password-length and complexity policy | Low |
| `diagnosis.wan_service_name()` | `'INTERNET'` | Low |

`onekey_diag`'s `speedLimitStatus` reads `0`, matching `monitoring_status.speedLimitStatus` — the two blocks cross-validate.

### `onekey_diag` decoded — by controlled disconnection, 2026-08-15

The block is a **set of causes behind one verdict**, not ten booleans. Established by taking mobile data down and reading it in both states. A reconnect was tried first and proved useless: the router auto-redials (`auto_dial_switch=1`) inside four seconds, so nothing is ever observably down.

| Field               | Connected | Disconnected |
| :------------------ | :-------- | :----------- |
| `connection_status` | **`2`**   | **`8`**      |
| `dialupswitch_off`  | `0`       | `1`          |
| `apnstatus`         | `0`       | `2`          |
| the other seven     | `0`       | `0`          |

**`connection_status` is the verdict, and `2` means healthy** — it is not a boolean and `0` is not its good value. The remaining nine read `0` when there is nothing to report, and the two that moved named the actual cause: the dial-up switch was off, and the APN could not come up as a result.

`speedLimitStatus` appears here and in `monitoring_status`, agreeing in both — the two blocks cross-validate.

**Only `2` and `8` have been observed.** A check of `!= "2"` is therefore sound — `2` is confirmed good, and anything else is at minimum not-the-known-good value — whereas `== "8"` would be a guess about every other code.

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

- `ha-zte-router-5g-monitor/docs/zte_how_to_access.md` — the ZTE companion, organized by `cmd` name because that interface is two endpoints with a parameter.
- `ha-unifi-network-monitor/docs/api_endpoints.md` — the UniFi companion, organized by URL.
- `.notes/info/extra_fields/extra_fields_decide_202608.md` — the field-by-field review this document's verdicts are drawn from, with sub-device, category and default decisions.
- `.notes/info/extra_fields/extra_fields_202608.md` — the raw working notes and evidence trail behind it.

> [!NOTE]
>
> **This document wins over both `extra_fields` files where they disagree**, and they disagree in two places. That review was written before the endpoints were exercised, and two of its conclusions were later reversed by measurement: **`net.reconnect()`** is refused by this hardware and Reconnect is implemented as `dialup/dial` (see _Three spellings that matter_), and the **voice group is readable** (see _A correction the scan forced_). Those files remain the record of the entity-level decisions — sub-device, category, enabled-by-default, long-term statistics — which this document does not repeat.

- `docs/all_sensors.md` — which entity each polled field becomes.
- `docs/DEVELOPMENT.md` — architecture, and the reasoning behind the guest-WiFi write path.
- `docs/ha_compatibility.md` — Home Assistant deprecations this integration absorbs.
- `docs/library_versions.md` — which `huawei-lte-api` version runs, what each version does, and what the integration does when Home Assistant core pins a different one.
