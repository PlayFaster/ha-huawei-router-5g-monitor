# Development & Architecture Notes: Huawei Router 5G Monitor

## 1. Project Objective

To develop a high-performance Home Assistant custom component for monitoring and managing Huawei LTE/5G Routers. The integration leverages the `huawei-lte-api` library to interface with the router's XML-based Web API, extracting signal metrics (RSRP, RSRQ, SINR), data usage, SMS management, and connected client information into the Home Assistant ecosystem.

## 2. Architecture & File Structure

The integration follows the standard Home Assistant Custom Component pattern, optimized for asynchronous performance and declarative entity management.

### Core Files (`custom_components/huawei_router_5g/`)

- **`api.py`**: Async wrapper for `huawei-lte-api`. Handles authentication (including session/token management), XML parsing, and safe execution of blocking library calls in the HA executor.
- **`coordinator.py`**: Specialized `DataUpdateCoordinator` implementation. Centralizes polling logic to ensure efficient data retrieval across multiple API endpoints (Signal, Traffic, SMS, LAN Clients). Includes the "3-strike" glitch protection rule.
- **`__init__.py`**: Manages the integration lifecycle (setup/unload). Implements background initialization to ensure a 0ms impact on Home Assistant startup time.
- **`sensor.py`**: Defines 100+ entities using declarative `value_fn` callbacks. Handles complex unit conversions (e.g., Duration to ISO Timestamp) and applies guard bands.
- **`binary_sensor.py`**: Maps boolean states such as connection status, LTE carrier aggregation, and unread SMS presence. Also carries the **Integration Health** sensor (`dev_standards` Section 19), which is always available — never `unavailable` — and reports capability degradation, contract drift and total outage.
- **`switch.py`**: Implements "Pause Polling" to stop API calls without disabling the integration.
- **`button.py`**: Triggers stateless actions such as Refresh Now, Reboot, and Clear Traffic Statistics. "Refresh Now" forces an immediate coordinator poll via `async_force_refresh()`, which sets a one-shot flag so the fetch happens **even while Pause Polling is on** — a bare `async_request_refresh()` is silently swallowed by the pause short-circuit at exactly the moment the user wanted fresh data.
- **`number.py`**: Provides UI control over the refresh interval with persistent storage in `ConfigEntry` options. The write is debounced by two seconds and **flushed rather than canceled** on removal — a reload lands inside that window (an options change is enough), and canceling discarded the value silently.
- **`config_flow.py`**: Manages initial setup and reconfiguration, implementing the "Flat Identity" pattern by persisting hardware metadata (Model, MAC, Version) at boot. Normalizes the host input (`_clean_host`) before storage, and on edit screens leaves credential fields blank (masked, never pre-filled) — restoring the stored password on a blank submit via `_merge_credentials`, so the password can be re-set without ever being displayed.
- **`helpers.py`**: Contains robust parsers for SMS lists and technical metric sanitization (e.g., stripping 'dBm', 'MHz' suffixes).

## 3. Historical Architectural Shifts

The project was built from the ground up using the latest "PlayFaster" standards, incorporating lessons learned from the ZTE and TP-Link monitor projects.

### Transition from `huawei_lte` Legacy Patterns

- **Initial State**: Reference projects often used the legacy `huawei_lte` core integration pattern, which can be complex and sometimes blocks the event loop.
- **Change**: Developed a flat, declarative architecture using the `DataUpdateCoordinator` and `EntityDescription` patterns.
- **Result**: A faster, more stable integration that is easier to maintain and extend with new sensors.

### Declarative Entity Engine (v1.0.0)

- **Change**: Moved all business logic out of the Entity class and into metadata descriptions.
- **Benefit**: Reduced thousands of lines of code into a maintainable list of descriptions. Adding a new sensor now requires only a single line of metadata.

### Sub-Device Granularity (v1.0.0)

- **Standard**: Grouped entities into six functional sub-devices: **System, Signal, Data, SMS, WiFi, and Clients**.
- **Benefit**: Prevents "entity fatigue" in the HA UI and provides a cleaner organization in the Device Registry.

### Dynamic Radio Mapping (v1.0.2-dev4)

- **Change**: Moved from hardcoded radio indices to a path-based discovery model for WiFi radios.
- **Logic**:
  1. Fetch all SSIDs via the `wlan_multi_basic_settings` API.
  2. Search for SSIDs by their firmware `ID` path fragment (e.g., `Radio.1` for 2.4GHz, `Radio.2` for 5GHz).
  3. Dynamically map status and configuration switches to the correctly discovered index.
- **Reason**: Huawei routers frequently shift radio indices between firmware versions (the "Index 5" bug).
- **Result**: Rock-solid WiFi status monitoring and switching across all H165-383 firmware variants.

## 4. Success Patterns

### MAC-Based Stable Unique ID (v1.0.3-dev4)

- **Pattern**: Use the router's MAC address as the config entry unique ID, not the host URL. A MAC address is hardware-stable and survives IP address changes, DHCP lease renewals, and router reconfiguration.
- **Normalization**: Normalize at the earliest point — inside `_validate_credentials()` before the value is returned and stored in `entry.data`. Strip colons and dashes, convert to lowercase: `mac.lower().replace(":", "").replace("-", "")`. This gives a consistent format (`001122aabbcc`) regardless of how the router reports it.
- **Fallback**: If none of the MAC fields are populated (rare on edge-case hardware), fall back to the host URL so setup doesn't fail. The fallback is `info["mac"] or user_input[CONF_HOST]`.
- **Cascade effect**: All entity `unique_id`s are derived from the config entry unique ID (`{entry.unique_id}_{sensor_key}`). Changing the unique ID scheme changes every entity's `unique_id` — requiring a delete-and-readd of the integration. This is acceptable for new projects with no existing users; for published projects it requires a migration strategy.

### Guest WiFi Writes Bypass the Library's Public Setter (v1.2.0)

- **Decision**: `set_guest_wifi` posts to `wlan/multi-basic-settings` through `client.wlan._session.post_set` rather than the public `client.wlan.set_multi_basic_settings()`, under a reasoned `# noqa: SLF001`.
- **Why the public setter is wrong here**: it builds its own payload — `{'Ssids': {'Ssid': clients}, 'WifiRestart': 1}` — and therefore **discards every other top-level key the router returned**.
- **Evidence**: probed against a live B535 on 2026-08-14, `multi_basic_settings()` returns three top-level keys: `Ssids`, `DbhoEnable` and `modify_guest_ssid`. Using the public setter would silently drop band-steering and guest-SSID state on every guest-WiFi toggle.
- **Correction to an earlier note**: a previous comment claimed the library exposed no public setter. That was false — `set_multi_basic_settings` exists, and existed in 1.11.0. The reason to avoid it is what it does, not its absence.
- **Guarded by**: `tests/test_api.py::test_set_guest_wifi_*`, which asserts `post_set` is called. A swap to the public setter fails that test **by design**; the failure is the guard working, not a test needing an update.

