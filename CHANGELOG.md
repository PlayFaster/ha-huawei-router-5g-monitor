# Changelog

## [1.2.0] - 2026-08-16

### Summary

- **38 New Entities & End-of-Cycle Forecast**: Adds broad diagnostic, system, and signal sensors across eight new router endpoints, including a Projected Usage forecast sensor.
- **Controls & Actions**: Adds a Master Wi-Fi switch, a Reconnect button, and a device tracker cleanup action.
- **Dynamic Network Mode Selection**: Dynamically discovers supported cellular network modes from the router (including 5G Only) while preventing accidental band resets.
- **Resilience & Health**: Introduces an Integration Health diagnostic sensor with contract drift detection, automated follow-up refreshes after reboots, and per-request transport timeouts.
- **Entity Identity & Guidance**: Migrates device tracker unique IDs to entry-scoped identifiers, standardizes `about` attribute guidance notes across all entities, and upgrades the underlying client library to `huawei-lte-api` 2.0.1.

### Added

- **New Router & Signal Entities**: Added 38 entities across eight new router endpoints, including six identity sensors, nine System sensors, four System binary sensors (including VoLTE), eight Signal entities, a data-plan block, a Line State sensor, and a **Router Diagnostics** sensor reporting the router's internal connection status.
- **Projected Data Usage**: Added a data usage forecast sensor that calculates projected monthly bandwidth consumption with credibility and confidence attributes.
- **Master Wi-Fi Switch**: Added a master Wi-Fi radio control switch that safely toggles the 2.4 GHz and 5 GHz hardware radios.
- **Reconnect Button**: Added a button to re-establish cellular data sessions on demand.
- **Entity Cleanup Action**: Added a `cleanup_unused_entities` action (with dry-run preview by default) to remove stale device tracker entities left behind by transient guest devices.
- **Integration Health Diagnostic Sensor**: Added a system health sensor that monitors endpoint availability, catches total connection outages, and alerts on firmware contract drift.
- **Action Icons & Context**: Added full icon translations for all registered actions across automation and script editors.

### Changed

- **Dynamic Network Mode Discovery**: The Preferred Network Mode select entity now queries the router for its exact supported modes (e.g. `Auto`, `5G Only`, `4G Only`) rather than offering static, unsupported presets.
- **Entity Details Guidance**: Reviewed and polished all 160 entity `about` attribute descriptions across Home Assistant entity dialogs to provide clear, standardized operational guidance and threshold interpretations.
- **Underlying Client Library**: Updated the underlying `huawei-lte-api` library to 2.0.1, ensuring compatibility with modern SCRAM authentication and future firmware releases.
- **Follow-Up Refresh Automation**: Pressing Reboot or Reconnect now automatically schedules an asynchronous follow-up poll when the router reconnects, including while background polling is paused.
- **Per-Request Timeouts**: Isolated slow or unresponsive router endpoints so a single stalled query does not fail the entire coordinator update cycle.
- **HACS Minimum Version Requirement**: Enforced the minimum Home Assistant version requirement (2025.1.0) in HACS package metadata.

### Fixed

- **5G Network Mode Mapping & Band Safety**: Added full mapping for 5G-Only mode (`08`), resolved transient `-1` confirmation errors during radio re-registration, and ensured mode changes preserve existing cellular band selections.
- **Device Tracker Multi-Router Conflicts**: Migrated device tracker unique IDs to be scoped per configuration entry, preventing entity collisions and missing client devices on setups with multiple Huawei routers.
- **Session Logout & Traffic Reset Calls**: Corrected library method bindings for session logout and traffic counter clearing, ensuring active sessions are properly closed on reload.
- **SMS Parsing Resilience**: Hardened inbox parsing to handle empty message indices without dropping remaining inbox items.
- **Repair Issue Titles**: Added vendor-prefixed translation strings for authentication failure and connection loss repairs in the Home Assistant Repairs dashboard.

_Full technical detail for every change in this release is in [`docs/changelog_local.md`](docs/changelog_local.md)._

## [1.1.2] - 2026-07-03 - Release - Refresh Now Button; Display Units; Config-Flow Hardening

### Added

- **Refresh Now Button**: New System button that triggers an immediate data refresh, complementing the existing Pause Polling switch and configurable polling interval.

### Changed

- **Display Units & Precision**: 23 sensors now display expected units and decimal places (data sizes in GB, data rates in Mbit/s, durations in hours, rounded signal/frequency values) while native values used for long-term statistics stay unchanged.
- **Polling Toggle Future Ready**: Turning off "Enable polling for changes" in the entry's system options now reliably stops scheduled polling and will satisfy the upcoming HA requirement (implicit `ContextVar` detection is being removed in HA 2026.8).
- **Disabled-by-Default Sensors**: User Capacity, Month Download (GB), and Month Upload (GB) are now disabled by default for new installs.

