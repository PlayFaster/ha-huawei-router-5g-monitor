# Internal Detailed Changelog: Huawei Router 5G Monitor

This document tracks technical shifts, architectural decisions, and detailed implementation notes for the Huawei Router 5G Monitor project.

---

## [1.0.1] - 2026-05-03

### Added

- **100% Test Coverage for `helpers.py`**: Achieved full coverage of the shared helpers module by adding 38 comprehensive test cases to `test_helpers.py`.
- **Complex Signal Parsing Tests**: Verified that multi-carrier and technical strings (e.g., `DL:500 UL:18500`) are correctly handled by the `_parse_complex_int` and `_parse_complex_float` logic.
- **SMS Hardware Variation Tests**: Implemented test scenarios for diverse router SMS behaviors, including metadata-offset lists, single-message dictionaries, and malformed container types.
- **Device Registry Logic Verification**: Added tests for `build_device_info` to ensure stable entity identification using both MAC and host-based fallbacks.

### Changed

- **Project-wide Test Coverage Milestone**: Successfully increased total project test coverage to **90%**.

### Fixed

- **Linting Compliance**: Resolved all `E501` (Line too long) issues in `test_helpers.py` comments to maintain 100% ruff compliance in the test suite.

---

## [1.0.1-rc5] - 2026-05-03

### Added

- **Guard bands on all 8 frequency/bandwidth sensors**: Added `max_limit` to complete the guard band coverage (all 8 already had `min_limit=0`). Limits are grounded in 3GPP standards:
  - `lte_uplink_frequency` / `lte_downlink_frequency`: `max_limit=3800` MHz — highest deployed mobile LTE band (B42/B43).
  - `lte_uplink_bandwidth` / `lte_downlink_bandwidth`: `max_limit=20` MHz — definitive 3GPP LTE maximum channel bandwidth per carrier.
  - `5g_uplink_frequency` / `5g_downlink_frequency`: `max_limit=7125` MHz — exact 3GPP FR1 upper boundary. FR2/mmWave not applicable to this hardware.
  - `5g_uplink_bandwidth` / `5g_downlink_bandwidth`: `max_limit=100` MHz — 3GPP FR1 maximum NR channel bandwidth per carrier.

### Fixed

- **Translation gap — 4 sensor keys missing from `strings.json`**: `primary_ipv6_dns`, `secondary_ipv6_dns`, `5g_uplink_frequency`, and `5g_downlink_frequency` were present in `en.json` but absent from `strings.json`. Added in positionally correct locations (IPv6 DNS keys after `secondary_dns`; 5G frequency keys after `lte_downlink_bandwidth`).

### Changed

- **`bandwidth_issue.md` fully rewritten**: The `.notes/bandwidth_issue.md` reference document was superseded — it encoded the original pre-fix understanding (wrong divisors, wrong field assignments, inverted warnings) and had never been updated after the bugs were corrected. Replaced with accurate field-to-sensor mapping table, correct helper function descriptions with raw-value examples, field-confusion history explaining the original bugs, the finalized guard band table, and observed live values from the H165-383.

---

## [1.0.1-rc4] - 2026-05-03

### Changed

- **Project Documentation Sync**: Conducted a full audit of all 106+ entities against the Home Assistant ground truth JSON.
- **Master Manifest Alignment**: Synchronized `docs/huawei_5g_all_sensors.md` with current implementation keys (e.g., legacy `nr_` prefix migrated to `5g_`), standardized names, and corrected categories. Added missing entries for **IPv6 DNS Servers** and the **Network Mode** sensor.
- **README Updates**: Updated `README.md` to reflect the current entity count (106+) and replaced the outdated "5G NR active" binary sensor with the overhauled **"Best Connection"** sensor in the "What You Get" table.
- **Guard Band & Dev Journal Sync**: Aligned `docs/value_min_max.md` and `docs/DEVELOPMENT.md` with finalized sensor names and documented the recent architectural shifts from dev18 to dev22.
- **Unit Source-of-Truth**: Re-confirmed and standardized documentation to use base units (Seconds, Bytes, B/s) as the authoritative source-of-truth, ensuring alignment with device output regardless of Home Assistant UI auto-scaling.

