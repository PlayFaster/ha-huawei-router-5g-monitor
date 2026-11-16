# Huawei Router 5G Monitor Capabilities Dossier

An architectural reference and at-a-glance inventory of verified capabilities, interfaces, technical guarantees, and version lineage for `ha-huawei-router-5g-monitor`.

**Current Through:** `v1.2.4` (covering `v1.0.1` to `v1.2.4`) · **Last Audited:** 2026-11-16 · **Status:** `Active`

---

## 1. Connection & Session Control

### Dual-Session Coexistence & Refusal Adjudication

- **Purpose**: Authenticates against Huawei router web APIs and distinguishes unsupported endpoint refusals from expired sessions, preventing premature re-authentication errors and unnecessary logins.
- **Entities & Interfaces**: Coordinator polling engine (`api.py`, `coordinator.py`), `binary_sensor.<name>_integration_health` (attribute `not_served`).
- **Technical Guarantees**:
  - Pre-login `user/state-login` check detects active router lockouts (`108007`) and raises `HuaweiLockoutError` without sending a login attempt; invalid credentials (`108001`, `108002`, `108006`) raise `HuaweiAuthError`, and only `HuaweiSessionExpiredError` is retried within a poll.
  - Distinguishes endpoint refusals (`100003`, `125002`, `125003`) from expired logins via an anonymous premise check on `device.information` (`PREMISE_TIMEOUT = 3s`), both inside polls and on standalone reads (`_read_refused_on_live_session`), without triggering extra logins on confirmed live sessions.
  - Non-critical dropped requests (`requests.ConnectionError`, `requests.Timeout`) are retried once (`_call_once_more_if_dropped`) within `ADJUDICATION_BUDGET`, and session-refused writes in `RETRIED_ON_REFUSAL` are retried once after a fresh login (`_retry_once_on_refusal`).
  - Live sessions are logged out via `_release_session` (`_RELEASE_TIMEOUT = 3s`) before idle or Reconnect resets.
  - Where `device/information` has never answered or is refused on the first read after login, setup and polling fall back to `device/basic-information` for device naming and software version.
  - Unanimously unsupported endpoints are recorded under `not_served` and persisted across restarts (`answered_endpoints`) without taking error strikes or degrading health severity.
- **Lifecycle Timeline**:
  - `v1.0.1`: Initial polling engine with basic exception handling.
  - `v1.1.1`: Automatic session re-login on expired mid-fetch calls.
  - `v1.2.0`: Timeout recovery closes underlying HTTP sockets and rebuilds fresh sessions.
  - `v1.2.3`: Full refusal adjudication introduced (`v123_dev16_plan.md`); added `not_served` attribute to prevent setup failure on partial firmware implementations.
  - `v1.2.4`: Added pre-login lockout check, `device/basic-information` fallback, live-session standalone adjudication, dropped-read and refused-write single retries, `_release_session` logout, and persisted `answered_endpoints`.

### Single-Flight API Mutex Lock

- **Purpose**: Serializes concurrent requests, background polls, and interactive write operations to prevent command collisions and router "Busy" (`110001`) refusals.
- **Entities & Interfaces**: `_locked` async method decorator in `api.py`.
- **Technical Guarantees**:
  - Maximum lock acquisition wait bounded by `LOCK_TIMEOUT = 60s`.
  - Task cancellation safely unwinds via `finally` blocks, releasing the lock to prevent integration deadlocks.
  - Long settling read-backs (e.g. 15s network mode settle) executed outside the lock.
- **Lifecycle Timeline**:
  - `v1.0.2`: Introduced basic API lock for SMS actions and configuration requests.
  - `v1.2.0`: Bound lock acquisition and write execution timeouts (`WRITE_TIMEOUT = 120s`); moved mode settling read-backs outside the lock.

### Cellular Bearer & Data Session Control

- **Purpose**: Provides programmatic controls to reconnect cellular data bearer sessions on demand without restarting the physical router.
- **Entities & Interfaces**: `button.<name>_reconnect`.
- **Technical Guarantees**:
  - Re-establishes WAN session via dual dial actions without dropping local LAN/Wi-Fi clients.
  - Opens an expected-outage window: polls are skipped and other controls refused with localized countdowns (`router_reconnecting`) until the router answers, or for up to 20 s (`OUTAGE_HOLD`) when it keeps answering (capped at `OUTAGE_CAP_RECONNECT = 60s`), and a closing poll then refreshes the entities.