### Fixed

- **Edit screen credential security**: Configured the password field on configuration screens to be masked and blank by default, preventing the stored password from being pre-filled or exposed.
- **Host URL sanitization**: Host input is now automatically sanitized to strip redundant prefixes or trailing slashes, preventing malformed device links.

## [1.1.1] - 2026-06-07 - Release - Startup Race, Session and Timestamp Fixes

### Summary

- v1.1.1 is clean-up and bug-fixes, no new features.
- Fixed a timestamp bug and removed several sensors from long term statistics.

### Fixed

- **Startup dependency resilience**: Replaced the external URL normalization dependency with a standard-library helper to prevent transient import race failures during cold Home Assistant starts.
- **Device tracker import paths**: Aligned `ScannerEntity` imports with canonical Home Assistant components paths to prevent deprecation warnings and ensure compatibility with future releases.
- **SMS session handling**: Implemented proactive session resets and automatic retries on expired logins to prevent authorization errors during sporadic SMS service calls.
- **Uptime tracking stability**: Latched the boot time calculation to prevent timestamp drift from independently ticking clocks, updating it only when a physical reboot drops the counter.
- **Schema configuration compliance**: Added the required `CONFIG_SCHEMA` declaration to satisfy integration setup validation checks.
- **Button error propagation**: Configured the Reboot and Clear Traffic buttons to propagate API failures to the UI and automations rather than swallowing errors silently.
- **Device tracker stability**: Replaced broad exception blocks with target-specific guards to prevent potential tracker platform initialization crashes.
- **Diagnostics query safety**: Added fallback guards to diagnostics generation to prevent potential crashes if queried before the initial integration coordinator update completes.

### Changed

- **Dynamic entity icons**: All entity icons migrated to HA's `icons.json` translation system. Signal bars (1–3), battery (10–100%), and SMS unread sensors now display context-aware icons that change automatically based on sensor value or state.
- **Long-term statistics cleanup**: Removed `state_class` from 32 sensors that were incorrectly generating Long Term Statistics entries — specifically frequency/bandwidth sensors, SMS count sensors, connection duration sensors, and data rate sensors. These sensors report instantaneous or cumulative values that are not suitable for HA's statistics pipeline.

## [1.1.0] - 2026-05-07 - Release - MAC-Based Unique ID; Code Clean-Up

### Changed

- **Under the Hood**: Significant code clean-up.
- **Unique ID via MAC**: Changed to have the Unique IDs generated from MAC not IP.
- **Automation Examples**: Updated the automation examples.

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

- **WiFi status reporting**: Resolved edge cases where the 2.4GHz and 5GHz WiFi status sensors could report out-of-sync states.
- **Guest WiFi control toggling**: Improved communication reliability when toggling the Guest WiFi Network switch.

## [1.0.1] - 2026-05-03 - GitHub Release - Best Connection Sensor; `send_sms` Action

### Added

- **Best Connection Sensor**: A new primary sensor (replacing "5G NR Active") using a 3-stage quality gate to accurately report 5G connectivity status.
- **Display Last SMS**: Added SMS "Last Msg" text sensor.
- **send_sms Service**: New service to send SMS messages with support for multiple recipients and content.

### Changed

- **LTE Carrier Aggregation**: Converted from a string sensor to a more appropriate Binary Sensor.
- **Test Coverage**: Internal test coverage at 90%.

### Fixed

- **Band attributes mapping**: Improved band extraction logic to derive LTE Carrier Aggregation and 5G NR Band values from composite band strings on newer firmware.

### Initial Commit - 2026-05-01

---

### Format

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entry structure — headers, titles, category headings and the split between this file and its counterpart — follows `.shared/dev_std/changelog_format.md`.

---

- [Changelog](#changelog)
  - [\[1.1.2\] - 2026-07-03 - Release - Refresh Now Button; Display Units; Config-Flow Hardening](#112---2026-07-03---release---refresh-now-button-display-units-config-flow-hardening)
  - [\[1.1.1\] - 2026-06-07 - Release - Startup Race, Session and Timestamp Fixes](#111---2026-06-07---release---startup-race-session-and-timestamp-fixes)
  - [\[1.1.0\] - 2026-05-07 - Release - MAC-Based Unique ID; Code Clean-Up](#110---2026-05-07---release---mac-based-unique-id-code-clean-up)
  - [\[1.0.2\] - 2026-05-05 - Release - SMS Management, WiFi Sub-Device and Client Counts](#102---2026-05-05---release---sms-management-wifi-sub-device-and-client-counts)
  - [\[1.0.1\] - 2026-05-03 - GitHub Release - Best Connection Sensor; `send_sms` Action](#101---2026-05-03---github-release---best-connection-sensor-send_sms-action)

---
