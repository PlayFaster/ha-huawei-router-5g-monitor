# Huawei Router 5G Monitor Capabilities Dossier

An architectural reference and at-a-glance inventory of verified capabilities, interfaces, technical guarantees, and version lineage for `ha-huawei-router-5g-monitor`.

**Current Through:** `v1.2.3` (covering `v1.0.1` to `v1.2.3`) · **Last Audited:** 2026-10-09 · **Status:** `Active`

---

## 1. Connection & Session Control

### Dual-Session Coexistence & Refusal Adjudication

- **Purpose**: Authenticates against Huawei router web APIs and distinguishes unsupported endpoint refusals from expired sessions, preventing premature re-authentication errors.
- **Entities & Interfaces**: Coordinator polling engine, `sensor.<name>_integration_health` (attribute `not_served`).
- **Technical Guarantees**:
  - Distinguishes endpoint refusals (`100003`, `125002`, `125003`) from expired logins via an anonymous premise check on `device.information` (`PREMISE_TIMEOUT = 3s`).
  - Adjudication loop bounded by `ADJUDICATION_BUDGET` to guarantee poll completion within `FETCH_TIMEOUT` (30s).
  - Unanimously unsupported endpoints recorded under `not_served` without taking error strikes or degrading health severity.
- **Lifecycle Timeline**:
  - `v1.0.1`: Initial polling engine with basic exception handling.
  - `v1.1.1`: Automatic session re-login on expired mid-fetch calls.
  - `v1.2.0`: Timeout recovery closes underlying HTTP sockets and rebuilds fresh sessions.
  - `v1.2.3`: Full refusal adjudication introduced (`v123_dev16_plan.md`); added `not_served` attribute to prevent setup failure on partial firmware implementations.

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
  - Automatically schedules asynchronous follow-up refresh when the cellular connection settles.
- **Lifecycle Timeline**:
  - `v1.2.0`: Introduced Reconnect button with dual dial action sequence.

### Device Reboot & Follow-Up Refresh Automation

- **Purpose**: Reboots the router hardware safely from Home Assistant with automated polling recovery.
- **Entities & Interfaces**: `button.<name>_reboot`.
- **Technical Guarantees**:
  - API errors during reboot submission are propagated directly to the UI rather than swallowed.
  - Schedules an asynchronous follow-up poll when the router completes rebooting, including when background polling is paused.
- **Lifecycle Timeline**:
  - `v1.0.1`: Basic reboot action added.
  - `v1.1.1`: Exception propagation hardened to surface API errors.
  - `v1.2.0`: Automated follow-up polling refresh scheduled upon reboot completion.

### Configurable Polling Interval & Polling Suspension

- **Purpose**: Controls update frequency and allows pausing scheduled background polling without taking integration entities offline.
- **Entities & Interfaces**:
  - `number.<name>_polling_interval`
  - `switch.<name>_pause_polling`
  - `button.<name>_refresh`
- **Technical Guarantees**:
  - Polling interval changes debounced for two seconds; pending values flushed on entity removal rather than discarded.
  - Pausing polling leaves entities in their last known valid state rather than setting them unavailable.
  - Manual Refresh Now overrides the pause state to fetch current router status immediately.
- **Lifecycle Timeline**:
  - `v1.0.1`: Initial polling interval slider and pause polling switch.
  - `v1.1.2`: Added Refresh Now button; debounced interval adjustments with safe removal flushing.
  - `v1.2.0`: Follow-up refresh actions after reboots and reconnects execute even while polling is paused.

---

## 2. Sensor Metrics, Data & Uptime Tracking

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
- **Entities & Interfaces**: `sensor.<name>_integration_health` (attributes `drift_rate_pct`, `drift_deficit_seconds`).
- **Technical Guarantees**:
  - Duration-weighted accumulators track counter drift across consecutive polling cycles.
  - Drift rate applied to boot anchor calculation (`now - counter / (1 - rate)`) with a 30-day window cap.
- **Lifecycle Timeline**:
  - `v1.2.3`: Added clock drift calibration, diagnostics attributes, and diagnostic export data.