---

## [1.0.1-rc3] - 2026-05-03

### Fixed

- **CI Validation Failure**: Resolved `ModuleNotFoundError: No module named 'huawei_lte_api'` in GitHub Actions by adding `huawei-lte-api` and `url-normalize` to `.validate/requirements_test.txt`.
- **CI Coverage Path**: Corrected the `--cov` flag in `.github/workflows/validate.yaml` to point to `custom_components/huawei_router_5g` (previously incorrectly pointing to a `zte` directory), ensuring valid coverage reports in CI.

---

## [1.0.1-dev22] - 2026-05-03

### Added

- **Primary/Secondary IPv6 DNS sensors**: New diagnostic sensors (`primary_ipv6_dns`, `secondary_ipv6_dns`) reading `PrimaryIPv6Dns`/`SecondaryIPv6Dns` from the `monitoring_status` API response. Mirrors the existing IPv4 DNS pair and fills a gap identified against the HA core Huawei LTE project.
- **5G Uplink/Downlink Frequency sensors**: Added `5g_uplink_frequency` and `5g_downlink_frequency` diagnostic sensors reading the `ulfrequency`/`dlfrequency` API fields (raw kHz, scaled ÷1000 via `format_khz_to_mhz`). Renamed from the generic `uplink_frequency`/`downlink_frequency` introduced in dev18 to make the 5G scope explicit and consistent with the naming convention used throughout this project.

### Fixed

- **"Unit of Measurement" selector absent on all 8 frequency/bandwidth sensors**: The `device_class=FREQUENCY` HA entity property pages showed no unit selector, preventing users from switching between MHz/kHz/GHz display units. Root cause: all 8 sensors had `state_class=SensorStateClass.MEASUREMENT` set, routing them through HA's long-term statistics path, which does not surface the unit selector for the `FREQUENCY` device class. Fixed by removing `state_class` from all 8 sensors (`lte_uplink_frequency`, `lte_downlink_frequency`, `lte_uplink_bandwidth`, `lte_downlink_bandwidth`, `5g_uplink_frequency`, `5g_downlink_frequency`, `5g_uplink_bandwidth`, `5g_downlink_bandwidth`), matching the pattern used by the HA core Huawei LTE project where frequency sensors carry only `device_class` and the unit selector is surfaced via HA's device-class auto-conversion path.
- **Preferred Network Mode sensor icon invalid**: `preferred_network_mode` was using `mdi:settings-transfer`, which does not resolve in current Material Design Icons. Replaced with `mdi:tune`.

### Changed

- **`format_bw_mhz` renamed to `format_khz_to_mhz`**: Helper function renamed to accurately reflect its sole purpose — scaling kHz carrier-frequency fields to MHz (÷1000). The original name was inherited from an earlier implementation where it was also (incorrectly) used for bandwidth fields; after that was corrected in dev18 the name became misleading.

---

## [1.0.1-dev21] - 2026-05-03

### Fixed

- **Test Suite Reliability**: Resolved `RuntimeWarning` for unawaited coroutines in setup tests by explicitly closing or awaiting background initialization tasks in `test_init.py`.
- **Linting Compliance**: Resolved all manual `ruff` errors (`SIM117`) in `tests/test_api.py` by combining nested `with` statements for `patch` and `pytest.raises`.

### Changed

- **Test Coverage Expansion**: Verified 220/220 tests passing with zero warnings and 100% clean linting in the Docker devcontainer environment.

---

## [1.0.1-dev19] - 2026-05-03

### Added

- **Best Connection logic document**: Created `docs/best_connection_logic.md` as a detailed reference for the 3-stage quality gate algorithm, threshold rationale, idle-stability analysis, and H165-383-specific API field behaviour.

### Changed

