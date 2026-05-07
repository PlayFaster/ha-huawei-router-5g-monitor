# Changelog

## [1.1.0] - 2026-05-07 - Pre-release

### Changed

- **Under the Hood**: Significant code clean-up.
- **Unique ID via MAC**: Changed to have the Unique IDz generated from MAC not IP.

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
