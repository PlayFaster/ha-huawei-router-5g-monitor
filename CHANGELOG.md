# Changelog

## [1.0.1-dev3] - 2026-05-02

### Added
- **Declarative Guard Bands**: Implemented comprehensive min/max limits for all numeric sensors (Signal, Data, SMS, Diagnostics) to protect long-term statistics.
- **Robust SMS Parsing**: Enhanced parser to handle varied router response formats and metadata offsets.
- **Internal Documentation**: Rewrote development notes, project structure, and entity manifest to reflect the new Huawei-specific architecture.

### Fixed
- Fixed `AttributeError` in `last_sms` sensor during initialization.
- Normalized MAC address formatting for stable entity unique IDs.

## [1.0.1-dev2] - 2026-05-02

## [1.0.0] - 2026-05-02

### Initial Release