- **Best Connection sensor overhauled**: Renamed from "5G NR Active" to "Best Connection". Replaced the simple NR active stub (checking `sc_band`/`nrrsrp` presence) with a 3-stage quality gate. All three stages must pass for the sensor to report ON:
  - **Stage 1 — NR band assignment**: `(N` present in composite `band` string (e.g. `(N28)`). Replaces `network_type` check, which reports `"LTE"` even in active NSA mode on the H165-383, and replaces `sc_band`, which is always null on this firmware.
  - **Stage 2 — LTE anchor health**: `rsrp > -100` OR `sinr > 15` OR `rsrq > -12`. RSRQ is load-bearing on real hardware: observed RSRP (-103) and SINR (13) both fail their thresholds on a healthy 4-bar connection; RSRQ (-9) passes.
  - **Stage 3 — 5G leg health**: `nr_rsrp > -105` OR `nr_sinr > 10` OR `nr_rsrq > -12` OR `5g_cqi >= 7` OR `bler < 10%`.
  - Promoted from `EntityCategory.DIAGNOSTIC` to primary entity (no category) — visible in the main entity list and usable in dashboards and automations.
- **Enabled by default — 11 entities** previously disabled without data on the H165-383 but confirmed populated:
  - _System timestamps_: Uptime, Connection Uptime, Total Uptime.
  - _Signal diagnostics_: LTE Transmit Power, LTE Uplink MCS, LTE Downlink MCS, LTE EARFCN, 5G Uplink MCS, 5G Downlink MCS, 5G Transmit Power.
  - _Binary sensor_: LTE Carrier Aggregation.

---

## [1.0.1-dev18] - 2026-05-03

### Added

- **LTE Uplink/Downlink Frequency (Secondary) sensors**: New diagnostic sensors (`uplink_frequency`, `downlink_frequency`) reading the `ulfrequency`/`dlfrequency` API fields (raw kHz, scaled ÷1000 to MHz). These expose the same carrier frequency as the primary sensors via a different API path, useful for cross-validation.

### Fixed

- **LTE Frequency sensors 10× too low**: `LTE Uplink Frequency` and `LTE Downlink Frequency` were reporting 197 MHz / 216 MHz instead of the correct ~1970 MHz / ~2160 MHz. Root cause: the `lteulfreq`/`ltedlfreq` fields are in 10ths of MHz; the `format_freq_mhz` helper was dividing by 100 instead of 10.
- **LTE Bandwidth sensors reporting frequency instead of bandwidth**: `LTE Uplink Bandwidth` and `LTE Downlink Bandwidth` were showing ~1970 MHz / ~2160 MHz instead of the correct 20 MHz. Root cause: sensors were reading the `ulfrequency`/`dlfrequency` fields (carrier frequency in kHz) rather than the correct `ulbandwidth`/`dlbandwidth` fields (channel width in MHz, no scaling required).
- **LTE Carrier Aggregation always "unknown"**: The `lte_ca` API field returns null on the H165-383. Sensor now derives CA status from the composite `band` string by detecting `+` separators between carrier entries.
- **5G NR Band always "unknown"**: The `sc_band` API field returns null on the H165-383. Sensor now parses the NR band label (e.g., `N28`) from the `(NXX)` segment in the composite `band` string.

### Changed

- **LTE Carrier Aggregation converted to binary sensor**: Moved `lte_ca` from a string-valued sensor ("enabled"/"disabled") to a proper `binary_sensor` (ON/OFF). The underlying value is inherently boolean (`"+" in band`), and a binary sensor is the correct HA platform for this. Remains disabled by default and in the Diagnostic category.
- **Max Download Rate / Max Upload Rate disabled by default**: These sensors are permanently "unknown" on the H165-383 as the firmware does not populate `MaxDownloadRate`/`MaxUploadRate` in the traffic statistics response. Disabled by default to avoid persistent unknown entities in the UI.

---

## [1.0.1-dev16] - 2026-05-03

### Added