### The Master WiFi Switch Works at the Radio Level, Not the SSID Level (v1.2.0)

- **Decision**: `set_wifi` reads `wlan/status-switch-settings`, flips `wifienable` on **every** radio, and writes the block back whole. It does not touch the per-SSID flags in `wlan/multi-basic-settings`.
- **Why an earlier attempt failed**: that attempt wrote the SSID flags. **The SSID flags are gated by the radio**, so writing them while the radio is off changes nothing observable — which is also why the Guest switch works while a WiFi switch built the same way did not.
- **The library's own setter is unusable here**: `wlan.wifi_network_switch()` answers `100005: Request format error` on this hardware.
- **Evidence**: verified `0,0 → 1,1 → 0,0` against a live B535.
- **State source**: `monitoring_status.WifiStatus`, which is already polled. Reading the radio block would be a second round trip for the same fact.

### Write Confirmation Keeps Three Outcomes Apart (v1.2.0, Section 22)

- **Decision**: a write is confirmed by re-reading **one** endpoint — `api.read_back()`, restricted to an explicit `READ_BACK_ENDPOINTS` map — rather than by a coordinator refresh.
- **Why**: `async_force_refresh()` is subject to HA's 10-second debounce and fetches all 26 endpoints to learn one flag. During that window the frontend's optimistic toggle reverts and then corrects itself.
- **The part that matters**: three outcomes stay distinct. Read agrees → publish immediately. Read disagrees **twice** → raise a translated error. Read failed or omitted the key → **unverified, not failed**: log, publish nothing, raise nothing, and let the next scheduled poll settle it. Collapsing the third into the second reports working commands as broken on every transient blip.
- **No refresh on the unverified path.** Forcing one would re-ask all 26 endpoints when the router has just failed to answer one — more work than the debounce this replaced, at the moment the router is least able to serve it.
- **The retry is not optional**: these routers commonly answer the first read after a write with the _old_ value, so a single read would report accepted-then-applied writes as refusals.
- **Exclusions**: anything that re-establishes the connection answers abnormally _while succeeding_. **Reconnect** therefore has **no reader** in the map, held by a test.
- **Network mode was excluded for that reason and no longer is (2026-08-16).** The reasoning was right but drawn too widely: re-registering the radio makes the router's answers unreliable **for a while**, not permanently. Where the resulting state is readable once things settle — the mode is, a dial is not — the answer is to wait and read, not to give up on confirming. `set_net_mode` now settles for `NET_MODE_SETTLE` and re-reads `net_mode`.
- **The router answers the write itself with `-1: Unknown` while applying it.** Verified live. So the POST response is no more trustworthy than an immediate read-back, and treating it as authoritative produced the opposite defect to the one this section fixed: an error reported for a change that worked. A genuine refusal answers `-1` too — only the read-back separates them.

### Options Changes Reload; Tuning Changes Do Not (v1.2.0, Section 9)

- **Decision**: `entry.add_update_listener` with a `LIVE_OPTION_KEYS` allow-list holding `scan_interval` and `stop_polling`. Everything outside it reloads the entry.
- **Why**: `async_setup_entry` hands host, username and password to the API object once. Without a listener an Options edit validated, wrote the entry, and changed nothing until a restart — while Reauth and Reconfigure both reloaded, so the same three fields behaved differently depending on which dialog was used.
- **Why an allow-list rather than reloading always**: the two polling controls are read fresh every cycle, and reloading on them would tear down the session and rebuild every entity each time the interval slider moved.
- **Ported from `zte_router_5g`**, including its `reload_signature` — comparing signatures is what tells a connection change from a tuning change.

### The Network Mode List Comes From the Router, and the Order It Is Read In Matters (v1.2.0)

- **Decision**: the select's options are read from `net.net_mode_list()` once after login, stored on the coordinator, and exposed through an `options` **property** on the entity. The entity description's list is only a fallback.
- **Why not a hardcoded list**: the original was copied from `huawei-lte-api`'s `NetworkModeEnum`, which ends at `MODE_4G_3G_AUTO` and **has no 5G member at all** — it predates 5G. The result on a 5G router was an eight-option list containing five modes the hardware rejects and missing `08`, the mode it was actually in. The library never forced this: `set_net_mode` takes `networkmode` as a plain `str` and passes it through unvalidated.
- **Why a property and not a value fixed at setup**: platforms are forwarded **before** the router is logged in (Section 1, non-blocking startup). Reading the list during `async_setup_entry` finds no client, fails, and falls back — on every startup, silently.
- **Why it is read before `coordinator.async_refresh()`**: `async_refresh` is what makes every entity write its state. Setting the list after it leaves the first state write carrying the fallback options, and nothing writes again until the next scheduled poll — **three minutes of wrong options by default**. This shipped briefly and was invisible: the log said initialization completed, the router answered correctly when queried by hand, and two restarts reproduced it exactly.
- **Why it is nonetheless guarded**: the list is a cosmetic label; the data fetch is not. An intermediate revision read it first with no guard of its own, and a failure took the whole initialization down. Both constraints hold at once — read it first, and never let it stop what follows.
- **The ordering is now asserted**, in `tests/test_init.py::test_supported_net_modes_is_read_before_the_first_refresh`, on **call order** rather than on the resulting value — the value is correct either way, only the timing is wrong. Verified by swapping the two lines and watching that test, and only that test, fail.
- **An unmapped code renders `Unknown (nn)` rather than disappearing**, matching `network_type`, and round-trips back to the code so the mode stays selectable. Had the select done this from the start, `08` would have surfaced immediately instead of reading as `unknown` — indistinguishable from a dead endpoint.
- **Hardware scope**: a router that cannot or will not publish an `AccessList` keeps the full fallback list, so no device is worse off than before. A code nobody has seen is still offered and still selectable.

### Concurrency Locking Pattern (v1.1.0)

- **Change**: Implemented an `asyncio.Lock` in `HuaweiRouter5GAPI` to serialize all router communication.
- **Reason**: Huawei routers often crash or return empty XML if hit with overlapping requests (e.g., a background poll occurring while a user sends an SMS).
- **Result**: Guaranteed session stability and eliminated "Busy" or "System Error" (110001) responses during heavy activity.

