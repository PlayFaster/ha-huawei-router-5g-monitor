# Changelog

## [1.1.2] - 2026-07-03 - Release

### Added

- **Refresh Now Button**: New System button that triggers an immediate data refresh, complementing the existing Pause Polling switch and configurable polling interval.

### Changed

- **Display Units & Precision**: 23 sensors now display expected units and decimal places (data sizes in GB, data rates in Mbit/s, durations in hours, rounded signal/frequency values) while native values used for long-term statistics stay unchanged.
- **Polling Toggle Future Ready**: Turning off "Enable polling for changes" in the entry's system options now reliably stops scheduled polling and will satisfy the upcoming HA requirement (implicit `ContextVar` detection is being removed in HA 2026.8).
- **Disabled-by-Default Sensors**: User Capacity, Month Download (GB), and Month Upload (GB) are now disabled by default for new installs.

### Fixed

- **Password No Longer Exposed on Edit Screens**: The password field is no longer pre-filled or revealable on the Reconfigure/Options/Reauth screens — leave it blank to keep the current password, or enter a new value to change it.
- **Host Field Normalization**: A scheme (`http://`) or trailing slash entered in the Host field is now stripped before storage, preventing a malformed device link (e.g. `http://http://192.168.8.1`).

## [1.1.1] - 2026-06-07 - Release

### Summary

- v1.1.1 is clean-up and bug-fixes, no new features.
- Fixed a timestamp bug and removed several sensors from long term statistics.

### Fixed

- **Integration startup failure on HA reboot**: Eliminated a transient import race in the `url_normalize` → `idna` → `uts46data` dependency chain. On cold HA startup, the integration could fail with `ImportError: cannot import name 'uts46data'` and would not recover without a full HA restart. Replaced with a stdlib-only URL normalisation helper.
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

## [1.1.0] - 2026-05-07 - Release

### Changed

- **Under the Hood**: Significant code clean-up.
- **Unique ID via MAC**: Changed to have the Unique IDs generated from MAC not IP.
- **Automation Examples**: Updated the automation examples.

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

## [1.0.1] - 2026-05-03 - GitHub Release

### Added

- **Best Connection Sensor**: A new primary sensor (replacing "5G NR Active") using a 3-stage quality gate to accurately report 5G connectivity status.
- **Display Last SMS**: Added SMS "Last Msg" text sensor.
- **send_sms Service**: New service to send SMS messages with support for multiple recipients and content.

### Changed

- **LTE Carrier Aggregation**: Converted from a string sensor to a more appropriate Binary Sensor.
- **Test Coverage**: Internal test coverage at 90%.

### Fixed

- **Unknown States**: Resolved "Unknown" status for LTE Carrier Aggregation and 5G NR Band on modern firmware by deriving values from composite band strings.

### Initial Commit - 2026-05-01