- **Complex Signal Metric Support**: Implemented robust parsing for technical diagnostic sensors that frequently return multi-valued strings (e.g., multi-carrier MCS or per-channel Transmit Power).
  - New `_parse_complex_int` and `_parse_complex_float` helpers preserve the full raw string when complexity (colons or spaces) is detected, preventing "Unknown" states.
  - Impacted entities: LTE/5G Downlink MCS, Uplink MCS, EARFCN, and Transmit Power.

### Changed

- **Guard Band Optimization**: Removed `min_limit` and `max_limit` constraints from 8 technical diagnostic sensors to ensure multi-carrier strings are not accidentally filtered or "partial-parsed" by the numeric validation engine.

### Fixed

- **LTE Carrier Aggregation Logic**: Corrected the `lte_ca` sensor to properly return `None` (Unavailable) when data is missing from the API response, rather than defaulting to "disabled".

---

## [1.0.1-dev15] - 2026-05-03

### Added

- **Dynamic SMS Box Selection**: Integration now automatically detects whether messages are stored in the Device Inbox or SIM Inbox by checking `sms_count` results before fetching the list. This ensures "Last Msg" works regardless of storage configuration.
- **Aggregate SMS Sensor**: Created `Total Msg` as a primary sensor that sums all messages across both Device and SIM storage.
- **SMS Entity Renaming Refactor**:
  - Removed redundant "SMS" prefix from all entities within the SMS sub-device to fix double-naming in the UI.
  - Standardized labels: `Unread Msg`, `Total Msg`, `Last Msg`, and simplified location-specific labels (e.g., `Total (SIM)`).
- **Corrected SMS Quantity Sensors**: Fixed invalid API keys for individual storage sensors (e.g., `LocalInbox` -> `LocalUnread` + `LocalRead`), resolving "Unknown" states for technical counters.

### Changed

- **SMS Category Optimization**:
  - Renamed **New Msg** -> **In Process** and moved to **Diagnostic** to reflect its transient notification state.
  - Moved **Total (Device)** and **Total (SIM)** to the **Diagnostic** category.
- **API Call Simplification**: Stripped non-essential parameters from `get_sms_list` (sort, order, preference) to ensure compatibility with modern 5G firmware that rejected extended XML payloads.
- **Library Compatibility**: Migrated to `BoxTypeEnum` for box selection to resolve attribute errors in recent `huawei-lte-api` versions.
- **Diagnostic Visibility**: Promoted SMS list fetch failures to the `WARNING` level with explicit error reporting.

---

## [1.0.1-dev14] - 2026-05-03

### Added

- **Explicit Reconnection Logging**: Coordinator now logs an `INFO` message when communication is restored after one or more failed fetches, improving visibility into network recovery.
- **Modern Data Management**: Migrated integration to use `entry.runtime_data` for coordinator storage, replacing the legacy `hass.data[DOMAIN]` pattern.
- **Domain-Level Service Registration**: Refactored `send_sms` service registration to `async_setup` (domain-level) rather than `async_setup_entry` (instance-level) to ensure singleton registration across multiple router entries.

### Changed

- **Parallel Update Optimization**: Added `PARALLEL_UPDATES = 0` to all platform files to indicate update coordination is handled by the coordinator.
- **Service Error Handling**: Updated `send_sms` to raise `HomeAssistantError` with descriptive feedback on failure, allowing automations to respond to errors.
- **Test Infrastructure Refactor**: Updated entire test suite to support `runtime_data` and verified 186/186 passing states.

---

## [1.0.1-dev13] - 2026-05-02

### Added

- **Full Translation Coverage (Option C)**:
  - Expanded `strings.json` and `en.json` to include 100% of the integration's entities (101 total).
  - Achieved compatibility with IQS Gold-tier naming standards.

### Changed

- **Entity Naming Refactor**:
  - Removed all hardcoded `name` parameters from `sensor.py`, `binary_sensor.py`, `select.py`, and `switch.py`.
  - Implemented `translation_key` across all platforms to enable native Home Assistant translation and dynamic naming.
  - Standardized `sms_total` as "SMS Total (Device)" in translations.

---

## [1.0.1-dev12] - 2026-05-02

### Changed