### The Lock Is Not Reentrant, and Nothing Above It Could Clear a Wedged One (v1.2.0-dev56)

- **A non-reentrant lock plus a helper that re-acquires it is a hang, not an error.** `set_net_mode` held `self._lock` and, on the router's `-1` answer, called `confirm_write` → `read_back`, which opens with the same lock. The task waited on itself for ever: no exception, no log, no recovery, and the whole integration offline until Home Assistant restarted. `switch.py` had the correct shape all along — confirm from the entity, after the API call has returned and released.
- **Stubbing that helper in tests hides it completely.** All four `-1` tests patched `confirm_write` with an `AsyncMock`, so `read_back` was never entered. 830 tests passed against code that deadlocked on every use of the control. A mock placed exactly where two components meet tests each half and never the join.
- **The layer that imposes a timeout owns the cleanup.** `asyncio.timeout(FETCH_TIMEOUT)` lives in `coordinator.py` and cancels the await from outside `api.py`, so none of that module's `except` blocks run and none of its `_reset_client()` calls fire. The API object kept its wedged client for ever. `coordinator` now calls `api.invalidate()` on `TimeoutError`, which is what turns any hang inside `get_data` — not just this one — into a single failed poll.
- **Guards now in place**: `_locked()` raises `RuntimeError` on re-entry by the same task (naming the operation), and bounds acquisition at `LOCK_TIMEOUT`, so a jam is a loud repeating error instead of a silent permanent one.

### Timestamp-Based SMS Tracking (v1.1.0)

- **Change**: Pivoted the `_check_new_sms` logic from comparing slot indices to comparing message dates.
- **Logic**:
  1. Store `last_sms_timestamp`.
  2. Maintain a `fired_sms_hashes` set of `{index}_{date}` to deduplicate messages arriving in the same second.
  3. Sort incoming messages chronologically before firing events.
- **Benefit**: Solves the "Slot Reuse" bug where a new message occupying a lower-numbered empty slot was previously ignored.

### Advanced Service Architecture (v1.1.0)

- **Change**: Expanded the service layer to include `delete_sms`, `delete_all_sms`, and `get_sms_list`.
- **Feature**: `get_sms_list` utilizes `SupportsResponse.ONLY`, allowing Home Assistant automations to programmatically ingest SMS content.
- **Implementation**: Service handlers use explicit `async def` wrappers to ensure coroutines are properly awaited by Home Assistant's service bus, preventing the "expected dictionary, but got coroutine" error.

## Other

- **`DataUpdateCoordinator`**: Essential for consolidating multiple API calls (Signal, Traffic, SMS, Clients) into a single orchestrated update cycle.
- **Flat Identity Strategy**: By storing Model, Version, and MAC in `entry.data` and loading them at `__init__`, the integration provides stable metadata to the UI instantly at boot, even if the hardware is offline.
- **Declarative Guard Bands**: Validating sensor values against realistic boundaries (e.g. -150 to -30 dBm for RSRP) before committing them to the state machine ensures data integrity in long-term statistics. The bands are listed per key in [`value_min_max.md`](value_min_max.md), which is **reconciled against the code by a test in both directions** — it had silently drifted before that test existed.
- **Dual Duration/Timestamp Sensors**: Providing both raw durations (disabled by default) and calculated timestamps (enabled by default) for metrics like Uptime and Connection Time, catering to both automation and UI needs.
- **High-Fidelity Logging**: Utilizing `_LOGGER.exception()` for all critical failure paths ensures full tracebacks are available in Home Assistant logs for remote debugging, while downgrading transient session timeouts to `DEBUG` keeps logs clean for end-users.
- **Architectural Consolidation**: Extracting highly duplicated properties like `device_info` into centralized helpers (e.g., `build_device_info`) to enforce DRY principles across 7+ platform files.
- **Modern Data Management**: Utilizing `ConfigEntry.runtime_data` to store the `DataUpdateCoordinator`. This removes the need for managing a complex `hass.data[DOMAIN]` dictionary and provides native Home Assistant support for type-safe data access.
- **Explicit Coordinator `config_entry` (HA polling option)**: Pass `config_entry=entry` to `DataUpdateCoordinator.__init__`. HA core's `_schedule_refresh()` reads `self.config_entry.pref_disable_polling` — the flag behind the "Enable polling for changes" system option — and skips arming the next timer when it's OFF (manual `update_entity` / "Refresh Now" still fetch via `async_request_refresh`, which ignores the flag). Passing the entry explicitly is also required going forward: HA deprecated implicit `ContextVar` detection and reports it as an error from **2026.8** (the argument dates from **2024.8**). Orthogonal to the "Pause Polling" switch (`CONF_STOP_POLLING`), which short-circuits `_async_update_data` to cached data for _all_ triggers. Full write-up: `.shared/info/sys_options_enable_polling.md`.
- **Parallel Update Coordination**: `PARALLEL_UPDATES` is set on every platform file, but **per write path rather than uniformly**. `0` on the read-only platforms tells Home Assistant the coordinator orchestrates updates internally, eliminating redundant overhead. `1` on `button`, `switch` and `select`, which issue commands with a real-world effect on the router — `api.py` already serializes every call behind an `asyncio.Lock` because concurrent calls answer "Busy" / `110001`, so the constant is a statement of intent at the platform boundary rather than the safety mechanism itself. `number` stays `0` despite being writable, because its only entity writes `ConfigEntry.options`, which Home Assistant owns. The values are pinned with their reasoning in `tests/test_entity_hygiene.py`, since a considered `0` and a copy-pasted `0` are indistinguishable in source.
- **Domain-Level Service Architecture**: Registering integration services (like `send_sms`) in `async_setup` rather than `async_setup_entry`. This ensures services are registered exactly once for the entire domain, regardless of how many router instances are configured.
- **Actionable Service Feedback**: Ensuring all services raise `HomeAssistantError` with descriptive messages upon failure. This allows Home Assistant automations and scripts to detect execution errors and provides users with meaningful feedback in the UI.
- **Seamless Session Recovery**: Implementing immediate retry logic in the `DataUpdateCoordinator` to handle fixed router session TTLs, ensuring continuous data flow and clean logs during reauthentication events.
- **Recovery Visibility**: Implementing explicit reconnection logging. The coordinator logs an `INFO` message only when communication is restored after a failure, providing a clear "log once on loss, log once on recovery" signal.
- **Long-Term Statistics Alignment**: Consistent use of `state_class` (`MEASUREMENT`, `TOTAL`, `TOTAL_INCREASING`) across volume, duration, and signal metrics to ensure high-quality historical data and compatibility with Home Assistant's Energy and Statistics dashboards.
- **Abstracted Select Mappings**: Utilizing internal mapping dictionaries in `select.py` to decouple technical API codes from user-friendly UI labels, ensuring a professional configuration experience without exposing protocol-level strings.
- **Entity Category Optimization**: Strategically utilizing `EntityCategory.DIAGNOSTIC` for granular infrastructure metrics (e.g., secondary frequency bands, per-bank SMS capacity) while keeping actionable or highly readable metrics (e.g., Signal Bars, SMS Unread) in the primary entity list to balance depth with UI cleanliness.
- **Multi-Stage Quality Gate Pattern**: The `best_connection` binary sensor demonstrates deriving a stable composite quality indicator from multiple metrics rather than a single API field. A 3-stage AND gate (NR band assignment → LTE anchor health → 5G leg health) using OR-of-thresholds within each stage prevents false negatives when individual metrics are borderline. This pattern is robust to the H165-383's `network_type` reporting `"LTE"` even in active NSA 5G mode, and to `sc_band` returning null. Documented in `docs/best_connection_logic.md`.