### Signal Diagnostics & 3-Stage Best Connection Gate

- **Purpose**: Monitors cellular radio metrics (RSRP, RSRQ, SINR, RSSI, Frequency, Band, Cell ID) and reports true 5G operational status.
- **Entities & Interfaces**:
  - `sensor.<name>_best_connection`
  - Radio signal sensors (RSRP, RSRQ, SINR, RSSI, Frequency, Band, Cell ID).
- **Technical Guarantees**:
  - 3-stage quality gate validates 5G NSA/SA operational readiness before asserting active 5G connectivity.
  - Min/max guard bands clamp unparsable or out-of-range frequency and transmit power readings.
- **Lifecycle Timeline**:
  - `v1.0.1`: Introduced Best Connection sensor with 3-stage quality gate and signal scaling.
  - `v1.2.0`: Added guard bands for transmit power and multi-valued metric parsers.

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
  - Option list queried directly from router hardware rather than offering hardcoded, unsupported modes.
  - State read-back executed outside locks to ensure radio re-registration settles without dropping cell band locking.
- **Lifecycle Timeline**:
  - `v1.0.1`: Basic static network mode select entity.
  - `v1.2.0`: Switched to dynamic router-queried option discovery; mapped 5G-only mode (`08`).

### SMS Inbox & Messaging Suite

- **Purpose**: Provides full programmatic SMS management directly from Home Assistant automations and scripts.
- **Entities & Interfaces**:
  - Actions: `huawei_router_5g.send_sms`, `delete_sms`, `delete_all_sms`, `get_sms_list`.
  - Sensors: `sensor.<name>_sms_unread`, `binary_sensor.<name>_sms_storage_full`.
- **Technical Guarantees**:
  - Message length validation supports up to 612 characters with automatic GSM-7 vs. Unicode segment calculation.
  - Proactive session recovery re-authenticates before executing SMS actions if previous session expired.
  - Storage full binary sensor enabled by default on new installations to prevent silent inbox dropouts.
- **Lifecycle Timeline**:
  - `v1.0.1`: Display Last SMS sensor introduced.
  - `v1.0.2`: Introduced SMS management services (`send_sms`, `delete_sms`, `delete_all_sms`, `get_sms_list`).
  - `v1.2.0`: Added encoding-aware length limits (up to 612 characters) and SMS Storage Full sensor.
  - `v1.2.2`: Enabled SMS Storage Full sensor by default on new setups.

### Client Device Tracking & Registry Hygiene

- **Purpose**: Monitors connected wired and wireless LAN clients and removes stale entries from the Home Assistant entity registry.
- **Entities & Interfaces**:
  - `device_tracker.<client_name>`
  - Action: `huawei_router_5g.cleanup_unused_entities`.
- **Technical Guarantees**:
  - Unique IDs scoped per configuration entry using device MAC addresses, preventing collisions on multi-router setups.
  - Cleanup service defaults to dry-run preview mode before deleting orphaned guest client tracker entities.
- **Lifecycle Timeline**:
  - `v1.0.1`: Basic IP-based client tracking.
  - `v1.1.0`: Migrated client tracker unique IDs to entry-scoped MAC addresses.
  - `v1.2.0`: Added `cleanup_unused_entities` maintenance action with dry-run support.

---

## 4. Diagnostics, Health & Platform Resilience

### Multi-Tier Integration Health Diagnostics

- **Purpose**: Provides continuous monitoring of endpoint availability, firmware changes, and communication degradation.
- **Entities & Interfaces**: `binary_sensor.<name>_integration_health`.
- **Technical Guarantees**:
  - Standardized 5-state health severity classification (`ok`, `degraded`, `warning`, `error`, `unknown`).
  - Tracks individual unpolled endpoints and surfaces newly refused endpoints under `not_served`.
  - Distinguishes expected transient outages from systemic communication failures.
- **Lifecycle Timeline**:
  - `v1.1.3`: Integration Health sensor introduced.
  - `v1.2.0`: Standardized 5-state severity enum and strike counters.
  - `v1.2.3`: Added `not_served` tracking for gracefully refused optional endpoints.