- **Signal UI Refinement**:
  - Renamed **LTE CQI 0** -> **LTE CQI** and promoted it to the main **Sensor** category (from Diagnostic) with `state_class: measurement` to match 5G CQI visibility.
  - Promoted **Signal Bars** to the main **Sensor** category, ensuring the most human-readable signal metric is visible by default.
- **SMS Entity Hygiene**:
  - Moved 12 granular SMS storage metrics (Unread/Inbox/Capacity for Device and SIM) to the **Diagnostic** category to reduce entity fatigue.
  - Kept primary actionable metrics (**SMS Unread**, **SMS New**, **SMS Total**, **Last SMS**) in the main entity list.

---

## [1.0.1-dev10] - 2026-05-02

### Changed

- **Test Suite Resilience**: Implemented a comprehensive fix for Windows-based test environments.
  - Switched to `WindowsSelectorEventLoopPolicy` in `conftest.py` to avoid `ProactorEventLoop` pipe issues.
  - Monkeypatched `pytest-socket` to prevent internal asyncio pipes from triggering `SocketBlockedError`.
- **API Exception Standardization**: Standardized the instantiation of `ResponseErrorException` and `ResponseErrorLoginRequiredException` in tests to ensure they include required `code` and `message` arguments, matching the underlying library's signature.
- **Test Alignment**:
  - Re-aligned `test_get_data_partial_failure` to reflect that `device_information` is now a critical, mandatory field.
  - Updated `test_select.py` to verify human-readable labels (e.g., "Auto", "4G Only") instead of technical numeric codes.
  - Updated SMS Storage Full tests to use the corrected `monitoring_check_notifications` data source.

### Fixed

- **Pytest Configuration**: Removed the deprecated/invalid `allow_hosts` option from `pyproject.toml` to eliminate test suite warnings.

---

## [1.0.1-dev9] - 2026-05-02

### Added

- **Long-Term Statistics Support**: Added `state_class` to key sensors to enable Home Assistant long-term statistics.
  - `TOTAL_INCREASING`: Total Duration, Connection Duration, Uptime Duration.
  - `TOTAL`: Month Download (GB), Month Upload (GB).
- **Human-Readable Network Mode**:
  - Added a diagnostic sensor that maps technical PLMN/Network codes to readable text (e.g., "4G/3G Auto").
  - Refactored the "Preferred Network Mode" select entity to use these readable labels in the dropdown while maintaining technical code mapping for the API.

### Changed

- **Entity Naming Consolidation**:
  - Renamed **Total Connection Duration** -> **Total Duration**.
  - Renamed **Total Connection Uptime** -> **Total Uptime**.
  - Renamed **Current Connection Uptime** -> **Connection Uptime**.
  - Renamed **Current Connection Duration** -> **Connection Duration**.
- **5G Rank Refinement**: Reverted "5G Rank" to a raw numeric measurement (1-4) and moved it to the standard Sensor category (from Diagnostic) for better historical charting.
- **Entity Defaults**: Ensured all duration and uptime sensors are disabled by default to minimize UI clutter for new users.
- **Wi-Fi Guest Network**: Explicitly named and translated the Guest Wi-Fi switch (previously appeared as the device name).

### Fixed

- **SMS Storage Full Source**: Corrected the data source for the SMS Storage Full binary sensor to use `monitoring_check_notifications`, matching reference behavior and resolving the "Unknown" state.

---

## [1.0.1-dev8] - 2026-05-02

### Added

- **Immediate Session Retry**: Implemented a seamless retry mechanism in the coordinator. If a session expires mid-fetch, the integration now immediately re-authenticates and retries the fetch within the same cycle, eliminating periodic "session timeout" warnings and data delays.

### Changed

- **Entity Metadata & Icons**:
  - Moved **Operator** entity to the **Diagnostic** category.
  - Set **Signal Bars** as a **Measurement** sensor for better historical tracking.
  - Corrected scaling for **Secondary Frequency** sensors (divided by 1000 to match primary MHz scaling).
  - Updated icons for over 35 entities, including new directional icons for 5G bandwidth and messaging icons for SMS Outboxes to ensure proper display in the HA UI.

