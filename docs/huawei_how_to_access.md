<!-- markdownlint-disable MD033 -->

# Huawei Router Access Reference 🔗

This document records how the integration reaches the Huawei HiLink API and how each router model measured behaves. It is organized by topic: connection and sessions, error codes, reads, writes and commands, SMS, field formats, and library versions. Each topic opens with a behavior table carrying one column per model and a source column with the date of the evidence. A cell reading "Not measured" means no measurement exists for that model.

| Model | Role | Firmware or software |
| :-- | :-- | :-- |
| H165-383 (sold as the B535) | Reference unit (authors router) | `4.4.0.1 (H1600SP2...)` |
| B315s-22 | Older unit set up for comparison | `21.329...` / Web UI: `17.100...` |
| B529s-23a | Via end-user supplied Diagnostic download | `11.182...`; not measured |

Values quoted are readings from the routers held. Where a statement rests on inference rather than observation, the text says so. Raw output, run sheets and per-run tables are kept with the project notes and are not published.

---

## 📐 How the API is reached

The three sibling projects reach their devices in three ways, and the difference decides how each access reference is organized:

| Project | Interface | Document organized by |
| :-- | :-- | :-- |
| `unifi_network_monitor` | REST, one URL per resource | URL |
| `zte_router_5g` | Two `goform` endpoints, resource named in a `cmd=` parameter | `cmd` / `goformId` name |
| `huawei_router_5g` | A third-party library over a reverse-engineered XML API | Library method |

