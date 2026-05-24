# Internal Detailed Changelog: Huawei Router 5G Monitor

This document tracks technical shifts, architectural decisions, and detailed implementation notes for the Huawei Router 5G Monitor project.

---

## [1.1.1-dev15] - 2026-05-24

### Fixed

- **Uptime timestamp drift**: Replaced `_get_timestamp()` (naive `now() − uptime` recomputed every poll) with a reboot-detection latch in the coordinator for all three timestamp sensors (`uptime_timestamp`, `current_connection_timestamp`, `total_connection_timestamp`). Boot/start times are now computed once and frozen; the latch re-fires only when the counter drops by more than 30 seconds (genuine reset). Eliminates clock-rate divergence drift and the minute-boundary backward jumps caused by the prior truncation approach. Six latch fields persisted to `entry.data` so timestamps survive HA restarts.
- **`month_download_gb` / `month_upload_gb` GB/GiB mismatch**: Both sensors were dividing bytes by `1024³` (producing GiB) while declaring `native_unit_of_measurement=GIGABYTES` (GB). Corrected divisor to `1,000,000,000` — fixes ~7.4% underreporting (e.g. actual 133 GB was displayed as 124 GB).
- **`dict` → `dict[str, Any]` mypy `[type-arg]` error** in `coordinator.py` on the `entry_data_updates` local variable.

## [1.1.1-dev14] - 2026-05-24 - Unreleased

### Changed