### Icon Translation Architecture (v1.1.1-dev9)

- **Pattern**: Centralized all entity icons in `icons.json` using the Home Assistant icon translation engine. Removed hardcoded `icon="..."` arguments from Python `EntityDescription` objects.
- **Logic**:
  - **Fallback**: Every entity defines a `default` icon in the JSON mapping.
  - **Dynamic States**: Binary sensors (like `wifi_status` or `best_connection`) use `state` mappings to toggle between different icons based on ON/OFF status.
  - **Dynamic Ranges**: Numeric sensors (like `battery` or `signal_bars`) use `range` mappings. The frontend automatically selects the icon for the highest range value that is less than or equal to the current state.
- **Benefit**:
  - **Decoupling**: Visual presentation is separated from business logic, making the Python code significantly cleaner and easier to read.
  - **IQS Compliance**: Achieved Gold-tier compliance for the `icon-translations` rule.
  - **Reactive UI**: Provides a more "alive" experience with icons that reflect signal strength and connectivity states without custom Python property overhead.

### Uptime Timestamp Stability — Reboot-Detection Latch (v1.1.1-dev15)

- **Problem**: All three uptime timestamp sensors (`uptime_timestamp`, `current_connection_timestamp`, `total_connection_timestamp`) used `_get_timestamp()` in `sensor.py`, which recomputed `now() − uptime_seconds` on every poll. Because the router's internal uptime counter and HA's wall clock tick at slightly different rates (crystal oscillator / NTP divergence), the computed boot time crept monotonically in one direction — visible as several minutes of drift over hours without any actual restart. A prior truncation fix (round to the nearest minute) converted continuous drift into periodic 60-second backward jumps at minute boundaries; the drift source was unchanged.
- **Root cause**: Two independent clocks. Any approach that derives a timestamp from `now() − counter` every poll inherits the divergence between those two clocks.
- **Fix (reboot-detection latch)**: Compute the frozen timestamp exactly once — on the first poll, or when the counter drops by more than `UPTIME_REBOOT_MARGIN = 30` seconds (a genuine reset). Hold it unchanged thereafter. The re-latch trigger compares uptime-to-uptime across polls, which is immune to wall-clock divergence. Implemented in `coordinator.py`; sensors read pre-computed keys (`system_boot_time`, `conn_start_time`, `total_conn_start_time`) from the data dict. Six fields persisted to `entry.data` so the frozen values survive HA restarts.
- **Three independent latches**: The Huawei project has three counters (`device_information.uptime`, `traffic_statistics.CurrentConnectTime`, `traffic_statistics.TotalConnectTime`), each with different reset semantics (router reboot / WAN reconnect / stats clear). Each requires its own latch state — do not share state between them.
- **What does not work** (documented in `.notes/issues/uptime_timestamp_strategy_20260523.md`):
  - Raw `now() − uptime` every poll: drifts continuously.
  - Truncate to nearest minute: replaces drift with periodic 60-second backward jumps.
  - Tolerance latch on timestamp delta (±30s): suppresses small jitter but not monotonic clock-rate divergence; accumulated drift re-trips the latch repeatedly.

### GB vs GiB — Data Sensor Unit Correctness

- **Pattern**: When HA declares `native_unit_of_measurement=UnitOfInformation.GIGABYTES`, the value must be in **decimal GB** (divide bytes by `1,000,000,000`). Dividing by `1024³` produces **GiB**, which HA treats as GB — causing ~7.4% under-reporting.
- **Example**: 133 GB actual → `133,000,000,000 / 1024³ ≈ 123.9` displayed as "124 GB" (wrong). `133,000,000,000 / 1,000,000,000 = 133.0` displayed as "133 GB" (correct).
- **Rule**: Use `/ 1_000_000_000` for `GIGABYTES`, `/ 1_073_741_824` (i.e. `/ 1024**3`) only when the unit is explicitly `GIBIBYTES`. HA's `UnitOfInformation` has both; choose the one that matches the divisor.

### Suggested Display Units & Precision (v1.1.2-dev6)

- **Pattern**: Keep sensors in their **canonical native unit** (`BYTES`, `BYTES_PER_SECOND`, `SECONDS`, `MEGAHERTZ`, `dBm`) so long-term statistics and guard-band limits stay unit-stable, then add `suggested_unit_of_measurement` / `suggested_display_precision` to control the **display** only. HA stores/accumulates the native value and renders in the suggested unit — the user can still override per-entity in the UI. This is the preferred approach over the legacy `_gb` value-fn conversion sensors (which pre-scale in Python and cannot be re-based for statistics). See `/dev_std/dev_standards.md` Section 5.
- **Applied mapping** (23 sensors):
  - Data size `BYTES` → `GIGABYTES`; precision **1** for totals/monthly, **2** for daily/session.
  - Data rate `BYTES_PER_SECOND` → `MEGABITS_PER_SECOND`; precision **2**.
  - Duration `SECONDS` → `HOURS`; precision **1**.
  - Frequency/bandwidth `MEGAHERTZ` → precision **0** (no unit change).
  - Signal strength `dBm` (`rsrp`/`rssi`/`nr_rsrp`) → precision **0** (no unit change); `rsrq`/`sinr` in `dB` left fractional.
