# Changelog

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