### Fixed

- **Frequency Scaling**: Resolved issue where secondary LTE frequency sensors were reporting values 100x higher than valid MHz ranges.

---

## [1.0.1-dev7] - 2026-05-02

### Changed

- **Robust Session Recovery**: Refactored `api.py` to use typed exceptions from the `huawei-lte-api` library (`ResponseErrorLoginRequiredException`, `ResponseErrorException`), enabling more reliable detection of session timeouts.
- **Error Code Detection**: Implemented explicit monitoring for router error codes `100002` (Not logged in), `125002` (Session timeout), and `125003` (Token error) during data fetch cycles to trigger immediate re-authentication.

### Fixed

- **Silent Fetch Failures**: Resolved "Critical data missing from fetch" errors by implementing a "Fast-Fail" mechanism for the `device_information` endpoint. Transient API errors for critical data are now properly surfaced as warnings and abort the fetch safely, rather than being swallowed as debug noise.
- **Reliability Test Coverage**: Expanded the reliability test suite to verify the new typed exception handling and critical key failure paths.

---

## [1.0.1-dev6] - 2026-05-02

### Added

- **send_sms Validation**: Implemented strict `voluptuous` schema validation for the `send_sms` service to ensure payloads are well-formed before API execution.

### Changed

- **Architectural Consolidation**: Extracted `device_info` generation into a shared `build_device_info` helper to enforce DRY principles across 7 platform files.
- **Signal Parsing Consolidation**: Removed redundant string parsing functions, making `helpers.py` the single source of truth for numeric sanitization (`parse_signal_value`) and network type mapping.
- **Auth Error Handling**: Switched from fragile string matching to catching specific library exceptions (`LoginErrorPasswordWrongException`, etc.) for robust auth failure detection.
- **Unit Standardization**: Replaced raw string units with Home Assistant constants (`UnitOfInformation.GIGABYTES`, `UnitOfFrequency.MEGAHERTZ`).

### Fixed

- **Critical Service Leak**: Fixed `send_sms` service not being unregistered during integration unload.
- **Configuration URL**: Resolved double-scheme (`http://http://`) bug in the Device Registry `configuration_url`.
- **Data Guard Propagation**: Fixed resilience logic improperly swallowing the `UpdateFailed` exception from the Critical Data Guard.
- **PII Leakage**: Redacted raw SMS contents and phone numbers from default logs.
- **False State Reporting**: Fixed `lte_ca` sensor reporting "disabled" instead of "Unavailable" when data was missing.
- **Client Tracking Logic**: Fixed `device_tracker` incorrectly assuming a missing `Active` field meant a client was connected.
- **Logout on Unload**: Integration now correctly calls `api.logout()` during shutdown to prevent holding zombie sessions on the router.

---

## [1.0.1-dev5] - 2026-05-02

### Added

- **Reliability Test Suite**: Implemented `tests/test_reliability_ext.py` to specifically target and verify the complex error handling and resilience logic.
  - Added tests for mid-fetch session expiration and automatic re-authentication.
  - Added tests for the **Critical Data Guard** to ensure partial responses are correctly rejected.
  - Verified `_LOGGER.exception()` tracebacks in critical failure paths.

### Changed

- **Codebase Maintenance**: Performed project-wide linting and formatting (Ruff, Prettier) to ensure 100% adherence to "PlayFaster" idiomatic standards.

---

## [1.0.1-dev4] - 2026-05-02

### Added

- **Logging Strategy Refinement**: Implemented high-fidelity diagnostics across all platforms.
  - Switched to `_LOGGER.exception()` in all critical failure paths to provide full tracebacks in Home Assistant logs.
  - Downgraded "Session Expired" mid-fetch warnings to `DEBUG` level to reduce log noise during normal re-authentication cycles.
  - Verified strict credential sanitization in all debug log calls.

### Fixed