The integration makes no HTTP request of its own to the router. Every call goes through [`huawei-lte-api`](https://pypi.org/project/huawei-lte-api/), which owns URL construction, XML parsing, the CSRF token and the session cookie. The unit that corresponds to an endpoint is therefore a library method, such as `client.monitoring.status()`. Paths the library does not wrap are posted through `client.<group>._session.post_set` or read through the session's `get`, and each is named where it is used: the two 2.0.1 reads on an older library, and the 18 diagnostic probes of 1.2.4-dev4.

- **A URL fault is fixed in the library, not here.** A wrongly built request is fixed by a library version change. `tests/test_library_contract.py` checks every method the integration calls against the installed package, so a rename fails the suite rather than raising `AttributeError` at run time.
- **A library method says nothing about hardware support.** The library covers the whole HiLink family, and each model refuses part of it (see [Not supported on this hardware](#not-supported-on-this-hardware)).
- **The library is synchronous.** Every call is wrapped in `asyncio.to_thread` in `api.py`. The IQS `async-dependency` and `inject-websession` rules stay at `todo` for this reason: there is no async interface to adopt and no `aiohttp` session to inject.

`_normalize_router_url` in `api.py` adds `http://` to a bare host such as `192.168.8.1`, because the library's `Connection` rejects a URL without a scheme.

---

## 🔧 Connection and sessions

| Behavior | H165-383 | B315s-22 | Source |
| :-- | :-- | :-- | :-- |
| Login | Password alone, empty username; one credential, no elevated tier | As the H165-383 | 2026-08-16; 2026-10-05 |
| Sessions open at once | 10; the 11th login answers `108003` | More than one; cap not measured | 2026-10-09; 2026-10-05 |
| A second login ends the first session | No: the first was read for 30 s, and eight writes on it after the second login were accepted | No: the first was read for 30 s | 2026-10-05; 2026-10-09 |
| Idle lifetime | About 180 s: alive at 180.5 s, expired by 185.3 s | Not measured | 2026-10-09 |
| `user/heartbeat` renews a session | No: a session sending one every 30 s had expired by 600 s | Not measured | 2026-10-09 |
| `user/state-login` | `State` 0 on every logged-in session, -1 without one; no takeover signal | Not measured | 2026-10-09 |
| How an expiry presents | `100003` on every login-only read at once | As the H165-383 | 2026-10-05 |
| Token carries the session | No: a garbage or emptied token still answered | No | 2026-10-05 |
| `100003` ends the session | No: the next read on the session answers | Not measured | 2026-09-07; 2026-10-09 |
| Connection drops | About one refusal in ten is followed by a TCP close without a response (`RemoteDisconnected`); the next request on the session answers | Overlapping requests drop connections | 2026-10-09; 2026-10-05 |
| Simultaneous requests | `110001` ("Busy"), a limit on requests in flight | Not measured | Changelog |
| Reboot | The session ends: `100003` after the router returns | The session ends: `100003` at 46 s | 2026-10-09; 2026-10-05 |
| Reconnect | The session is held throughout | Not measured | 2026-10-09 |

### A login is required

The router accepts a single username and password, and there is no separate `admin` account or elevated tier. `Connection(url, username=..., password=...)` logs in during construction. The config entry stores an empty username with the real password, and the library authenticates on the password alone, so the integration holds an authenticated session.

**The session rule.** More than one session can be open at a time, and a newer login does not end an older session. The cap is 10 on the H165-383 and unmeasured on other models. Reaching it shows as `LoginErrorAlreadyLoginException`, code `108003`, which a 42-endpoint sweep with repeated logins also provoked on 2026-09-07. An idle session expires after about 180 s on the H165-383, `user/heartbeat` does not renew it, and a session dropped without a logout holds its place until then. Ten discarded sessions within about three minutes therefore lock out every further login until the oldest expires. The integration resets an idle session after 100 s (`_ensure_client`), inside the measured lifetime. The docstrings in `api.py` and the comments in `coordinator.py` refer here and do not restate the rule.

**"Busy" is a different limit.** `110001` answers simultaneous requests and limits requests in flight, not sessions. `api.py` serializes every call behind one lock for that reason.

> [!IMPORTANT]
>
> **The stored password is required.** `device.information`, the `CRITICAL_ENDPOINT` whose failure aborts the whole fetch, answers `100003: No rights (needs login)` on an anonymous session. This was verified on 2026-08-16 as a sole call on a fresh connection, so it is not a bulk-sweep artefact.

Some reads answer anonymously, among them `device.basic_information`, `device.vendorname` and `system.deviceinfoex`, and the per-model counts are under [Reads](#-reads). `device.information` is not among them on either router measured.

About 90 of the library's roughly 240 read methods answer `100003` on the H165-383. They are the configuration surface: WiFi security settings, MAC filters, VPN, USB storage, voice and SIP account details, and firmware update controls. Supplying the stored password as `admin` changed none of them. Four were probed individually and stayed refused, so they are not bulk-sweep artefacts:

| Endpoint | What is behind it | Consequence |
| :-- | :-- | :-- |
| `device.antenna_status` | The configured antenna mode: Auto, Internal, External or Mix | Only the resulting state is readable, from `device.antenna_type` (see [Field formats and traps](#-field-formats-and-traps)) |
| `dial_up.auto_apn` | Automatic APN selection | The APN itself is readable from `dial_up.profiles`, which is polled |
| `led.nightmode` | LED night-mode schedule | No route to LED state |
| `monitoring.wifi_month_setting` | Per-WiFi monthly data plan | The WAN-side plan is readable from `monitoring.start_date` |

### Logout

`api.py` ends a session with `client.user.logout()`. The library has no `Connection.logout()`. A failed logout is swallowed so that an unload is never blocked by it. On the H165-383 a logout on an expired session answers `100003`, and the library's `Connection.close()` raises on a dropped connection, so a script that logs out wraps both.

`tests/test_entity_hygiene.py` checks every `type: ignore[attr-defined]` against a reviewed allow-list, because such a suppression on a library call is a claim about that library.

### Sessions and connections under load

**A bulk sweep produces false `100003` results.** A sweep calling about 240 read methods back to back returned `100003` for endpoints that answer: `wlan.multi_basic_settings` and `wlan.host_list` both failed in the sweep, answered at once on a fresh connection, and are polled every cycle. Endpoints are therefore probed in small batches, and a negative result is read again on a fresh session before it is believed. The cause is in [Why a bulk sweep produces false `100003` results](#why-a-bulk-sweep-produces-false-100003-results).

**A dropped connection is not a lost session.** On the H165-383 about one refusal in ten is followed by the router closing the TCP connection without a response, and the next request on the same session answers. A login made about 0.3 s after another once failed the same way. On the B315s-22, four connection errors in a read matrix coincided with the integration's own poll; whether load or the SIM caused them is not established, and checks against that router pause the integration's polling first.

**A mode change leaves half-closed sockets.** The router closes its end during radio re-registration. Sockets from before the change sit in `CLOSE_WAIT`, and three connections were open during the 2026-08-17 lockup, two of them half-closed. A `requests.Session` that is only dereferenced does not close them, and its pool can hand a dead one back out. `_reset_client()` calls `session.close()` for this reason.

### Telling a refusal from an expiry

`100003` is the router's answer to a read it refuses on a live session, and also its answer to every login-only read once a session has ended. Issue 50 arose from this: a B529s-23a failed every poll because one optional endpoint raised a session signal, and at setup the config flow reported `invalid_auth` although the login had worked. The report names neither the endpoint nor the code, so `100003`, `125002` and `125003` are handled alike. The rule below has been built since 1.2.3-dev16.

`device_information` is the critical endpoint, and a session signal from it is always an expiry. A non-critical endpoint that raises one of the three codes is adjudicated:

| Step | What `api.py` does | Result |
| :-- | :-- | :-- |
| 1. Premise | A new `Connection` with no credentials reads `device.information`. It opens no session and makes no login attempt | `100003` confirms the premise that this router refuses `device_information` without a login. An answer means the router serves it anonymously, and any other failure leaves the premise unknown, which is not kept |
| 2. Re-read | With the premise confirmed, `device_information` is read again on the session, at most once per poll | An answer means the session is live: the endpoint is recorded `refused` with `judged: live_session` and the poll continues. One of the three codes means the session has ended, and `HuaweiAuthError` is raised |
| 3. History | With the premise not confirmed, or with more than 10 s of the poll's 30 s used, the history of the run decides | An endpoint that has never answered is recorded `refused` with `judged: history`. An endpoint that answered earlier in the run raises `HuaweiAuthError` |

**Why `device_information`.** It is the one polled read that needs a login on both routers measured, and it is read every poll. A read that answers without a login cannot show a dead session, and a read refused on a live session cannot show a live one.

**Bounds.** Each request of the premise check is allowed `PREMISE_TIMEOUT`, 3 s. The premise check and the re-read are made only while the poll has used at most `ADJUDICATION_BUDGET`, 10 s of the 30 s, so the adjudication cannot reach the coordinator's `asyncio.timeout`. The premise is kept for the run and cleared whenever the client is reset, so a router restarted by a firmware update is checked again. The recorded premise result holds an outcome and a code and never the payload, because a router serving `device_information` anonymously returns identifiers in it. The history and the premise are written only if the client generation is unchanged since the read began, so a worker thread orphaned by a timeout cannot write after a reset.

**The history** is `HuaweiRouter5GAPI.answered_endpoints`, the endpoint names that have answered since the object was created. It lives on the API object and not on the library client, so a reset does not clear it, and it is held in memory only. The coordinator keeps a persisted copy for the health sensor (1.2.4-dev2), which this judgement does not read.

**Integration Health.** An endpoint refused with a router code on a poll, and never answered on this entry, including before a restart, is not a lost capability. It is listed under the `not_served` attribute of the Integration Health sensor and takes no strike, so severity stays `ok`. An endpoint that answered earlier and now refuses still accrues strikes and reads `degraded`. A timeout is not a router code.

**The probe sweep of the diagnostics download** holds the API lock for its duration and reads `device_information` after any probe that does not answer. A `100003` from that read is a lost session: the sweep logs in once through `_login_internal`, which does not take the lock, and repeats the probe, at most twice per sweep. A connection error from the read is unknown and causes no login. The sweep stops at 20 s, after a failed login, after a third loss, or if the client was reset under it, and marks the remaining probes `not_run`. The download records the premise result and the number of sessions lost.

**Known limits.**

- **The router's own refusal of a polled endpoint has not been observed.** No router held refuses one. The refusal path is verified by unit tests built from the report and by a simulated refusal on two routers, in which the premise check and the re-read are real. The first evidence from a B529s is its author's diagnostics download.
- **The premise is measured on two routers and assumed on the B529s.** Where it does not hold there, the history decides.
- **The history fallback is more permissive than failing closed.** It reads a signal from an endpoint that has never answered as a refusal, so a session lost before any endpoint answered reads as a refusal. The task `tighten_premise_failure_fallback_after_ops_download` records the review against the author's download.
- **A refusal can follow the router's state.** The B315s-22 answers the SMS list with `125003` when it has no SIM and answers it with one. An endpoint that answered earlier and later draws such a code is an expiry under the history fallback.
- **The history that decides a refusal is the current run's.** From 1.2.4-dev2 the coordinator persists the answered set for the health sensor, so a capability lost while Home Assistant was stopped reads `degraded`; the judgement above does not read the persisted set.
- **A read outside a poll is adjudicated by `_execute_with_retry`** from 1.2.4-dev2: a refusal on a live session raises with no login, and an expiry logs in once. A write refused with a session code raises `HuaweiWriteRefusedError` and, where it sets a complete state, is sent once more after a fresh login.

### Why a bulk sweep produces false `100003` results

The cause, measured on 2026-09-07, is in the integration rather than the router. `huawei-lte-api` raises `ResponseErrorLoginRequiredException` for `100003` and for no other code; `125002` and `125003` map to `ResponseErrorLoginCsrfException` and `ResponseErrorWrongSessionToken` (`Session.py:189`). Until 1.2.4-dev2, `api.py:_execute_with_retry` opened its handler with `isinstance(err, ResponseErrorLoginRequiredException)`, so a `100003` discarded the client and logged in again. The figures below are for that wrapper; from 1.2.4-dev2 a `100003` on a live session costs a premise check and a re-read of `device_information` and no login.

| Call through the wrapper, before 1.2.4-dev2 | Logins |
| :-- | --: |
| A read that answers | 1 |
| `100002: No support` | 1 |
| `100003: No rights` | 2 |

Every refusal in a sweep therefore costs a logout and a login. A 42-endpoint sweep on 2026-09-07 accumulated enough sessions that the router began answering `LoginErrorAlreadyLoginException` and then refused connections for the rest of the run, and the remaining endpoints reported artefacts. The same 42 calls on one session, made without the wrapper, completed in about 900 ms with every endpoint returning a real outcome. Anything sweeping endpoints outside the polled set bypasses `_execute_with_retry` and calls on one established session, with no delay needed between calls.

---

## ⚠️ Error codes

| Code | Meaning | H165-383 | B315s-22 | What the integration does |
| :-- | :-- | :-- | :-- | :-- |
| `100002: No support` | The hardware or firmware does not implement the call | 51 reads | 106 reads | Nothing: no retry, no sensor |
| `100003: No rights (needs login)` | The router refuses this read, or the session has ended | 38 reads on a live session; every login-only read after an expiry | 0 reads on a live session; every login-only read after an expiry | Adjudicated in the fetch loop (see [Telling a refusal from an expiry](#telling-a-refusal-from-an-expiry)) |
| `100005: Request format error` | The request is malformed for this model | `wlan.wifi_network_switch()` | Not measured | Not called |
| `103005` | Not decoded | Not seen | One diagnostic probe | Recorded as a refusal with its code |
| `108001` | Username wrong (`LoginErrorUsernameWrongException`) | Not measured | Not measured | `HuaweiAuthError`: `invalid_auth` in the dialogs, reauth once the strike budget is spent |
| `108002` | Password wrong (`LoginErrorPasswordWrongException`) | Not measured | Not measured | `HuaweiAuthError`, as `108001` |
| `108003` | Already logged in (`LoginErrorAlreadyLoginException`): the session table is full | The 11th login | Not measured | Not a credentials failure and not a takeover. The liveness probe reads it as a refused second session |
| `108006` | Username and password wrong (`LoginErrorUsernamePasswordWrongException`) | Not measured | Not measured | `HuaweiAuthError`, as `108001` |
| `108007` | Password overrun, the lockout after repeated failures (`LoginErrorUsernamePasswordOverrunException`) | Threshold not measured | Not measured | `HuaweiLockoutError`: `login_attempts_exceeded` in the dialogs, no repair and no reauth |
| `110001` | Busy: simultaneous requests | Not measured | Not measured | Avoided by one lock around every call |
| `115002` | Password modify: the router asks for a password change (`LoginErrorUsernamePasswordModifyException`) | Not measured | Not measured | Not caught as a credentials failure; it reads as a connection failure |
| `125002`, `125003` | CSRF token and session token errors | 0 on a live session; one read returned `125003`, ended the session and answered `100002` on a fresh one | 3 on a live session: two SMS reads and `vpn.toggle_status` | Handled as `100003` |
| `-1: Unknown` | A refusal, or a command applied that the router could not answer for | See below | Not measured | Never read as a refusal on its own; the state is read back |

Sources: the per-model read classes of 2026-10-05, the session measurements of 2026-10-09, and the probe list of 2026-10-05. The library's exception names are from `huawei-lte-api` 2.0.1.

> [!IMPORTANT]
>
> **`-1` is the answer both to a refused command and to a command applied that the router could not answer for.** Two writes draw it, and they mean opposite things:
>
> - **`net.reconnect()`** is refused. The H165-383 does not implement it, and `dialup/dial` is used instead.
> - **`net.set_net_mode()`** is applied and answered badly. On 2026-08-16 a write of `00` from `03` raised `-1`, and the web interface showed Auto immediately afterwards. The radio is re-registering, so the response is as unreliable as an immediate read-back would be.
>
> `api.set_net_mode` therefore waits `NET_MODE_SETTLE` and reads `net_mode` again, and that read alone separates the two cases. `net_mode.NetworkMode` is read back on every hardware check run, so a firmware rename of the key that `confirm_write` compares would show at once.
>
> **`-1` is occasional.** On 2026-08-19 the hardware check wrote `03` from `00` and the router accepted it outright, and what decides it has not been isolated. A mode outside the router's list also answers `-1`, and the read-back disagreeing catches it: on 2026-10-09 a write of `02`, not in the H165-383's list, answered `-1` and left the mode unchanged.

---

## 📥 Reads

| Measure | H165-383 | B315s-22, no SIM | Source |
| :-- | :-- | :-- | :-- |
| Reads tried, taking no required argument | 243 | 251 | 2026-10-05 |
| Answered when logged in | 149 | 86 | 2026-10-05 |
| Answered both anonymously and logged in | 46 | 76 | 2026-10-05 |
| `100002` when logged in | 51, of which 13 were also `100002` anonymously | 106, of which 81 were also `100002` anonymously | 2026-10-05 |
| `100003` on a live session | 38, and a read of `device.information` answered after each | 0 | 2026-10-05 |
| A refused read answers after a fresh login | No: all 38 refused again, on the live session and each on its own fresh login | Not applicable | 2026-10-09 |
| Refused `100003` anonymously and answered logged in | 103 | 32 | 2026-10-05 |
| Polled reads mapped | 23 of 26 | 23 of 26 | 2026-10-05 |
| Polled reads that need a login | 14 | 6 | 2026-10-05 |
| Polled reads that answer without a login | 9 | 11, of which 5 answer `100002` and `sms.get_sms_list` answers `125003` | 2026-10-05 |
| Polled reads refused on a live session | None | None | 2026-10-05 |
| Diagnostic probes | 46 in 1.6 s: 31 answered, 10 `100002`, 5 `100003` on a live session | 46 in 2.2 s, with a SIM: 22 answered, 23 `100002`, 1 `103005` | 2026-10-05 |

The 14 polled reads that need a login on the H165-383 are `device.information`, `net.net_mode`, `sms.sms_count`, `sms.get_sms_list`, `lan.host_info`, `wlan.host_list`, `wlan.multi_basic_settings`, `dial_up.profiles`, `device.antenna_type`, `net.csps_state`, `security.sip`, `security.upnp`, `voice.voicebusy` and `voice.volte`. The 6 on the B315s-22 are `device.information`, `wlan.host_list`, `wlan.multi_basic_settings`, `dial_up.profiles`, `security.sip` and `security.upnp`.

A re-login never makes a refused endpoint answer on the H165-383, so a re-login on a `100003` from one of the 38 costs a login and changes nothing.

### What the integration polls

Twenty-six read endpoints per cycle, all in `api.py::get_data`, are merged into one flat dictionary keyed by block name. Every block key also appears in `const.py::ENDPOINT_NAMES`; a block missing from that map cannot be reported as a degraded capability, so its endpoint could fail every poll while Integration Health stays green.

| Endpoint | Block key | Feeds |
| :-- | :-- | :-- |
| `device.information` | `device_information` | Model, firmware, hardware, WAN IP, DNS, uptime |
| `device.signal` | `device_signal` | 55 keys: RSRP, RSRQ, SINR and RSSI for LTE and NR, bands, cell IDs |
| `monitoring.status` | `monitoring_status` | Connection status, network type, roaming, WiFi user counts |
| `monitoring.traffic_statistics` | `traffic_statistics` | Session and lifetime byte counters, current rates |
| `monitoring.month_statistics` | `month_statistics` | Monthly and daily usage, durations |
| `monitoring.check_notifications` | `monitoring_check_notifications` | Unread SMS, update status |
| `net.current_plmn` | `current_plmn` | Operator name and numeric |
| `net.net_mode` | `net_mode` | Preferred network mode and band masks |
| `dial_up.mobile_dataswitch` | `mobile_dataswitch` | Mobile data on or off |
| `sms.sms_count` | `sms_count` | Inbox, outbox and unread counts |
| `sms.get_sms_list` | `sms_list` | Message list |
| `lan.host_info` | `lan_host_info` | Connected clients, the `device_tracker` source |
| `wlan.host_list` | `wlan_host_list` | WiFi clients |
| `wlan.multi_basic_settings` | `wlan_multi_basic_settings` | SSIDs, guest network state |
| `wlan.wifi_feature_switch` | `wlan_wifi_feature_switch` | 49 WiFi capability flags |
| `monitoring.start_date` | `start_date` | Data plan: allowance, cycle start day, threshold |
| `monitoring.converged_status` | `converged_status` | SIM and country |
| `dial_up.profiles` | `dial_up_profiles` | APN profiles, matched on `Index`, never list position |
| `dial_up.connection` | `dial_up_connection` | Connection settings |
| `device.antenna_type` | `antenna_type` | Antenna selection |
| `net.csps_state` | `csps_state` | Network registration |
| `security.sip` | `security_sip` | SIP ALG |
| `security.upnp` | `security_upnp` | UPnP |
| `voice.voicebusy` | `voice_busy` | Line state; returns a bare string (`Idle`), not a dict |
| `voice.volte` | `voice_volte` | VoLTE status |
| `monitoring.onekey_diag` | `onekey_diag` | Router self-diagnosis, decoded under [`onekey_diag`](#onekey_diag) |

**One further endpoint is read but not polled.** `net.net_mode_list()` is read once, after login, and its `AccessList.Access` becomes the Network Mode select's option list: `00`, `08` and `03` on the H165-383, the three modes its web interface offers. It changes only with a firmware update, so it is not polled. Adopting it is what surfaced `08`.

`lan_host_info` and `wlan_host_list` carry the MAC, hostname and IP of every device on the user's network. No sibling project has that privacy surface, and it is why `diagnostics.py` recurses and pseudonymizes rather than redacting by key name.

### How often the figures change

On the H165-383, on 2026-10-09, one session read `device.signal`, `monitoring.traffic_statistics` and `monitoring.status` once a second for 299 s. The traffic counters, including `CurrentConnectTime`, advanced every 2 s. The per-second link figures (`txpower`, `nrtxpower`, the CQI and MCS fields) changed at nearly every read, and `rsrq`, `rssi`, `sinr` and `nrsinr` every 2 to 4 s. Cell identity, band, frequencies and every `monitoring.status` field did not change. No polled figure holds a value long enough for a poll interval to be derived from it.

### Reads with and without a login

| Read | H165-383 without a login | H165-383 with a login | Source |
| :-- | :-- | :-- | :-- |
| `global_module_switch`, `device_feature_switch`, `net_feature_switch`, `monitoring_statistic_feature_switch`, `system_devcapacity`, `dial_up_feature_switch` | Answered, same values | Answered | 2026-10-09 |
| `sms_feature_switch`, `voice_featureswitch`, `security_feature_switch`, `dhcp_feature_switch`, `cradle_feature_switch` | `100003` | Answered | 2026-10-09 |
| `sntp/timeinfo`, `device/boot_time`, `net/net-mode`, `net/net-mode-list` | `100003` | Answered | 2026-10-09 |
| `device/nbrcellinfo`, `device/seccellinfo`, read through `Connection.get` | `100003` | Answered | 2026-10-09 |

These reads were not compared on the B315s-22.

### `net.current_plmn` and the SIM state

| State | B315s-22 | Source |
| :-- | :-- | :-- |
| No SIM, Ethernet WAN | `net.current_plmn` returns the string `FAILED`, with and without a login. `sms.get_sms_list` called with no argument answers `125003` on a live session | 2026-10-05 |
| SIM fitted and registered on LTE, 5 signal bars | `net.current_plmn` returns a dictionary. `sms.get_sms_list` answers and needs a login. 6 of 243 reads differ between the two states | 2026-10-05 |

Without a SIM the B315s-22's Integration Health sensor read `warning`, with six degraded capabilities and a signal-block drift; with one it read `degraded`, with five degraded capabilities and no drift. The sensor code does not expect the string `FAILED`, and the task `current_plmn_failed_string_crashes_sensors` records the three sensor sites. A router with its WAN on Ethernet shows an empty signal block, a `FAILED` operator string and 53 of 124 entities unknown. The integration has not been tested in that mode, which is a roadmap item.

### The diagnostic probe list

`api.DIAGNOSTIC_PROBES` calls 47 unpolled endpoints once per diagnostics download and records each as answered, refused with the router's own code, or unavailable; the capability probes also record their values (1.2.4-dev1). On the H165-383 on 2026-09-07, of the 46 then probed, 31 answered and 15 were refused, eleven with `100002` and four with `100003`, and none was unavailable. A download from a model not held here therefore states which of those each missing endpoint was.

The five `100003` probes on the H165-383 on 2026-10-05 were `device_autorun_version`, `device_antenna_status`, `device_antenna_settings`, `monitoring_wifi_month_setting` and `dial_up_auto_apn`. Each was followed by a read of `device.information` that answered, except the last. After the last probe that read raised a connection error and not a `100003`, so the session was not shown to be dead, and the connect time of 9793 s afterwards shows the sweep did not restart the data connection. A canary read that raises a connection error is therefore treated as unknown.

**Reads that start something.** `net.plmn_list` starts a network scan. On the H165-383 it timed out in a read sweep and was followed by a brief data-connection restart on two runs, so it is the likely cause. It is not among the `DIAGNOSTIC_PROBES`, and a read sweep of the library excludes it, together with `net.reconnect` and the `accept`, `compress`, `operate` and `toggle` methods.

### Readable endpoints reviewed

This section records a survey. The first table was adopted; the two after it were not. Verdicts are from the field review in `.notes/info/extra_fields/`.

#### Adopted in `[1.2.0-dev11]`

All eight are polled and appear in the polled table above and in `ENDPOINT_NAMES`. They are listed with the values the decision was made on.

| Endpoint | Keys of interest | Value read | Why |
| :-- | :-- | :-- | :-- |
| `monitoring.start_date` | `StartDay`, `trafficmaxlimit`, `MonthThreshold`, `SetMonthData` | `1`, `2147483648000`, `80`, `1` | The data-plan block: cycle day and allowance, the inputs a usage projection needs |
| `dial_up.profiles` | `CurrentProfile`, `Profiles.Profile[]` | `3`, three APNs | APN name and profile |
| `device.antenna_type` | `antenna1type`, `antenna2type` | `0` / `0` | `0` is Internal, `1` is External |
| `net.csps_state` | `psstate`, `csstate` | `1`, `1` | Data and voice network registration |
| `monitoring.converged_status` | `CountryCode`, `SimLockEnable` | A two-letter code, `0` | Country, SIM PIN lock |
| `dial_up.connection` | `MTU`, `RoamAutoConnectEnable` | `1500`, `1` | MTU diagnosis; roaming auto-connect |
| `security.sip` | `SipStatus` | `1` | SIP ALG, the usual cause of one-way VoIP audio |
| `security.upnp` | `UpnpStatus` | `0` | UPnP on or off |

#### Readable, reviewed, not adopted

| Endpoint | Returns | Why not |
| :-- | :-- | :-- |
| `device.boot_time` | `04:48:35` | Duplicates `device_information.uptime`: read together they matched exactly (17,315 s), formatted `HH:MM:SS` |
| `wlan.wlandbho` | `DbhoEnable`, `MloEnable` | Not polled; `DbhoEnable` already arrives in `wlan_multi_basic_settings`. The two fields are the web interface's "5 GHz preferred" and "Wi-Fi band aggregation (MLO)" toggles: see [Radios, bands and the combine toggles](#radios-bands-and-the-combine-toggles) |
| `net.cell_info` | `cellinfo`, `lac` | `cell_id` and `pci` are already exposed from `device_signal` |
| `s_ntp.timeinfo` | Time zone, sync status, servers | Router clock; nothing acts on it. Its format is under [Field formats and traps](#-field-formats-and-traps) |
| `dhcp.settings` | DHCP range, lease, `homerouter.cpe` | Static configuration, not state |
| `device.device_feature_switch` | `onekeydiag_enabled` and others | Capability flags, of use as a precondition check rather than a sensor |
| `net.net_feature_switch` | 9 capability flags | As above |
| `wlan.wifi_feature_switch` | 49 keys, 47 unread | Polled, but almost entirely firmware capability flags rather than state |
| `config_statistic.config` | More than 60 keys | A firmware configuration template dated 2012 whose values are defaults. It mirrors `start_date` but is not live state |
| `device.vendorname` | `version_name='ZOWEE'` | The ODM, not the brand (see [Field formats and traps](#-field-formats-and-traps)) |
| `device.basic_information` | `classify='cpe'`, `devicename`, `spreadname_en` | Every field duplicates `device_information`. HA Core reads it as a fallback where `device.information` is thin, which it is not here |
| `system.deviceinfoex` | `UpTime`, `custinfo`, `devcap` | `UpTime` duplicates `device_information.uptime`; the rest are capability flags, and `devcap.Vendor` is empty |

#### Readable, never reviewed

Found by the endpoint sweep and not assessed as entity candidates. Five are called on every diagnostics download by `api.DIAGNOSTIC_PROBES`, and their shape on the H165-383, measured on 2026-09-07, is in the rows below.

| Endpoint | Keys | Note |
| :-- | :-- | :-- |
| `global_.module_switch` | 94 | The largest capability block on the device. Probed: 94 keys, all populated |
| `security.get_firewall_switch` | 11 | Firewall toggles. Probed: 11 keys, all populated |
| `security.nat`, `.dmz`, `.virtual_servers`, `.mac_filter`, `.url_filter` | 1 to 3 each | Firewall and forwarding configuration |
| `diagnosis.diagnose_ping`, `.diagnose_traceroute` | 11, 6 | The router runs a ping or traceroute on request. Not explored |
| `diagnosis.time_reboot` | 4 | Scheduled reboot, enabled on the reference unit: `enable='1'`, `dayinterval='7'`, `begintime='60'`, `endtime='300'`. A reboot every 7 days, in a window that reads as 01:00 to 05:00 if the times are minutes past midnight; that reading is inferred from the values, not measured. It explains a weekly uptime reset and interacts with reboot detection. `zte_router_5g` exposes an equivalent |
| `online_update.status`, `.configuration`, `.autoupdate_config` | 8, 4, 2 | Firmware update state, which may decode `monitoring_status.OnlineUpdateStatus`. Probed: `status` answers 8 keys, all populated |
| `sms.config` | 16 | SMS settings. Probed on 2026-09-07: 16 keys, 14 populated, and no length ceiling among them. The keys are `SaveMode`, `Sca`, `SendType`, `UseSReport`, `Validity`, `country_number`, `import_enabled`, `maxphone`, `pagesize`, `phone_number`, `sms_center_number_editabled`, `sms_forward_enable`, `smscharlang`, `smsisusepdu`, `switch_enable` and `url_enabled`. `smscharlang` and `smsisusepdu` bear on GSM-7 versus UCS-2 selection |
| `led.appctrlled` | 3 | LED control. Probed: 3 keys, all populated |
| `redirection.homepage`, `staticroute.wanpath`, `dhcp.static_addr_info` | 1 to 2 | Minor configuration |

#### Not wrapped by the library, and answering on the H165-383

A GET-only sweep on 2026-10-10 of the paths named in the H165-383's `/js/main.js` found 18 that the library does not wrap and that answer after a login. Only names and shapes are recorded; none has been assessed for an entity, and a reading's meaning is not known unless stated. From 1.2.4-dev4 all 18 are probed in the diagnostics download, after the other probes, read by path on the established session and recorded by key name only.

| Path | Keys | Note |
| :-- | :-- | :-- |
| `device/nbrcellinfo`, `device/seccellinfo` | 2 each | Neighbor and secondary cells; the field order is under [Field formats and traps](#-field-formats-and-traps) |
| `device/ri` | `ri` | Read 2. By its name the rank indicator, the number of MIMO layers; the meaning is not confirmed by the router |
| `dialup/apn-retry` | `retrystatus` | Read 1. Meaning unknown |
| `monitoring/best-position-status`, `monitoring/best-position-result` | `funcStatus`; none | Read 0 and empty. The web interface's placement test; no way to start it is known, so neither is usable |
| `ntwk/wlan_easymesh` | `mode` | Read 0 |
| `lan/switch-ipmode` | `switchmode`, `ipmode` | Read 2 and 3. Meaning unknown |
| `webserver/accessibility` | `timeout`, `enable` | Also answers without a login |
| `security/wan-ipv6-filter` | `WanIpv6Filters` | Null |
| `dialup/IptvProfile`, `dialup/voice-profiles` | `Profile` | Profile lists |
| `ntwk/childFrame`, `ntwk/childAppList`, `hilink/higame` | 1 to 2 each | Parental-control and game-acceleration lists, empty or off |
| `prsite/homepage`, `prsite/getrandurl` | 2, 1 | Redirect page settings; answer without a login |
| `appturbo/acc-list` | `errcode` | Answers with error 100002 in its body, so it is not readable |

**Path variants.** The web script names more than one path for some resources. On the H165-383 only one of each answers: `system/devcapacity` (not `devcapacity/devcapacity`), `system/deviceinfoex` (not `system/deviceinfo` or `deviceInfo/deviceInfo`) and `device/device-feature-switch` (not `device/device-feature-switchion`). Whether another model answers the other spelling is not measured.

### The voice group is readable

The voice group was first recorded as having no registration status, call state or line status, from a bulk sweep that had produced false `100003` results. Probed again in small batches on fresh connections:

| Method | Value read |
| :-- | :-- |
| `voice.voicebusy()` | `Idle`, the line state |
| `voice.sipaccount()` | SIP proxy and register server addresses, and an account password field |
| `voice.sipserver()` | Server profile, IP type, secondary server |
| `voice.voiperstatus()` | `voiper_enable='1'` |
| `voice.voiceadvance()` | `dtmfmethod='InBand'`, `EchoCancellationEnable='1'` |
| `voice.featureswitch()`, `.functioncode()`, `.speeddial()` | Readable; thin or empty here |

Only `voice.codec()` refuses.

> [!WARNING]
>
> **`voice.sipaccount()` returns a password.** If it is added to the fetch set, the key goes into `diagnostics.py`'s `TO_REDACT` in the same change, because the diagnostics download dumps `coordinator.data` whole.

### Not supported on this hardware

These answer `100002: No support` on the H165-383 and are not added or retried:

`monitoring.daily_data_limit` · `monitoring.month_statistics_wlan` · `wlan.station_information` · `wlan.basic_settings` · `ntwk.celllock` · `system.deviceinfo` · `statistic.feature_roam_statistic` · `user.remember_pwd`

`wlan.station_information` is the notable loss: it would give per-client WiFi signal strength, which nothing else provides.

---

## 📤 Writes and commands

Ten writes, all serialized behind one `asyncio.Lock` and routed through `_execute_with_retry`. Each is classified in `scripts/write_classification.py`, and `tests/test_write_classification.py` fails on an unclassified write.

| Endpoint | Action | Register tier |
| :-- | :-- | :-- |
| `user.logout` | End the session | SAFE |
| `device.set_control(REBOOT)` | Reboot | ATTENDED |
| `monitoring.set_clear_traffic` | Zero the byte counters | ATTENDED |
| `dial_up.set_mobile_dataswitch` | Mobile data on or off | ATTENDED |
| `dial_up._session.post_set` | Reconnect | ATTENDED |
| `wlan._session.post_set` | Master WiFi on or off | ATTENDED |
| `net.set_net_mode` | Preferred network mode | ATTENDED |
| `wlan._session.post_set` | Guest WiFi on or off | ATTENDED |
| `sms.send_sms` | Send a message | ATTENDED |
| `sms.delete_sms` | Delete a message | ATTENDED |

| Command behavior | H165-383 | B315s-22 | Source |
| :-- | :-- | :-- | :-- |
| Reconnect: call returns | 0.2 s | Not measured | 2026-10-09 |
| Reconnect: outage | `CurrentConnectTime` reset by 0.77 s; status 900 seen once; 901 by 1.1 s, on 2 runs | Not measured | 2026-10-09 |
| Reconnect: session | Answered throughout | Not measured | 2026-10-09 |
| Reboot: call returns | 0.56 s | Not measured | 2026-10-09 |
| Reboot: router silent | Last answer 5 to 7 s after the command, silent by 10 to 12 s, first answer again at 68.5 to 72.6 s, on 3 runs | Unreachable from about 18 s to 44 s | 2026-10-09; 2026-10-05 |
| Reboot: data connection up | About 52 s after the command, before the web interface answers | Not measured | 2026-10-09 |
| Reboot: first login after | Refused with a dropped connection at 68.5 s, accepted at 73.7 s | Accepted after 46 s | 2026-10-09; 2026-10-05 |
| Reboot: uptime clock restarts | About 14 s after the command, from `device/boot_time` | Not measured | 2026-10-09 |
| Reboot: integration outcome | Not measured through Home Assistant | One fetch failure logged, no repair raised | 2026-10-05 |
| Network mode: write in the list | `03` applied within 2 s; `ConnectionStatus` 902 at 2.2 s and 901 at 3.3 s | Not measured | 2026-10-09 |
| Network mode: write outside the list | `02` answered `-1` and the mode stayed `00` | Not measured | 2026-10-09 |
| Network mode: restoring `00` through the integration | 17 to 19 s, matching the read-back wait after a `-1`, so the restores were probably answered `-1` and applied | Not measured | 2026-10-09 |
| Master WiFi | `0,0 → 1,1 → 0,0` verified | Not measured | 2026-08 |

### Three spellings that matter

**`device.set_control(ControlModeEnum.REBOOT)`, not `device.reboot()`.** Both exist in 1.11.0, but 2.0.0 removes `reboot()` and `control()` and keeps only `set_control`, so the spelling used is correct on both.

**`monitoring.set_clear_traffic()`, not `Monitoring.clear_traffic()`.** The latter has never existed in the library.

**`dialup/dial`, not `net.reconnect()`.** The library exposes `net.reconnect()` and the router advertises the feature, but the H165-383 refuses it with `-1: Unknown`. Reconnect posts `dialup/dial` with `Action: 0` and then `Action: 1` through `client.dial_up._session.post_set`, then resets the client. It was verified by `CurrentConnectTime` falling from 135 to 5, and in the web interface, on 2026-08-15.

### `set_net_mode` takes bands as well, and they come from the router

`net/net-mode` sets the mode, the LTE band mask and the network band mask together, so a mode change cannot omit the bands. The integration reads the current bands and hands them back. The library constants `LTEBandEnum.ALL` and `NetworkBandEnum.ALL` were sent before; the H165-383 clamps them, reporting `LTEBand=7A0880800D5`, its own supported mask, after a write of `ALL`, and a `NetworkBand` matching neither the value sent nor anything in its published `BandList`. A model taking the value literally would have its band selection reset on every mode change.

**`08` is 5G Only.** The library's `NetworkModeEnum` ends at `MODE_4G_3G_AUTO` and has no 5G member, so a table copied from it cannot name the mode the H165-383 sits in. The library does not constrain the write: `networkmode` is a plain `str`, passed through unvalidated.

**A mode change holds the session.** A network-mode write occupies the router for `NET_MODE_SETTLE` (15 s) plus a read-back, because the router may answer the write with `-1` and only a re-read after the radio settles shows whether the mode took. No other command holds the session as long, and nothing else is sent to the router while it does.

### The master WiFi switch works at the RADIO level, not the SSID level

The per-SSID flags in `wlan/multi-basic-settings` are gated by the radio, and writing them while the radio is off changes nothing observable. The radio state is `wlan/status-switch-settings`, as `wifienable` per radio, and turning WiFi on or off writes that block back whole. The library's own `wlan.wifi_network_switch()` answers `100005: Request format error` on the H165-383, so it is not an alternative. The current WiFi state is read from `monitoring_status.WifiStatus`, which is already polled.

### Radios, bands and the combine toggles

Measured on the H165-383 on 2026-10-23, with the owner changing each setting in the router's web interface between reads. Recorded in [`changelog_local.md` `[1.2.4-dev7]`](changelog_local.md#124-dev7---2026-10-23---access-reference-and-task-queue-radio-band-and-guest-wifi-fields-measured-queue-refined-defensive-behavior-audit-closed).

| Field | Meaning | Values observed |
| :-- | :-- | :-- |
| `wlan/status-switch-settings` `Radio.1.` `wifienable` | 2.4 GHz radio on | `0` and `1` |
| `wlan/status-switch-settings` `Radio.2.` `wifienable` | 5 GHz radio on | `0` and `1` |
| `wlan/wlandbho` `DbhoEnable` | "5 GHz preferred": the two bands are combined and shown as one network, and 5 GHz is preferred when signal strength is equal; off, the bands are used separately | `False` and `True` |
| `wlan/wlandbho` `MloEnable` | "Wi-Fi band aggregation (MLO)": Wi-Fi 7 devices connect on several bands at once by multi-link operation, when Wi-Fi 7 mode, 5 GHz preferred and a security mode are set | `True` |

- **Neither WLAN block names a band.** A radio entry carries only `ID`, `index`, `wifienable` and `RestrictState`, and an SSID entry in `wlan/multi-basic-settings` has no frequency field. The mapping above comes from the trial, not from the API.
- **With "5 GHz preferred" on, both radios read `wifienable` `1`.** The web interface then offers no per-band control.
- **`DbhoEnable` is in two blocks.** `wlan/wlandbho` and `wlan/multi-basic-settings` both carry it. It is not band steering in the sense of a separate feature: it is the combine toggle.
- **`wifi_feature_switch` `dbhoswitchshow` is `1`** on this router, which reads as the flag that shows the combine toggle in the web interface.
- **The library reads `wlan/wlandbho` and `wlan/status-switch-settings` on 1.11.0 and 2.0.1, and has a setter for neither.**
- **Separate mode renames the 5 GHz network.** With "5 GHz preferred" off, the 5 GHz SSID gains the suffix in `wifi_feature_switch` `wifi5gnamepostfix` (`_5G`); combined, both bands share one name.
- **Turning a band off in the web interface turns its SSIDs off, and turning it on restores them.** With the 2.4 GHz band off, `Radio.1.` and every SSID under it, the guest SSID included, read `WifiEnable` `0`; with the band back on, each SSID returned to its previous state. `monitoring_status` `currenttotalwifiuser` halves with one radio off (128 to 64).
- Not yet measured: which block accepts a `DbhoEnable` write, and whether a write to one radio leaves the other unchanged.

### Guest WiFi state and settings

Measured on the H165-383 on 2026-10-23, with the owner changing each setting in the web interface between reads. Recorded in [`changelog_local.md` `[1.2.4-dev7]`](changelog_local.md#124-dev7---2026-10-23---access-reference-and-task-queue-radio-band-and-guest-wifi-fields-measured-queue-refined-defensive-behavior-audit-closed).

| Setting | Field | Values observed |
| :-- | :-- | :-- |
| Guest on or off | `wlan/multi-basic-settings`, the SSID with `wifiisguestnetwork` `1`, `WifiEnable` | `0`, `1` |
| Duration | `wifiguestofftime`, written to every SSID in the block | `4` (4 hours, the default), `24` (1 day), `0` (unlimited) |
| Security | the guest SSID's `WifiAuthmode`, with `WifiBasicencryptionmodes` or `WifiWpaencryptionmodes` | `OPEN` with `NONE`; `WPA/WPA2-PSK` with `MIX` |
| Time remaining | `wlan/guesttime-setting` `remaintime`, in seconds | Counting down with a limited duration (`86244`, then `86163` 81 s later); `0` with an unlimited duration and with guest off |

- **The guest network is on the 2.4 GHz radio only** (`Radio.1.Ssid.3.`).
- **The router stores the guest choice and its settings.** With guest on, turning the 2.4 GHz band off set the guest SSID's `WifiEnable` to `0`, and turning the band on restored `1`. With guest off, the band cycle left it `0`. While the band is off, `WifiEnable` reads `0` whatever the stored choice, so the guest state is unknown then. Duration and security are kept while guest is off.
- **The web interface offers the guest settings only while guest is on.**
- **`wlan/guesttime-setting`** also returns `isvalidtime`, `1` in every state read, and `extendtime`, `30` in every state read; their meanings are not established. It answered after login with guest on and off, at a limited and an unlimited duration. The 2026-10-10 sweep recorded it, and `time/timeout`, as `100003`; both answer when read on their own, which matches the false refusals described under [Why a bulk sweep produces false `100003` results](#why-a-bulk-sweep-produces-false-100003-results).
- **Passwords are not readable.** Every key field (`WifiWpapsk`, `MixWifiWpapsk`, the WEP keys) reads `null`.
- Not yet measured: whether a write of `wifiguestofftime` or of the guest security through the guest write path holds.

### Guest WiFi deliberately bypasses the public setter

The library's `client.wlan.set_multi_basic_settings()` builds its own payload, `{'Ssids': {...}, 'WifiRestart': 1}`, and discards every other top-level key. On the H165-383 `multi_basic_settings()` returns three keys: `Ssids`, `DbhoEnable` and `modify_guest_ssid`. The public setter would therefore drop band-steering and guest-SSID state on every guest toggle, and the router accepts the truncated block without complaint. The guest write goes to `wlan/multi-basic-settings` through `client.wlan._session.post_set` instead, keeping the keys it does not set. The code-side decision and its test guard are in [`DEVELOPMENT.md`](DEVELOPMENT.md).

---

## 📨 SMS

| Behavior | H165-383 | B315s-22 | Source |
| :-- | :-- | :-- | :-- |
| Longest outgoing message | 612 GSM-7 characters or 268 UCS-2, four segments, from the web interface | Not measured | Web interface |
| `Date` on a received message | Local time, `YYYY-MM-DD HH:MM:SS`, no offset, within 1 s of the send time | Not measured | 2026-10-09 |
| `Date` on a sent message | The same form, in the sent box | Not measured | 2026-10-09 |
| `Smstat` | 0 unread and 1 read in the inbox; 3 in the sent box | Not measured | 2026-10-09 |
| A send | Accepted, received 5 to 7 s later, `LocalOutbox` up by one and `LocalDraft` unchanged, on three sends | Not measured | 2026-10-09 |
| Arrival | In the local inbox at the first read, 2.3 s after the send, on three messages | Not measured | 2026-10-09 |
| A delete | Taken effect by the time the router replies: gone at the first read, within 30 ms, in 8 inbox and 10 sent-box deletes | Not measured | 2026-10-09 |
| Deleted-message box | None: `LocalDeleted` stayed 0 | Not measured | 2026-10-09 |
| SMS list without a SIM | Not applicable | `125003` on a live session | 2026-10-05 |

**Length.** Both ceilings divide exactly by one segment, 612 = 4 × 153 and 268 = 4 × 67, so the H165-383 concatenates at most four segments; `zte_router_5g` allows five. The content decides which ceiling applies: one emoji or curly quote forces UCS-2 for the whole message. The figures are read from the web interface, not measured through the API, and `sms.config` carries no length ceiling (see [Readable, never reviewed](#readable-never-reviewed)). Behavior past four segments is untested, and the integration refuses such a message.

**Checked delete.** The integration's checked delete and its delete all were run against the H165-383 on 2026-10-09 and passed. Delete all reading a second page was not exercised, because the inbox held fewer than 50 messages.

---

## 🔤 Field formats and traps

**`DataLimit` is a display string; `trafficmaxlimit` is bytes.** `'2000GB'` needs parsing and carries a GB or GiB ambiguity, while `2147483648000` is the same figure as an integer (2000 × 1024³). The integration uses `trafficmaxlimit`.

**The router's statistics page is in GiB.** Its "156.96 GB" is `CurrentMonthDownload + CurrentMonthUpload` divided by 1024³, to the byte, and its "GB" and "TB" labels mean GiB and TiB throughout.

**`MonthDuration` counts from the billing cycle start, not from the last manual clear.** It measured 1,202,664 s, 13.92 days, against a `StartDay` of 1 on 14 August. `MonthLastClearTime`, `2026-04-18`, is the manual counter reset and is unrelated.

**`workmode` reports the LTE anchor, not the aggregate.** It reads `LTE` while `EndcStatus=1` and `SignalIconNr=5` show the modem attached to 5G NSA, so it is not presented as the current network type.

**`device_signal.band` is the full carrier aggregation; `bandInfo` is only the primary.** `band` returns `20MHz@<channel>(B1) + 15MHz@<channel>(B3) + ...` while `bandInfo` returns `B1`.

**`dial_up.profiles` returns profiles out of order.** The list came back indexed 1, 3, 2, so `CurrentProfile` is resolved by matching the `Index` field, never by list position.

**`device.vendorname` returns the ODM, not the brand.** It answers `{"version_name": "ZOWEE"}` on the reference unit, the contract manufacturer. `manufacturer` is a hardcoded `"Huawei"` in `helpers.py` and `__init__.py` for this reason. No brand field exists on the H165-383: probed on 2026-08-16, `device.information` has none, `device.basic_information` gives only `classify: cpe` and `devicename`, and `system.deviceinfoex` carries `devcap.Vendor` as an empty string. Brovi and SoyeaLink units therefore also show as Huawei, which the README states under Compatibility.

**`antenna1type` and `antenna2type` report the antenna in use, not the setting.** Decoded on 2026-08-15 by a controlled change: `0` is Internal and `1` External, both moving with the web interface. Under Auto they read `1`, the antenna the router chose. The configured mode is behind `device.antenna_status`, which is refused. Mix is the two values disagreeing.

**`antenna1insertstatus` and `antenna2insertstatus` carry no information on the H165-383.** Both stayed `1` across every antenna setting, so the field does not show that an external antenna is plugged in.

**`ImeiSvn` is not part of the IMEI and is not redacted.** It is the IMEI Software Version Number, a two-digit manufacturer revision counter, `01` on the reference unit. It carries no subscriber or device identity, and `SoftwareVersion` and `iniversion`, both published in full, say more about the same build. No entity exposes it.

**`maxsignal` is the bar-scale denominator.** It reads `5` beside `SignalIcon = 4`, four bars of five. It is constant and not exposed, but it is what makes `SignalIcon` interpretable.

**`WifiMacAddrWl0` and `WifiMacAddrWl1` are the 2.4 GHz and 5 GHz radio MACs**, and are already present as `WifiMac` in the SSID list.

**`scc_pci` is a secondary carrier's physical cell ID.** Under carrier aggregation `pci` identifies the primary cell and `scc_pci` one of the secondaries.

**Identifiers are digits that are not quantities.** `Imei`, `Imsi`, `Iccid`, `Msisdn`, `SerialNumber`, `Mccmnc` and `scc_pci` carry no `state_class`, `device_class`, unit or display precision; with any of them set, Home Assistant coerces the value, turning `01` into `1` and a 15-digit IMEI into scientific notation.

**Several status fields are undecodable codes.** `SimState=257`, `CurrentNetworkTypeEx=1011`, `CurrentServiceDomain=3`, `OnlineUpdateStatus=14` and `cellroam=2`. The library ships enums only for `NetworkMode`, `NetworkBand`, the SMS box types and `SaveMode`, and Huawei publishes no specification. A typed endpoint is preferred to a guess: `net.csps_state` supersedes `CurrentServiceDomain`, and `converged_status.SimLockEnable` supersedes `simlockStatus`. `online_update.status()` returns `CurrentComponentStatus='14'`, the same `14` as `monitoring_status.OnlineUpdateStatus`, which may decode it; this has not been pursued.

**Neighbor and secondary cells.** `device/nbrcellinfo` returns `nbrcell_ltelist` and `nbrcell_nrlist`, and `device/seccellinfo` returns `lteseccell_list` and `nrseccell_list`. Each is a string of records separated by `;`, each record of fields separated by `,`: seven fields for a neighbor cell and eight for a secondary cell, which adds a bandwidth after the band. The order was measured on the H165-383 on 2026-10-10 by reading both lists beside `device.signal`, whose fields are named: channel number (EARFCN or NR-ARFCN, matching the `band` string), band, bandwidth (secondary cells only), PCI (matching `scc_pci` and the PCIs in `nei_cellid`), RSRP and RSRQ (matching `nrrsrp` and `nrrsrq` for the NR secondary cell), RSSI, and SINR (matching `nrsinr`). RSSI is the remaining field by elimination, because `device.signal` reported no NR RSSI. A neighbor record's last field is the SINR position and reads `--`. The neighbor list includes the secondary carrier's own cell, and `nbrcell_nrlist` was null on every reading.

**Time.** On the H165-383 `sntp/timeinfo` returns `currentlocaltime` as local time with no offset, `localtimezonename` as a POSIX time-zone rule including the daylight-saving rule, `currenttimezone` as the standard offset, unchanged during daylight saving, and `syncstatus`. The current offset is therefore derived from the rule and the date, or from `currentlocaltime` against UTC; `currenttimezone` alone gives the wrong offset in summer. An SMS `Date` carries no offset either (see [SMS](#-sms)).

### `onekey_diag`

The block is a set of causes behind one verdict. It was decoded on 2026-08-15 by taking mobile data down and reading it in both states; a reconnect does not serve, because the router redials (`auto_dial_switch=1`) within four seconds.

| Field | Connected | Disconnected |
| :-- | :-- | :-- |
| `connection_status` | `2` | `8` |
| `dialupswitch_off` | `0` | `1` |
| `apnstatus` | `0` | `2` |
| The other seven | `0` | `0` |

`connection_status` is the verdict, and `2` means healthy; it is not a boolean. The other nine read `0` when there is nothing to report, and the two that moved named the cause: the dial-up switch was off, and the APN could not come up as a result. `speedLimitStatus` appears here and in `monitoring_status`, agreeing in both. Only `2` and `8` have been observed, so a check of `!= "2"` is sound and a check of `== "8"` would be a guess about every other code.

---

## 🆕 Library versions

The integration runs on `huawei-lte-api` 1.11.0 or 2.0.1. Home Assistant core pins 1.11.0 for its own `huawei_lte` integration, so the two methods that exist only from 2.0.1, `voice.volte` and `monitoring.onekey_diag`, are replaced on 1.11.0 by reads of their router paths, `voice/volte` and `monitoring/onekey_diag`, through the library session (from 1.2.4-dev4). Which version runs, what each does and why both are supported are in `docs/library_versions.md`.

The surfaces of 1.11.0 and 2.0.1 were compared by unpacking both and enumerating every group, method signature, enum member and exception. 70 groups and 336 methods became 70 groups and 340 methods, with no new group, enum change or exception change; most signature differences are typing changes from `Dict[str, Any]` to `dict[str, Any]`.

| Method added in 2.0 | Value read on the H165-383 | Worth |
| :-- | :-- | :-- |
| `monitoring.onekey_diag()` | Ten fields, decoded under [`onekey_diag`](#onekey_diag) | The router's own self-diagnosis; polled |
| `voice.volte()` | `volte_enable='1'`, `ui_display_ims='1'` | VoLTE state, which the SIP ALG flag is not; polled |
| `wlan.guesttime_setting()` | `isvalidtime='1'`, `remaintime='0'`, `extendtime='30'` | Guest-WiFi time limit |
| `security.acl()` | `https_enable='1'`, `icmp_enable='0'`, `acs_enable='0'` | Remote-management access control |
| `user.rule()` | Password length and complexity policy | Low |
| `diagnosis.wan_service_name()` | `'INTERNET'` | Low |

`device.control` and `device.reboot` were removed in 2.0. The integration calls `device.set_control(ControlModeEnum.REBOOT)`, which both versions provide.

---

## 🔬 Not measured

| Measure | H165-383 | B315s-22 |
| :-- | :-- | :-- |
| Lockout threshold, the code a wrong password returns, and `lockstatus` and `remainwaittime` during a lock | Three wrong passwords lock logins for about 65 s; `lockstatus` 1 and `remainwaittime` during the lock, 0 after (2026-10-10); read before each login from 1.2.4-dev4 | Not measured |
| Delete all across more than one inbox page | Not measured | Not measured |
| A write refused with `100003` | Not produced | Not produced |
| A request that draws no answer | Not produced | Not produced |
| Session cap and idle lifetime | Measured | Not measured |
| Reconnect timing | Measured | Not measured |
| Path variants other than those listed | One spelling of each answers | Not measured |

The register of measurements not yet made is kept with the project notes as `info/router_measurements_register.md`.

---

## 📚 Related documents

- `ha-zte-router-5g-monitor/docs/zte_how_to_access.md`: the ZTE companion, organized by `cmd` name because that interface is two endpoints with a parameter.
- `ha-unifi-network-monitor/docs/api_endpoints.md`: the UniFi companion, organized by URL.
- `.notes/info/extra_fields/extra_fields_decide_202608.md`: the field-by-field review behind the verdicts above, with the sub-device, category and default decisions.
- `.notes/info/extra_fields/extra_fields_202608.md`: the working notes and evidence behind it.

> [!NOTE]
>
> **This document wins over both `extra_fields` files where they disagree**, and they disagree in two places, both reversed by measurement after that review: `net.reconnect()` is refused and Reconnect is `dialup/dial` (see [Three spellings that matter](#three-spellings-that-matter)), and the voice group is readable (see [The voice group is readable](#the-voice-group-is-readable)). Those files remain the record of the entity-level decisions, which this document does not repeat.

- `docs/all_sensors.md`: which entity each polled field becomes.
- `docs/DEVELOPMENT.md`: architecture, and the reasoning behind the guest-WiFi write path.
- `docs/ha_compatibility.md`: Home Assistant deprecations the integration absorbs.
- `docs/library_versions.md`: which `huawei-lte-api` version runs, what each does, and what the integration does when Home Assistant core pins a different one.