- **Dependabot**: Bump PlayFaster/.github shared validation from v1.02 to v1.04
- **Dependabot**: Bump [zizmor](https://github.com/zizmorcore/zizmor-pre-commit) from v1.24.1 to 1.25.2
- **Dependabot**: Bump [python-typing](https://github.com/cdce8p/python-typing-update) from v0.6.0 to 0.8.1

## [1.1.1-dev12] - 2026-05-11

### Added

- **Code Review**: Carried out a code review, implemented several improvements.

### Changed

- **Extracted `FETCH_TIMEOUT` constant**: Moved the hardcoded 30-second fetch timeout value from `coordinator.py` to a named constant `FETCH_TIMEOUT = 30` in `const.py` for discoverability and reuse.

### Fixed

- **Duplicate assert in `api.py`**: Removed a duplicate `assert client is not None` statement — copy-paste error with no runtime impact.
- **Diagnostics None guard**: Added `coordinator.data or {}` guard in `diagnostics.py` to prevent crash if diagnostics is queried before the first successful coordinator poll. Updated test assertion accordingly.
- **Device tracker exception handling**: Replaced overly broad try-except blocks in `device_tracker.py` with `isinstance` guards and early-return `None` checks. The old code wrapped `.get()` chains that already supplied default empty dicts — the try-except was dead code for normal data shapes but masked the real issue when `coordinator.data` was `None`. Added explicit `if not data` guards in both `_get_entities()` and `_host_data()` matching the pattern used by all other platforms.

### Documentation

- **Updated `DEVELOPMENT.md`**: Clarified Python 3.14 `except A, B:` comma syntax behavior — it is now valid multi-catch per PEP 3111 on Python 3.14+, but ruff with `target-version = "py314"` will auto-format to it. Added guidance on pinning `target-version = "py313"` for backward compatibility.

## [1.1.1-dev11] - 2026-05-11

### Changed

- **Final icons.json cleanup**: Removed last inline `icon=` declarations from `select.py` and `button.py` — all entity icons are now served exclusively via `icons.json`. Previous rounds had already migrated `sensor.py`, `binary_sensor.py`, and `switch.py`; this completes the migration for all 6 entity types (sensor, binary_sensor, switch, select, button, number).

### Fixed

- **Test assertions aligned with icons.json approach**: Updated 4 icon assertions in `test_binary_sensor.py` and `test_coverage_ext.py` to expect `sensor.icon is None` — icons are now resolved by the HA frontend from `icons.json`, not via Python `@property icon`. The `HuaweiBestConnectionSensor` no longer declares an inline `icon` property.

## [1.1.1-dev10] - 2026-05-11

### Changed

- **IQS Platinum**: With icons.json and strict typing the IQS scale is now "near-platinum", with the major caveats that (i) IQS does not apply to cusomt components and (ii) several standards are N/A but still a very positive indicator.
- **Project Structure Document**: Updated the project structure document to v1.2.4.

## [1.1.1-dev9] - 2026-05-11

### Added

- IQS Standards Review carried out. Added next steps document and implemented icons.json based on it.
- **Full Implementation of `icons.json`**: Achieved IQS Gold compliance for `icon-translations` by moving all entity icons to a centralized translation-based system.
- **Dynamic Icons**: Added dynamic state-based icons for 5G connectivity (`best_connection`), SMS storage status, and roaming.
- **Range-Based Icons**: Added dynamic icons for battery (10-100%) and signal bars (1-3) that change automatically based on the sensor value.
- **SMS Inbox-State Icons**: Added dynamic switching for `sms_unread` sensors, showing `mdi:message-badge` when unread messages are present.

### Changed

- **Removed Hardcoded Icons**: Refactored `sensor.py`, `binary_sensor.py`, and `switch.py` to remove redundant `icon="..."` arguments in favor of translation keys.
- **`README.md` Terminology Update**: Updated all documentation references from "Services" to modern Home Assistant **"Actions"** terminology; updated SMS service examples to use `action` blocks.
- **Documentation Enhancement**: Added specific tested firmware version `11.0.2.11(H1352SP2C00)` to the hardware compatibility section.
- **IQS Tracking Updated**: Updated `quality_scale.yaml` and family compliance matrix to reflect 100% completion of `strict-typing` (Platinum) and `icon-translations` (Gold).

### Fixed

- **Initial Icon Mapping Gaps**: Resolved missing icon definitions for `sms_storage_full`, `endc_restricted`, `current_connection_duration`, and `total_connection_time` identified during implementation validation.

## [1.1.1-dev8] - 2026-05-11

### Changed

- **Devcontainer mount consolidation**: Moved `.notes` and `.shared` mounts from `devcontainer.json` to `docker-compose.yml` — mounts with absolute paths are unreliable in Docker Compose mode when declared in `devcontainer.json`; compose-file volumes are authoritative for the compose service.
- **HA core mounted for mypy**: Mounted HA core source (`C:/Local/Code/ha_core/core` → `/ha_core`) into the devcontainer via `docker-compose.yml` as read-only, so mypy can resolve HA type stubs without installing the full HA package.
- **`mypy_path` configured**: Added `mypy_path = "/ha_core"` to `[tool.mypy]` in `pyproject.toml` to point mypy at the mounted HA source.
- **mypy scoped to custom component**: Added `[[tool.mypy.overrides]]` for `homeassistant.*` with `ignore_errors = true` and `follow_imports = "silent"` to prevent mypy from checking and reporting errors from HA core files while still using them for type resolution.

### Fixed

- **10 `[type-arg]` strict mypy errors**: Replaced bare `dict` annotations with `dict[str, Any]` across `helpers.py` (3), `sensor.py` (2), `config_flow.py` (2), `__init__.py` (3).

## [1.1.1-dev7] - 2026-05-11

### Changed

- **HA Core stubs mounted in devcontainer**: Mounted HA core files into the devcontainer at `/ha_core` so mypy can resolve HA type stubs. This surfaced 33 previously hidden strict mypy errors that were blocked by missing type information. pro

### Fixed

- **33 Strict Mypy Errors Resolved**: All remaining strict mypy errors fixed across 7 files (`coordinator.py`, `switch.py`, `sensor.py`, `select.py`, `number.py`, `device_tracker.py`, `config_flow.py`). Key fixes: removed 3 redundant `cast()` calls and annotated `last_update_success_time` as `datetime | None` in `coordinator.py`; corrected `EntityCategory` import path to `homeassistant.const` (4 files); used `NumberMode.SLIDER` enum instead of string `"slider"` in `number.py`; corrected `ScannerEntity` import to `device_tracker.config_entry` and added `# type: ignore[misc]` for `@final device_info` override in `device_tracker.py`; replaced `FlowResult` with `ConfigFlowResult` return type, added null-safety asserts, changed parameter type to `Mapping[str, Any]`, and moved `callback` import to `homeassistant.core` in `config_flow.py`.

## [1.1.1-dev6] - 2026-05-11

### Changed

- Added HA core files to Devcon as a mount to try to get the remaining mypy strict errors resolved.

### Fixed

- **11 Mypy Errors Resolved (batch 1)**: Fixed `no-untyped-call` in `api.py` by extracting fetcher list to a typed `list[tuple[str, Callable[[], Any]]]` variable; fixed 3× `no-any-return` in `coordinator.py` via `cast("dict[str, Any]", self.data)`; fixed `no-any-return` in `switch.py` via `bool()` wrapper, `device_tracker.py` via `str(ip)` wrapper, and `binary_sensor.py` via `str(value)` wrapper; fixed `untyped-decorator` in `config_flow.py` via typed `_ha_callback` alias; fixed 3× `no-any-return` in `__init__.py` via `cast` for `entry.runtime_data` and `bool()` for `unload_ok`.
- **10 Mypy Errors Resolved (batch 2)**: Fixed missing type arguments for bare `dict` annotations (`type-arg`) across `helpers.py` (3), `sensor.py` (2), `config_flow.py` (2), `__init__.py` (3) — added `[str, Any]` type parameters to all generic `dict` usages in function signatures.

## [1.1.1-dev5] - 2026-05-10

### Fixed

- **`CONFIG_SCHEMA` hassfest warning**: Added `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)` to `__init__.py`. Integrations that implement `async_setup` must declare one of `CONFIG_SCHEMA`, `PLATFORM_SCHEMA`, or `PLATFORM_SCHEMA_BASE`; using `config_entry_only_config_schema` is the correct choice for UI-only (config entry) integrations and surfaces a clear error if YAML setup is attempted.
- **Duplicate sensor unique ID errors**: Removed duplicate `month_upload` and `month_upload_gb` entries from `SENSOR_TYPES` in `sensor.py`. Both descriptors were defined twice identically, causing HA to log `"ID already exists — ignoring"` warnings at startup and silently drop those two sensors. Likely introduced via accidental copy-paste during the mypy fix session (dev4).

## [1.1.1-dev4] - 2026-05-10

### Fixed

- **71 Mypy Errors Resolved**: Comprehensive type annotation fixes across 11 source files (`api.py`, `config_flow.py`, `sensor.py`, `switch.py`, `number.py`, `select.py`, `helpers.py`, `coordinator.py`, `device_tracker.py`, `button.py`, `binary_sensor.py`). Key fixes: added missing parameter/return type annotations; narrowed `Client | None` union throughout `api.py` using assertion-driven pattern; corrected `set_net_mode` keyword arguments to match library API (`lteband`/`networkband`/`networkmode`); typed `_refresh_task` as `asyncio.Task[None] | None` to resolve unreachable code in `number.py`; added `or 0` guard for `_safe_int` division in `month_download_gb`/`month_upload_gb` sensors.

## [1.1.1-dev3] - 2026-05-10

### Changed Dev Tooling

- **Shared Reusable CI Workflow**: Created `PlayFaster/.github` organisation repo containing a parameterised reusable workflow (`validate.yaml`, named "Validate (Shared)"). All 8 validation jobs (`hassfest`, `hacs_val`, `py_val`, `test_val`, `file_val`, `codespell`, `zizmor`, `mypy_val`) now live in the shared repo and are called by each integration via a thin caller. Changes to validation logic propagate to all 4 projects on the next CI run without per-project edits.
- **Thin Caller Workflow**: Replaced the 270-line inline `.github/workflows/validate.yaml` with a ~30-line caller that delegates to the shared workflow via `uses: PlayFaster/.github/.github/workflows/validate.yaml@main`. Permissions correctly scoped: `contents: read` at workflow level, `contents: write` and `pull-requests: write` at job level (required by `test_val` for coverage badge and PR comments).
- **Shared Workflow Concurrency**: Reusable workflow uses `${{ github.workflow }}-${{ github.ref }}-${{ github.repository }}` as its concurrency group, preventing cross-repo cancellation when multiple integrations trigger simultaneously.
- **Shared Workflow Dependabot**: Added `dependabot.yml` to `PlayFaster/.github` tracking the `github-actions` ecosystem weekly, keeping SHA pins in the shared workflow current.
- **Pre-commit: Suppress Inapplicable Hooks**: Added `stages: [manual]` to the `no-commit-to-branch` hook — direct commits to `main`/`dev` are the working pattern for this project, so the hook is retained for explicit use but removed from the default commit flow. Added `exclude: \.yamllint$` to the `yamllint` hook to prevent it from linting its own config file (which lacks `---` and uses CRLF).
- **VS Code Tasks**: Added `Zizmor: Fix (Safe Auto-Fix)` task (`zizmor --fix .github/`) for applying zizmor's safe auto-fixes on demand. Added `Pre-commit: Autoupdate Hooks` task (`pre-commit autoupdate`) for updating all hook `rev:` pins to their latest releases. Neither task is wired into `Fix All` or `Validate All`.

## [1.1.1-dev1] - 2026-05-07

### Changed

- **Readme**: Changed the top level info in readme to line up with GitHub description.

## [1.1.0] - 2026-05-07 - Release

### Changed

- **Under the Hood**: Significant code clean-up.
- **Unique ID via MAC**: Changed to have the Unique IDs generated from MAC not IP.
- **Automation Examples**: Updated the automation examples.

## [1.1.0-rc2] - 2026-05-07

### Changed

- **Automation Examples**: Updated the automation examples, modern syntax (action vs service).

## [1.1.0-rc1] - 2026-05-07

### Changed

- **Linting**: Fixed some linting and formatting issues.
- **Tests**: Added pytests, improved coverage.
- **IQS**: Corrected format of quality_scale.yaml.

## [1.1.0-dev2] - 2026-05-07

### Changed

- **Test Coverage**: Improved test coverage including new test file for diagnistics.py.

## [1.1.0-dev1] - 2026-05-07

### Changed

- **Service Parameter Rename — `device_id` → `entry_id`**: Renamed the router selector field in all 4 SMS service schemas (`send_sms`, `delete_sms`, `delete_all_sms`, `get_sms_list`) to accurately reflect that it accepts a config entry ID, not a HA device registry ID. Updated `services.yaml`, `__init__.py` schemas and `_get_coordinator()`, and `tests/test_init.py`.
- **SMS Event Payload**: Renamed `device_id` → `entry_id` in the `huawei_router_5g_sms_received` event payload for consistency with the service rename.
- **MAC-Based Config Entry Unique ID**: `async_set_unique_id` in `config_flow.py` now uses the router MAC address (with host URL fallback) instead of the host URL, ensuring a stable unique ID that survives IP address changes. MAC is normalized to lowercase colon/dash-stripped format at `_validate_credentials()` return time before being stored in `entry.data`.

### Added

- **Deferred Review Note**: Created `.notes/code_review/code_review_20260507_deferred.md` documenting the M9 (Config Entry → DeviceRegistry) deferral — issue, boot-sequence complexity, and recommended implementation path if revisited.

## [1.0.3-dev3] - 2026-05-07

### Fixed

- **Python 3.14 Syntax Compatibility**: Replaced 6 bare-tuple `except A, B:` clauses (SyntaxWarning in Python 3.14) with `except (A, B):` across `helpers.py`, `sensor.py`, and `device_tracker.py`.
- **Ghost Device Tracker Bug**: Fixed `is_connected` in `device_tracker.py` incorrectly treating hosts with a missing `Active` field as connected.
- **Device Tracker Listener Leak**: Wrapped coordinator listener registration in `entry.async_on_unload()` to ensure cleanup on integration removal.
- **SMS Box Selection Logic**: Fixed operator precedence bug (`or 0 > 0`) in `api.py` that made the LocalInbox count check always evaluate to `False`.
- **Reboot Session Cleanup**: Added `self._reset_client()` after a successful reboot so the stale connection is not reused after the router restarts.
- **Guest WiFi API Guard**: Wrapped the `_session.post_set()` call in `set_guest_wifi` with an `AttributeError` catch to surface a clean error if `huawei_lte_api` internals change.
- **Debounce Task Leak**: Added `async_will_remove_from_hass` to `HuaweiPollingInterval` in `number.py` to cancel any pending refresh task on entity removal.
- **SMS Service ValueError**: Moved `BoxTypeEnum()` conversion inside the try-except in `async_get_sms_list` so invalid `box_type` values raise a clean `HomeAssistantError`.
- **Reauth None Guard**: Added a None check in `async_step_reauth` to abort cleanly if the config entry cannot be found.
- **Diagnostics MAC Redaction**: Added `"mac"` to `TO_REDACT` in `diagnostics.py` so the router MAC is redacted from diagnostic data dumps.
- **Timestamp Truncation**: Fixed `_get_timestamp` in `sensor.py` to truncate seconds/microseconds from the result timestamp rather than rounding the duration.

### Changed

- **SMS Message Helper**: Extracted `_get_messages()` in `sensor.py` to deduplicate `parse_sms_list` calls across `native_value` and `extra_state_attributes` of the `last_sms` sensor.
- **Button Device Info**: Replaced a duplicated `device_info` property in `button.py` with the shared `build_device_info` helper.

## [1.0.3-dev2] - 2026-05-07

### Added

- **IQS Gold Elevation**: Implemented Diagnostics, Reauthentication, Reconfiguration, and Repair Issues to achieve Gold status.
- **Diagnostics Support**: Created `diagnostics.py` to provide sanitized data dumps for troubleshooting.
- **Repair System**: Integrated `issue_registry` to surface persistent authentication and transient connection issues in the HA Repairs dashboard.

### Changed

- **Config Flow Overhaul**: Added support for UI-based reauthentication and reconfiguration (changing host/credentials without re-setup).
- **Resilience Logic**: Coordinator now raises `ConfigEntryAuthFailed` for persistent authentication errors to trigger the reauth flow.
- **Documentation**: Added "Removal" section to README and established `ha_quality_standard.md` as the master quality reference.

### Fixed

- **Import Error**: Resolved `AttributeError` for `Platform.DIAGNOSTICS` during integration setup.

## [1.0.3-dev1] - 2026-05-07 - Unreleased

### Added

- **Quality Scale**: Added quality_scale.yaml into project folder to track compliance to Home Assistant Integration Quality Scale (IQS). As a custom component full compliance is not possible but this is a good mechanism to ensure alignment with Home Assistant best practise.

## [1.0.2] - 2026-05-05 - Release

### Added

- **SMS Management**: Improved SMS management significantly with services to list all, delete all and delete individual SMS messages.
- **WiFi Sub-Device**: Moved all WiFi related entities into a WiFi sub-device.
- **Wired Device Count**: Added sensors to track the number of wired and total (wired plus wifi) active clients.
- **WiFi Single SSID Mode**: Added a sensor to track the status of single SSID mode (2.4GHz and 5GHz WiFi using the same SSID - "5GHz Preferred").
- **5G ENDC Active**: Added sensor to track the status of ENDC connectivity.
- **5G Signal Bars**: Added a sensor for 5G signal bars, in addition to the existing Signal Bars. These are both as-reported by the router, not calculated.

### Changed

- **Readme**: Added clarifying info to readme file, and several example automations.
- **Test Coverage**: Internal test coverage improved to > 95%.

### Fixed

- **WiFi Status**: Fixed an issue where 2.4GHz and 5GHz WiFi status sensors did not always report correct status.
- **Guest WiFi Toggle**: Fixed an issue where the Guest WiFi Network toggle switch did not always work.

## [1.0.2-dev4] - 2026-05-05

### Added

- **WiFi Sub-Device**: Created a dedicated 'WiFi' sub-device to group all wireless networking entities, improving UI organization and logical separation from core system metrics.
- **Critical Fixes for H165-383**:
  - Fixed **Request Format Error (100005)** by implementing a "Full Payload" POST strategy that preserves `DbhoEnable` and other mandatory fields during Wi-Fi updates.
  - Fixed **AttributeError** in Single SSID toggle by correctly targeting the internal session object and correcting fallback method names.
- **Enhanced Client Connectivity Sensors**:
  - `total_connected`: Sum of all active LAN and WLAN clients.
  - `wired_connected`: Calculated as Total Active minus Wireless Active clients.
- **5G Signal Bars**: Added a dedicated `signal_bars_nr` sensor to track 5G signal quality separately from LTE.
- **WiFi User Capacity**: Added `wifi_capacity` sensor to report the maximum supported wireless users for the hardware.
- **Dynamic Radio Discovery**: Implemented `find_ssid_by_path` helper to automatically map 2.4GHz and 5GHz radios using firmware "ID paths" (e.g., `Radio.1.Ssid.1`). This eliminates the "Index 5 bug" on H165-383 models where radio indices shifted between firmware versions.
- **Organization Test Suite**: Created `tests/test_organization.py` to verify sub-device grouping, entity categories, and naming conventions across all platforms.

### Changed

- **Entity Naming Refinement**:
  - Renamed **5G Active** to **5G ENDC Active** for technical accuracy (E-UTRA New Radio Dual Connectivity).
  - Stripped "WiFi" and "Wi-Fi" prefixes from all entities within the WiFi sub-device to prevent redundant labeling (e.g., "WiFi Status" becomes "Status" under the WiFi sub-device).
  - Stripped redundant "Wi-Fi" from the **Guest Network** switch.
- **Category Optimization**:
  - Promoted **WiFi Connected** (`wifi_users`) from Diagnostic to the main **Sensor** category (grouped under Clients).
  - Promoted **Last Updated** from Diagnostic to the main **Sensor** category for immediate data-freshness visibility.
  - Moved **Total Uptime** (`total_connection_timestamp`) from Sensor to **Diagnostic**, prioritizing it for long-term troubleshooting rather than daily monitoring.
- **Sub-Device Grouping**:
  - Moved `wifi_status`, `wifi24g_status`, `wifi5g_status`, `single_ssid_mode`, `wifi_capacity`, and `wifi_guest_network` to the new **WiFi** sub-device.
  - Consolidated client tracking entities under the **Clients** sub-device.
- **Metadata Refinement**: Removed `measurement` state class from **WiFi User Capacity** as it is a static hardware capability, preventing unnecessary long-term statistics tracking.

### Fixed

- **H165-383 WiFi Stability**: Resolved "Guest WiFi always off" bug on modern firmware by implementing a "Full List POST" strategy in `set_guest_wifi`, ensuring all SSID indices are maintained during single-SSID updates.
- **API Error Suppression**: Downgraded Error 100002 (Not Supported) to `DEBUG` level for 5G/LTE status checks, preventing log spam on older router models that don't support modern EN-DC metrics.
- **ConfigEntry Attribute Assignment**: Fixed `AttributeError` in tests caused by direct assignment to `ConfigEntry.options`, migrating to `MockConfigEntry` initialization standard.

---

## [1.0.2-dev3] - 2026-05-04

### Added

- **Expanded SMS Service Suite**: Implemented three new services and enhanced one existing service:
  - `delete_sms`: Deletes a specific message by its storage index.
  - `delete_all_sms`: Performs bulk deletion with a `keep_last` safety parameter to maintain minimal history.
  - `get_sms_list`: Provides a full inbox dump with **Service Response** support, enabling automated ingestion of SMS content.
  - `send_sms`: Upgraded to support targeting multiple recipients and specific `device_id` identifiers.
- **Dedicated `__init__.py` Test Suite**: Created `tests/test_init.py` to target service registration, handler routing, and error propagation, achieving high coverage for the integration lifecycle.

### Changed

- **Timestamp-Based SMS Tracking**: Replaced the brittle "Index-based" detection logic with a robust timestamp-based system. The coordinator now uses a combination of message `date` and a `{index}_{date}` hash set to identify new messages, effectively eliminating the "Slot Reuse" bug where messages in recycled slots were previously ignored.
- **API Concurrency Locking**: Integrated an `asyncio.Lock` into the `HuaweiRouter5GAPI` class. All router communications are now serialized, preventing the session crashes and "Busy" errors caused by simultaneous polling and service execution.
- **Modernized Service Handlers**: Refactored service registration from lambdas to explicit `async def` wrappers. This resolved a critical bug where `get_sms_list` returned an unawaited coroutine instead of the expected data dictionary.
- **Enhanced Polling Parameters**: Re-enabled `SortTypeEnum.DATE` and `unread_preferred=True` in the SMS poll cycle. Serialization via the new API lock ensures these advanced parameters are now accepted by the router firmware without triggering system errors.
- **Test Coverage Recovery**: Restored overall project coverage to **95%** after the introduction of complex async logic. Updated `tests/test_api.py` and `tests/test_coverage_ext.py` to match the new lock-protected API structure and verified all 285 tests passing in the devcontainer.

### Fixed

- **SMS Deletion Argument Bug**: Resolved a `TypeError` in the `delete_sms` service caused by using the incorrect keyword argument (`index` instead of `sms_id`). This fix also restores functionality to the `delete_all_sms` service.
- **Network Mode Argument Order**: Corrected the argument order in `set_net_mode` and migrated to keyword arguments (`lte_band`, `network_band`, `network_mode`) to ensure compatibility with the `huawei-lte-api` library's expectations.
- **Robustness in Tests**: Updated the API test suite to verify correct keyword arguments for SMS and network mode operations, preventing future regressions of library-specific signatures.

---

## [1.0.2-dev1] - 2026-05-04

### Changed

- **100% Test Coverage for `api.py`**: Achieved full coverage (143 lines) by implementing 41 tests covering edge-case ResponseErrorException paths, generic SMS list fetch failures, and verified execution of all async setter closures.
- **100% Test Coverage for `switch.py`**: Achieved full coverage (106 lines) by implementing 23 tests covering missing API data keys, exception handling for mobile/guest toggles, and Guest WiFi deactivation logic.
- **100% Test Coverage for `binary_sensor.py`**: Achieved full coverage (119 lines) by consolidating external tests and implementing missing scenarios for WiFi status, mobile connection, and null-data edge cases.
- **100% Test Coverage for `sensor.py`**: Achieved full coverage of the main sensor platform (120 lines) by implementing 46 comprehensive tests.
- **98% Test Coverage for `device_tracker.py`**: Added 8 tests for dynamic listener discovery and malformed host-data resilience, reaching near-total coverage.
- **Consolidated Binary Sensor Test Suite**: Merged `test_binary_sensor_ext.py` into the primary `test_binary_sensor.py` for better maintainability and unified validation.
- **Improved Sensor Resilience Testing**: Verified IPv6 formatting safeguards, negative duration guards for connection sensors, and 5G band extraction fallbacks.
- **SMS Metadata & Attribute Verification**: Added exhaustive tests for the `last_sms` sensor and the detailed attribute breakdown in `sms_total`, ensuring coverage for all logical branches including missing or malformed coordinator data.
- **100% Test Coverage for `coordinator.py`**: Achieved full coverage (92 lines) by implementing targeted tests for communication restoration logging, SMS debug output, and the end-to-end SMS event-firing logic. Verified that the first fetch sets the baseline index without firing events, while subsequent fetches correctly dispatch `huawei_router_5g_sms_received` events for new messages only.
- **100% Test Coverage for `__init__.py`**: Reached full coverage (62 lines) by implementing success-path and failure-path verification for background initialization tasks, ensuring the integration remains responsive during boot while handling API login failures gracefully.
- **100% Test Coverage for `select.py`**: Achieved full coverage (38 lines) by adding tests for the `device_info` property and error handling in `async_select_option`, verifying that API failures are correctly captured and logged.
- **Testing Infrastructure Enhancement**: Implemented a `mock_report_usage` fixture in new test suites to bypass Home Assistant's internal `Frame helper not set up` runtime errors during standalone coordinator and platform testing.
- **Project-wide Coverage Milestone**: Increased total project test coverage to **99.8%**.

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
- **SMS Event Firing**: Added `huawei_router_5g_sms_received` firing in the coordinator when new messages are detected at the top of the inbox.
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