### Diagnostic Bundle Sanitization & Endpoint Probes

- **Purpose**: Generates diagnostic exports for troubleshooting without leaking sensitive network credentials or private data.
- **Entities & Interfaces**: Home Assistant Diagnostics platform (`async_get_config_entry_diagnostics`).
- **Technical Guarantees**:
  - Multi-pass sanitization redacts passwords, Wi-Fi keys, IP addresses, MAC addresses, and tokenizes phone numbers.
  - Probes 46 diagnostic endpoints on demand while enforcing internal session churn limits.
- **Lifecycle Timeline**:
  - `v1.0.3`: Diagnostics platform baseline.
  - `v1.2.0`: Added diagnostic tokenization and privacy filters for phone numbers.
  - `v1.2.3`: Widened diagnostic probe set to 46 endpoints and added endpoint classification reporting.

### Dual-Platform Library Coexistence Guard

- **Purpose**: Enables installation and operation alongside Home Assistant Core's built-in `huawei_lte` integration without dependency collisions.
- **Entities & Interfaces**: `library_guard.py`, `repair.library_restart_required`.
- **Technical Guarantees**:
  - Manifest specifies wide dependency range `>=1.11.0,<2.0.2` to prevent pip package conflicts.
  - Background startup guard verifies core presence and automatically installs `2.0.1` when safe.
  - Raises a fixable Home Assistant Repair issue notifying user when a restart is required.
- **Lifecycle Timeline**:
  - `v1.2.3`: Introduced library coexistence guard, version range widening, and restart repair flow.

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
- **Interfaces**: Pytest test suite (`tests/`).
- **Technical Guarantees**:
  - 1,312 automated tests achieving 100% statement and branch test coverage.
  - Autouse conftest fixtures block unauthorized external network calls and catch unawaited async tasks.
- **Lifecycle Timeline**:
  - `v1.0.1`: Initial unit test suite.
  - `v1.1.1`: Achieved 100% statement test coverage baseline.
  - `v1.2.0`: Enforced 100% line and branch coverage threshold in test runners.
  - `v1.2.3`: Test surface expanded to 1,311+ tests covering refusal adjudication and coexistence.

### Automated Mutation Testing Verification

- **Purpose**: Proves that test assertions actively verify business logic by mutating production code and verifying test failures.
- **Interfaces**: Mutation testing runner and mutation test proofs.
- **Technical Guarantees**:
  - 100% catch rate across write locks, parser branches, uptime reconciliation, and refusal checks.
- **Lifecycle Timeline**:
  - `v1.2.0`: Mutation testing framework established across parsers and write methods.
  - `v1.2.3`: Mutation verification proofs applied to refusal adjudication and uptime store logic.

### Stateful Mock Router Transport Harness

- **Purpose**: Provides offline simulation of Huawei router firmware behaviors for repeatable testing.
- **Interfaces**: `tests/transport.py`.
- **Technical Guarantees**:
  - Accurately models session cookies, token rotation, mid-fetch expirations, endpoint refusals, and worker-thread delays.
- **Lifecycle Timeline**:
  - `v1.0.1`: Basic static response mock transport.
  - `v1.2.0`: Added thread contention and concurrency delay simulation.
  - `v1.2.3`: Added session state, cookie jar modeling, and configurable endpoint refusal error codes.

### Code Complexity & Architectural Governance

- **Purpose**: Maintains strict software engineering standards and limits routine bloat.
- **Interfaces**: `docs/project_complexity.md`, McCabe complexity checks (`ruff`).
- **Technical Guarantees**:
  - Maximum cyclomatic complexity $V(G)$ strictly capped below 20 (peak routine 18 in `get_data`).
  - Strict MyPy type checking enforced across all 17 integration source files.
- **Lifecycle Timeline**:
  - `v1.1.1`: Strict MyPy type checking adopted.
  - `v1.2.3`: Coordinator complexity refactored from 25 to 16; complexity scorecard tracked in `docs/project_complexity.md`.

---

*Capabilities dossier audited against codebase and changelogs up to `v1.2.3` on 2026-10-09. Maintained via `capabilities_build.md`.*