- **Gotcha**: `suggested_unit_of_measurement` must be in the **same HA unit class** as the native unit (`DATA_SIZE`, `DATA_RATE`, `DURATION`, `FREQUENCY`), or HA silently ignores the hint. When only precision changes (frequency, dBm), omit `suggested_unit_of_measurement` entirely.

## 5. Technical Pitfalls & Fixes

- **`_unrecorded_attributes` is NOT unioned across the class hierarchy (v1.2.0)**: a shared mixin declaring it does **not** contribute keys to a subclass. `Entity.__init_subclass__` unions the **component** set with the class's **own** attribute and never walks the MRO, so a subclass that assigns `_unrecorded_attributes` shadows its parent completely. Six subclasses here were silently dropping `about` from the recorder exclusion — every state change writing the same static note to history forever.
  - _Fix_: repeat the mixin's keys in **every** subclass that assigns the attribute, and assert it with a runtime sweep over live entities rather than a static check. `# noqa`-free alternatives were considered and rejected: unioning the parent explicitly trips `SLF` private-member rules at every site. Recorded family-wide in `dev_standards` §14.
- **A string split across lines can ship a defect no grep will find (v1.2.0)**: implicit concatenation that breaks mid-word — `"...which often re- "` then `"homes the router..."` — puts a space inside the word in the **assembled** string. Four such words shipped in entity `about` notes (`re- homes`, `Multi- carrier`, `half- parsed`, `per- location`) and users saw them in the More Info dialog.
  - _Fix_: move the line break, never delete text to fix spacing. **The reason two earlier sweeps missed these is worth remembering: the broken text never appears on a single source line**, so a `grep` for it returns nothing. Reviewing the assembled value — or reading the rendered doc — is the only thing that finds them.
- **100% coverage and zero-assertion tests are compatible, and both audits are needed (v1.2.0)**: coverage marks a line covered when it **executes**, whether or not anything checks the result. Two tests added specifically to close a coverage gap did close it, while asserting nothing — they awaited the call and passed on "did not raise", so neither would have failed had the behaviour been wrong.
  - _Fix_: run `Tests: Assertion Audit` alongside coverage; passing one says nothing about the other. Resist allow-listing a bare test — the entry records the gap instead of closing it.
- **Auth Error Handling**: Relying on string matching (e.g., `"password" in str(err)`) to detect login failures is brittle and breaks if library messages change.
  - _Fix_: Catch specific, typed exceptions from the underlying library (`LoginErrorPasswordWrongException`, etc.) to trigger auth failures.
- **SMS List Parsing**: Different Huawei models return SMS lists in varying formats (some as lists, some as single dictionaries).
  - _Fix_: Implemented a robust parser in `helpers.py` that handles metadata offsets and varied structure.
- **Partial Entity Failure (v1.0.1-dev4)**: Transient session timeouts mid-fetch could cause some sensors (like SMS or System Info) to become 'Unknown' while others (like Data) stayed active.
  - _Fix_: Implemented mid-fetch error detection for session codes 125002/125003 in `api.py` and a **Critical Data Guard** in the coordinator to reject partial data objects.
- **Predictable Session Expiration (v1.0.1-dev8)**: Router sessions often have a fixed TTL (e.g., 6 minutes), leading to periodic auth failures during polling.
  - _Fix_: Implemented an immediate retry mechanism in the coordinator. If a `HuaweiAuthError` is caught, the fetch is retried once immediately, masking the recovery from the user and ensuring data continuity.
- **Numeric Sanitization**: The Huawei API often returns strings with technical suffixes (e.g., "120dBm", "20MHz").
  - _Fix_: Implemented `parse_signal_value` helper in `helpers.py` to strip these suffixes before numeric conversion across all platforms.
- **MAC Address Stability**: Some routers report MAC addresses with or without colons.
  - _Fix_: Normalized all MAC identifiers to a consistent lowercase, colon-less format for use in `unique_id`.
- **Numeric vs. Multi-Carrier Ambiguity (v1.0.1-dev16)**: Standard numeric parsers like `parse_signal_value` are designed to extract the _first_ number found. This is dangerous for multi-carrier strings (e.g., `DL:500 UL:18500`) as it causes "partial-parsing" where only the first value is captured and the rest is discarded.
  - _Fix_: Implemented complexity detection in `helpers.py`. If a string contains colons or multiple segments, the parser bypasses numeric conversion entirely and returns the full raw string, preserving technical fidelity.
- **Background Task Mocking**: Standard tests can fail if background tasks aren't properly awaited.
  - _Fix_: Ensured all tests use `hass.async_block_till_done()` after setup to catch initialization tasks.
- **SMS Inbox Browsing**: The integration provides the last received message content and unread counts. Browsing the full inbox or replying to specific messages requires the router's web interface.
- **Slot Reuse Event Suppression (v1.1.0)**: Huawei routers reuse memory slot indices (1-50). Comparing `index > last_seen_index` failed when a new message took a lower-numbered empty slot.
  - _Fix_: Switched to **Timestamp-Based Tracking**. The coordinator now tracks the latest `date` and uses a `{index}_{date}` hash set for deduplication within the same second.
- **Service Response Coroutine Error (v1.1.0)**: Registering `async` service handlers with a `lambda` (e.g., `lambda call: async_func(call)`) returns an unawaited coroutine object. While this works for one-way services, it fails for services with responses, as Home Assistant expects a dictionary.
  - _Fix_: Refactored service handlers into explicit `async def` wrappers that `await` the implementation before returning.
- **HA `device_id` vs `entry_id` — Different Things**: In Home Assistant, `device_id` is a reserved term for the **device registry** UUID (the internal ID of a device entity like "Huawei Router System"). A `config_entry_id` (or `entry_id`) is the ID of a config entry. These are completely different objects. Using `device_id` as a service parameter name when the value is actually a config entry ID misleads users and breaks type safety — automations built with the HA device picker would pass the wrong value type.
  - _Fix_: Name service fields `entry_id` when they expect `hass.config_entries.async_get_entry()` to resolve them. Use the `config_entry` selector in `services.yaml` (not the `device` selector) so the UI presents the correct picker.
- **Python 3.14 Bare-Tuple Except Syntax — Nuance Update**: The `except A, B:` form (Python 2 style) generates a `SyntaxWarning` in Python 3.12–3.13 because the interpreter parses it as `except A, (B):` — catching only `A` and binding the exception to the name `B`. However, **Python 3.14 (PEP 3111) changed the grammar** to treat `except A, B:` as valid multi-catch (catching both `A` and `B`). Additionally, `ruff` with `target-version = "py314"` will auto-format `except (A, B):` back to `except A, B:`.
  - _Fix_: Always use `except (A, B):` with explicit parentheses when catching multiple exception types. To prevent ruff from reverting to the comma form, pin `target-version = "py313"` in `pyproject.toml` under `[tool.ruff]`. This ensures backward compatibility with HA versions running Python <3.14.
