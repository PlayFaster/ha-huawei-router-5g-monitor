# Internal Detailed Changelog: Huawei Router 5G Monitor

This document tracks technical shifts, architectural decisions, and detailed implementation notes for the Huawei Router 5G Monitor project.

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