- **Lifecycle Timeline**:
  - `v1.2.0`: Introduced Reconnect button with dual dial action sequence.
  - `v1.2.4`: Follow-up refresh replaced by the expected-outage window and localized refusal key.

### Device Reboot & Expected-Outage Window

- **Purpose**: Reboots the router hardware safely from Home Assistant with automated polling recovery.
- **Entities & Interfaces**: `button.<name>_reboot`.
- **Technical Guarantees**:
  - API errors during reboot submission are propagated directly to the UI rather than swallowed.
  - Opens an expected-outage window once `user/state-login` stops answering (`REBOOT_VERIFY_SECONDS = 20s`): polls are skipped and other controls refused with localized countdowns (`router_restarting`), a check every 5 s closes it on the router's first answer through a closing poll (including when background polling is paused), and a router still silent at 240 s (`OUTAGE_CAP_REBOOT`) is logged.
- **Lifecycle Timeline**:
  - `v1.0.1`: Basic reboot action added.
  - `v1.1.1`: Exception propagation hardened to surface API errors.
  - `v1.2.0`: Automated follow-up polling refresh scheduled upon reboot completion.
  - `v1.2.4`: Follow-up refresh replaced by the expected-outage window and localized refusal key.

### Configurable Polling Interval & Polling Suspension

- **Purpose**: Controls update frequency and allows pausing scheduled background polling without taking integration entities offline.
- **Entities & Interfaces**:
  - `number.<name>_polling_interval`
  - `switch.<name>_pause_polling`
  - `button.<name>_refresh`
- **Technical Guarantees**:
  - Polling interval changes debounced for two seconds; pending values flushed on entity removal rather than discarded.
  - Pausing polling leaves entities in their last known valid state rather than setting them unavailable.
  - Manual Refresh Now overrides the pause state to fetch current router status immediately (and respects active outage windows).
- **Lifecycle Timeline**:
  - `v1.0.1`: Initial polling interval slider and pause polling switch.
  - `v1.1.2`: Added Refresh Now button; debounced interval adjustments with safe removal flushing.
  - `v1.2.0`: Follow-up refresh actions after reboots and reconnects execute even while polling is paused.
  - `v1.2.4`: Closing poll of a Reboot or Reconnect window runs even while polling is paused.

---

## 2. Sensor Metrics, Data & Uptime Tracking

### Firmware Update & Text Transition History

- **Purpose**: Preserves firmware update history and key network state transitions across Home Assistant restarts so silent router updates and address changes are never lost.
- **Entities & Interfaces**:
  - `observations.py` (`huawei_router_5g_<entry_id>_history` and `_observed` stores)
  - Unrecorded attributes `history`, `previous_version`, and `last_changed` on Software Version, WAN IP Address, APN, LTE Cell ID, Operator, Carrier Build, WAN IPv6 Address, and Primary DNS Server
  - Eight `TOTAL_INCREASING` change-counter sensors (with `Software Version Changes` enabled by default)
- **Technical Guarantees**:
  - Retains the last 20 transitions per tracked sensor across Home Assistant restarts.
  - Stores are cleanly deleted on integration removal (`async_remove_entry`).
- **Lifecycle Timeline**:
  - `v1.2.4`: Added 20-entry text transition history, `previous_version`/`last_changed` attributes, and eight change-counter sensors (`1.2.4-dev4`).

### Store-Backed Uptime & Reboot Latching

- **Purpose**: Tracks physical device uptime and active connection durations independently from Home Assistant restarts or transient carrier drops.
- **Entities & Interfaces**:
  - `sensor.<name>_uptime`
  - `sensor.<name>_connection_uptime`
  - `sensor.<name>_total_connected_time`
- **Technical Guarantees**:
  - Boot timestamps latched to the whole second to eliminate independent clock tick drift.
  - Uptime state persistently stored across Home Assistant restarts using `homeassistant.helpers.storage.Store`.
  - Startup shortfall test evaluates counter progression to detect reboots that occurred while Home Assistant was offline.
  - `TotalConnectTime` monotonic floor rule prevents negative counter steps during link outages.
- **Lifecycle Timeline**:
  - `v1.0.1`: Initial system uptime calculation based on raw counter.
  - `v1.1.1`: Introduced latching to prevent clock tick drift.
  - `v1.2.0`: Separated physical uptime from cellular connection duration; added Total Connected Time.
  - `v1.2.3`: Migrated persistence to storage `Store`; added offline reboot detection and shortfall evaluation.

