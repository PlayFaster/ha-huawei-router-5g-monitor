# Changelog

## [1.2.2] - 2026-08-26 - Release: Reauthentication Repair Flow and Default SMS Storage Monitoring

Routine maintenance update refining Repair notifications with no changes to daily operation; safe to skip until you are next updating integrations.

### Summary

- **Reauthentication Repair Flow**: Clicking the Fix button on an authentication failure Repair now directly opens the reauthentication dialog so you can update your router credentials immediately.
- **SMS Storage Full Sensor Enabled by Default**: The SMS Storage Full binary sensor is now enabled by default on new setups, making inbox capacity issues immediately visible for dashboards and alerts.

### Fixed

- **Authentication Failure Repair Fix Flow**: Added an interactive fix flow to the `auth_failed` Repair card. Submitting the fix now launches the integration's reauthentication dialog directly, resolving an issue where the Fix button dismissed the notification card without updating the stored credentials.

### Changed

- **SMS Storage Full Entity Default**: Enabled `binary_sensor.*_sms_storage_full` by default on new setups so full router SMS storage states are automatically tracked without requiring manual entity activation.
- **Repairs Reference Documentation**: Updated the Repairs documentation, separating persistent Repairs (`auth_failed`, `conn_error`) from transient errors.

### Under the hood

- Expanded test coverage across repair flows and validation schemas to maintain 100% line and branch coverage.

## [1.2.1] - 2026-08-24 - Release: Connection Loss Repair Triggering

### Summary

- **Connection Loss Repairs**: The "router is not responding" Repair now triggers reliably across all failure modes, including refused connections when the router is powered off or relocated.

### Fixed

- **Connection Error Repair on Refused Connections**: The `conn_error` Repair ("Huawei router is not responding") now triggers on refused socket connections (e.g. router powered off, cable unplugged, or changed IP address) after the strike budget is spent, rather than only on timeouts.

## [1.2.0] - 2026-08-20 - Release: New Telemetry Entities, Data Projections, Control Switches, and Health Monitoring

### Highlights

- **WiFi Switch**: Turn your main router WiFi on and off, plus Guest WiFi.
- **Reconnect Button**: Quick reconnect now available, in addition to existing full reboot.
- **Data Use Projection**: Predict and track monthly data usage for your billing cycle.
- **Longer SMS**: Send longer SMS messages (up to 612 characters), same as Router web GUI.

### Summary

- **Controls & Actions**: Adds a Master Wi-Fi switch, a Reconnect button, and a device tracker cleanup action.
- **38 New Entities & End-of-Cycle Forecast**: Adds broad diagnostic, system, and signal sensors across eight new router endpoints, including a Projected Usage forecast sensor.
- **Dynamic Network Mode Selection**: Dynamically discovers supported cellular network modes from the router (including 5G Only) while preventing accidental band resets.
- **Resilience & Health**: Introduces an Integration Health diagnostic sensor with 5-state severity and firmware API change detection, automated follow-up refreshes after reboots, and bounded write execution.
- **Connection Recovery & Timeouts**: Recovers automatically from transport timeouts by resetting wedged sessions, clearing stale sockets, and enforcing internal fetch deadlines to preserve partial poll data.
- **Entity Identity & Guidance**: Migrates device tracker unique IDs to entry-scoped identifiers, standardizes `about` attribute guidance notes across all entities, and upgrades the underlying client library to `huawei-lte-api` 2.0.1.

### Added

- **New Router & Signal Entities**: Added 38 entities across eight router endpoints, including identity sensors, System metrics, VoLTE and binary sensors, Signal diagnostics, and a **Router Diagnostics** connection status sensor.
- **Projected Data Usage**: Added a data usage forecast sensor that calculates projected monthly bandwidth consumption with credibility and confidence attributes.
- **Master Wi-Fi Switch**: Added a master Wi-Fi radio control switch that safely toggles the 2.4 GHz and 5 GHz hardware radios.
- **Reconnect Button**: Added a button to re-establish cellular data sessions on demand.
- **Entity Cleanup Action**: Added a `cleanup_unused_entities` action (with dry-run preview by default) to remove stale device tracker entities left behind by transient guest devices.
- **Integration Health Diagnostic Sensor**: Added a diagnostic problem sensor monitoring endpoint availability, standardized 5-state severity (`ok`, `degraded`, `warning`, `error`, `unknown`), and unexpected firmware-driven changes.
- **Action Icons & Context**: Added full icon translations for all registered actions across automation and script editors.

### Changed

- **Dynamic Network Mode Discovery**: The Preferred Network Mode select entity now queries the router for its exact supported modes (e.g. `Auto`, `5G Only`, `4G Only`) rather than offering static, unsupported presets.
- **Entity Details Guidance**: Reviewed and polished all 160 entity `about` attribute descriptions across Home Assistant entity dialogs to provide clear, standardized operational guidance and threshold interpretations.
- **Underlying Client Library**: Updated the underlying `huawei-lte-api` library to 2.0.1, ensuring compatibility with modern SCRAM authentication and future firmware releases.
- **Follow-Up Refresh Automation**: Pressing Reboot or Reconnect now automatically schedules an asynchronous follow-up poll when the router reconnects, including while background polling is paused.
- **Bounded Writes & Fetch Deadlines**: Write actions and concurrency locks are strictly bounded to prevent background stalls, and polling loops enforce internal deadlines to preserve collected endpoint data during slow responses.
- **HACS Minimum Version Requirement**: Enforced the minimum Home Assistant version requirement (2025.1.0) in HACS package metadata.

