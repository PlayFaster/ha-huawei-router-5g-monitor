# Development & Architecture Notes: Huawei Router 5G Monitor

## 1. Project Objective

To develop a high-performance Home Assistant custom component for monitoring and managing Huawei LTE/5G Routers. The integration leverages the `huawei-lte-api` library to interface with the router's XML-based Web API, extracting signal metrics (RSRP, RSRQ, SINR), data usage, SMS management, and connected client information into the Home Assistant ecosystem.

## 2. Architecture & File Structure

The integration follows the standard Home Assistant Custom Component pattern, optimized for asynchronous performance and declarative entity management.

### Core Files (`custom_components/huawei_router_5g/`)

- **`api.py`**: Async wrapper for `huawei-lte-api`. Handles authentication (including session/token management), XML parsing, and safe execution of blocking library calls in the HA executor.
- **`coordinator.py`**: Specialized `DataUpdateCoordinator` implementation. Centralizes polling logic to ensure efficient data retrieval across multiple API endpoints (Signal, Traffic, SMS, LAN Clients). Includes the "3-strike" glitch protection rule.
- **`__init__.py`**: Manages the integration lifecycle (setup/unload). Implements background initialization to ensure a 0ms impact on Home Assistant startup time.
- **`sensor.py`**: Defines 80+ entities using declarative `value_fn` callbacks. Handles complex unit conversions (e.g., Duration to ISO Timestamp) and applies guard bands.
- **`binary_sensor.py`**: Maps boolean states such as connection status and unread SMS presence.
- **`switch.py`**: Implements "Pause Polling" to stop API calls without disabling the integration.
- **`button.py`**: Triggers stateless actions such as Reboot and Clear SMS.
- **`number.py`**: Provides UI control over the refresh interval with persistent storage in `ConfigEntry` options.
- **`config_flow.py`**: Manages initial setup and reconfiguration, implementing the "Flat Identity" pattern by persisting hardware metadata (Model, MAC, Version) at boot.
- **`helpers.py`**: Contains robust parsers for SMS lists and technical metric sanitization (e.g., stripping 'dBm', 'MHz' suffixes).

## 3. Historical Architectural Shifts

The project was built from the ground up using the latest "PlayFaster" standards, incorporating lessons learned from the ZTE and TP-Link monitor projects.

### Transition from `huawei_lte` Legacy Patterns

- **Initial State**: Reference projects often used the legacy `huawei_lte` core integration pattern, which can be complex and sometimes blocks the event loop.
- **Change**: Developed a flat, declarative architecture using the `DataUpdateCoordinator` and `EntityDescription` patterns.
- **Result**: A faster, more stable integration that is easier to maintain and extend with new sensors.

### Declarative Entity Engine (v1.0.0)

- **Change**: Moved all business logic out of the Entity class and into metadata descriptions.
- **Benefit**: Reduced thousands of lines of code into a maintainable list of descriptions. Adding a new sensor now requires only a single line of metadata.

### Sub-Device Granularity (v1.0.0)

- **Standard**: Grouped entities into five functional sub-devices: **System, Signal, Data, SMS, and Clients**.
- **Benefit**: Prevents "entity fatigue" in the HA UI and provides a cleaner organization in the Device Registry.

## 4. Success Patterns

- **`DataUpdateCoordinator`**: Essential for consolidating multiple API calls (Signal, Traffic, SMS, Clients) into a single orchestrated update cycle.
- **Flat Identity Strategy**: By storing Model, Version, and MAC in `entry.data` and loading them at `__init__`, the integration provides stable metadata to the UI instantly at boot, even if the hardware is offline.
- **Declarative Guard Bands**: Validating sensor values against realistic boundaries (e.g., -140 to -30 for RSRP) before committing them to the state machine ensures data integrity in long-term statistics.
- **Dual Duration/Timestamp Sensors**: Providing both raw durations (disabled by default) and calculated timestamps (enabled by default) for metrics like Uptime and Connection Time, catering to both automation and UI needs.
- **High-Fidelity Logging**: Utilizing `_LOGGER.exception()` for all critical failure paths ensures full tracebacks are available in Home Assistant logs for remote debugging, while downgrading transient session timeouts to `DEBUG` keeps logs clean for end-users.
- **Architectural Consolidation**: Extracting highly duplicated properties like `device_info` into centralized helpers (e.g., `build_device_info`) to enforce DRY principles across 7+ platform files.
- **Seamless Session Recovery**: Implementing immediate retry logic in the `DataUpdateCoordinator` to handle fixed router session TTLs, ensuring continuous data flow and clean logs during re-authentication events.

## 5. Technical Pitfalls & Fixes

- **Auth Error Handling**: Relying on string matching (e.g., `"password" in str(err)`) to detect login failures is brittle and breaks if library messages change.
  - _Fix_: Catch specific, typed exceptions from the underlying library (`LoginErrorPasswordWrongException`, etc.) to trigger auth failures.
- **SMS List Parsing**: Different Huawei models return SMS lists in varying formats (some as lists, some as single dictionaries).
  - _Fix_: Implemented a robust parser in `helpers.py` that handles metadata offsets and varied structure.
- **Partial Entity Failure (v1.0.1-dev4)**: Transient session timeouts mid-fetch could cause some sensors (like SMS or System Info) to become 'Unknown' while others (like Data) stayed active.
  - _Fix_: Implemented mid-fetch error detection for session codes 125002/125003 in `api.py` and a **Critical Data Guard** in the coordinator to reject partial data objects.
- **Predictable Session Expiration (v1.0.1-dev8)**: Router sessions often have a fixed TTL (e.g., 6 minutes), leading to periodic auth failures during polling.
  - _Fix_: Implemented an immediate retry mechanism in the coordinator. If a `HuaweiAuthError` is caught, the fetch is retried once immediately, masking the recovery from the user and ensuring data continuity.
- **Numeric Sanitization**: The Huawei API often returns strings with technical suffixes (e.g., "120dBm", "20MHz").
  - _Fix_: Implemented `parse_signal_value` helper in `helpers.py` to strip these suffixes before numeric conversion across all platforms.
- **MAC Address Stability**: Some routers report MAC addresses with or without colons.
  - _Fix_: Normalized all MAC identifiers to a consistent lowercase, colon-less format for use in `unique_id`.
- **Background Task Mocking**: Standard tests can fail if background tasks aren't properly awaited.
  - _Fix_: Ensured all tests use `hass.async_block_till_done()` after setup to catch initialization tasks.

## 6. Environment Constraints

- **Async Wrapper**: While `huawei-lte-api` is primarily synchronous, this integration wraps all calls in `hass.async_add_executor_job` or uses the library's async capabilities where available to ensure the HA event loop is never blocked.
- **XML/SOAP API**: The integration handles the heavy lifting of XML parsing and session token management required by Huawei's API.

## 7. Technical Debt & Future Work

- **Signal Guard Band Refinement**: Continue to tune min/max limits as more users provide data from different signal environments (e.g., extreme fringe areas).
- **Client Metadata**: Expand the "Clients" sub-device to include more detailed information like hostnames if supported by the router firmware.
- **Multi-SIM Support**: Investigate support for routers with dual SIM slots.