### Clock Drift Diagnostics & Calibration

- **Purpose**: Measures and calibrates hardware clock drift against wall-clock time to ensure long-term counter accuracy.
- **Entities & Interfaces**: `binary_sensor.<name>_integration_health` (attributes `drift_rate_pct`, `drift_intervals`, `drift_measured_seconds`).
- **Technical Guarantees**:
  - Duration-weighted accumulators track counter drift across consecutive polling cycles.
  - Drift rate applied to boot anchor calculation (`now - counter / (1 - rate)`) with a 30-day window cap.
- **Lifecycle Timeline**:
  - `v1.2.3`: Added clock drift calibration, diagnostics attributes, and diagnostic export data.

### Signal Diagnostics & 3-Stage Best Connection Gate

- **Purpose**: Monitors cellular radio metrics (RSRP, RSRQ, SINR, RSSI, Frequency, Band, Cell ID), mobile connection status, and operator/Wi-Fi metadata.
- **Entities & Interfaces**:
  - `sensor.<name>_best_connection`
  - `binary_sensor.<name>_mobile_connection` (attribute `additional_state`)
  - Radio signal, operator, and Wi-Fi sensors
- **Technical Guarantees**:
  - 3-stage quality gate validates 5G NSA/SA operational readiness before asserting active 5G connectivity.
  - Min/max guard bands clamp out-of-range frequency and transmit power readings; comparison-prefixed signal values (`>=-51dBm`, `&lt;-20dB`, `&gt;=30dB`) parse to their boundary value.
  - No-SIM `net.current_plmn` string responses and non-list `Ssids.Ssid` payloads read safely as `unknown` without raising.
  - `additional_state` reports non-connected `ConnectionStatusEnum` states (`900`, `902`–`906`) without altering binary sensor on/off state.
- **Lifecycle Timeline**:
  - `v1.0.1`: Introduced Best Connection sensor with 3-stage quality gate and signal scaling.
  - `v1.2.0`: Added guard bands for transmit power and multi-valued metric parsers.
  - `v1.2.4`: Added comparison-prefix signal parsing, `additional_state`, and no-SIM/non-list `Ssid` guards.

### End-of-Cycle Bandwidth Usage Forecast

- **Purpose**: Predicts end-of-billing-cycle monthly bandwidth consumption based on configured billing days.
- **Entities & Interfaces**: `sensor.<name>_projected_usage`.
- **Technical Guarantees**:
  - Linear extrapolation calculates projected monthly data with confidence and credibility indicators.
  - Automatically handles billing date rollover and zero-traffic boundary conditions.
- **Lifecycle Timeline**:
  - `v1.2.0`: Introduced Projected Usage sensor and month data usage forecasts.

### Traffic Counter Management & Hardware Statistics Reset

- **Purpose**: Tracks cumulative cellular network data volumes and resets hardware counters on demand.
- **Entities & Interfaces**:
  - `button.<name>_clear_traffic`
  - Total and monthly bandwidth sensors (`sensor.<name>_total_download`, `_total_upload`, `_month_download`, `_month_upload`)
- **Technical Guarantees**:
  - Reset executes directly against router hardware; sets `Counters Last Reset` timestamp without altering billing cycle day configuration.
  - Failures during reset submission propagate directly to Home Assistant rather than failing silently.
- **Lifecycle Timeline**:
  - `v1.0.1`: Initial traffic byte volume sensors and clear traffic button.
  - `v1.1.1`: Hardened exception propagation to surface API errors.
  - `v1.2.0`: Corrected library binding for traffic counter clearing during reload.

---

## 3. Control, Networking & SMS Management

### Master Wi-Fi Radio Hardware Control

- **Purpose**: Toggles primary router Wi-Fi radios safely from Home Assistant without altering SSID configurations.
- **Entities & Interfaces**: `switch.<name>_master_wifi_switch`.
- **Technical Guarantees**:
  - Safely powers off or enables both 2.4 GHz and 5 GHz hardware radios simultaneously.
  - Preserves Guest Wi-Fi settings and internal radio parameter structures across state changes.
- **Lifecycle Timeline**:
  - `v1.2.0`: Added Master Wi-Fi radio control switch.

### Mobile Data Bearer Disconnect Control