- **Operator Precedence Trap (`or 0 > 0`)**: The expression `x or 0 > 0` evaluates as `x or (0 > 0)` — i.e., `x or False` — which always reduces to `bool(x)`. The parenthesization `(x or 0) > 0` is required to get "treat `None` as 0, then compare". This pattern appears naturally when guard-banding a nullable integer against a threshold.
  - _Fix_: When using `or 0` as a None-guard before a comparison, always wrap the entire `or` expression in parentheses: `(val or 0) > threshold`.
- **Debounce Task Lifecycle (`async_will_remove_from_hass`)**: Entities that schedule background `asyncio` tasks (e.g., debounced refresh) must cancel them on removal. Without this, the task holds a reference to the coordinator and fires after the entity is gone, causing "entity not found" log noise.
  - _Fix_: Override `async_will_remove_from_hass` and call `task.cancel()` on any stored task handle.
- **SMS API Parameter Constraints (v1.0.1-dev15)**: Modern 5G firmware is highly sensitive to the XML payload sent to `get_sms_list`. Including optional parameters like `sort_type` or `unread_preferred` can cause the router to reject the request with a "System Error" (110001) or return empty results.
  - _Correction_: While simplified in v1.0.1-dev15, these were **re-added and verified** in v1.1.0 alongside the `asyncio.Lock`. Concurrency was the true root cause; with serialized requests, the router accepts the advanced sort/unread parameters correctly.
- **Transient Notification Counters**: The `NewMsg` API key does not represent a persistent state (like "Unread"); it is a transient notification counter that resets as soon as a client fetches the message list.
  - _Fix_: Renamed the sensor to **"In Process"** and moved it to **Diagnostic** to prevent user confusion during polling cycles.
- **Library Enum Requirements**: Recent versions of `huawei-lte-api` expect `Enum` objects (like `BoxTypeEnum`) rather than literal integers for certain parameters. Passing an integer can trigger attribute errors (`'int' object has no attribute 'value'`) within the library's internal logic.
  - _Fix_: Explicitly import and utilize the library's Enum definitions for all box selection logic.
- **Invalid API Key Mismatch**: Technical storage metrics (e.g., `LocalInbox`, `SimInbox`) are often used in documentation but do not exist in the actual `sms_count` response for many models.
  - _Fix_: Corrected mappings to sum physical counters: `Inbox = Read + Unread`, `Outbox = Outbox + Sent`.
- **LTE Frequency Scaling Error (v1.0.1-dev18)**: The `lteulfreq` and `ltedlfreq` API fields are in **10ths of MHz** (e.g., raw 19700 = 1970 MHz), not 100ths. The initial `/100` divisor produced values 10× too small (e.g., 197 MHz instead of 1970 MHz).
  - _Fix_: Changed the `format_freq_mhz` helper divisor from `/100` to `/10`.
- **LTE Bandwidth Field Misidentification (v1.0.1-dev18)**: The `ulfrequency` and `dlfrequency` API fields are **carrier frequency fields in kHz** (e.g., 1970000 kHz = 1970 MHz), not bandwidth fields. Mapping them to bandwidth sensors produced 1970/2160 MHz instead of the correct 20 MHz. The correct bandwidth fields are `ulbandwidth` and `dlbandwidth`, which return the channel width directly in MHz (no scaling required), matching the pattern already used by the 5G bandwidth sensors (`nrulbandwidth`/`nrdlbandwidth`). The repurposed kHz fields are now correctly used by the new LTE Uplink/Downlink Frequency (Secondary) sensors.
  - _Fix_: Changed bandwidth sensors to read `ulbandwidth`/`dlbandwidth` with no scaling. Added secondary frequency sensors reading `ulfrequency`/`dlfrequency` via `format_khz_to_mhz` (÷1000).
- **LTE CA and 5G NR Band API Fields Absent (v1.0.1-dev18)**: On the H165-383 router, the dedicated `lte_ca` and `sc_band` API fields return null, causing both entities to permanently report "unknown". The required data is present but embedded in the composite `band` string (e.g., `"20MHz@500(B1) + 15MHz@1875(B3) + 10MHz@152690(N28)"`).
  - _Fix_: Replaced both with band-string parsers. `5g_nr_band` (sensor) extracts the `(NXX)` label from the last carrier segment. `lte_ca` was also converted from a string-valued sensor ("enabled"/"disabled") to a proper **binary sensor** (ON/OFF) — the underlying value is inherently boolean (`"+" in band`), and `binary_sensor` is the correct HA platform for this state.
- **Unit Selector Absence (v1.0.1-dev22)**: The eight `FREQUENCY` entities do not have the unit selector in home assistant (stuck on kHz or MHz). Data (MB/GB) and Duration (sec/hr/day) entities do. The frequency entities in the core component also have the unit selector.
  - _This is NOT fixed_: Be aware that investigating this will results in incorrect analysis that the root cause is `diagnostic` vs `sensor` or the presence of `state_class` . This is wrong. Further investigation required, low priority.
- **IPv6 DNS Gaps (v1.0.1-dev22)**: While IPv4 DNS was tracked, IPv6 DNS was missing, leading to incomplete network visibility on modern dual-stack connections.
  - _Fix_: Added `primary_ipv6_dns` and `secondary_ipv6_dns` sensors reading from the `monitoring_status` endpoint.
- **Session Expiration during Service Calls (v1.1.1-dev21)**: Calling SMS or other device services after ~2 minutes of inactivity resulted in a `100003: No rights (needs login)` error due to the router's session expiring.
  - _Fix_: Implemented proactive inactivity-based session resetting (100-second threshold) in `_ensure_client()` and a reactive retry wrapper `_execute_with_retry` that catches `ResponseErrorLoginRequiredException` and codes `125002`/`125003`/`100003`, resets the client, and automatically retries the operation once.
- **`asyncio.to_thread` Mock Compatibility (v1.1.1-dev21)**: Unit test mocks that stub `asyncio.to_thread` with custom lambda syntax (e.g. `lambda fn, **kwargs: fn(**kwargs)`) would fail with `TypeError` when `asyncio.to_thread` was invoked with extra positional arguments like `asyncio.to_thread(func, client)`.
  - _Fix_: Wrapped the client function in a zero-argument lambda: `asyncio.to_thread(lambda: func(client))`. This ensures exactly one positional argument is passed, preserving compatibility with all unit test mocking styles.
