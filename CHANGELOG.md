# Changelog

## [1.0.1] - 2026-05-03 - Github Release

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