- **Purpose**: Enables and disables the router's mobile data connection from Home Assistant without dropping local LAN and Wi-Fi networks.
- **Entities & Interfaces**: `switch.<name>_mobile_data`.
- **Technical Guarantees**:
  - State latching retains the confirmed position immediately after toggle, preventing UI flip-back until next poll.
  - Router write refusals explicitly raise `HomeAssistantError` instead of reporting unearned success.
  - Disabling mobile data drops only external WAN routing; local client routing and Wi-Fi remain active.
- **Lifecycle Timeline**:
  - `v1.0.1`: Initial mobile data switch.
  - `v1.1.3`: Hardened write failure reporting to raise explicit `HomeAssistantError`.
  - `v1.2.0`: Implemented state latching to eliminate optimistic flip-back.

### Dynamic Network Mode Selection

- **Purpose**: Selects preferred cellular network technology (e.g. 5G Only, Auto, 4G Only) from options dynamically supported by router firmware.
- **Entities & Interfaces**: `select.<name>_preferred_network_mode`.
- **Technical Guarantees**:
  - Option list queried directly from router hardware rather than offering hardcoded, unsupported modes; an active mode outside the router's list is still displayed and writes of that mode are rejected via localized `network_mode_not_listed` without sending a request.
  - State read-back executed outside locks to ensure radio re-registration settles without dropping cell band locking.
- **Lifecycle Timeline**:
  - `v1.0.1`: Basic static network mode select entity.
  - `v1.2.0`: Switched to dynamic router-queried option discovery; mapped 5G-only mode (`08`).
  - `v1.2.4`: Added unlisted active mode display and localized `network_mode_not_listed` refusal.

### SMS Inbox, Event Entity & Messaging Suite

- **Purpose**: Provides full programmatic SMS management and reliable incoming-message automation triggers directly from Home Assistant.
- **Entities & Interfaces**:
  - Actions: `huawei_router_5g.send_sms`, `delete_sms`, `delete_all_sms`, `get_sms_list`.
  - Entities: `event.<name>_incoming_sms` (`received` event), `sensor.<name>_sms_unread`, `binary_sensor.<name>_sms_storage_full`.
- **Technical Guarantees**:
  - Message length validation supports up to 612 characters with automatic GSM-7 vs. Unicode segment calculation.
  - Incoming SMS detection uses storage index and content hash (`_sms_identity`) so daylight-saving clock changes never hide messages; HMAC-hashed identities (capped at 200) persist across restarts so messages arriving while Home Assistant was stopped are announced once on startup.
  - `delete_sms` and paged `delete_all_sms` verify removal against the router's inbox before reporting success.
  - Proactive session recovery re-authenticates before executing SMS actions if previous session expired; storage full binary sensor enabled by default on new installations.
- **Lifecycle Timeline**:
  - `v1.0.1`: Display Last SMS sensor introduced.
  - `v1.0.2`: Introduced SMS management services (`send_sms`, `delete_sms`, `delete_all_sms`, `get_sms_list`).
  - `v1.2.0`: Added encoding-aware length limits (up to 612 characters) and SMS Storage Full sensor.
  - `v1.2.2`: Enabled SMS Storage Full sensor by default on new setups.
  - `v1.2.4`: Added `event.<name>_incoming_sms`, stopped-HA message announcement, DST-safe `_sms_identity`, and inbox-verified SMS deletes.

### Client Device Tracking & Registry Hygiene

- **Purpose**: Monitors connected wired and wireless LAN clients and manages enabled integration entities and stale registry entries.
- **Entities & Interfaces**:
  - `device_tracker.<client_name>`
  - Actions: `huawei_router_5g.reset_entities`, `huawei_router_5g.cleanup_unused_entities`.
- **Technical Guarantees**:
  - Unique IDs scoped per configuration entry using device MAC addresses, preventing collisions on multi-router setups; sub-device parent links use `DeviceInfo` dataclass initialization for Home Assistant `2026.11` compatibility.
  - `reset_entities` provides 11-parameter bulk entity management defaulting to dry-run preview mode while leaving device trackers untouched.
  - `cleanup_unused_entities` defaults to dry-run preview mode before deleting orphaned guest client tracker entities.
- **Lifecycle Timeline**:
  - `v1.0.1`: Basic IP-based client tracking.
  - `v1.1.0`: Migrated client tracker unique IDs to entry-scoped MAC addresses.
  - `v1.2.0`: Added `cleanup_unused_entities` maintenance action with dry-run support.
  - `v1.2.4`: Added `reset_entities` bulk entity management action and HA `2026.11` `DeviceInfo` parent-link compatibility.