- **`url_normalize` / `idna` UTS46 Startup Race (v1.1.1-dev22)**: On HA reboot, the integration occasionally failed with `ImportError: cannot import name 'uts46data' from 'idna.uts46data'`. The file existed on disk but the module was partially initialized — a Python import-system race caused by HA loading many integrations concurrently during cold startup. The `url_normalize` library triggers this via `idna.encode(p, uts46=True)`, which lazily loads the large `uts46data` generated module. A partially initialized module gets cached in `sys.modules`, so the integration could not recover via manual reload — only a full HA restart (fresh Python process) cleared it.
  - _Fix_: Replaced `url_normalize` entirely with a private `_normalize_router_url()` helper using `urllib.parse.urlparse` / `urlunparse` (stdlib, no external deps). For local router IP/hostname URLs, stdlib covers 100% of real-world input forms (bare IP, missing scheme, trailing slash, uppercase scheme, non-default port). The `url-normalize==3.0.0` requirement was removed from `manifest.json` at the time, and from `.validate/requirements_custom.txt` in `[1.2.0-dev27]` — it had remained a dev/test dependency for a year after nothing imported it. The pattern to follow: avoid third-party libraries that eagerly or lazily load large Unicode data tables at import time when a stdlib equivalent exists.
- **`ScannerEntity` Import Path Deprecated in HA 2026.6 (v1.1.1-dev22)**: HA 2026.6 deprecated the `homeassistant.components.device_tracker.config_entry.ScannerEntity` alias, triggering a log warning on every startup. The alias will be removed in HA 2027.6.
  - _Fix_: Import `ScannerEntity` from `homeassistant.components.device_tracker` (the canonical top-level path). When HA deprecates a platform submodule import, the fix is always to move the import to the parent module. Watch for similar patterns in other platform files (e.g., `binary_sensor`, `sensor`, `switch`) if HA continues this consolidation pattern in future releases.

- **mypy Configuration Alignment with HA's Internal `mypy.ini` (v1.1.1-dev23)**: When aligning a custom component's mypy config with HA's own `mypy.ini` (auto-generated by `script/hassfest -p mypy_config`), several non-obvious interactions apply:
  - HA's global mypy config does **not** include `disallow_any_generics = true`. Setting it globally in the project makes the project stricter than HA on generics, which can cause the project to reject patterns HA itself allows. Apply this flag only to specific modules if needed, or remove it from the global section.
  - HA uses `disable_error_code = ["annotation-unchecked", "import-not-found", "import-untyped"]` rather than `ignore_missing_imports = true`. These are subtly different: `ignore_missing_imports` is a blanket flag; the `disable_error_code` approach is targeted and aligns with HA's convention.
  - HA enables `enable_error_code = ["deprecated", "ignore-without-code", "redundant-self", "truthy-iterable"]`. The `ignore-without-code` code is particularly important: it requires every `# type: ignore` comment to carry a specific error code (e.g. `# type: ignore[attr-defined]`). Bare `# type: ignore` comments become errors.
  - HA sets `no_implicit_reexport = true` for `homeassistant.*` modules via `[mypy-homeassistant.*]`. Applying this in the project's `homeassistant.*` override (alongside `ignore_errors = true` and `follow_imports = "silent"`) replicates HA's own policy and ensures the project's mypy checks catch the same import-surface inconsistencies HA itself would catch. Without this, basic mypy (no `--strict`) allows implicit re-exports from HA modules while strict mypy rejects them — creating a mode-dependent split that makes `# type: ignore` comments simultaneously needed and unused depending on which mode runs.
  - _Pattern_: To verify HA's actual config, read `/ha_core/mypy.ini` from inside the devcontainer. This file is auto-generated and is the ground truth. Do not infer HA's mypy configuration from documentation — it changes with HA releases.
- **ruff / mypy Comment Placement Deadlock on Multi-Line Imports (v1.1.1-dev23)**: A `# type: ignore[code]` comment suppresses a mypy error only on the **exact line** where mypy reports the error. For multi-line parenthesized imports, mypy always attributes errors (`[attr-defined]`, `[import-untyped]`, etc.) to the **`from` line** (the line containing the `from` keyword and the opening parenthesis), never to the member lines. ruff, when expanding a single-line import to multi-line (due to line length), moves any trailing comment from the import statement to the **last member line**. This creates a deadlock when the import line is over the length limit:
  - Single-line with comment → over length limit → ruff expands to multi-line → comment moves to member line → mypy error on `from` line is not suppressed → pre-commit mypy fails
  - Adding the comment back to the single-line form → over length limit → ruff expands again → loop repeats
  - _Fix_: Use the multi-line form with the `# type: ignore` comment on the `from (` line (not on any member line):

    ```python
    from homeassistant.components.device_tracker import (  # type: ignore[attr-defined]
        ScannerEntity,
    )
    ```

    ruff does **not** move a comment that is already on the `from (` line — it only moves comments during initial expansion of single-line imports. Verified: `ruff format` on this exact form returns "already formatted". mypy correctly sees the comment on the same line as the reported error and suppresses it. The `from (` line in this form is 83 chars (within the 88-char limit), so ruff has no reason to reformat it, and cannot collapse it back to single-line (the single-line form would be 95 chars). This placement is stable.

- **VS16 Compound Emoji in README Headings (2026-06-08)**: Using VS16 compound emoji (e.g., `⚙️`, `🏗️`, `⚠️`, `🗑️`) in README headings causes Table of Contents links to silently 404. GitHub's anchor generator strips VS16 bytes (U+FE0F) when computing heading slugs, but Markdown tooling includes them in `href` values. The mismatch is completely invisible in source editors — the heading renders fine and GitHub preview looks correct, but clicking a ToC link jumps nowhere.
  - _Fix_: Replace all VS16 compound emoji in headings and their corresponding ToC `href` values with always-color single-codepoint alternatives (e.g., 🔧 🔩 ❌ ❗ 🔄 💬). See root `CLAUDE.md` → "Shared Markdown Notes" for the full replacement table and detection script.