### Fixed

- **5G Network Mode Mapping & Band Safety**: Added full mapping for 5G-Only mode (`08`), handled transient radio re-registration responses, moved confirmation read-backs outside locks, and ensured mode changes preserve active cellular band selections.
- **Connection Recovery on Timeout**: Automatically resets and closes underlying HTTP sessions on coordinator timeouts, clearing stale sockets and rebuilding fresh client sessions without requiring a Home Assistant restart.
- **Device Tracker Multi-Router Conflicts**: Migrated device tracker unique IDs to be scoped per configuration entry, preventing entity collisions and missing client devices on setups with multiple Huawei routers.
- **Session Logout & Traffic Reset Calls**: Corrected library method bindings for session logout and traffic counter clearing, ensuring active sessions are properly closed on reload.
- **SMS Parsing Resilience**: Hardened inbox parsing to handle empty message indices without dropping remaining inbox items.
- **Repair Issue Titles**: Added vendor-prefixed translation strings for authentication failure and connection loss repairs in the Home Assistant Repairs dashboard.

## [1.1.2] - 2026-07-03 - Release: Manual Refresh Controls, Display Precision Units, and Configuration Hardening

### Added

- **Refresh Now Button**: New System button that triggers an immediate data refresh, complementing the existing Pause Polling switch and configurable polling interval.

### Changed

- **Display Units & Precision**: 23 sensors now display configured units and precision (GB, Mbit/s, hours, rounded signal/frequency values) without altering native values used for long-term statistics.
- **Polling Toggle Future Ready**: Turning off "Enable polling for changes" in the entry's system options now reliably stops scheduled polling and will satisfy the upcoming HA requirement (implicit `ContextVar` detection is being removed in HA 2026.8).
- **Disabled-by-Default Sensors**: User Capacity, Month Download (GB), and Month Upload (GB) are now disabled by default for new installs.

### Fixed

- **Edit screen credential security**: Configured the password field on configuration screens to be masked and blank by default, preventing the stored password from being pre-filled or exposed.
- **Host URL sanitization**: Host input is now automatically sanitized to strip redundant prefixes or trailing slashes, preventing malformed device links.

## [1.1.1] - 2026-06-07 - Release: Startup Timing Resilience, Session Lifecycle, and Uptime Timestamp Drift

### Summary

- Maintenance and stability release addressing uptime timestamp drift, session handling, and long-term statistics tracking.

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
- **Long-term statistics cleanup**: Removed `state_class` from 32 sensors (frequency, bandwidth, SMS counts, connection durations, and data rates) that report instantaneous values not suited for long-term statistics.

## [1.1.0] - 2026-05-07 - Release: MAC-Based Unique Identifier Migration and Code Hygiene

### Changed

- **Under the Hood**: Significant internal code clean-up.
- **MAC-Based Unique IDs**: Migrated entity unique IDs from IP address to MAC address to ensure stable entity identity across network reconfigurations.
- **Automation Examples**: Updated and modernized example automations.

## [1.0.2] - 2026-05-05 - Release: SMS Management Actions, WiFi Sub-Device Hierarchy, and Client Tracking

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

## [1.0.1] - 2026-05-03 - Release: Connection Quality Telemetry and SMS Messaging Actions

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
  - [\[1.2.2\] - 2026-08-26 - Release: Reauthentication Repair Flow and Default SMS Storage Monitoring](#122---2026-08-26---release-reauthentication-repair-flow-and-default-sms-storage-monitoring)
  - [\[1.2.1\] - 2026-08-24 - Release: Connection Loss Repair Triggering](#121---2026-08-24---release-connection-loss-repair-triggering)
  - [\[1.2.0\] - 2026-08-20 - Release: New Telemetry Entities, Data Projections, Control Switches, and Health Monitoring](#120---2026-08-20---release-new-telemetry-entities-data-projections-control-switches-and-health-monitoring)
  - [\[1.1.2\] - 2026-07-03 - Release: Manual Refresh Controls, Display Precision Units, and Configuration Hardening](#112---2026-07-03---release-manual-refresh-controls-display-precision-units-and-configuration-hardening)
  - [\[1.1.1\] - 2026-06-07 - Release: Startup Timing Resilience, Session Lifecycle, and Uptime Timestamp Drift](#111---2026-06-07---release-startup-timing-resilience-session-lifecycle-and-uptime-timestamp-drift)
  - [\[1.1.0\] - 2026-05-07 - Release: MAC-Based Unique Identifier Migration and Code Hygiene](#110---2026-05-07---release-mac-based-unique-identifier-migration-and-code-hygiene)
  - [\[1.0.2\] - 2026-05-05 - Release: SMS Management Actions, WiFi Sub-Device Hierarchy, and Client Tracking](#102---2026-05-05---release-sms-management-actions-wifi-sub-device-hierarchy-and-client-tracking)
  - [\[1.0.1\] - 2026-05-03 - Release: Connection Quality Telemetry and SMS Messaging Actions](#101---2026-05-03---release-connection-quality-telemetry-and-sms-messaging-actions)

---