---

## 4. Diagnostics, Health & Platform Resilience

### Multi-Tier Integration Health Diagnostics

- **Purpose**: Provides continuous monitoring of endpoint availability, firmware changes, library state, and communication degradation.
- **Entities & Interfaces**: `binary_sensor.<name>_integration_health`.
- **Technical Guarantees**:
  - Standardized 5-state health severity classification (`ok`, `degraded`, `warning`, `error`, `unknown`).
  - Tracks individual unpolled endpoints and surfaces newly refused endpoints under `not_served` (persisted across restarts), alongside `library_loaded`, `library_installed`, and `core_huawei_lte_configured` status attributes.
  - Distinguishes expected transient outages from systemic communication failures.
- **Lifecycle Timeline**:
  - `v1.1.3`: Integration Health sensor introduced.
  - `v1.2.0`: Standardized 5-state severity enum and strike counters.
  - `v1.2.3`: Added `not_served` tracking for gracefully refused optional endpoints.
  - `v1.2.4`: Persisted `answered_endpoints` / `not_served` across restarts and added library coexistence status attributes.

### Diagnostic Bundle Sanitization & Endpoint Probes

- **Purpose**: Generates diagnostic exports for troubleshooting without leaking sensitive network credentials or private data.
- **Entities & Interfaces**: Home Assistant Diagnostics platform (`async_get_config_entry_diagnostics`).
- **Technical Guarantees**:
  - Multi-pass sanitization redacts passwords, Wi-Fi keys, IP addresses, MAC addresses, operator `ApnName` in `dial_up_profiles`, and tokenizes phone numbers matched by shape under any key.
  - Probes 65 diagnostic endpoints on demand (including 18 unwrapped router paths read by path and recorded by key name only), records capability probe values safely, lists `unread_keys`, and records per-endpoint `http_statuses` via a passive post-login response hook.
- **Lifecycle Timeline**:
  - `v1.0.3`: Diagnostics platform baseline.
  - `v1.2.0`: Added diagnostic tokenization and privacy filters for phone numbers.
  - `v1.2.3`: Widened diagnostic probe set to 46 endpoints and added endpoint classification reporting.
  - `v1.2.4`: Expanded to 65 probes (18 unwrapped), shape-matched phone tokenization, `ApnName` redaction, `unread_keys`, and per-endpoint `http_statuses`.

### Dual-Platform Library Coexistence Guard

- **Purpose**: Enables installation and operation alongside Home Assistant Core's built-in `huawei_lte` integration without dependency collisions or restart prompts.
- **Entities & Interfaces**: `library_guard.py`, `binary_sensor.<name>_integration_health` (`library_loaded`, `library_installed`, `core_huawei_lte_configured`).
- **Technical Guarantees**:
  - Manifest specifies wide dependency range `>=1.11.0,<2.0.2` to prevent pip package conflicts.
  - Background startup guard installs `2.0.1` silently when safe without raising a repair (and clears any leftover `library_restart_required` repair).
  - `_call_added_endpoint` reads `voice/volte` and `monitoring/onekey_diag` directly through the library session when running alongside `1.11.0`.
- **Lifecycle Timeline**:
  - `v1.2.3`: Introduced library coexistence guard, version range widening, and restart repair flow.
  - `v1.2.4`: Removed restart repair flow in favor of silent `2.0.1` install and added direct `1.11.0` reads for `voice/volte` and `monitoring/onekey_diag`.

### Interactive Re-Authentication & Repairs Integration

- **Purpose**: Alerts users to authentication failures or persistent communication errors with actionable fix flows.
- **Entities & Interfaces**: `repair.auth_failed`, `repair.conn_error`.
- **Technical Guarantees**:
  - Clicking "Fix" on an authentication repair opens the re-authentication dialog directly.
  - Automatically clears stale repair issues upon successful coordinator poll recovery.
- **Lifecycle Timeline**:
  - `v1.2.0`: Introduced Repairs platform integration with vendor-prefixed issue titles.
  - `v1.2.2`: Implemented interactive re-authentication fix flow for `auth_failed`.

### Config Flow Security, Host Sanitization & Reconfiguration