- **Doubled `configuration_url` from Stored Host Scheme (v1.1.2-dev5)**: The default host in the config flow was `http://192.168.8.1` (scheme included), and the API layer's `_normalize_router_url` re-adds a scheme at runtime — so the raw value was stored as-is in `entry.options`. Because `__init__.py` builds the **root** System device link as `configuration_url=f"http://{host}"`, storing `http://192.168.8.1` produced `http://http://192.168.8.1`. (The sub-devices were unaffected — `build_device_info` uses `coordinator.api.url`, the already-normalized URL.)
  - _Fix_: Added `_clean_host()` to `config_flow.py` and applied it at the top of all four steps (user, reconfigure, reauth, options) so only the bare host is persisted. The API layer still re-adds the scheme, so connectivity is unchanged. This is a PlayFaster standard — see `dev_standards.md` Section 9.
- **Stored Password Exposed on Reconfigure (v1.1.2-dev5)**: Pre-filling the password field from `entry.options` on the Reconfigure/Options/Reauth screens meant the stored secret was sent to the browser as a masked value — and could be revealed with the UI eye icon.
  - _Fix_: Split the config-flow schema into `_user_schema` (setup) and `_edit_schema` (edit). Edit screens use a masked `TextSelector` (`TextSelectorType.PASSWORD`) and leave the password blank; `_merge_credentials()` restores the stored value on a blank submit, so the field can re-set the password without ever displaying it. A `data_description` under the field tells the user "Leave blank to keep the current password." The reconfigure step was also changed to merge into existing options rather than replace them, preserving `scan_interval` / `stop_polling`. See `dev_std/dev_standards.md` Section 9.

## 6. Environment Constraints

- **Async Wrapper**: While `huawei-lte-api` is primarily synchronous, this integration wraps all calls in `hass.async_add_executor_job` or uses the library's async capabilities where available to ensure the HA event loop is never blocked.
- **XML/SOAP API**: The integration handles the heavy lifting of XML parsing and session token management required by Huawei's API.
- **Windows Testing**: The Home Assistant test suite (via `pytest-asyncio`) uses the `ProactorEventLoop` by default on Windows, which utilizes internal sockets that can be blocked by `pytest-socket`.
  - _Standard_: Use `WindowsSelectorEventLoopPolicy` and monkeypatch `pytest-socket.disable_socket` in `conftest.py` to ensure local tests pass without disabling security guards entirely.

## 7. Technical Debt & Future Work

- **Signal Guard Band Refinement**: Continue to tune min/max limits as more users provide data from different signal environments (e.g., extreme fringe areas).
- **Client Metadata**: Expand the "Clients" sub-device to include more detailed information like hostnames if supported by the router firmware.
- **Multi-SIM Support**: Investigate support for routers with dual SIM slots.
- **Band arguments on a mode change rest on one device's evidence (v1.2.0)**: `net/net-mode` takes mode and both band masks together, so `set_net_mode` must send bands. It used to send `LTEBandEnum.ALL` / `NetworkBandEnum.ALL`; it now reads the router's current `LTEBand` / `NetworkBand` and hands them straight back, so a mode change no longer widens or resets a band selection made elsewhere. **The reference H165-383 is the only hardware this has been seen on.** Its values are hex strings without `0x`, and the library passes strings through untouched. A model that reports bands in a form it will not accept on write would now fail a mode change that previously worked, because the old constant sidestepped the question. Low likelihood, small benefit, non-zero risk — revisit if a mode change is ever reported failing on other hardware, where reverting to `ALL` is the immediate mitigation.
- **The accepted-mode list is read once per run, with no retry**: one failed `net.net_mode_list()` call leaves the select on its fallback list until Home Assistant restarts. Deliberate — the alternative was a retry in the poll path for a value that changes only with firmware — but a router briefly busy at startup gives the user the long list for the session.

---

_[1.0.3-dev3] — Added pitfall entries for Python 3.14 bare-tuple except syntax, operator precedence (`or 0 > 0`), and debounce task lifecycle (`async_will_remove_from_hass`)._

_[1.0.3-dev4] — Added success pattern for MAC-based stable unique ID with normalization. Added pitfall entry for HA `device_id` vs `entry_id` naming._

_[1.1.1-dev22] — Added pitfall entries for `url_normalize`/`idna` UTS46 startup import race and `ScannerEntity` import path deprecation (HA 2026.6)._

_[1.1.1-dev23] — Added pitfall entries for mypy configuration alignment with HA's internal `mypy.ini` and the ruff/mypy comment-placement deadlock on multi-line imports._

_[1.1.1-dev12] — Updated Python 3.14 bare-tuple except pitfall entry with PEP 3111 clarification, ruff auto-format behavior, and `target-version` pinning guidance._

_[1.1.1-dev15] — Added "Uptime Timestamp Stability — Reboot-Detection Latch" success pattern and "GB vs GiB — Data Sensor Unit Correctness" pattern._

_[1.1.1-dev21] — Added "Session Expiration during Service Calls" and "asyncio.to_thread Mock Compatibility" pitfall entries._

_[2026-06-08] — Added VS16 compound emoji in README headings pitfall entry._

_[1.1.2-dev5] (2026-07-02) — Documented config-flow host normalization (doubled `configuration_url` fix) and the blank/masked password-on-edit pattern (stored secret no longer exposed via the eye icon). Added the "Refresh Now" button (immediate coordinator refresh)._

_[1.1.2-dev6] (2026-07-02) — Added "Suggested Display Units & Precision" success pattern. Applied `suggested_unit_of_measurement` / `suggested_display_precision` to 23 sensors (data size → GB, data rate → Mbit/s, duration → hours, frequency/bandwidth and dBm → 0 dp)._

_[1.1.2-dev7] (2026-07-02) — Documented passing `config_entry=entry` to the coordinator (honours the "Enable polling for changes" system option via `pref_disable_polling`; required as HA removes implicit context detection in 2026.8)._

_[1.2.0-dev28] (2026-08-15) — Added three success patterns from the `dev_std_review` / `code_review` remediation: the radio-level master WiFi switch, the Section 22 write confirmation and its three outcomes, and the Section 9 options reload with its live-key allow-list. Updated the `url_normalize` pitfall to record that the dev/test requirement was finally dropped in `[1.2.0-dev27]`._

_[1.2.0-dev53] (2026-08-17) — Reconciliation pass. Added the "Network Mode List Comes From the Router" success pattern with its ordering constraint, and three pitfalls the session produced but never recorded: `_unrecorded_attributes` is not unioned across the class hierarchy; a string split mid-word ships a defect no `grep` can find, because the broken text never appears on one source line; and 100% coverage is compatible with tests that assert nothing, so both audits are needed. Corrected the Section 22 exclusions bullet, which still said network mode has no read-back reader — it gained one when `-1` was found to mean "applied, answered badly" rather than "refused"._
