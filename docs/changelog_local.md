# Internal Detailed Changelog: Huawei Router 5G Monitor

All changes to this project will be documented in this file. This is the detailed changelog, to include non user facing changes and intra-release changes.

---

- [Internal Detailed Changelog: Huawei Router 5G Monitor](#internal-detailed-changelog-huawei-router-5g-monitor)
  - [\[1.2.0-dev15\] - 2026-08-15 - Follow-Up Refresh Fires While Paused](#120-dev15---2026-08-15---follow-up-refresh-fires-while-paused)
  - [\[1.2.0-dev14\] - 2026-08-15 - Follow-Up Refresh After Reboot and Reconnect](#120-dev14---2026-08-15---follow-up-refresh-after-reboot-and-reconnect)
  - [\[1.2.0-dev13\] - 2026-08-15 - Reconnect Button Fixed](#120-dev13---2026-08-15---reconnect-button-fixed)
  - [\[1.2.0-dev12\] - 2026-08-15 - huawei-lte-api 2.0.1](#120-dev12---2026-08-15---huawei-lte-api-201)
  - [\[1.2.0-dev11\] - 2026-08-15 - New Entity Set and Data-Usage Projection](#120-dev11---2026-08-15---new-entity-set-and-data-usage-projection)
  - [\[1.2.0-dev10\] - 2026-08-15 - Huawei API Access Reference](#120-dev10---2026-08-15---huawei-api-access-reference)
  - [\[1.2.0-dev9\] - 2026-08-14 - Roadmap Reconciled](#120-dev9---2026-08-14---roadmap-reconciled)
  - [\[1.2.0-dev8\] - 2026-08-14 - Two Dead Entity Strings Removed](#120-dev8---2026-08-14---two-dead-entity-strings-removed)
  - [\[1.2.0-dev7\] - 2026-08-14 - quality_scale.yaml Completeness](#120-dev7---2026-08-14---quality_scaleyaml-completeness)
  - [\[1.2.0-dev6\] - 2026-08-14 - Write-Classification Register and Hardware Check](#120-dev6---2026-08-14---write-classification-register-and-hardware-check)
  - [\[1.2.0-dev5\] - 2026-08-14 - Four Diagnostics Leaks Closed](#120-dev5---2026-08-14---four-diagnostics-leaks-closed)
  - [\[1.2.0-dev4\] - 2026-08-14 - Guest-WiFi Write Decision; Structured Exempts](#120-dev4---2026-08-14---guest-wifi-write-decision-structured-exempts)
  - [\[1.2.0-dev3\] - 2026-08-14 - masked_errors_check Audit](#120-dev3---2026-08-14---masked_errors_check-audit)
  - [\[1.2.0-dev2\] - 2026-08-14 - Changelog Backfill](#120-dev2---2026-08-14---changelog-backfill)
  - [\[1.2.0-dev1\] - 2026-08-14 - Two Dead Library Calls; Tracker Unique IDs; Entity Cleanup Action](#120-dev1---2026-08-14---two-dead-library-calls-tracker-unique-ids-entity-cleanup-action)
  - [\[1.1.3-dev17\] - 2026-08-14 - Add HA Compatibility Document](#113-dev17---2026-08-14---add-ha-compatibility-document)
  - [\[1.1.3-dev16\] - 2026-08-14 - CI Bumps Zizmor MyPy JSONSchema PHACC](#113-dev16---2026-08-14---ci-bumps-zizmor-mypy-jsonschema-phacc)
  - [\[1.1.3-dev15\] - 2026-08-14 - Documentation Phase: Repair Titles, Roadmap, Spelling, Sweep Table](#113-dev15---2026-08-14---documentation-phase-repair-titles-roadmap-spelling-sweep-table)
  - [\[1.1.3-dev14\] - 2026-08-14 - Integration Health and Drift Detection; Guard Bands Reconciled](#113-dev14---2026-08-14---integration-health-and-drift-detection-guard-bands-reconciled)
  - [\[1.1.3-dev13\] - 2026-08-14 - Action Icons; Icon and `PARALLEL_UPDATES` Sweeps; Secret Pre-Fill Guards](#113-dev13---2026-08-14---action-icons-icon-and-parallel_updates-sweeps-secret-pre-fill-guards)
  - [\[1.1.3-dev12\] - 2026-08-14 - Silent Write Failures; Orphaned Repairs; Lost Debounced Writes; Diagnostics Rewritten](#113-dev12---2026-08-14---silent-write-failures-orphaned-repairs-lost-debounced-writes-diagnostics-rewritten)
  - [\[1.1.3-dev11\] - 2026-08-14 - Zero Partial Branches; Zero-Assertion Tests Closed](#113-dev11---2026-08-14---zero-partial-branches-zero-assertion-tests-closed)
  - [\[1.1.3-dev10\] - 2026-08-14 - Four Statistics-Corrupting Counters; `via_device` Deprecation; Recorder Hygiene; Refresh While Paused](#113-dev10---2026-08-14---four-statistics-corrupting-counters-via_device-deprecation-recorder-hygiene-refresh-while-paused)
  - [\[1.1.3-dev9\] - 2026-08-08 - CI Bumps; Github Zipfile; PyTest Branch \& Mutation Testing](#113-dev9---2026-08-08---ci-bumps-github-zipfile-pytest-branch--mutation-testing)
  - [\[1.1.3-dev8\] - 2026-07-28 - Automation Example Glitch Guards \& Float Rounding in README](#113-dev8---2026-07-28---automation-example-glitch-guards--float-rounding-in-readme)
  - [\[1.1.3-dev7\] - 2026-07-12 - PHACC Bump; README Alignment and Codespell](#113-dev7---2026-07-12---phacc-bump-readme-alignment-and-codespell)
  - [\[1.1.3-dev6\] - 2026-07-06 - Shared CI Bump v2.0.5 → v2.0.6](#113-dev6---2026-07-06---shared-ci-bump-v205--v206)
  - [\[1.1.3-dev5\] - 2026-07-06 - Test Suite Repaired After the Ruff Extension](#113-dev5---2026-07-06---test-suite-repaired-after-the-ruff-extension)
  - [\[1.1.3-dev4\] - 2026-07-06 - Ruff Checks Extended to Match Home Assistant](#113-dev4---2026-07-06---ruff-checks-extended-to-match-home-assistant)
  - [\[1.1.3-dev3\] - 2026-07-06 - IQS Static Check Added; Check-Drift Fixed](#113-dev3---2026-07-06---iqs-static-check-added-check-drift-fixed)
  - [\[1.1.3-dev2\] - 2026-07-03 - SMS Actions Default to the Sole Router](#113-dev2---2026-07-03---sms-actions-default-to-the-sole-router)
  - [\[1.1.3-dev1\] - 2026-07-03 - Docs Aligned With the ZTE Project](#113-dev1---2026-07-03---docs-aligned-with-the-zte-project)
  - [\[1.1.2\] - 2026-07-03 - Release - Refresh Now Button; Display Units; Config-Flow Hardening](#112---2026-07-03---release---refresh-now-button-display-units-config-flow-hardening)
  - [\[1.1.2-dev10\] - 2026-07-03 - README Screenshots and Sensor Counts](#112-dev10---2026-07-03---readme-screenshots-and-sensor-counts)
  - [\[1.1.2-dev9\] - 2026-07-03 - Ruff Bump 0.15.19 → 0.15.20](#112-dev9---2026-07-03---ruff-bump-01519--01520)
  - [\[1.1.2-dev8\] - 2026-07-03 - Three Sensors Disabled by Default](#112-dev8---2026-07-03---three-sensors-disabled-by-default)
  - [\[1.1.2-dev7\] - 2026-07-02 - Explicit `config_entry` on the Coordinator](#112-dev7---2026-07-02---explicit-config_entry-on-the-coordinator)
  - [\[1.1.2-dev6\] - 2026-07-02 - Suggested Display Units and Precision on 23 Sensors](#112-dev6---2026-07-02---suggested-display-units-and-precision-on-23-sensors)
  - [\[1.1.2-dev5\] - 2026-07-02 - Config-Flow Hardening \& Refresh Now Button](#112-dev5---2026-07-02---config-flow-hardening--refresh-now-button)
  - [\[1.1.2-dev4\] - 2026-06-18 - CI Validation Overhaul](#112-dev4---2026-06-18---ci-validation-overhaul)
  - [\[1.1.2-dev2\] - 2026-06-11 - Validation Tooling Sync System](#112-dev2---2026-06-11---validation-tooling-sync-system)
  - [\[1.1.1\] - 2026-06-07 - Release - Startup Race, Session and Timestamp Fixes](#111---2026-06-07---release---startup-race-session-and-timestamp-fixes)
  - [\[1.1.1-dev24\] - 2026-06-07 - Project-Wide Test Coverage to 100%](#111-dev24---2026-06-07---project-wide-test-coverage-to-100)
  - [\[1.1.1-dev23\] - 2026-06-07 - `ScannerEntity` Import; mypy Config Realigned With HA](#111-dev23---2026-06-07---scannerentity-import-mypy-config-realigned-with-ha)
  - [\[1.1.1-dev22\] - 2026-06-07 - `url_normalize` Startup Race Eliminated](#111-dev22---2026-06-07---url_normalize-startup-race-eliminated)
  - [\[1.1.1-dev21\] - 2026-06-02 - Proactive Session Reset; Exception Syntax Fixes](#111-dev21---2026-06-02---proactive-session-reset-exception-syntax-fixes)
  - [\[1.1.1-dev20\] - 2026-05-25 - `state_class` Removed From 32 Sensors](#111-dev20---2026-05-25---state_class-removed-from-32-sensors)
  - [\[1.1.1-dev19\] - 2026-05-25 - Button Handlers Raise `HomeAssistantError`](#111-dev19---2026-05-25---button-handlers-raise-homeassistanterror)
  - [\[1.1.1-dev18\] - 2026-05-25 - Six Entities Documented; IQS Matrix Corrected](#111-dev18---2026-05-25---six-entities-documented-iqs-matrix-corrected)
  - [\[1.1.1-dev17\] - 2026-05-24 - README Automation Examples and Icons](#111-dev17---2026-05-24---readme-automation-examples-and-icons)
  - [\[1.1.1-dev16\] - 2026-05-24 - Coordinator Coverage to 100%](#111-dev16---2026-05-24---coordinator-coverage-to-100)
  - [\[1.1.1-dev15\] - 2026-05-24 - Uptime Timestamp Drift; GB/GiB Mismatch Fixed](#111-dev15---2026-05-24---uptime-timestamp-drift-gbgib-mismatch-fixed)
  - [\[1.1.1-dev14\] - 2026-05-24 - Dependabot Bumps](#111-dev14---2026-05-24---dependabot-bumps)
  - [\[1.1.1-dev12\] - 2026-05-11 - Code Review; `FETCH_TIMEOUT` Constant Extracted](#111-dev12---2026-05-11---code-review-fetch_timeout-constant-extracted)
  - [\[1.1.1-dev11\] - 2026-05-11 - Final `icons.json` Cleanup](#111-dev11---2026-05-11---final-iconsjson-cleanup)
  - [\[1.1.1-dev10\] - 2026-05-11 - IQS Near-Platinum Recorded](#111-dev10---2026-05-11---iqs-near-platinum-recorded)
  - [\[1.1.1-dev9\] - 2026-05-11 - `icons.json` Implemented; Dynamic and Range Icons](#111-dev9---2026-05-11---iconsjson-implemented-dynamic-and-range-icons)
  - [\[1.1.1-dev8\] - 2026-05-11 - Devcontainer Mounts and mypy Path Setup](#111-dev8---2026-05-11---devcontainer-mounts-and-mypy-path-setup)
  - [\[1.1.1-dev7\] - 2026-05-11 - 33 Strict mypy Errors Resolved](#111-dev7---2026-05-11---33-strict-mypy-errors-resolved)
  - [\[1.1.1-dev6\] - 2026-05-11 - 21 mypy Errors Resolved in Two Batches](#111-dev6---2026-05-11---21-mypy-errors-resolved-in-two-batches)
  - [\[1.1.1-dev5\] - 2026-05-10 - `CONFIG_SCHEMA` Added; Duplicate Sensor IDs Removed](#111-dev5---2026-05-10---config_schema-added-duplicate-sensor-ids-removed)
  - [\[1.1.1-dev4\] - 2026-05-10 - 71 mypy Errors Resolved](#111-dev4---2026-05-10---71-mypy-errors-resolved)
  - [\[1.1.1-dev3\] - 2026-05-10 - Shared Reusable CI Workflow Created](#111-dev3---2026-05-10---shared-reusable-ci-workflow-created)
  - [\[1.1.1-dev1\] - 2026-05-07 - README Top-Level Info Aligned](#111-dev1---2026-05-07---readme-top-level-info-aligned)
  - [\[1.1.0\] - 2026-05-07 - Release - MAC-Based Unique ID; Code Clean-Up](#110---2026-05-07---release---mac-based-unique-id-code-clean-up)
  - [\[1.1.0-rc2\] - 2026-05-07 - Automation Examples Modernized](#110-rc2---2026-05-07---automation-examples-modernized)
  - [\[1.1.0-rc1\] - 2026-05-07 - Linting, Tests and `quality_scale.yaml` Format](#110-rc1---2026-05-07---linting-tests-and-quality_scaleyaml-format)
  - [\[1.1.0-dev2\] - 2026-05-07 - Diagnostics Test Coverage](#110-dev2---2026-05-07---diagnostics-test-coverage)
  - [\[1.1.0-dev1\] - 2026-05-07 - `device_id` → `entry_id`; MAC-Based Config Entry ID](#110-dev1---2026-05-07---device_id--entry_id-mac-based-config-entry-id)
  - [\[1.0.3-dev3\] - 2026-05-07 - Python 3.14 Syntax; Eleven Code-Review Fixes](#103-dev3---2026-05-07---python-314-syntax-eleven-code-review-fixes)
  - [\[1.0.3-dev2\] - 2026-05-07 - IQS Gold: Diagnostics, Reauth and Repairs](#103-dev2---2026-05-07---iqs-gold-diagnostics-reauth-and-repairs)
  - [\[1.0.3-dev1\] - 2026-05-07 - `quality_scale.yaml` Added](#103-dev1---2026-05-07---quality_scaleyaml-added)
  - [\[1.0.2\] - 2026-05-05 - Release - SMS Management, WiFi Sub-Device and Client Counts](#102---2026-05-05---release---sms-management-wifi-sub-device-and-client-counts)
  - [\[1.0.2-dev4\] - 2026-05-05 - WiFi Sub-Device; H165-383 Fixes; Client Counts](#102-dev4---2026-05-05---wifi-sub-device-h165-383-fixes-client-counts)
  - [\[1.0.2-dev3\] - 2026-05-04 - SMS Service Suite Expanded; API Concurrency Lock](#102-dev3---2026-05-04---sms-service-suite-expanded-api-concurrency-lock)
  - [\[1.0.2-dev1\] - 2026-05-04 - Test Coverage to 99.8% Across Seven Modules](#102-dev1---2026-05-04---test-coverage-to-998-across-seven-modules)
  - [\[1.0.1\] - 2026-05-03 - `helpers.py` Coverage to 100%; Project Coverage to 90%](#101---2026-05-03---helperspy-coverage-to-100-project-coverage-to-90)
  - [\[1.0.1-rc5\] - 2026-05-03 - Guard Bands on Eight Frequency Sensors; Translation Gap](#101-rc5---2026-05-03---guard-bands-on-eight-frequency-sensors-translation-gap)
  - [\[1.0.1-rc4\] - 2026-05-03 - Documentation Sync Against 106 Entities](#101-rc4---2026-05-03---documentation-sync-against-106-entities)
  - [\[1.0.1-rc3\] - 2026-05-03 - CI Requirements and Coverage Path Fixed](#101-rc3---2026-05-03---ci-requirements-and-coverage-path-fixed)
  - [\[1.0.1-dev22\] - 2026-05-03 - IPv6 DNS and 5G Frequency Sensors; Unit Selector Fixed](#101-dev22---2026-05-03---ipv6-dns-and-5g-frequency-sensors-unit-selector-fixed)
  - [\[1.0.1-dev21\] - 2026-05-03 - Test Warnings and `SIM117` Resolved](#101-dev21---2026-05-03---test-warnings-and-sim117-resolved)
  - [\[1.0.1-dev19\] - 2026-05-03 - Best Connection Sensor Overhauled; 11 Entities Enabled](#101-dev19---2026-05-03---best-connection-sensor-overhauled-11-entities-enabled)
  - [\[1.0.1-dev18\] - 2026-05-03 - LTE Frequency and Bandwidth Fields Corrected](#101-dev18---2026-05-03---lte-frequency-and-bandwidth-fields-corrected)
  - [\[1.0.1-dev16\] - 2026-05-03 - Complex Signal Metric Parsing](#101-dev16---2026-05-03---complex-signal-metric-parsing)
  - [\[1.0.1-dev15\] - 2026-05-03 - Dynamic SMS Box Selection; SMS Entities Renamed](#101-dev15---2026-05-03---dynamic-sms-box-selection-sms-entities-renamed)
  - [\[1.0.1-dev14\] - 2026-05-03 - `runtime_data` Migration; Domain-Level Service Registration](#101-dev14---2026-05-03---runtime_data-migration-domain-level-service-registration)
  - [\[1.0.1-dev13\] - 2026-05-02 - Full Translation Coverage; Entity Naming Refactor](#101-dev13---2026-05-02---full-translation-coverage-entity-naming-refactor)
  - [\[1.0.1-dev12\] - 2026-05-02 - Signal and SMS Entity Category Refinement](#101-dev12---2026-05-02---signal-and-sms-entity-category-refinement)
  - [\[1.0.1-dev10\] - 2026-05-02 - Windows Test-Suite Resilience](#101-dev10---2026-05-02---windows-test-suite-resilience)
  - [\[1.0.1-dev9\] - 2026-05-02 - Long-Term Statistics; Human-Readable Network Mode](#101-dev9---2026-05-02---long-term-statistics-human-readable-network-mode)
  - [\[1.0.1-dev8\] - 2026-05-02 - Immediate Session Retry; Icons for 35 Entities](#101-dev8---2026-05-02---immediate-session-retry-icons-for-35-entities)
  - [\[1.0.1-dev7\] - 2026-05-02 - Typed Session Exceptions; Fast-Fail on Critical Data](#101-dev7---2026-05-02---typed-session-exceptions-fast-fail-on-critical-data)
  - [\[1.0.1-dev6\] - 2026-05-02 - Shared `build_device_info`; Auth and PII Fixes](#101-dev6---2026-05-02---shared-build_device_info-auth-and-pii-fixes)
  - [\[1.0.1-dev5\] - 2026-05-02 - Reliability Test Suite](#101-dev5---2026-05-02---reliability-test-suite)
  - [\[1.0.1-dev4\] - 2026-05-02 - Logging Strategy; Critical Data Guard](#101-dev4---2026-05-02---logging-strategy-critical-data-guard)
  - [\[1.0.1-dev3\] - 2026-05-02 - Guard Bands on 80 Sensors; SMS Parsing and Events](#101-dev3---2026-05-02---guard-bands-on-80-sensors-sms-parsing-and-events)
  - [\[1.0.1-dev2\] - 2026-05-02 - Entity Engine: 80 Sensors and Six Platforms](#101-dev2---2026-05-02---entity-engine-80-sensors-and-six-platforms)
  - [\[1.0.1-dev1\] - 2026-05-02 - Core Architecture: Coordinator, API and Config Flow](#101-dev1---2026-05-02---core-architecture-coordinator-api-and-config-flow)
  - [\[1.0.0\] - 2026-05-02 - Baseline Project Structure](#100---2026-05-02---baseline-project-structure)

---

## [1.2.0-dev15] - 2026-08-15 - Follow-Up Refresh Fires While Paused

### Changed

- **The follow-up refresh after Reboot and Reconnect now fires even while polling is paused.** §13 already required that an explicit user action must not be swallowed by the pause; the follow-up is part of the press, and while paused it is the only way the result is ever seen. Every other write path here already forced through the pause, so this was the exception.
- The interval shortcut no longer applies while paused — the poll it would defer to returns cached data.

### Notes

- `unifi_network_monitor` had the correct behaviour already. Recorded as `x_proj_chores` C-011 and written into `dev_standards.md` §13 at **1.23.0**, so ZTE inherits the settled rule.

---

## [1.2.0-dev14] - 2026-08-15 - Follow-Up Refresh After Reboot and Reconnect

### Added

- **Reboot and Reconnect now schedule one refresh after the router comes back** — 60s and 20s respectively. The reading straight after either write is stale by definition, so without this the entities sat wrong until the next scheduled poll, twenty minutes by default.
- Verified live at the 20s mark: `CurrentConnectTime` 374 → 21, connected, no empty blocks.

### Notes

- **Declines in two cases.** While polling is paused, because a timer the user did not start is background polling — the write still happens, only the follow-up is suppressed. And when the delay would land after the next scheduled poll, which generalises "only if the interval is greater than a minute".
- Routes through `async_force_refresh`, so pausing between the press and the timer does not swallow it. A second press replaces the pending refresh rather than queueing another, and unload cancels it before the logout.

---

## [1.2.0-dev13] - 2026-08-15 - Reconnect Button Fixed

### Fixed

- **Reconnect failed with `-1: Unknown` on every press.** `net/reconnect` is refused by this hardware even though the library exposes it and the router advertises the feature (`net_feature_switch.reconnect_switch` is `1`). A method existing in the library says nothing about the device accepting it.
- Now posts `dialup/dial` `Action: 0` then `Action: 1`. Verified live: `CurrentConnectTime` 135 → 5, serving again inside five seconds.

### Notes

- The disconnect half has no public wrapper — `DialUp.dial()` hardcodes `Action: 1` — so it reaches through `_session.post_set` under a reasoned suppression. The connect half uses the public method.
- Caught only by pressing the button. The suite passed, and so did the contract test, because the method genuinely exists.

---

## [1.2.0-dev12] - 2026-08-15 - huawei-lte-api 2.0.1

### Changed

- **Library pinned to `2.0.1`**, in `manifest.json` and `.validate/requirements_custom.txt`. 2.0.0 was tagged but never published to PyPI; 2.0.1 is the first available release of that line and is functionally equivalent.
- **No code change was needed.** All 32 library calls, all five enums, all four exception types and the `Connection` signature survive unchanged. `device.set_control` was already the spelling that outlives 2.0.0's removal of `reboot()` and `control()`.
- Verified against the installed 2.0.1 by `tests/test_library_contract.py`, then against the live router: 23 blocks returned, none empty, all 36 new entities resolving.
- **Still synchronous.** No async client, so the IQS `async-dependency` and `inject-websession` rules remain unachievable rather than merely unmet.

---

## [1.2.0-dev11] - 2026-08-15 - New Entity Set and Data-Usage Projection

### Added

- **38 entities** across eight endpoints the integration had never called: six identity sensors, nine System sensors, four System binary sensors, eight Signal entities, the data-plan block, and a **Reconnect** button.
- **Projected Usage** — end-of-cycle forecast ported from `zte_router_5g`. Denominator floored at one day; no `state_class`, because the usage behind it is already in long-term statistics; `confidence` attribute.
- Long-term-statistics exclusion sweep, and `test_projection_has_no_state_class`.

### Fixed

- The write detector was blind to `reconnect`, a fourth unprefixed write, and reported the new classification as stale.
- `docs/all_sensors.md` carried two pre-existing count errors — SMS 22 rows under a header of 18, Clients 4 under 6.

### Notes

- `elapsed_days` is wall-clock from `StartDay`, **not** `MonthDuration` — that field is connected time and would inflate the rate by whatever share of the cycle the router spent offline.
- `net.reconnect()` has deliberately never been called. Classified ATTENDED.

---

## [1.2.0-dev10] - 2026-08-15 - Huawei API Access Reference

### Added

- `docs/huawei_how_to_access.md` — organised by library endpoint, since this integration never speaks HTTP to the router. Records what is polled, what is readable and unused, what the hardware refuses, and the field formats that mislead.

### Notes

- There is no `admin` tier: ~90 of ~240 read methods answer `100003`, and supplying the password as `admin` changes nothing.
- The session degrades under sustained bulk querying — a 240-method sweep reported `100003` for endpoints polled successfully every cycle.

---

## [1.2.0-dev9] - 2026-08-14 - Roadmap Reconciled

### Changed

- Removed two shipped entries (write-classification register; diagnostics verification). An IMEI-restore entry was added and then withdrawn — roadmap entries are the owner's call.

---

## [1.2.0-dev8] - 2026-08-14 - Two Dead Entity Strings Removed

### Fixed

- `entity.sensor.hw_version` and `entity.sensor.imei` were defined in `strings.json` with no `translation_key` producing them, orphaned since `364942c` deleted both sensors on 2026-05-02. Sensor artefacts now reconcile 96/96/96.

---

## [1.2.0-dev7] - 2026-08-14 - quality_scale.yaml Completeness

### Fixed

- `docs-conditions` and `docs-triggers` were absent; the file held 52 of the canonical 54. Both added as `exempt` — the integration registers no conditions and no triggers. An absent rule is not a low-priority gap, it is an unmeasured one.

---

## [1.2.0-dev6] - 2026-08-14 - Write-Classification Register and Hardware Check

### Added

- `scripts/write_classification.py` classifying all eight writes, `scripts/hardware_check.py` with separate unattended and attended tiers, and ten tests.
- SAFE holds only `logout`; everything else fails the "either resting state must be harmless" rule. `set_guest_wifi` is ATTENDED on evidence — the live guest SSID carries `WifiAuthmode: OPEN`.
- Suppression sweep extended to `scripts/`, which exposed a blind spot: the file-level ruff directive form matched nothing.

---

## [1.2.0-dev5] - 2026-08-14 - Four Diagnostics Leaks Closed

### Fixed

- A live capture audited field by field found four leaks the rewrite had not: `Mccmnc` (published while the identical `current_plmn.Numeric` was redacted beside it), `Spn` (listed in the wrong case), `tac`/`scc_pci` (published while `cell_id` and `pci` were tokenized), and all WiFi key material including `WifiWpapsk`.
- Three of the four sat immediately next to a correctly-handled field. The pre-fix leak was reproduced to prove the new tests are not vacuous.

---

## [1.2.0-dev4] - 2026-08-14 - Guest-WiFi Write Decision; Structured Exempts

### Changed

- Recorded why `set_guest_wifi` bypasses the library's public setter: it posts only `Ssids` and `WifiRestart`, discarding `DbhoEnable` and `modify_guest_ssid`.
- Three `quality_scale.yaml` exemptions converted to the structured `{status, comment}` form.

---

## [1.2.0-dev3] - 2026-08-14 - masked_errors_check Audit

### Fixed

- Class D suppression audit across the component. Closed a blind spot in the contract sweep, which matched `client.` literally and missed calls reached through a lambda parameter — 21 calls found where there were 22.

---

## [1.2.0-dev2] - 2026-08-14 - Changelog Backfill

### Notes

- Entries `dev2` through `dev11` were written on 2026-08-15, after the fact. **Ten commits were tagged `[1.2.0-dev1]` in error** rather than incrementing, and the changelog was not updated as each landed — contrary to the project's own "one entry per phase, not one at the finish" rule. The commit tags are left as they are; these entries are the record.

---

## [1.2.0-dev1] - 2026-08-14 - Two Dead Library Calls; Tracker Unique IDs; Entity Cleanup Action

Section §S of the August 2026 update plan — work raised by the `huawei-lte-api` 2.0.0 review and the Home Assistant device-tracker review. **Opens the `1.2.0` release line**, which also settles the long-standing divergence between `manifest.json` and this changelog.

### Fixed

- **Two library calls have never worked, on the pinned version.** Both were verified absent from the installed `huawei-lte-api` 1.11.0 — and from 2.0.0 — rather than inferred:
  - **Logout.** `api.py` called `self._connection.logout`. `Connection` has no `logout` method and never has. The call raised `AttributeError` straight into a `_LOGGER.debug` handler, so **every unload, reload and options change silently failed to close the router session**, which then expired on its own TTL. That matters on a device whose concurrent-session limit is the reason `api.py` holds a lock at all. The real method is `client.user.logout()`.
  - **Clear Traffic Statistics.** `api.py` called `client.monitoring.clear_traffic()`; the method is `set_clear_traffic()`. The button could not work.

  Both were hidden by `# type: ignore[attr-defined]` — the suppression silenced precisely the check that would have caught them. `clear_traffic` was hidden twice over, because its test asserted `clear_traffic.assert_called_once()` against a bare `MagicMock`, which creates any attribute on demand. **The suite enforced the defect.**

- **Device tracker unique IDs were not unique across config entries.** `ScannerEntity.unique_id` is a property returning the bare MAC address, and it wins over the `_attr_unique_id` this integration had been setting — so that line had been dead code all along, and the entity IDs were globally the client's MAC. Two Huawei routers seeing the same client mint the same id, and Home Assistant's response is to **refuse the second entity entirely** (`entity_platform`: _"does not generate unique IDs … ignoring"_). Not an `_2` suffix — that is entity-**id** behavior. The client would simply never appear under the second router.

  **Fixed without a breaking change.** The entity now scopes its own id, and a one-time `entity_registry.async_migrate_entries` in `async_setup_entry` rewrites the existing registry rows before any platform is forwarded. Because the row is rewritten rather than replaced, the **`entity_id`, name, area, enabled state and every customisation are preserved** — automations and dashboards are unaffected. The migration is idempotent and scoped to `device_tracker`; every other platform has always built entry-scoped ids.

### Added

- **A library contract test.** Every `client.<group>.<method>` reference is extracted from `api.py` **by parsing the source**, then checked against the installed package. Not a hand-maintained list — forgetting to update a list is the exact failure being guarded against. This is what would have caught both dead calls, and it turns a future library bump into a red suite rather than a runtime `AttributeError`.

- **A suppression allow-list sweep.** Every `# type: ignore`, `# noqa` and `# pragma: no cover` must appear in `ALLOWED_SUPPRESSIONS` with a written reason; the sweep fails when the set grows, and a companion test fails on a dead entry or a token justification. Comments are found with `tokenize`, so directives quoted inside docstrings are not mistaken for live ones.

  **Ruff and mypy cannot cover this.** `RUF100` and mypy's `warn_unused_ignores` report a suppression that is _unnecessary_; they are silent on one that is doing real work because the error is real. Both were clean while two calls to non-existent methods sat behind `type: ignore`.

- **A `cleanup_unused_entities` action.** A `device_tracker` entity is created for every client the router has ever reported and nothing removed it, so a guest's phone seen once left a permanent entity. With a second router configured that stops being cosmetic. Modelled on `unifi_network_monitor`'s.

  **It previews by default** (`dry_run: true`). Two guards matter more than the feature: nothing is ever removed while `coordinator.data` is empty, and nothing is removed when the router reports zero clients — an outage would otherwise make every client look stale and delete the lot, which is irreversible.

- **A per-request transport timeout.** `Connection(timeout=REQUEST_TIMEOUT)`, deliberately well under `FETCH_TIMEOUT`. Previously a single hung endpoint consumed the entire 30-second poll budget and failed the whole update; now that endpoint fails alone and the other fourteen still return — and its absence is no longer silent, because the Integration Health sensor reports it as a degraded capability once it persists.

### Changed

- **`reboot` pre-migrated to `set_control(ControlModeEnum.REBOOT)`.** Library 1.11.0 carries `reboot()`, `control()` **and** `set_control()`; 2.0.0 removes the first two. Adopting the surviving spelling now means the eventual bump needs no code change here at all.
- **`hacs.json` now declares `"homeassistant": "2025.1.0"`**, so the minimum the README has always claimed is finally enforced. Before this, HACS would install on any version.
- **Every date written in the previous session was wrong** — recorded as 2026-08-09 when the work happened on 2026-08-14. 59 corrections across this changelog, `ROADMAP.md`, `value_min_max.md` and the tracking notes.

### Not done, and why

- **The `huawei-lte-api` 2.0.0 bump is blocked: the release is not on PyPI.** The GitHub tag exists, but the newest published version is 1.11.0 — confirmed against both `pip index` and the PyPI JSON API. Home Assistant installs requirements from PyPI, so pinning `2.0.0` would break every install. The pin was raised, verified to be uninstallable, and reverted. **All the code changes it would have required are already made**, so the bump becomes a two-line change whenever the package is published.
- **The six new 2.0.0 endpoints cannot be probed yet** — `onekey_diag`, `guesttime_setting`, `volte`, `acl`, `user.rule` and `wan_service_name` are all absent from 1.11.0. Blocked with the bump.
- **The public `wlan.set_multi_basic_settings()` was deliberately _not_ adopted**, reversing the plan. An earlier comment claiming no public setter existed was false and has been corrected — but the public setter posts only `{'Ssids': …, 'WifiRestart': 1}` and discards every other top-level key. Probed against a live B535: the GET returns **`Ssids`, `DbhoEnable` and `modify_guest_ssid`**, so calling it would silently drop band-steering and guest-SSID state on every guest-WiFi toggle. Round-tripping the full response, as the existing code does, is the correct behavior; the `# noqa: SLF001` now says so and is on the reviewed allow-list.

### Recorded decisions

- **`quality_scale.yaml` exempt entries converted to the structured form.** Three rules carried a bare `exempt`; hassfest's schema requires `{status, comment}` and skips the check entirely for custom components, so nothing caught it. **Huawei was the only one of the four projects using the bare form** — ZTE and WiFi already use the structured one — so this was local divergence rather than a family gap.

  `stale-devices` stays exempt and the comment now says why, including the part that is easy to lose: the exemption **depends on** the `device_info` override keeping clients as entities rather than devices. Remove that override and HA 2026.9+ would create a device per client, at which point the rule becomes live. Two coupled decisions that previously lived in different files.

  `discovery` is exempt with an honest comment rather than a convenient one: SSDP discovery **is** technically possible here — core `huawei_lte` matches Huawei `InternetGatewayDevice` — but it would only pre-fill the host while credentials are still required. Worth revisiting rather than assumed closed.

- **The guest-WiFi write decision is now recorded in three places that a future reader will actually hit**: the call site in `api.py`, a new section in `docs/DEVELOPMENT.md`, and the assertion in `test_api.py` that guards it. The test previously enforced the decision without explaining it, so someone swapping to the public setter would have met a bare failure and could reasonably have "fixed" the test. It now says the swap is the bug.

### `masked_errors_check` audit — run last, as designed

Run after every other change in this batch, per §S-13 of the tracking notes: the queued work changes the surface the prompt audits, and the prompt is also the check on that work.

| Class | Result |
| :-- | :-- |
| **A** — swallowed exceptions | **1 accepted.** Every broad `except` in `api.py` re-raises, bar two: the logout teardown (best-effort by design, and the connection is discarded regardless) and the per-endpoint handler in `get_data`, which drops a failed optional endpoint. The second is deliberate **and no longer silent** — the Integration Health sensor reports it as a degraded capability once it persists. |
| **B** — silent auth timeouts | **None.** Session expiry is detected from typed exceptions and the `125002` / `125003` / `100003` codes, plus a time-based inactivity reset in `_ensure_client`. |
| **C** — mock-masked tests | **Mitigated rather than removed.** The API tests still mock the client, but every method name they assert is now independently verified against the installed package by the contract test, which is the layer that was missing. |
| **D** — suppressed directives | **3, all reviewed and allow-listed** with written reasons. Down from five, of which three were wrong. |

**The audit found one new defect — in the contract test written earlier the same day.** Its pattern matched the receiver literally as `client.`, so `lambda c: c.dial_up.set_mobile_dataswitch(...)` was invisible to it: one real library call, unswept, by a test whose whole purpose is to sweep them. The rule now keys on the endpoint-group names taken from `Client` itself, so a receiver of any name is covered, and the previously-missed call is pinned by name. Coverage went 21 → 22 calls.

That is the argument for running this prompt last rather than first, made concrete: it caught a hole in the very mechanism built to prevent the original bug.

### Verification

**540 tests passing** (was 515), 100% line and 100% branch coverage, 0 partial branches, assertion audit PASSED, `ruff` lint and format clean, mypy standard and strict clean.

**Clear Traffic Statistics is fixed but not yet exercised against hardware** — deferred to month-end at the owner's request, since it resets counters. The Reboot change is likewise unexercised by choice.

## [1.1.3-dev17] - 2026-08-14 - Add HA Compatibility Document

### Changes

- **HA Compatibility**: Add new document `docs/ha_compatibility.md`to document HA compatibility, versus versus changes (including future planned deprecations).

## [1.1.3-dev16] - 2026-08-14 - CI Bumps Zizmor MyPy JSONSchema PHACC

### Bumps

- **Validate Bump**: Update `zizmor` from 1.28.0 to 1.29.0
- **Validate Bump**: Update `mypy` from 2.1.0 to 2.3.0
- **Validate Bump**: Update `check-jsonschema` from 0.37.4 to 0.38.0
- **Validate Bump**: Bumped PHACC `pytest-homeassistant-custom-component` from 0.13.354 to 0.13.355

## [1.1.3-dev15] - 2026-08-14 - Documentation Phase: Repair Titles, Roadmap, Spelling, Sweep Table

Phase 3 of the August 2026 update plan — all documentation and recorded decisions in one phase and one lint run, deliberately after the code settled.

### Fixed

- **The two repair issues had no translations at all.** `coordinator.py` raises `auth_failed` and `conn_error` with `translation_key`s that had **no matching `issues` block** in `strings.json` or `translations/en.json` — so the Repairs panel showed the raw key rather than a title. Added both, written to `x_proj_checks` §3.4's two rules: **prefix the vendor**, because the Repairs panel shows every integration's entries together, and **do not assert a cause the user cannot check**. "Huawei router sign-in failed" and "Huawei router is not responding", neither blaming firmware.

  This was invisible to the shared cross-project document, which states in four separate rows that Huawei has no repair issues at all.

- **US spelling swept across shipped text.** Twelve occurrences in six files — `cancelled`/`cancelling`, `colour`, `favour`, `quantisation`, `parenthesisation`/`parenthesised`. `codespell` does not flag UK spellings, so this needed a targeted word list; a looser pattern matched `raises`, `noise` and `otherwise` and was narrowed before use. The Python identifier `CancelledError` is deliberately untouched.

- **Three more stale statements in `docs/DEVELOPMENT.md`.** It described Refresh Now as calling `async_request_refresh()` (changed in `[1.1.3-dev10]`), quoted the RSRP guard band as `-140 to -30` when the code and `value_min_max.md` both say `-150` , and described `number.py` as merely persisting the interval without mentioning that the debounced write is now flushed on removal.

### Changed

- **`docs/ROADMAP.md` reconciled against the code and against `roadmap_format.md`.** Two entries were stale: "Dynamic Polling Interval Slider" had **already shipped** as the `polling_interval` number entity, and "Static Test Sweeps Implementation" landed across this cycle. The **Done** group is removed per the format's direction not to backfill one from the changelog. Added the write-classification register, the first mutation run, per-endpoint strike budgets, the blocked diagnostics verification, the version-convention question, and the `FREQUENCY` unit-selector issue that had only ever been recorded in `AGENTS.md`. Asterisk bullets converted to dashes — the file had never passed `markdownlint`.

- **`AGENTS.md` gains a "Tests that will stop you" table.** Sixteen rows covering every coverage sweep, what it guards and why it exists, with the standing direction: **if one of these fails it has found something — do not reach for the allow-list first.** These tests fail when a _set grows_, so the failure looks unrelated to whatever was just changed, and the reflex is to suppress it.

- **`README.md`** documents the Integration Health sensor with its attribute table and an example automation (diffed against the implementation, not written from memory), records that **Refresh Now now works while Pause Polling is on**, and notes that a refused control change surfaces an error instead of silently reverting.

- **The `device_tracker` privacy surface is documented.** No sibling project has this platform, so there was no prior art to inherit. The README now states plainly that an entity is created per network client carrying its MAC, hostname and IP; that those attributes are excluded from long-term history; that a diagnostics download replaces every one of them with a stable placeholder; and that the entities can be disabled without affecting the rest of the integration.

- **`docs/all_sensors.md`** gains the Integration Health entity (System sub-device 23 → 24, total 121 → 122). Counts in that file are authoritative only after a `sensor_review` run against live Home Assistant; this edit adds the one known new entity rather than re-deriving the inventory.

### Recorded decisions

- **Four entities repeat their sub-device word** — `total_data` in Data, `signal_bars` and `signal_bars_nr` in Signal, `sms_storage_full` in SMS. **Deliberately not renamed.** Home Assistant never renames an existing `entity_id`, so the only beneficiary would be a new install while anyone referencing the current friendly name gets a silent break. `zte_router_5g` kept two for the same reason. Recorded under Declined in the roadmap; the convention applies to new entities from here.

### Verification

515 tests passing, 100% line and branch coverage, `ruff` clean, mypy standard and strict clean, `markdownlint` clean across every tracked Markdown file, `prettier` clean, `codespell` clean, 46 README links checked, all JSON schema-valid.

## [1.1.3-dev14] - 2026-08-14 - Integration Health and Drift Detection; Guard Bands Reconciled

Phase 2 (third part) of the August 2026 update plan. Huawei was the family's only outlier on `dev_standards` Section 19, and `docs/value_min_max.md` had never been checked against the code since it was written.

### Added

- **Integration Health binary sensor (`dev_standards` Section 19).** A diagnostic `problem` sensor on the System sub-device, surfacing the failure Home Assistant does **not** catch: a poll that _succeeds_ while the data is wrong.

  That failure mode is specific and real here. `api.get_data()` fetches fifteen endpoints and **silently omits any optional one that fails** — only `device_information` raises. So SMS, WiFi clients, monthly usage or the network operator can each disappear from the payload while the integration reports a clean update and the affected sensors simply go blank. Nothing anywhere said so.

  What it reports:
  - **Capability degradation** — an endpoint absent for three consecutive polls, named in plain language (`SMS messages`, `WiFi clients`), not by raw endpoint key. Strike-budgeted so a single dropped poll raises no alarm.
  - **Contract drift** — a `device_signal` block that is present and non-empty but carries **none** of `rsrp`, `rsrq`, `rssi`, `sinr`. That is the direct catch for a firmware field rename, and it is the highest-value check in the section. One recognized field is enough to clear it: a weak signal is not a renamed field.
  - **Total outage** — flagged on the **first** failure at cold start (there are no held values, so waiting out the budget would leave the user with a wholly unavailable integration and no explanation), and on the **third** at runtime.

  Three properties worth stating because each is easy to get wrong:
  - **The sensor is never `unavailable`.** `available` returns `True` unconditionally. The inherited `CoordinatorEntity.available` returns `last_update_success`, which would take the sensor down at exactly the moment it has something to say — and a user reads `unavailable` as "this sensor is broken", not "my router is down".
  - **The verdict is stored outside `coordinator.data`.** `data` is `None` before the first success and frozen at the last good values during an outage, so a verdict held there could never describe the failure that stopped it being updated. It lives on `coordinator.health_snapshot`, written on **both** the success and failure paths.
  - **The health computation can never crash the poll it diagnoses.** It is wrapped; any internal error degrades to "healthy/unknown" and logs at debug.

  The attribute names — `severity`, `issues`, `degraded_capabilities`, `drift`, `last_good_update` — are the **normative Section 19 contract**, not internal names. Users write templates against them, so a project spelling one differently silently breaks every example written for a sibling. Pinned by a test against the entity's own output.

- **Guard-band coverage sweeps.** `test_every_numeric_sensor_has_a_guard_band` with an empty exemption allow-list and a dead-entry check. The rule is deliberately narrow — a sensor must declare bounds only when it carries a **unit or a state class**, i.e. when Home Assistant treats it as a measurement. A wider first draft on a sibling project flagged forty sensors where the sensors were right and the rule was wrong.

### Fixed

- **`docs/value_min_max.md` reconciled against the code for the first time, in both directions.** It had drifted badly:
  - It documented guard bands on **Transmit Power** and **5G Transmit Power** (-30 to 40) that **did not exist in the code at all**. Now implemented. Note these fields can hold a multi-carrier string (`"PPusch:12dBm PPucch:5dBm"`), which the guard passes through untouched — the band applies to the simple-number case, which is where an implausible reading appears.
  - It **omitted roughly twenty bands that did exist** — every frequency, every bandwidth, all four data rates, 5G rank and CQI.
  - `cqi_0` carried a minimum but **no maximum**, while its 5G twin `5g_cqi_0` carried `[0, 16]`. The same quantity on different radios, disagreeing only because nobody had compared them. Aligned to `[0, 16]`.

  The document is now a per-key table generated from source and **pinned by a test** (`test_value_min_max_doc_matches_the_code`) that fails on an undocumented band, a documented band that does not exist, and any value mismatch. Verified non-vacuous by mutation. This is the check that was structurally impossible before: a guard band is never published as a state or an attribute, so no live query can observe one.

### Changed

- **`AGENTS.md` and `docs/DEVELOPMENT.md` corrected.** Both still stated that every platform sets `PARALLEL_UPDATES = 0`, which stopped being true in `[1.1.3-dev13]`. `AGENTS.md` also described sub-device linking as using `via_device`, which stopped being true in `[1.1.3-dev10]`. Both now describe what the code does, and `AGENTS.md` gains the per-platform table and the standing direction never to assert `info["via_device"]` in a test.
- Repair ids and the endpoint/health constants moved into `const.py` (`REPAIR_NAMES`, `ENDPOINT_NAMES`, `SIGNAL_CONTRACT_KEYS`, `HEALTH_STRIKE_LIMIT`), replacing literal domain strings in `coordinator.py`.

### Verification

**515 tests passing** (was 497), 100% line and branch coverage, 0 partials, assertion audit PASSED (0 of 453), mypy standard and strict clean, `ruff` clean.

## [1.1.3-dev13] - 2026-08-14 - Action Icons; Icon and `PARALLEL_UPDATES` Sweeps; Secret Pre-Fill Guards

Phase 2 (second part) of the August 2026 update plan — the cheap ports and the decisions that need recording.

### Added

- **Action icons — the integration had no `services` block at all** while registering four actions. Action icons appear in the automation and script editors and in the Tools → Actions picker, so every one of this integration's actions showed the generic default while a sibling's carried theirs. Nothing was broken, which is why it went unnoticed. Added in the **nested** form (`{"service": "mdi:…"}`) that Home Assistant's current documentation shows — the flat form still renders but has nowhere to put per-`section` icons, and UniFi is the only project left on it.

- **A missing icon on the Refresh Now button, found by the new sweep.** `button.refresh` had neither an icon nor a `device_class`, so it rendered with the generic default; ZTE's equivalent has carried `mdi:refresh` all along. This is exactly what a coverage sweep is for — one offender out of 50-odd descriptions, invisible to review.

- **Icon coverage is now swept in both directions.** The only prior icon tests were two single-entity behavior tests for one sensor. Added:
  - every registered action has an icon, read from **`services.yaml`** rather than from a list in the test or from `icons.json` itself;
  - no icon entry names an action that is not registered, so a dead entry cannot accumulate invisibly;
  - action icons use the nested form;
  - every entity description has an icon or a `device_class`, read from **module source** across all seven platforms — two hand-maintained files can agree perfectly and both describe an entity that no longer exists.

- **`PARALLEL_UPDATES` decided per write path, and pinned.** The rule is that the constant is set deliberately, and that is not something a reader can verify: `0` from a considered decision and `0` from a copy-paste look identical. The decision is now a table in `tests/test_entity_hygiene.py` with its reasoning, and a second test fails if a new platform appears that the table does not cover.

  | Platform | Value | Why |
  | :-- | --: | :-- |
  | `button`, `switch`, `select` | **1** | Issue commands with a real-world effect. `api.py` already serializes every call behind an `asyncio.Lock` because concurrent calls answer "Busy" / `110001`; the lock is the actual safety mechanism and `1` states the same intent at the platform boundary. |
  | `number` | **0** | **Deliberately unlike `zte_router_5g`**, which sets `1` on every writable platform. The only number entity writes to `ConfigEntry.options`, which Home Assistant owns — no session to tear down, no command to duplicate. |
  | `sensor`, `binary_sensor`, `device_tracker` | **0** | Read-only and coordinator-driven; nothing to serialize. |

- **Secret pre-fill guards, ported from `zte_router_5g`.** `test_stored_secrets_are_never_pre_filled` and `test_no_field_leaks_the_stored_secret`, both parametrized over the user and edit schemas. **There is no defect here today** — the component has zero `suggested_value` uses — so these are a guard rather than a fix. They are worth having because the failure is silent: the screen looks correct and the stored password is exposed only when someone clicks the eye icon.

### Verification

**497 tests passing** (was 487), 100% line and branch coverage, 0 partials, mypy standard and strict clean, `ruff` clean, `icons.json` and `manifest.json` schema-valid.

## [1.1.3-dev12] - 2026-08-14 - Silent Write Failures; Orphaned Repairs; Lost Debounced Writes; Diagnostics Rewritten

Phase 2 (first part) of the August 2026 update plan — the standards defects that are not in the "confirmed four", plus the privacy rewrite. Tracked in `.notes/info/updates_202608/status_plan.md`.

### Fixed

- **Three write paths reported success having done nothing.** `HuaweiMobileDataSwitch.async_turn_on` / `async_turn_off`, `HuaweiGuestWifiSwitch` and `HuaweiRouterSelect.async_select_option` each caught `Exception`, logged it, and returned normally — so a refused write succeeded as far as Home Assistant was concerned, the control sprang back on the next poll, and the user's only evidence was a log line they had no reason to read. All three now raise `HomeAssistantError`, matching `button.py`, which already had this right.

  The guest-WiFi case was masked twice: the swallowed exception was followed by a refresh in a `finally`, which made a failed write look like a successful one that had merely been re-read.

  **This is a deliberate user-visible change.** A failed toggle now surfaces an error in the UI instead of silently reverting. That is the point.

  The post-write refresh now sits **outside** the error boundary in all three. Inside it, a transient failure while re-reading would report a write that had already succeeded as failed — inviting the user to retry a command with a real-world effect.

- **Repair issues outlived the entry that raised them.** `async_unload_entry` made no issue-registry call and there was **no `async_remove_entry` at all**. Deleting the integration with `auth_failed` raised left it in the Repairs panel permanently — `is_fixable=True`, offering a repair flow for an integration that no longer existed, with no coordinator left that could ever clear it. Added `clear_repairs()` on the coordinator, called on unload, and an `async_remove_entry` that clears them without going through `runtime_data` (which is gone by then).

  The two repair ids were **already entry-scoped**, so §3.8a of `x_proj_checks` does not apply here. The ids and their names are now named constants in `const.py` with the standing warning that renaming one orphans a live repair permanently.

- **A pending debounced polling-interval write was canceled rather than flushed.** `async_will_remove_from_hass` canceled the task without writing. The debounce is two seconds and a reload lands squarely inside it — an options change is enough to cause one — so a value the user had just set was discarded with nothing logged and no error. The pending value is now held separately and flushed on removal. No refresh is requested on that path: the entity is being torn down.

### Changed

- **`diagnostics.py` rewritten: 44 lines of key-name redaction → a layered scrubber.** The old module was a `TO_REDACT` set of twenty key names handed to `async_redact_data`, with the whole of `coordinator.data` poured through it. `async_redact_data` matches **by key name and does not recurse**, so everything below the top level was published verbatim — including `lan_host_info → Hosts → Host → […]`, the list carrying the **MAC address, hostname and IP of every device on the user's network**, and the SMS list carrying message bodies and sender numbers.

  This integration is more exposed than any sibling on exactly these two points: it is the only one in the family with a `device_tracker` platform, and one of two with SMS. The precedent for the failure is exact — `unifi_network_monitor` held `diagnostics: done` across two full IQS scans while leaking device MACs, user-assigned device names, internal IPs, the subscriber's ISP and third-party SSIDs.

  The replacement is layered and **recursive**: credentials and subscriber identifiers are blanked; IPs, MACs, hostnames, SSIDs and cell ids become stable tokens (`ip-1`, `mac-1`) so cross-references survive; SMS bodies are reduced to a length; and every remaining string is swept for anything address-shaped, as a structural backstop for keys the module does not enumerate — which is every key a future firmware invents. Everything diagnostically useful is preserved: model, firmware, hardware version, all signal metrics, band and channel, byte counters, uptime, connection status and failure counts.

  **Two false positives were caught by test, and are worth recording.** A first-draft sweep rewrote the firmware version `11.0.1.1(H192SP1C983)` as `ip-1(H192SP1C983)` — a four-part version parses as an IPv4 address — and the SMS timestamp `2026-08-14 10:00:00` as `2026-08-14 ip6-1`, because `10:00:00` reads as three hex groups. The rules were narrowed (octet bounds, and IPv6 now requires a `::` elision or the full eight-group form) and the genuinely ambiguous keys are named in `NEVER_SWEPT_KEYS`. An invented pattern that "usually" tells a version from an address would corrupt some other router's version string instead.

- **The diagnostics tests now assert the output rather than the mechanism.** The previous suite mocked `async_redact_data` and asserted it had been _called_ with the right arguments — which is equally true of an implementation that redacts nothing useful, and is the exact shape that produced two false clean verdicts on UniFi. The replacement asserts the negative property structurally: fifteen distinctive identifiers, each checked against the **serialized** document so nested lists and dicts are covered, parametrized so a failure names the value that leaked.

### Verification

**487 tests passing** (was 453), **100% line and 100% branch coverage, 0 partials**, mypy standard and strict clean, `ruff` lint and format clean.

**Not yet verified against a real download.** The scrubber is unit-tested against a realistic payload, but confirming it against a regenerated diagnostics file **with real router data in it** needs a live instance and is parked — see §P-2 of `status_plan.md`. Reading the code is what produced UniFi's two false clean verdicts, so this is deliberately **not** claimed as closed.

## [1.1.3-dev11] - 2026-08-14 - Zero Partial Branches; Zero-Assertion Tests Closed

Phase 1 of the August 2026 update plan — the test baseline. No source changes; this phase is entirely about what the suite can see.

### Added

- **Branch coverage is now 100% — eleven partial branches closed with nine tests.** A partial branch is a conditional where only one side has ever been taken; line coverage cannot see them, which is how this project sat at 100% lines with eleven of them. **None of the eleven was dead code**, which independently confirms the same result on `wifi_ssid_monitor` (12 of 12), `zte_router_5g` (11 of 11) and `unifi_network_monitor` (33 of 33). No new `# pragma: no cover` was added — the pragma changes the denominator, so it raises the number without anything being tested.

  The three largest were the uptime reboot-detection latches in `coordinator.py`. Every existing test hit the **first** poll, where all three latch; the steady-state path that runs on every subsequent poll was untested. The new test asserts the distinction that matters — the latched start times stay **frozen** rather than drifting forward each poll, which is what feeds the uptime-derived sensors.

  The rest, each stated as the behavior it now guards:
  - `device_tracker.py` — a malformed `lan_host_info` must not discard the clients in `wlan_host_list`. Written with two sources and the broken one **first**, so "skipped and continued" is distinguishable from "skipped and stopped".
  - `device_tracker.py` — a poll that finds no new client must not call `async_add_entities` at all.
  - `config_flow.py` — a router that reports no MAC under any of the three keys yields `mac: None` rather than an `AttributeError` surfacing as "unknown error".
  - `config_flow.py` — opening Reconfigure renders the form without contacting the router. Every prior test passed `user_input`, so the branch every user hits first was never taken.
  - `config_flow.py` — saving Options without renaming must not rewrite the entry title. `async_update_entry` with a title triggers listeners and a reload, so this is not cosmetic.
  - `binary_sensor.py` — the 5 GHz name fallback must skip the guest network. Set up so the guest is **enabled** and the real 5 GHz radio **disabled**, so matching the wrong one gives a different answer rather than the same one.
  - `switch.py` — the guest-SSID search walks past the primary SSIDs, in the order a real router lists them.
  - `sensor.py` — a truncated `(N…` band segment is skipped and parsing continues to the next segment.

### Changed

- **The four zero-assertion tests are closed, with no allow-list.** Each asserted only that a call did not raise, which is satisfied equally by the code doing the wrong thing quietly:
  - `test_debounced_apply_error` now asserts the write was **aborted rather than half-applied** — the coordinator interval is untouched, options are not rewritten and no refresh is requested. The previous form passed even if the failure came after persisting a value the user never confirmed.
  - `test_async_will_remove_from_hass_no_task` now asserts the task slot is still empty, which separates "there was nothing to cancel" from "something was created and canceled".
  - Both `logout`-with-no-connection tests now assert the no-op is observable — nothing dispatched to a thread, connection and client left as they were.

  `tests/zero_assertion_allowlist.txt` is deliberately **not** created. Every one of the four was expressible as a checkable outcome, which is what the audit's own guidance asks you to try before allow-listing.

### Verification

**453 tests passing** (was 444), **100% line and 100% branch coverage, 0 partial branches**, assertion audit **PASSED** (0 of 409), mypy standard and strict clean, `ruff` lint and format clean.

**This closes the last blocker on a family-wide gate.** `fail_under = 100` in `dev-workbench/workbench/python/pyproject.toml` is synced into every project and is all-or-none by design; WiFi, ZTE and UniFi reached zero partials on 2026-08-05, -07 and -08 respectively, and Huawei was the remaining one. That workbench change is a separate, deliberate four-project edit and is **not** made here.

## [1.1.3-dev10] - 2026-08-14 - Four Statistics-Corrupting Counters; `via_device` Deprecation; Recorder Hygiene; Refresh While Paused

Phase 0 of the August 2026 update plan — the four confirmed defects that no sibling project has. Two were causing harm every day; one has an external Home Assistant deadline. Tracked in `.notes/info/updates_202608/status_plan.md`.

### Fixed

- **Four resetting counters were walking long-term statistics backwards.** `current_day_used`, `month_download`, `month_upload` and `month_total` were declared `SensorStateClass.TOTAL`. Under `TOTAL`, Home Assistant recognizes a reset **only** from a `last_reset` attribute this integration has never published — so every daily and every billing-month rollover was recorded as one large negative delta and subtracted from the statistics sum. All four are now `TOTAL_INCREASING`, which detects the drop to zero itself and needs no attribute. `total_download`, `total_upload` and `total_data` were already correct and are unchanged.

  **Existing history is not repaired by this change.** Home Assistant applies the new state class going forward only. Tools → Statistics offers a per-entity fix-up for the skewed periods.

- **Refresh Now, and nine other explicit user actions, did nothing while Pause Polling was on.** The coordinator short-circuited on the pause flag before fetching, and every user-initiated refresh went through a bare `async_request_refresh()` — so the action reported success and returned cached data at exactly the moment a fresh reading was wanted. A one-shot `async_force_refresh()` now sets a force flag that is consumed at the top of the update cycle and bypasses the pause; **scheduled polls still respect it**. All eleven call sites are routed through it: Refresh Now, Clear Traffic Statistics, resume polling, mobile data on/off, guest WiFi on/off, network mode, polling interval, delete SMS and delete all SMS.

- **The deprecated `via_device` identifier tuple is removed.** Home Assistant 2026.8 deprecates `DeviceInfo.via_device` and `async_get_device(identifiers=…)`; both are **removed in 2027.8**. A `_compat.py` shim, ported from `zte_router_5g` (originally `unifi_network_monitor`), feature-detects the replacement and emits a resolved `via_device_id` where available, falling back to the tuple on older Home Assistant. The integration stays floor-free — one behavior on 2026.7 and on post-2027.8 alike. Both call sites are converted: the sub-device builder in `helpers.py` and the Clients root registration in `__init__.py`.

- **Every entity attribute was being written to the recorder on every state change.** The component declared no `_unrecorded_attributes` anywhere. The SMS sensor republished the sender's phone number, message date and index each poll; the device tracker republished interface type, associated SSID and address source **once per connected client per poll**; the guest WiFi switch republished a static SSID string. All are now declared unrecorded — none is a time series, and all three are visible as current state where they are useful.

### Added

- **`tests/test_entity_hygiene.py`** — coverage sweeps rather than mechanism tests, so they fail when the set grows rather than when a path changes:
  - `test_no_sensor_uses_the_total_state_class`, backed by an **empty** `ALLOWED_TOTAL_STATE_CLASS`, so typing `TOTAL` into a new description is a test failure and exempting one is a reviewable act. With `test_allowed_total_state_class_has_no_dead_entries` so an exemption cannot outlive its sensor.
  - `test_every_entity_publishing_attributes_declares_unrecorded`, which discovers entity classes by inspection rather than from a list, so a new platform cannot be added without the sweep seeing it.
  - A "guard the guard" test beside each, because both sweeps pass vacuously if the set they inspect becomes empty.
- **`tests/test_compat.py`** — both branches of each shim forced by patching the detection flag, since the suite only ever runs against one Home Assistant version.
- **`assert_links_to_parent()` / `assert_is_root()` in `tests/conftest.py`.** Twelve tests asserted `info["via_device"] == (DOMAIN, …)` directly and were green only because the installed Home Assistant happened to take that branch. They now assert the link's **presence and exclusivity** rather than which key carries it. Verified non-vacuous by mutation: making the shim emit no link fails seven of them.
- Four coordinator tests covering the force flag: that a forced cycle really reaches the router while paused, that the flag is consumed after one cycle so the next scheduled poll still respects the pause, that it is set before the refresh is awaited, and that it is cleared when the request raises.

### Changed

- **`helpers.py`** gains `from __future__ import annotations` and hoists the function-local `CONF_HOST` import to module scope, which also clears a `TC004` lint error.
- **`api.py`** — the deliberate reach into `huawei_lte_api`'s session for the multi-basic-settings endpoint now carries an explicit `# noqa: SLF001` with its reasoning, rather than a project-local lint config change that the next shared sync would erase. A stale `# noqa: BLE001` on `logout` is removed.

### Verification

429 → **444 tests passing**, 100% line coverage, mypy standard and strict clean, `ruff check` clean (was 4 errors). Partial branches unchanged at **11** — none introduced by this work; closing them is the next phase.

## [1.1.3-dev9] - 2026-08-08 - CI Bumps; Github Zipfile; PyTest Branch & Mutation Testing

### Bumps

- **Shared CI**: Bump `.github` Shared CI Validation via SHA from v2.0.6 to v2.0.10
- **Validate Bump**: Update `ruff` from 0.15.20 to 0.16.1
- **Validate Bump**: Update `zizmor` from 1.25.2 to 1.28.0
- **Validate Bump**: Update `codespell` from 2.42 to 2.43
- **Validate Bump**: Bumped PHACC `pytest-homeassistant-custom-component` from 0.13.346 to 0.13.354

### Changed

- **`release.yaml`**: Along with `.github`shared CI v2.0.10, added `release.yaml`to auto create and attached a zipfile to each new release, for download tracking purposes.
- **`hacs.json`:** Updated to add `filename:`and `zip_release: true`fields, for zipfile use, for download tracking.
- **PyTest Branch Coverage:** Added branch coverage to existing PyTest line coverage measurement. Added via shared sync `tasks.json`.
- **`mutmut`:** Added `mutmut` via shared Dockerfile base image for Mutation Testing. Added task to `tasks.json`via shared sync.
- **`ruff`Rules:** Updated `ruff`rules, via shared CI to match latest HA exclusions and inclusions.
- **Shared Sync Do Not Edit**: Added comments to several of the shared sync files to clarify they were shared and not to be edited locally.
- **AGENTS No git:** Updated `AGENTS.md` to clarify strict restrictive rules around write git use.
- **US UK Spelling**: Updated spelling to US standard (z vs s, color vs color etc), to match HA standard.
- **Tools not Dev Tools**: Changed References to "Developer Tools" to "Tools" to align with HA 2026.8+
- **`changelog_local` ToC**: Added Table of Contents to `changelog_local` (top-of-file) and to end of `CHANGELOG`.
- **Documentation**: the README's example automations now ignore `unknown` and `unavailable` states, to avoid false alerts from a HA restart or router reboot.
- **Icons and branding** refreshed.

## [1.1.3-dev8] - 2026-07-28 - Automation Example Glitch Guards & Float Rounding in README

Reinforced example automations in `README.md` to prevent false triggers during router reboots, polling glitches, or entity unavailability, and rounded numeric outputs.

### Changed

- **`README.md` Example Automations Glitch Protection**:
  - **`High Data Usage Alert`**: Fixed string-to-float template conversion by applying `| float(0) | round(0)` to daily and monthly data total templates to prevent unrounded decimal output.
  - **`Signal Quality Alert`**: Added `not_from: ["unknown", "unavailable"]` state trigger filters and annotated with a `note:` to prevent router reboots from triggering false degradation alerts.

---

## [1.1.3-dev7] - 2026-07-12 - PHACC Bump; README Alignment and Codespell

### Bumps

- **Validate Bump**: Bumped pytest-homeassistant-custom-component from 0.13.345 to 0.13.346

### Changed

- **Docs**: Minor fixes to README for alignment with other project READMEs (clarification on disabling devices and/vs. entities)
- **Formats**: Codespell alignment, words like behavior and color etc.

## [1.1.3-dev6] - 2026-07-06 - Shared CI Bump v2.0.5 → v2.0.6

### Bumps

- **Shared .github CI Validation**: Bump .github Shared CI Validation via SHA from v2.0.5 to v2.0.6

## [1.1.3-dev5] - 2026-07-06 - Test Suite Repaired After the Ruff Extension

### Changed

- **PyTest Errors and Coverage**: The changes in dev4 below caused several of the existing PyTests to fail and also introduced new uncovered statements. Fixed and added tests to get to 100% coverage with all tests passing.

## [1.1.3-dev4] - 2026-07-06 - Ruff Checks Extended to Match Home Assistant

### Changed

- **Ruff Checks Extended**: As of shared CI Dev-workbench v2.2.1, Ruff checks have been extended to align with Home Assistant. This involves INcluding a wide range of checks and then EXcluding several items because of the wider range. In this project, that lead to 24 issues to be addressed.
- **Ruff Compliance Alignment**: Resolved 24 static analysis lint warnings in the custom component and test files under stricter Home Assistant Core rules:
  - **Exception Flow Refactoring (`TRY301` / `TRY300`)**: Isolated network data fetches from subsequent structure validation in `coordinator.py` and `api.py` to prevent raising exceptions inside try blocks. Moved return statements outside try blocks in `api.py`.
  - **Timezone Awareness (`DTZ005`)**: Replaced all naive `datetime.now()` calls in `api.py` session updates and mock setup in `tests/test_api.py` with timezone-aware `datetime.now(UTC)` using the Python UTC alias.
  - **Production Assertion Checks (`S101`)**: Replaced insecure assertions (`assert self.url is not None`) in `api.py` and `config_flow.py` with explicit check guards throwing `ValueError`.
  - **Defensive Error Handling (`BLE001` / `TRY401`)**: Converted generic exception catches on entity actions to traceback-preserving `_LOGGER.exception()` or explicit debug logs. Removed redundant exception variables from `_LOGGER.exception()` formatting signatures in `select.py`.

## [1.1.3-dev3] - 2026-07-06 - IQS Static Check Added; Check-Drift Fixed

### Changed

- **IQS Validation**: `dev-workbench` script `iqs_static_check.py` added via `tasks.json` now checks for Home Assistant Integration Quality Scale ( IQS ) compliance to 7 basic IQS rules.
- **Dev-WorkBench**: Updated the Check Drift script to account for the situation where the HA Core version online is ahead of the local version (dev-workbench v2.1.0-dev9).
- **Documentation**: Updated README.md , re-ordered some sections for logical flow and readability.

### Bumps

- **Validate Bump**: Bumped `pytest-homeassistant-custom-component` from 0.13.344 to 0.13.345

## [1.1.3-dev2] - 2026-07-03 - SMS Actions Default to the Sole Router

### Changed

- **SMS Actions Default to the Sole Router**: The `delete_sms`, `delete_all_sms`, and `get_sms_list` actions no longer require `entry_id`. When exactly one router is configured it is selected automatically; with more than one configured, `entry_id` is required and omitting it now raises a clear "specify entry_id" error instead of silently acting on an arbitrary router (`send_sms` already behaved this way). Implemented by relaxing the three service schemas and `services.yaml` to optional, and tightening `_get_coordinator` to auto-select only when a single entry is loaded. Added a test for the multiple-entry guard (single-entry fallback was already covered).
- **Documentation**: Updated the README to align as closely as possible with the ZTE 5G Monitor README.

## [1.1.3-dev1] - 2026-07-03 - Docs Aligned With the ZTE Project

### Changed

- **Docs**: Minor updates to README and CHANGELOG to align with changes made in ZTE Project docs.

## [1.1.2] - 2026-07-03 - Release - Refresh Now Button; Display Units; Config-Flow Hardening

### Added

- **Refresh Now Button**: New System sub-device button that triggers an immediate data refresh.

### Changed

- **Display Units & Precision**: 23 sensors now display expected units and decimal places (data sizes in GB, data rates in Mbit/s, durations in hours, rounded signal/frequency values) while native values used for long-term statistics stay unchanged.
- **Polling Toggle Future Ready**: Turning off "Enable polling for changes" in the entry's system options now reliably stops scheduled polling and will satisfy the upcoming HA requirement (implicit `ContextVar` detection is being removed in HA 2026.8).
- **Disabled-by-Default Sensors**: User Capacity, Month Download (GB), and Month Upload (GB) are now disabled by default for new installs.

### Fixed

- **Password No Longer Exposed on Edit Screens**: The password field is no longer pre-filled or revealable on the Reconfigure/Options/Reauth screens — leave it blank to keep the current password, or enter a new value to change it.
- **Host Field Normalization**: A scheme (`http://`) or trailing slash entered in the Host field is now stripped before storage, preventing a malformed device link (e.g. `http://http://192.168.8.1`).

## [1.1.2-dev10] - 2026-07-03 - README Screenshots and Sensor Counts

### Changed

- **Documentation**: Updated the README screenshots to include Refresh Now button and with higher resolution. Updated all_sensors.md and README.md to correctly reflect sensor counts and groups.

## [1.1.2-dev9] - 2026-07-03 - Ruff Bump 0.15.19 → 0.15.20

### Bumps

- **Validate Bump**: Update Ruff from 0.15.19 to 0.15.20

## [1.1.2-dev8] - 2026-07-03 - Three Sensors Disabled by Default

### Changed

- **Disabled-by-Default Sensors**: Made sensors User Capacity (wifi_capacity), Month Download (GB) (month_download_gb), and Month Upload (GB) (month_upload_gb) disabled-by-default for new installs.

## [1.1.2-dev7] - 2026-07-02 - Explicit `config_entry` on the Coordinator

### Summary

- **Explicit `config_entry` on the Coordinator**: Pass the config entry explicitly to `DataUpdateCoordinator` so Home Assistant reliably honours the "Enable polling for changes" system option and to satisfy the upcoming HA requirement (implicit `ContextVar` detection is being removed in HA 2026.8).

### Changed

- **Coordinator `config_entry`**: `HuaweiRouter5GDataUpdateCoordinator` now passes `config_entry=entry` to `super().__init__()`. This makes `self.config_entry` explicit, which is what HA core's `_schedule_refresh()` checks (`config_entry.pref_disable_polling`) to stop scheduled polling when the user sets **System options → "Enable polling for changes" = OFF**. Manual updates (`homeassistant.update_entity`, "Refresh Now", Pause-Polling off→on) still fetch. No behavior change on current HA — it removes reliance on implicit context detection, which HA logs as an error from **2026.8**. (Minimum HA is already 2025.1, so no version bump was needed.)

### Tests

- Added a coordinator test asserting `coordinator.config_entry is entry`.

### Bumps

- **Shared .github CI Validation**: Bump .github Shared CI Validation via SHA from v2.0.4 to v2.0.5 (PR #21)

## [1.1.2-dev6] - 2026-07-02 - Suggested Display Units and Precision on 23 Sensors

### Summary

- **Suggested Display Units & Precision**: Applied Home Assistant's `suggested_unit_of_measurement` / `suggested_display_precision` to 23 sensors so the UI shows friendly units and sensible decimal places while native values (used for long-term statistics) stay canonical.

### Changed

- **Data Size Sensors (Bytes → GB)**: `total_download`, `total_upload`, `total_data`, `month_download`, `month_upload`, `month_total` suggest `GIGABYTES` at precision **1** (totals/monthly); `current_day_used`, `current_connection_upload`, `current_connection_download` suggest `GIGABYTES` at precision **2** (daily/session). Native unit stays `BYTES`.
- **Data Rate Sensors (B/s → Mbit/s)**: `current_download_rate`, `current_upload_rate`, `max_download_rate`, `max_upload_rate` suggest `MEGABITS_PER_SECOND` at precision **2**. Native unit stays `BYTES_PER_SECOND`.
- **Duration Sensors (s → h)**: `uptime`, `current_connection_duration`, `total_connection_time` suggest `HOURS` at precision **1**. Native unit stays `SECONDS`.
- **Frequency / Bandwidth (MHz)**: the 4 LTE/5G frequency and 4 LTE/5G bandwidth sensors now round to **0** decimal places (`suggested_display_precision=0`); unit unchanged (`MEGAHERTZ`).
- **Signal Strength (dBm)**: `rsrp`, `rssi`, `nr_rsrp` round to **0** decimal places; unit unchanged. (RSRQ/SINR in dB left fractional.)

### Notes

- Native units are unchanged in every case — only the display hint is added, so long-term statistics and the guard-band limits (defined in native units) are unaffected.
- The legacy `month_download_gb` / `month_upload_gb` sensors (already GB, disabled by default) were intentionally left as-is.

### Tests

- Added parametrized coverage asserting the suggested unit/precision on all 23 affected sensors.

## [1.1.2-dev5] - 2026-07-02 - Config-Flow Hardening & Refresh Now Button

### Summary

- **Config Flow Hardening & Refresh Button**: Normalized host input before storage, stopped exposing the stored password on edit screens, and added a "Refresh Now" button.

### Added

- **Refresh Now Button**: New System sub-device button that triggers an immediate coordinator refresh (`async_request_refresh`), complementing the existing Pause Polling switch and configurable polling interval.

### Changed

- **Host Normalization in Config Flow**: Added `_clean_host()` and applied it to all four config-flow steps (user, reconfigure, reauth, options) so a scheme prefix (`http://`/`https://`) or trailing slash entered in the Host field is stripped before it is stored in `entry.options`. Prevents the doubled root device `configuration_url` (`http://{host}` → `http://http://192.168.8.1`) that resulted from the default host including a scheme. The API layer's `_normalize_router_url` re-adds the scheme at runtime, so connectivity is unaffected.
- **Password No Longer Exposed on Edit Screens**: Split the config-flow schema into setup (`_user_schema`) and edit (`_edit_schema`). The password now uses a masked `TextSelector` and is left blank on Reconfigure/Options/Reauth — the stored value is never pre-filled or revealable via the UI eye icon. A blank submission keeps the stored password via `_merge_credentials()`; entering a value changes it.
- **Field Helper Text**: Added `data_description` guidance under the password field on the Reconfigure/Options screens ("Leave blank to keep the current password, or enter a new one to change it.").
- **Reconfigure Preserves Runtime Options**: `async_step_reconfigure` now merges into existing options (`{**entry.options, **merged}`) instead of replacing them, so `scan_interval` / `stop_polling` are no longer dropped when the connection details are reconfigured.

- **YAML Lint**: Added "document-start: disable" to .yamllint rule file, to stop warns/fails for "no --- at document start", which brings it in line with Home Assistant.
- **YAML Files**: Updated YAML files to remove any "---" document starts added.
- **Tasks.json**: Updated tasks.json, via hosts-tooling so that YAML-Lint only runs on git tracked files.
- **.gitignore**: Added scratch folders

### Tests

- Added coverage for host cleaning, credential merge, URL-host stripping in the user flow, blank-password retention (reconfigure + options), and the new Refresh Now button. Updated the button setup test to expect three entities.

### Bumps

- **Validate Bump**: Updated `ruff` from 0.15.16 to 0.15.19 (PR #16)
- **Validate Bump**: Bumped `pytest-homeassistant-custom-component` from 0.13.326 to 0.13.344
- **Validate Bump**: Bumped `check-jsonschema` from 0.37.2 to 0.37.4

## [1.1.2-dev4] - 2026-06-18 - CI Validation Overhaul

### Summary

- **CI Validation Overhaul**: Major overhaul of the local (tasks.json) and online (github.com CI) Validation system

### Changed

- **dev-workbench**: Moved CI Validation and Sync to dev-workbench system, with major restructure of files and folders.
- **CI Local Tasks**: Reordered local tasks.json, added color for pass/fail.
- **CI Validation Bump**: Shared CI validation bumped to v2.0.3. No user changes in this release, background/infrastructure only.
- **CI Validation Bump**: Shared CI validation bumped from v2.0.1 to v2.0.2
- **CI Coverage Report**: Removed the pytest coverage report as it required extra permissions and is separate to the coverage badge, which is what is really required.
- **CodeQL**: CodeQL shared config and local caller modified to detail permissions to that Zizmor will pass
- **CodeQL**: Added a shared CodeQL validation config to the shared validation repo, pulled into each project, incl this one.
- **Validation Config**: Fixed use of .prettierrc.json
- **Link Check**: Updated markdown-link-check to ignore .notes/ and .shared/ links in projects as these are excluded.
- **Validation Config**: Changed from .prettierrc.js to .prettierrc.json to allow GitHub.com CodeQL to run without errors
- **.gitignore**: Multiple updates to .gitignore
- **AGENTS.md**: Added AGENTS.md to repo root

## [1.1.2-dev2] - 2026-06-11 - Validation Tooling Sync System

### Changed

- **Validation Sync**: Moved to a better system and process to keep validation (lint/format/test) tools in sync, across PlayFaster projects and between the projects and what Home Assistant uses.
  - .validate/version_matrix.json added as the definitive source of tool version use.
  - Several Env: entries added to .vscode/tasks.json for tool sync and checking.
  - .validate/requirements_test.txt pulled as generic, with all tools pinned to versions, and requirements_custom.txt used to add project specific items.
  - As part of the sync, docker-compose.yml and devcontainer.json are now generic, with a .env file holding project specific info and a docker-compose.override.yml holding additional, project specific steps.
  - HA Manifest and HACS schema files updated.
- **DependaBot**: Bumped Ruff from 0.15.12 to 0.15.16

## [1.1.1] - 2026-06-07 - Release - Startup Race, Session and Timestamp Fixes

### Summary

- v1.1.1 is clean-up and bug-fixes, no new features.
- Fixed a timestamp bug and removed several sensors from long term statistics.

### Fixed

- **Integration startup failure on HA reboot**: Eliminated a transient import race in the `url_normalize` → `idna` → `uts46data` dependency chain. On cold HA startup, the integration could fail with `ImportError: cannot import name 'uts46data'` and would not recover without a full HA restart. Replaced with a stdlib-only URL normalization helper.
- **HA 2026.6 deprecation warning**: Updated `ScannerEntity` import to the canonical `homeassistant.components.device_tracker` path, eliminating the HA 2026.6 startup warning and preventing a hard failure when the deprecated alias is removed in HA 2027.6.
- **SMS actions failing after inactivity**: Calling SMS services (`send_sms`, `delete_sms`, etc.) after ~2 minutes of inactivity resulted in `100003: No rights` errors. Fixed with proactive session reset (100-second inactivity threshold) and automatic single retry on session expiry.
- **Uptime/connection timestamp drift**: Replaced the polling-based uptime calculation (which recomputed `now() − uptime` on every poll) with a reboot-detection latch. Boot and connection start times are now computed once and frozen, eliminating clock-rate drift and backward jumps at minute boundaries.
- **Startup validation warning**: Added the required `CONFIG_SCHEMA` declaration to `__init__.py`, resolving a hassfest validation warning on integration setup.
- **Button failures invisible to automations**: Reboot and Clear Traffic buttons previously caught API errors silently. Both now raise `HomeAssistantError` so automations can detect and respond to failures.
- **Device tracker crash resilience**: Replaced broad try-except blocks in `device_tracker.py` with explicit `None` guards matching the pattern used by all other platforms.
- **Diagnostics crash on early query**: Added a `coordinator.data or {}` guard in `diagnostics.py` — previously, opening the diagnostics panel before the first successful poll caused a crash.

### Changed

- **Dynamic entity icons**: All entity icons migrated to HA's `icons.json` translation system. Signal bars (1–3), battery (10–100%), and SMS unread sensors now display context-aware icons that change automatically based on sensor value or state.
- **Long-term statistics cleanup**: Removed `state_class` from 32 sensors that were incorrectly generating Long Term Statistics entries — specifically frequency/bandwidth sensors, SMS count sensors, connection duration sensors, and data rate sensors. These sensors report instantaneous or cumulative values that are not suitable for HA's statistics pipeline.

## [1.1.1-dev24] - 2026-06-07 - Project-Wide Test Coverage to 100%

### Added

- **100% Project-Wide Test Coverage**: Closed the last 10 uncovered statements across 5 source files by writing 10 new tests in existing test files. No source code files were modified.
  - `switch.py` (3): Normalization when `Ssid` is a single dict in `_is_on` and `extra_state_attributes`, and fallthrough `return {}` when no guest SSID is found.
  - `number.py` (2): `async_will_remove_from_hass` entity lifecycle cleanup — both with and without a pending `_refresh_task`.
  - `binary_sensor.py` (3): Single-dict `Ssid` normalization for `HuaweiWifi24GStatusSensor` and `HuaweiWifi5GStatusSensor`; `data=None` guard for `HuaweiEndcRestrictedSensor`.
  - `config_flow.py` (1): Successful reauth path — `async_step_reauth` when a valid config entry exists.
  - `device_tracker.py` (1): `_host_data` returns `None` when `coordinator.data` is `None`.
  - Total coverage: 99% → 100% (1420/1420 statements). All 383 tests passing.

## [1.1.1-dev23] - 2026-06-07 - `ScannerEntity` Import; mypy Config Realigned With HA

### Fixed

- **`ScannerEntity` Import — mypy / ruff / Line-Length Deadlock Resolved**: The `# type: ignore[attr-defined]` suppress comment introduced in dev22 was landing on the wrong line and therefore never suppressed the error. The full chain of causation:
  1. **Why the import is multi-line**: The single-line form (`from homeassistant.components.device_tracker import ScannerEntity  # type: ignore[attr-defined]`) is 95 characters — over the 88-char `line-length` limit. ruff therefore always expands it to multi-line.

  2. **What ruff does to the comment on expansion**: When ruff expands a single-line import to multi-line form, it moves any trailing comment from the import statement onto the last imported member line. The result was:

     ```python
     from homeassistant.components.device_tracker import (
         ScannerEntity,  # type: ignore[attr-defined]   ← comment on member line (line 7)
     )
     ```

  3. **Where mypy attributes the error**: mypy reports `[attr-defined]` on the `from` line (the statement opener, line 6), not on the member line (line 7). A `# type: ignore` comment on line 7 has no effect on an error reported on line 6 — mypy's line-matching is exact. So the error was never suppressed and pre-commit mypy failed.

  4. **Why this was also a contradiction in the earlier config**: In the config before dev23, the `homeassistant.*` override lacked `no_implicit_reexport = true`, so basic mypy (no `--strict`) never raised `[attr-defined]` at all. That made the `# type: ignore[attr-defined]` simultaneously needed (strict mode) and unused (basic mode), triggering `[unused-ignore]` in basic mode. Adding `no_implicit_reexport = true` to the override (see Changed below) resolved the basic/strict split — both modes now raise `[attr-defined]`, so the ignore is always in use.

  5. **The fix**: Use the multi-line form with the `# type: ignore[attr-defined]` on the `from (` line, not the member line:

     ```python
     from homeassistant.components.device_tracker import (  # type: ignore[attr-defined]
         ScannerEntity,
     )
     ```

     Verified in the devcontainer: running `ruff format` on this exact form returns "1 file already formatted" — ruff does not move a comment that is already on the `from (` line (it only moves comments to the member line when _expanding_ a single-line import). Running mypy against this form returns "no issues found" — the suppress comment is on the same line as the reported error.

  6. **`warn_unused_ignores = false` override removed**: The per-file override for `custom_components.huawei_router_5g.device_tracker` that disabled `warn_unused_ignores` was removed. It was only needed while basic and strict mypy disagreed on whether `[attr-defined]` fired. With `no_implicit_reexport = true` now applied consistently, both modes raise the error and the ignore is always used — the override served no further purpose.

### Changed

- **`pyproject.toml` — mypy Configuration Realigned with HA's Internal `mypy.ini`**: The project's `[tool.mypy]` section has been restructured to closely match HA's auto-generated `mypy.ini` (produced by `script/hassfest -p mypy_config`). This ensures the pre-commit mypy hook, and the project's basic `mypy custom_components/` check, run under materially the same conditions as HA's own integration quality checks. The goal is for any type errors caught here to be errors HA itself would also catch — and vice versa.

  **Flags added** (HA applies these globally; the project previously lacked them):

  | Flag | Why added |
  | --- | --- |
  | `platform = "linux"` | Matches HA's platform assumption; eliminates platform-specific type divergence |
  | `local_partial_types = true` | Prevents deferred variable typing (e.g. `x = []` with no annotation) |
  | `strict_bytes = true` | Stricter bytes/str distinction |
  | `warn_incomplete_stub = true` | Surfaces partially-typed stubs that could produce misleading "no error" results |
  | `disallow_incomplete_defs = true` | Flags functions with only some arguments annotated |
  | `disallow_untyped_calls = true` | Flags calls into untyped functions (catches missing annotations in third-party wrappers) |
  | `enable_error_code = ["deprecated", "ignore-without-code", "redundant-self", "truthy-iterable"]` | HA's four enabled codes. Notably `ignore-without-code` requires every `# type: ignore` to carry a specific error code — bare `# type: ignore` comments are now an error |

  **Flag changed**:

  | Before | After | Why |
  | --- | --- | --- |
  | `ignore_missing_imports = true` | `disable_error_code = ["annotation-unchecked", "import-not-found", "import-untyped"]` | HA's approach is targeted error-code suppression rather than a blanket flag. Effect is functionally similar for missing stubs but matches HA's convention exactly |

  **Flag removed**:

  | Flag | Why removed |
  | --- | --- |
  | `disallow_any_generics = true` (global) | HA only applies this to ~10 specific HA core modules (auth, core, helpers), not globally. Keeping it global made the project stricter than HA on generics without a matching rationale |

  **`homeassistant.*` override updated**:

  | Change | Detail |
  | --- | --- |
  | Removed `implicit_reexport = true` | This was an incorrect addition from a prior fix attempt. It contradicted HA's own `no_implicit_reexport = true` policy for HA modules and masked potential import errors across all of `homeassistant.*` |
  | Added `no_implicit_reexport = true` | Matches HA's own `[mypy-homeassistant.*] no_implicit_reexport = true` exactly. HA explicitly enforces that its modules only export names declared in `__all__`. Setting this in the project's override causes both basic and strict mypy to apply the same rule when the project imports from HA — surfacing cases where HA's public API surface doesn't match its declared exports (such as the `ScannerEntity` gap) |
  | Kept `ignore_errors = true` | Project-specific necessity: prevents HA's internal type errors from surfacing in the project's checks. HA is responsible for its own type correctness |
  | Kept `follow_imports = "silent"` | Project-specific: avoids walking all of HA's source tree on every type check, keeping mypy runs fast |

  **Net result**: both `mypy custom_components/` (basic) and `mypy custom_components/ --strict` pass with zero errors. The pre-commit mypy hook (which runs basic mode) is now consistent with HA's own integration quality checks.

  **Note**: `ScannerEntity` is re-exported in `homeassistant/components/device_tracker/__init__.py` via `from .config_entry import ScannerEntity  # noqa: F401` without `__all__`. HA's own mypy (`no_implicit_reexport = true` for `homeassistant.*`) would reject this if HA's internal code used the public path — which is why HA's own code imports `ScannerEntity` from `config_entry` directly. The `# type: ignore[attr-defined]` in `device_tracker.py` documents this HA inconsistency and should be removed once HA adds `ScannerEntity` to `device_tracker/__all__`.

## [1.1.1-dev22] - 2026-06-07 - `url_normalize` Startup Race Eliminated

### Fixed

- **`url_normalize` Startup Race Eliminated**: Replaced the `url_normalize` third-party library with a private `_normalize_router_url()` helper in `api.py` using stdlib `urllib.parse`. The `url_normalize` → `idna` → `uts46data` import chain was susceptible to a transient Python module initialization race during HA's concurrent startup, causing `ImportError: cannot import name 'uts46data'` on reboot. The integration would not recover without a full HA restart. The stdlib replacement covers all real-world router URL forms (bare IP, missing scheme, trailing slash, uppercase scheme, port) with no external dependencies and no UTS46 exposure.
- **`ScannerEntity` Deprecation Warning Suppressed**: Updated `device_tracker.py` to import `ScannerEntity` from `homeassistant.components.device_tracker` (the canonical path since HA 2026.6) rather than the deprecated alias at `homeassistant.components.device_tracker.config_entry`. Eliminates the HA 2026.6 log warning; prevents a hard failure when the alias is removed in HA 2027.6.
- **`manifest.json` Requirements**: Removed `url-normalize==3.0.0` from `requirements` following the stdlib replacement above.

### Added

- **`test_normalize_router_url` Parametrized Test**: Added 7-case test in `test_api.py` covering bare IP, well-formed URL, trailing slash, uppercase scheme, port-only (no scheme), port with scheme, and leading/trailing whitespace — replacing the implicit coverage that `url_normalize` provided via its own library tests.

### Changed

- **README Emoji Consistency**: Replaced all VS16 compound emoji in headings and ToC links with always-color single-codepoint alternatives (`⚙️`→`🔧`, `🗑️`→`❌`, `⚠️`→`❗`, `⏱️`→`🔁`, `✉️`→`💬`, `⏯️`→`🔁`, `🛠️`→`🔩`, `🎛️`→`🔘`); moved License badge out of heading; standardized Use Cases icon to `🎯`.

## [1.1.1-dev21] - 2026-06-02 - Proactive Session Reset; Exception Syntax Fixes

### Fixed

- **Proactive & Reactive Session Stability**: Implemented proactive inactivity-based session resetting (100-second threshold) and a reactive auto-retry wrapper in `HuaweiRouter5GAPI` to prevent `100003: No rights (needs login)` errors during SMS actions.
- **`asyncio.to_thread` Mock Compatibility**: Wrapped operations in a zero-argument lambda to prevent `TypeError` when test mocks expect `asyncio.to_thread` to receive only one positional argument.
- **Python Exception Syntax**: Fixed syntax errors on Python 3.12–3.13 by parenthesizing exception tuples (`except (ValueError, TypeError):`) in `helpers.py` and `sensor.py`.
- **Undefined Name `HuaweiRouter5GOptionsFlow`**: Resolved `F821` undefined name lint error in `config_flow.py` by adding `from __future__ import annotations`.
- **Mypy Strict return type**: Resolved mypy strict type check error in `api.py` by casting the `get_sms_list` return value to `dict[str, Any]`.

## [1.1.1-dev20] - 2026-05-25 - `state_class` Removed From 32 Sensors

### Changed

- **Sensors**: Removed `state_class` from 32 sensors to prevent non-critical sensors from generating Long Term Statistics entries. Removed from: `battery`, `current_connection_duration`, `total_connection_time` (system); `lte_uplink_frequency`, `lte_downlink_frequency`, `lte_uplink_bandwidth`, `lte_downlink_bandwidth`, `5g_uplink_frequency`, `5g_downlink_frequency`, `5g_uplink_bandwidth`, `5g_downlink_bandwidth` (signal); `current_download_rate`, `current_upload_rate`, `max_download_rate`, `max_upload_rate`, `current_connection_upload`, `current_connection_download`, `month_download_gb`, `month_upload_gb` (data); `sms_inbox_device`, `sms_outbox_device`, `sms_drafts_device`, `sms_deleted_device`, `sms_capacity_device`, `sms_unread_sim`, `sms_inbox_sim`, `sms_outbox_sim`, `sms_drafts_sim`, `sms_capacity_sim`, `sms_messages_sim`, `sms_new` (SMS).

## [1.1.1-dev19] - 2026-05-25 - Button Handlers Raise `HomeAssistantError`

### Fixed

- **`button.py` `async_press` handlers now raise `HomeAssistantError` on failure**: `HuaweiRebootButton` and `HuaweiClearTrafficButton` previously caught API exceptions, logged them, and returned silently — meaning automations calling `button.press` would succeed with no indication of failure. Both handlers now `raise HomeAssistantError(...) from err`, consistent with the service handler pattern (`send_sms`, `delete_sms`, etc.). `logging` import and `_LOGGER` removed from `button.py` as no longer needed.

### Changed

- **`action-exceptions` IQS compliance PARTIAL→DONE**: Closes the last Silver tier gap for `huawei_router_5g`. Scorecard updated (DONE 46→47, PARTIAL 1→0). `ha_quality_standard.md` v1.9.1 and `next_steps_20260525.md` updated accordingly.
- **`test_button.py` error-path tests updated**: `test_reboot_button_press_error` and `test_clear_traffic_button_press_error` now assert `HomeAssistantError` is raised (with match strings) rather than asserting no exception propagates.

## [1.1.1-dev18] - 2026-05-25 - Six Entities Documented; IQS Matrix Corrected

### Added

- **6 entities documented in all_sensors.md**: Mobile Data (Switch), Preferred Network Mode (Select), SIM Card Status (Binary Sensor), Roaming Status (Binary Sensor), 5G Uplink Frequency (Sensor), 5G Downlink Frequency (Sensor) — all were present in HA output but missing from documentation.

### Changed

- **IQS compliance matrix (v1.9.0)**: Full SCAN=Full pass for `huawei_router_5g`. `action-exceptions` downgraded DONE→PARTIAL (button `async_press` handlers log errors but do not raise `HomeAssistantError`). Scorecard updated (DONE 47→46, PARTIAL 0→1).
- **quality_scale.yaml corrected**: `brands` and `integration-owner` changed from `exempt` to `done` (both are implemented). `async-dependency` and `inject-websession` added as `todo` (were missing from Platinum tier).
- **all_sensors.md entity counts updated**: System 19→22, Signal 46→49 to reflect newly documented entities.

### Fixed

- **SMS key backtick formatting in all_sensors.md**: 4 rows in the SMS Device section had malformed Key fields (`key"` instead of `` `key` ``) causing incorrect markdown rendering.

## [1.1.1-dev17] - 2026-05-24 - README Automation Examples and Icons

### Changed

- **Documentation**: Additional updates to README, more automation examples, more icons. Consistency with ZTE project README.

## [1.1.1-dev16] - 2026-05-24 - Coordinator Coverage to 100%

### Added

- **Coordinator test coverage to 100%**: Added 8 new test functions for uptime latch blocks (system boot time, connection start time, total connection origin — each with first-latch and reboot-detection scenarios) and the timeout-after-max-failures `UpdateFailed` path. coordinator.py coverage raised from 79% to 100%, total project coverage to 99%.

## [1.1.1-dev15] - 2026-05-24 - Uptime Timestamp Drift; GB/GiB Mismatch Fixed

### Fixed

- **Uptime timestamp drift**: Replaced `_get_timestamp()` (naive `now() − uptime` recomputed every poll) with a reboot-detection latch in the coordinator for all three timestamp sensors (`uptime_timestamp`, `current_connection_timestamp`, `total_connection_timestamp`). Boot/start times are now computed once and frozen; the latch re-fires only when the counter drops by more than 30 seconds (genuine reset). Eliminates clock-rate divergence drift and the minute-boundary backward jumps caused by the prior truncation approach. Six latch fields persisted to `entry.data` so timestamps survive HA restarts.
- **`month_download_gb` / `month_upload_gb` GB/GiB mismatch**: Both sensors were dividing bytes by `1024³` (producing GiB) while declaring `native_unit_of_measurement=GIGABYTES` (GB). Corrected divisor to `1,000,000,000` — fixes ~7.4% under-reporting (e.g. actual 133 GB was displayed as 124 GB).
- **`dict` → `dict[str, Any]` mypy `[type-arg]` error** in `coordinator.py` on the `entry_data_updates` local variable.

## [1.1.1-dev14] - 2026-05-24 - Dependabot Bumps

### Changed

- **Dependabot**: Bump PlayFaster/.github shared validation from v1.02 to v1.04
- **Dependabot**: Bump [zizmor](https://github.com/zizmorcore/zizmor-pre-commit) from v1.24.1 to 1.25.2
- **Dependabot**: Bump [python-typing](https://github.com/cdce8p/python-typing-update) from v0.6.0 to 0.8.1

## [1.1.1-dev12] - 2026-05-11 - Code Review; `FETCH_TIMEOUT` Constant Extracted

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

## [1.1.1-dev11] - 2026-05-11 - Final `icons.json` Cleanup

### Changed

- **Final icons.json cleanup**: Removed last inline `icon=` declarations from `select.py` and `button.py` — all entity icons are now served exclusively via `icons.json`. Previous rounds had already migrated `sensor.py`, `binary_sensor.py`, and `switch.py`; this completes the migration for all 6 entity types (sensor, binary_sensor, switch, select, button, number).

### Fixed

- **Test assertions aligned with icons.json approach**: Updated 4 icon assertions in `test_binary_sensor.py` and `test_coverage_ext.py` to expect `sensor.icon is None` — icons are now resolved by the HA frontend from `icons.json`, not via Python `@property icon`. The `HuaweiBestConnectionSensor` no longer declares an inline `icon` property.

## [1.1.1-dev10] - 2026-05-11 - IQS Near-Platinum Recorded

### Changed

- **IQS Platinum**: With icons.json and strict typing the IQS scale is now "near-platinum", with the major caveats that (i) IQS does not apply to custom components and (ii) several standards are N/A but still a very positive indicator.
- **Project Structure Document**: Updated the project structure document to v1.2.4.

## [1.1.1-dev9] - 2026-05-11 - `icons.json` Implemented; Dynamic and Range Icons

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

## [1.1.1-dev8] - 2026-05-11 - Devcontainer Mounts and mypy Path Setup

### Changed

- **Devcontainer mount consolidation**: Moved `.notes` and `.shared` mounts from `devcontainer.json` to `docker-compose.yml` — mounts with absolute paths are unreliable in Docker Compose mode when declared in `devcontainer.json`; compose-file volumes are authoritative for the compose service.
- **HA core mounted for mypy**: Mounted HA core source (`C:/Local/Code/ha_core/core` → `/ha_core`) into the devcontainer via `docker-compose.yml` as read-only, so mypy can resolve HA type stubs without installing the full HA package.
- **`mypy_path` configured**: Added `mypy_path = "/ha_core"` to `[tool.mypy]` in `pyproject.toml` to point mypy at the mounted HA source.
- **mypy scoped to custom component**: Added `[[tool.mypy.overrides]]` for `homeassistant.*` with `ignore_errors = true` and `follow_imports = "silent"` to prevent mypy from checking and reporting errors from HA core files while still using them for type resolution.

### Fixed

- **10 `[type-arg]` strict mypy errors**: Replaced bare `dict` annotations with `dict[str, Any]` across `helpers.py` (3), `sensor.py` (2), `config_flow.py` (2), `__init__.py` (3).

## [1.1.1-dev7] - 2026-05-11 - 33 Strict mypy Errors Resolved

### Changed

- **HA Core stubs mounted in devcontainer**: Mounted HA core files into the devcontainer at `/ha_core` so mypy can resolve HA type stubs. This surfaced 33 previously hidden strict mypy errors that were blocked by missing type information. pro

### Fixed

- **33 Strict Mypy Errors Resolved**: All remaining strict mypy errors fixed across 7 files (`coordinator.py`, `switch.py`, `sensor.py`, `select.py`, `number.py`, `device_tracker.py`, `config_flow.py`). Key fixes: removed 3 redundant `cast()` calls and annotated `last_update_success_time` as `datetime | None` in `coordinator.py`; corrected `EntityCategory` import path to `homeassistant.const` (4 files); used `NumberMode.SLIDER` enum instead of string `"slider"` in `number.py`; corrected `ScannerEntity` import to `device_tracker.config_entry` and added `# type: ignore[misc]` for `@final device_info` override in `device_tracker.py`; replaced `FlowResult` with `ConfigFlowResult` return type, added null-safety asserts, changed parameter type to `Mapping[str, Any]`, and moved `callback` import to `homeassistant.core` in `config_flow.py`.

## [1.1.1-dev6] - 2026-05-11 - 21 mypy Errors Resolved in Two Batches

### Changed

- Added HA core files to Devcon as a mount to try to get the remaining mypy strict errors resolved.

### Fixed

- **11 Mypy Errors Resolved (batch 1)**: Fixed `no-untyped-call` in `api.py` by extracting fetcher list to a typed `list[tuple[str, Callable[[], Any]]]` variable; fixed 3× `no-any-return` in `coordinator.py` via `cast("dict[str, Any]", self.data)`; fixed `no-any-return` in `switch.py` via `bool()` wrapper, `device_tracker.py` via `str(ip)` wrapper, and `binary_sensor.py` via `str(value)` wrapper; fixed `untyped-decorator` in `config_flow.py` via typed `_ha_callback` alias; fixed 3× `no-any-return` in `__init__.py` via `cast` for `entry.runtime_data` and `bool()` for `unload_ok`.
- **10 Mypy Errors Resolved (batch 2)**: Fixed missing type arguments for bare `dict` annotations (`type-arg`) across `helpers.py` (3), `sensor.py` (2), `config_flow.py` (2), `__init__.py` (3) — added `[str, Any]` type parameters to all generic `dict` usages in function signatures.

## [1.1.1-dev5] - 2026-05-10 - `CONFIG_SCHEMA` Added; Duplicate Sensor IDs Removed

### Fixed

- **`CONFIG_SCHEMA` hassfest warning**: Added `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)` to `__init__.py`. Integrations that implement `async_setup` must declare one of `CONFIG_SCHEMA`, `PLATFORM_SCHEMA`, or `PLATFORM_SCHEMA_BASE`; using `config_entry_only_config_schema` is the correct choice for UI-only (config entry) integrations and surfaces a clear error if YAML setup is attempted.
- **Duplicate sensor unique ID errors**: Removed duplicate `month_upload` and `month_upload_gb` entries from `SENSOR_TYPES` in `sensor.py`. Both descriptors were defined twice identically, causing HA to log `"ID already exists — ignoring"` warnings at startup and silently drop those two sensors. Likely introduced via accidental copy-paste during the mypy fix session (dev4).

## [1.1.1-dev4] - 2026-05-10 - 71 mypy Errors Resolved

### Fixed

- **71 Mypy Errors Resolved**: Comprehensive type annotation fixes across 11 source files (`api.py`, `config_flow.py`, `sensor.py`, `switch.py`, `number.py`, `select.py`, `helpers.py`, `coordinator.py`, `device_tracker.py`, `button.py`, `binary_sensor.py`). Key fixes: added missing parameter/return type annotations; narrowed `Client | None` union throughout `api.py` using assertion-driven pattern; corrected `set_net_mode` keyword arguments to match library API (`lteband`/`networkband`/`networkmode`); typed `_refresh_task` as `asyncio.Task[None] | None` to resolve unreachable code in `number.py`; added `or 0` guard for `_safe_int` division in `month_download_gb`/`month_upload_gb` sensors.

## [1.1.1-dev3] - 2026-05-10 - Shared Reusable CI Workflow Created

### Changed — dev tooling

- **Shared Reusable CI Workflow**: Created `PlayFaster/.github` organization repo containing a parameterized reusable workflow (`validate.yaml`, named "Validate (Shared)"). All 8 validation jobs (`hassfest`, `hacs_val`, `py_val`, `test_val`, `file_val`, `codespell`, `zizmor`, `mypy_val`) now live in the shared repo and are called by each integration via a thin caller. Changes to validation logic propagate to all 4 projects on the next CI run without per-project edits.
- **Thin Caller Workflow**: Replaced the 270-line inline `.github/workflows/validate.yaml` with a ~30-line caller that delegates to the shared workflow via `uses: PlayFaster/.github/.github/workflows/validate.yaml@main`. Permissions correctly scoped: `contents: read` at workflow level, `contents: write` and `pull-requests: write` at job level (required by `test_val` for coverage badge and PR comments).
- **Shared Workflow Concurrency**: Reusable workflow uses `${{ github.workflow }}-${{ github.ref }}-${{ github.repository }}` as its concurrency group, preventing cross-repo cancellation when multiple integrations trigger simultaneously.
- **Shared Workflow Dependabot**: Added `dependabot.yml` to `PlayFaster/.github` tracking the `github-actions` ecosystem weekly, keeping SHA pins in the shared workflow current.
- **Pre-commit: Suppress Inapplicable Hooks**: Added `stages: [manual]` to the `no-commit-to-branch` hook — direct commits to `main`/`dev` are the working pattern for this project, so the hook is retained for explicit use but removed from the default commit flow. Added `exclude: \.yamllint$` to the `yamllint` hook to prevent it from linting its own config file (which lacks `---` and uses CRLF).
- **VS Code Tasks**: Added `Zizmor: Fix (Safe Auto-Fix)` task (`zizmor --fix .github/`) for applying zizmor's safe auto-fixes on demand. Added `Pre-commit: Autoupdate Hooks` task (`pre-commit autoupdate`) for updating all hook `rev:` pins to their latest releases. Neither task is wired into `Fix All` or `Validate All`.

## [1.1.1-dev1] - 2026-05-07 - README Top-Level Info Aligned

### Changed

- **Readme**: Changed the top level info in readme to line up with GitHub description.

## [1.1.0] - 2026-05-07 - Release - MAC-Based Unique ID; Code Clean-Up

### Changed

- **Under the Hood**: Significant code clean-up.
- **Unique ID via MAC**: Changed to have the Unique IDs generated from MAC not IP.
- **Automation Examples**: Updated the automation examples.

## [1.1.0-rc2] - 2026-05-07 - Automation Examples Modernized

### Changed

- **Automation Examples**: Updated the automation examples, modern syntax (action vs service).

## [1.1.0-rc1] - 2026-05-07 - Linting, Tests and `quality_scale.yaml` Format

### Changed

- **Linting**: Fixed some linting and formatting issues.
- **Tests**: Added pytests, improved coverage.
- **IQS**: Corrected format of quality_scale.yaml.

## [1.1.0-dev2] - 2026-05-07 - Diagnostics Test Coverage

### Changed

- **Test Coverage**: Improved test coverage including new test file for diagnostics.py.

## [1.1.0-dev1] - 2026-05-07 - `device_id` → `entry_id`; MAC-Based Config Entry ID

### Changed

- **Service Parameter Rename — `device_id` → `entry_id`**: Renamed the router selector field in all 4 SMS service schemas (`send_sms`, `delete_sms`, `delete_all_sms`, `get_sms_list`) to accurately reflect that it accepts a config entry ID, not a HA device registry ID. Updated `services.yaml`, `__init__.py` schemas and `_get_coordinator()`, and `tests/test_init.py`.
- **SMS Event Payload**: Renamed `device_id` → `entry_id` in the `huawei_router_5g_sms_received` event payload for consistency with the service rename.
- **MAC-Based Config Entry Unique ID**: `async_set_unique_id` in `config_flow.py` now uses the router MAC address (with host URL fallback) instead of the host URL, ensuring a stable unique ID that survives IP address changes. MAC is normalized to lowercase colon/dash-stripped format at `_validate_credentials()` return time before being stored in `entry.data`.

### Added

- **Deferred Review Note**: Created `.notes/code_review/code_review_20260507_deferred.md` documenting the M9 (Config Entry → DeviceRegistry) deferral — issue, boot-sequence complexity, and recommended implementation path if revisited.

## [1.0.3-dev3] - 2026-05-07 - Python 3.14 Syntax; Eleven Code-Review Fixes

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

## [1.0.3-dev2] - 2026-05-07 - IQS Gold: Diagnostics, Reauth and Repairs

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

## [1.0.3-dev1] - 2026-05-07 - `quality_scale.yaml` Added

### Added

- **Quality Scale**: Added quality_scale.yaml into project folder to track compliance to Home Assistant Integration Quality Scale (IQS). As a custom component full compliance is not possible but this is a good mechanism to ensure alignment with Home Assistant best practice.

## [1.0.2] - 2026-05-05 - Release - SMS Management, WiFi Sub-Device and Client Counts

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

## [1.0.2-dev4] - 2026-05-05 - WiFi Sub-Device; H165-383 Fixes; Client Counts

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

## [1.0.2-dev3] - 2026-05-04 - SMS Service Suite Expanded; API Concurrency Lock

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

## [1.0.2-dev1] - 2026-05-04 - Test Coverage to 99.8% Across Seven Modules

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

## [1.0.1] - 2026-05-03 - `helpers.py` Coverage to 100%; Project Coverage to 90%

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

## [1.0.1-rc5] - 2026-05-03 - Guard Bands on Eight Frequency Sensors; Translation Gap

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

## [1.0.1-rc4] - 2026-05-03 - Documentation Sync Against 106 Entities

### Changed

- **Project Documentation Sync**: Conducted a full audit of all 106+ entities against the Home Assistant ground truth JSON.
- **Master Manifest Alignment**: Synchronized `docs/huawei_5g_all_sensors.md` with current implementation keys (e.g., legacy `nr_` prefix migrated to `5g_`), standardized names, and corrected categories. Added missing entries for **IPv6 DNS Servers** and the **Network Mode** sensor.
- **README Updates**: Updated `README.md` to reflect the current entity count (106+) and replaced the outdated "5G NR active" binary sensor with the overhauled **"Best Connection"** sensor in the "What You Get" table.
- **Guard Band & Dev Journal Sync**: Aligned `docs/value_min_max.md` and `docs/DEVELOPMENT.md` with finalized sensor names and documented the recent architectural shifts from dev18 to dev22.
- **Unit Source-of-Truth**: Re-confirmed and standardized documentation to use base units (Seconds, Bytes, B/s) as the authoritative source-of-truth, ensuring alignment with device output regardless of Home Assistant UI auto-scaling.

---

## [1.0.1-rc3] - 2026-05-03 - CI Requirements and Coverage Path Fixed

### Fixed

- **CI Validation Failure**: Resolved `ModuleNotFoundError: No module named 'huawei_lte_api'` in GitHub Actions by adding `huawei-lte-api` and `url-normalize` to `.validate/requirements_test.txt`.
- **CI Coverage Path**: Corrected the `--cov` flag in `.github/workflows/validate.yaml` to point to `custom_components/huawei_router_5g` (previously incorrectly pointing to a `zte` directory), ensuring valid coverage reports in CI.

---

## [1.0.1-dev22] - 2026-05-03 - IPv6 DNS and 5G Frequency Sensors; Unit Selector Fixed

### Added

- **Primary/Secondary IPv6 DNS sensors**: New diagnostic sensors (`primary_ipv6_dns`, `secondary_ipv6_dns`) reading `PrimaryIPv6Dns`/`SecondaryIPv6Dns` from the `monitoring_status` API response. Mirrors the existing IPv4 DNS pair and fills a gap identified against the HA core Huawei LTE project.
- **5G Uplink/Downlink Frequency sensors**: Added `5g_uplink_frequency` and `5g_downlink_frequency` diagnostic sensors reading the `ulfrequency`/`dlfrequency` API fields (raw kHz, scaled ÷1000 via `format_khz_to_mhz`). Renamed from the generic `uplink_frequency`/`downlink_frequency` introduced in dev18 to make the 5G scope explicit and consistent with the naming convention used throughout this project.

### Fixed

- **"Unit of Measurement" selector absent on all 8 frequency/bandwidth sensors**: The `device_class=FREQUENCY` HA entity property pages showed no unit selector, preventing users from switching between MHz/kHz/GHz display units. Root cause: all 8 sensors had `state_class=SensorStateClass.MEASUREMENT` set, routing them through HA's long-term statistics path, which does not surface the unit selector for the `FREQUENCY` device class. Fixed by removing `state_class` from all 8 sensors (`lte_uplink_frequency`, `lte_downlink_frequency`, `lte_uplink_bandwidth`, `lte_downlink_bandwidth`, `5g_uplink_frequency`, `5g_downlink_frequency`, `5g_uplink_bandwidth`, `5g_downlink_bandwidth`), matching the pattern used by the HA core Huawei LTE project where frequency sensors carry only `device_class` and the unit selector is surfaced via HA's device-class auto-conversion path.
- **Preferred Network Mode sensor icon invalid**: `preferred_network_mode` was using `mdi:settings-transfer`, which does not resolve in current Material Design Icons. Replaced with `mdi:tune`.

### Changed

- **`format_bw_mhz` renamed to `format_khz_to_mhz`**: Helper function renamed to accurately reflect its sole purpose — scaling kHz carrier-frequency fields to MHz (÷1000). The original name was inherited from an earlier implementation where it was also (incorrectly) used for bandwidth fields; after that was corrected in dev18 the name became misleading.

---

## [1.0.1-dev21] - 2026-05-03 - Test Warnings and `SIM117` Resolved

### Fixed

- **Test Suite Reliability**: Resolved `RuntimeWarning` for unawaited coroutines in setup tests by explicitly closing or awaiting background initialization tasks in `test_init.py`.
- **Linting Compliance**: Resolved all manual `ruff` errors (`SIM117`) in `tests/test_api.py` by combining nested `with` statements for `patch` and `pytest.raises`.

### Changed

- **Test Coverage Expansion**: Verified 220/220 tests passing with zero warnings and 100% clean linting in the Docker devcontainer environment.

---

## [1.0.1-dev19] - 2026-05-03 - Best Connection Sensor Overhauled; 11 Entities Enabled

### Added

- **Best Connection logic document**: Created `docs/best_connection_logic.md` as a detailed reference for the 3-stage quality gate algorithm, threshold rationale, idle-stability analysis, and H165-383-specific API field behavior.

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

## [1.0.1-dev18] - 2026-05-03 - LTE Frequency and Bandwidth Fields Corrected

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

## [1.0.1-dev16] - 2026-05-03 - Complex Signal Metric Parsing

### Added

- **Complex Signal Metric Support**: Implemented robust parsing for technical diagnostic sensors that frequently return multi-valued strings (e.g., multi-carrier MCS or per-channel Transmit Power).
  - New `_parse_complex_int` and `_parse_complex_float` helpers preserve the full raw string when complexity (colons or spaces) is detected, preventing "Unknown" states.
  - Impacted entities: LTE/5G Downlink MCS, Uplink MCS, EARFCN, and Transmit Power.

### Changed

- **Guard Band Optimization**: Removed `min_limit` and `max_limit` constraints from 8 technical diagnostic sensors to ensure multi-carrier strings are not accidentally filtered or "partial-parsed" by the numeric validation engine.

### Fixed

- **LTE Carrier Aggregation Logic**: Corrected the `lte_ca` sensor to properly return `None` (Unavailable) when data is missing from the API response, rather than defaulting to "disabled".

---

## [1.0.1-dev15] - 2026-05-03 - Dynamic SMS Box Selection; SMS Entities Renamed

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

## [1.0.1-dev14] - 2026-05-03 - `runtime_data` Migration; Domain-Level Service Registration

### Added

- **Explicit Reconnection Logging**: Coordinator now logs an `INFO` message when communication is restored after one or more failed fetches, improving visibility into network recovery.
- **Modern Data Management**: Migrated integration to use `entry.runtime_data` for coordinator storage, replacing the legacy `hass.data[DOMAIN]` pattern.
- **Domain-Level Service Registration**: Refactored `send_sms` service registration to `async_setup` (domain-level) rather than `async_setup_entry` (instance-level) to ensure singleton registration across multiple router entries.

### Changed

- **Parallel Update Optimization**: Added `PARALLEL_UPDATES = 0` to all platform files to indicate update coordination is handled by the coordinator.
- **Service Error Handling**: Updated `send_sms` to raise `HomeAssistantError` with descriptive feedback on failure, allowing automations to respond to errors.
- **Test Infrastructure Refactor**: Updated entire test suite to support `runtime_data` and verified 186/186 passing states.

---

## [1.0.1-dev13] - 2026-05-02 - Full Translation Coverage; Entity Naming Refactor

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

## [1.0.1-dev12] - 2026-05-02 - Signal and SMS Entity Category Refinement

### Changed

- **Signal UI Refinement**:
  - Renamed **LTE CQI 0** -> **LTE CQI** and promoted it to the main **Sensor** category (from Diagnostic) with `state_class: measurement` to match 5G CQI visibility.
  - Promoted **Signal Bars** to the main **Sensor** category, ensuring the most human-readable signal metric is visible by default.
- **SMS Entity Hygiene**:
  - Moved 12 granular SMS storage metrics (Unread/Inbox/Capacity for Device and SIM) to the **Diagnostic** category to reduce entity fatigue.
  - Kept primary actionable metrics (**SMS Unread**, **SMS New**, **SMS Total**, **Last SMS**) in the main entity list.

---

## [1.0.1-dev10] - 2026-05-02 - Windows Test-Suite Resilience

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

## [1.0.1-dev9] - 2026-05-02 - Long-Term Statistics; Human-Readable Network Mode

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

## [1.0.1-dev8] - 2026-05-02 - Immediate Session Retry; Icons for 35 Entities

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

## [1.0.1-dev7] - 2026-05-02 - Typed Session Exceptions; Fast-Fail on Critical Data

### Changed

- **Robust Session Recovery**: Refactored `api.py` to use typed exceptions from the `huawei-lte-api` library (`ResponseErrorLoginRequiredException`, `ResponseErrorException`), enabling more reliable detection of session timeouts.
- **Error Code Detection**: Implemented explicit monitoring for router error codes `100002` (Not logged in), `125002` (Session timeout), and `125003` (Token error) during data fetch cycles to trigger immediate reauthentication.

### Fixed

- **Silent Fetch Failures**: Resolved "Critical data missing from fetch" errors by implementing a "Fast-Fail" mechanism for the `device_information` endpoint. Transient API errors for critical data are now properly surfaced as warnings and abort the fetch safely, rather than being swallowed as debug noise.
- **Reliability Test Coverage**: Expanded the reliability test suite to verify the new typed exception handling and critical key failure paths.

---

## [1.0.1-dev6] - 2026-05-02 - Shared `build_device_info`; Auth and PII Fixes

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

## [1.0.1-dev5] - 2026-05-02 - Reliability Test Suite

### Added

- **Reliability Test Suite**: Implemented `tests/test_reliability_ext.py` to specifically target and verify the complex error handling and resilience logic.
  - Added tests for mid-fetch session expiration and automatic reauthentication.
  - Added tests for the **Critical Data Guard** to ensure partial responses are correctly rejected.
  - Verified `_LOGGER.exception()` tracebacks in critical failure paths.

### Changed

- **Codebase Maintenance**: Performed project-wide linting and formatting (Ruff, Prettier) to ensure 100% adherence to "PlayFaster" idiomatic standards.

---

## [1.0.1-dev4] - 2026-05-02 - Logging Strategy; Critical Data Guard

### Added

- **Logging Strategy Refinement**: Implemented high-fidelity diagnostics across all platforms.
  - Switched to `_LOGGER.exception()` in all critical failure paths to provide full tracebacks in Home Assistant logs.
  - Downgraded "Session Expired" mid-fetch warnings to `DEBUG` level to reduce log noise during normal reauthentication cycles.
  - Verified strict credential sanitization in all debug log calls.

### Fixed

- **Partial Entity Failure**: Resolved issue where SMS, System, and Client entities would become 'Unknown' due to silent session timeouts mid-fetch.
  - Implemented mid-fetch error detection for session timeouts (125002/125003) in `api.py`.
  - Added a **Critical Data Guard** in the coordinator to reject fetches missing essential keys like `device_information`, preventing "partial success" objects from clearing sensors.
  - Integrated authentication failures into the 3-strike resilience logic to hold last known good data during transient session drops.

## [1.0.1-dev3] - 2026-05-02 - Guard Bands on 80 Sensors; SMS Parsing and Events

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

## [1.0.1-dev2] - 2026-05-02 - Entity Engine: 80 Sensors and Six Platforms

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

## [1.0.1-dev1] - 2026-05-02 - Core Architecture: Coordinator, API and Config Flow

### Added

- **Core Architecture**: Implemented `HuaweiRouter5GDataUpdateCoordinator` with "3-strike" failure counter to mask transient network glitches.
- **API Integration**: Created `HuaweiRouterAPI` async wrapper for the `huawei-lte-api` library.
- **Flat Identity Pattern**: Implemented hardware metadata persistence (Model, MAC, Version) in `ConfigEntry.data` during initial setup.
- **Non-Blocking Startup**: Migrated initialization logic to `entry.async_create_background_task` for 0ms impact on Home Assistant boot time.
- **Config Flow**: Developed a robust config flow with credential validation and model discovery.

---

## [1.0.0] - 2026-05-02 - Baseline Project Structure

### Initial Release

- Baseline project structure following "PlayFaster" v1.2 architectural standards.

---

### Format

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entry structure — headers, titles, category headings and the split between this file and its counterpart — follows `.shared/dev_std/changelog_format.md`.