- **Purpose**: Provides secure UI setup, credential updates, host URL cleaning, and dynamic options reconfiguration.
- **Entities & Interfaces**: Config flow, Reconfiguration flow, Options flow (`config_flow.py`).
- **Technical Guarantees**:
  - Passwords masked with `TextSelector` and omitted on edit forms so stored credentials are never exposed or pre-filled.
  - Strips protocol schemes (`http://`, `https://`) and trailing slashes from host inputs before saving, preventing doubled `configuration_url` endpoints.
  - Reconfiguration seamlessly updates credentials while preserving runtime options (`scan_interval`, `stop_polling`).
- **Lifecycle Timeline**:
  - `v1.0.1`: Initial config flow with basic credential entry.
  - `v1.1.2`: Split setup and edit schemas; masked passwords; added host cleaning helper `_clean_host()`.
  - `v1.2.0`: Added live options updates with clean runtime merge and rename handling.

---

## 5. Platform, Tooling & Infrastructure

### Comprehensive Unit & Regression Test Suite

- **Purpose**: Verifies integration behavior, error handling, and platform contracts offline.
- **Interfaces**: Pytest test suite (`tests/`), `pytest-homeassistant` on Home Assistant `2026.11.1`.
- **Technical Guarantees**:
  - `1,580` automated tests achieving `100.00%` statement and branch test coverage.
  - Autouse conftest fixtures block unauthorized external network calls, catch unawaited async tasks, pin `huawei-lte-api` empty-body `503` behavior (`test_library_contract.py`), and guard deprecated device-registry usage (`test_entity_hygiene.py`).
- **Lifecycle Timeline**:
  - `v1.0.1`: Initial unit test suite.
  - `v1.1.1`: Achieved 100% statement test coverage baseline.
  - `v1.2.0`: Enforced 100% line and branch coverage threshold in test runners.
  - `v1.2.3`: Test surface expanded to 1,311+ tests covering refusal adjudication and coexistence.
  - `v1.2.4`: Migrated harness to `pytest-homeassistant` on HA `2026.11.1`; expanded to `1,580` tests at `100.00%` coverage with `503` contract and registry-guard tests.

### Automated Mutation Testing Verification

- **Purpose**: Proves that test assertions actively verify business logic by mutating production code and verifying test failures.
- **Interfaces**: Mutation testing runner and mutation test proofs.
- **Technical Guarantees**:
  - 100% catch rate across write locks, parser branches, uptime reconciliation, refusal adjudication, outage windows, and SMS identity checks.
- **Lifecycle Timeline**:
  - `v1.2.0`: Mutation testing framework established across parsers and write methods.
  - `v1.2.3`: Mutation verification proofs applied to refusal adjudication and uptime store logic.
  - `v1.2.4`: Extended mutation proofs to outage windows, session release, write retries, checked SMS deletes, and `503` contract tests.

### Stateful Mock Router Transport Harness

- **Purpose**: Provides offline simulation of Huawei router firmware behaviors for repeatable testing.
- **Interfaces**: `tests/transport.py`.
- **Technical Guarantees**:
  - Accurately models session cookies, token rotation, mid-fetch expirations, endpoint refusals, stateful SMS inboxes, and worker-thread delays.
- **Lifecycle Timeline**:
  - `v1.0.1`: Basic static response mock transport.
  - `v1.2.0`: Added thread contention and concurrency delay simulation.
  - `v1.2.3`: Added session state, cookie jar modeling, and configurable endpoint refusal error codes.
  - `v1.2.4`: Added stateful SMS inbox modeling (`inbox`, `kept_on_delete`, `fill_inbox`).

### Code Complexity & Architectural Governance

- **Purpose**: Maintains strict software engineering standards and limits routine bloat.
- **Interfaces**: `docs/project_complexity.md`, `manifest.json`, McCabe complexity checks, Ruff (`PLC0415` enforced outside `tests/`), strict Mypy.
- **Technical Guarantees**:
  - Maximum cyclomatic complexity $V(G)$ strictly capped below 20 (peak routine `16` in `_fetch_one`).
  - Strict Mypy type checking enforced across all `20` integration source files; HACS `categories` metadata validated.
- **Lifecycle Timeline**:
  - `v1.1.1`: Strict Mypy type checking adopted.
  - `v1.2.3`: Coordinator complexity refactored from 25 to 16; complexity scorecard tracked in `docs/project_complexity.md`.
  - `v1.2.4`: Enforced strict Mypy across `20` source files, Ruff `PLC0415` top-level imports, and HACS `categories` in `manifest.json`.

---

*Capabilities dossier audited against codebase and changelogs up to `v1.2.4` on 2026-11-16. Maintained via `capabilities_build.md`.*