- **Partial Entity Failure**: Resolved issue where SMS, System, and Client entities would become 'Unknown' due to silent session timeouts mid-fetch.
  - Implemented mid-fetch error detection for session timeouts (125002/125003) in `api.py`.
  - Added a **Critical Data Guard** in the coordinator to reject fetches missing essential keys like `device_information`, preventing "partial success" objects from clearing sensors.
  - Integrated authentication failures into the 3-strike resilience logic to hold last known good data during transient session drops.

## [1.0.1-dev3] - 2026-05-02

### Added

- **Declarative Guard Bands**: Implemented comprehensive min/max limits for over 80 numeric sensors. Centralized validation in `native_value` to return `None` (Unavailable) for out-of-bounds data, protecting Home Assistant's long-term statistics.
- **Robust SMS Parsing**: Implemented a resilient parser in `helpers.py` that handles varied router responses (single dictionary vs. multi-message list) and metadata offsets.
- **SMS Event Firing**: Added `huawei_router_5g_sms_event` firing in the coordinator when new messages are detected at the top of the inbox.
- **send_sms Service**: Implemented the `send_sms` service with support for multiple recipients and message content.
- **Numeric Sanitization**: Added `_safe_float` and `_safe_int` helpers to strip technical suffixes ('dBm', 'MHz', 'mbps') from API strings before conversion.

### Changed

- **Sub-device Reorganization**: Finalized grouping into 5 logical sub-devices: **System, Signal, Data, SMS, and Clients**.
- **Data Categories**: Relocated rapidly changing signal metrics (RSRP, RSRQ, SINR, RSSI) from the 'Diagnostic' to the 'Sensor' category.
- **Unit Normalization**: Ensured all data volume sensors use `UnitOfInformation.BYTES` and signal metrics use `dBm`/`dB`.

### Fixed

- **SMS Null Handling**: Fixed `AttributeError` for the `last_sms` sensor by adding coordinator data null checks.
- **Registry Stability**: Normalized all MAC identifiers to a consistent lowercase, colon-less format for stable `unique_id` generation.
- **Linting & Formatting**: Resolved all Ruff violations and formatted codebase with Prettier.

---

## [1.0.1-dev2] - 2026-05-02

### Added

- **Entity Engine Implementation**: Defined over 80 sensors using the declarative `HuaweiSensorEntityDescription` pattern.
- **Multi-Platform Support**:
  - **Binary Sensor**: Connectivity, WiFi status, and SMS storage full flags.
  - **Button**: Reboot and Clear Traffic Statistics actions.
  - **Number**: Persistent UI slider for Polling Interval (30s - 3600s) with debounced application.
  - **Select**: Network Mode selection (Auto, 4G Only, 5G Only, etc.).
  - **Switch**: Pause Polling, Mobile Data toggle, and Guest WiFi control.
  - **Device Tracker**: Dynamic discovery and tracking of LAN/WLAN clients.
- **Sub-Device Chaining**: Implemented `via_device` linking to ensure all sub-devices (Signal, Data, etc.) correctly parent to the System root device.

### Changed

- **Duration Sensors**: Implemented dual sensors for durations (raw seconds as DURATION and calculated TIMESTAMP) for Uptime and Connection Time.

---

## [1.0.1-dev1] - 2026-05-02

### Added

- **Core Architecture**: Implemented `HuaweiRouter5GDataUpdateCoordinator` with "3-strike" failure counter to mask transient network glitches.
- **API Integration**: Created `HuaweiRouterAPI` async wrapper for the `huawei-lte-api` library.
- **Flat Identity Pattern**: Implemented hardware metadata persistence (Model, MAC, Version) in `ConfigEntry.data` during initial setup.
- **Non-Blocking Startup**: Migrated initialization logic to `entry.async_create_background_task` for 0ms impact on Home Assistant boot time.
- **Config Flow**: Developed a robust config flow with credential validation and model discovery.

---

## [1.0.0] - 2026-05-02

### Initial Release

- Baseline project structure following "PlayFaster" v1.2 architectural standards.

---

### Format

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
