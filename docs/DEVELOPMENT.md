# Development & Architecture Notes: Huawei Router 5G Monitor

## 1. Project Objective

To develop a high-performance Home Assistant custom component for monitoring and managing Huawei LTE/5G Routers. The integration leverages the `huawei-lte-api` library to interface with the router's XML-based Web API, extracting signal metrics (RSRP, RSRQ, SINR), data usage, SMS management, and connected client information into the Home Assistant ecosystem.

## 2. Architecture & File Structure

The integration follows the standard Home Assistant Custom Component pattern, optimized for asynchronous performance and declarative entity management.

### Core Files (`custom_components/huawei_router_5g/`)

- **`api.py`**: Async wrapper for `huawei-lte-api`. Handles authentication (including session/token management), XML parsing, and safe execution of blocking library calls in the HA executor.
- **`coordinator.py`**: Specialized `DataUpdateCoordinator` implementation. Centralizes polling logic to ensure efficient data retrieval across multiple API endpoints (Signal, Traffic, SMS, LAN Clients). Includes the "3-strike" glitch protection rule.
- **`__init__.py`**: Manages the integration lifecycle (setup/unload). Implements background initialization to ensure a 0ms impact on Home Assistant startup time.
- **`sensor.py`**: Defines 100+ entities using declarative `value_fn` callbacks. Handles complex unit conversions (e.g., Duration to ISO Timestamp) and applies guard bands.
- **`binary_sensor.py`**: Maps boolean states such as connection status, LTE carrier aggregation, and unread SMS presence.
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
- **Modern Data Management**: Utilizing `ConfigEntry.runtime_data` to store the `DataUpdateCoordinator`. This removes the need for managing a complex `hass.data[DOMAIN]` dictionary and provides native Home Assistant support for type-safe data access.
- **Parallel Update Coordination**: Explicitly setting `PARALLEL_UPDATES = 0` in all platform files. This informs Home Assistant that the coordinator handles update orchestration internally, eliminating redundant update overhead.
- **Domain-Level Service Architecture**: Registering integration services (like `send_sms`) in `async_setup` rather than `async_setup_entry`. This ensures services are registered exactly once for the entire domain, regardless of how many router instances are configured.
- **Actionable Service Feedback**: Ensuring all services raise `HomeAssistantError` with descriptive messages upon failure. This allows Home Assistant automations and scripts to detect execution errors and provides users with meaningful feedback in the UI.
- **Seamless Session Recovery**: Implementing immediate retry logic in the `DataUpdateCoordinator` to handle fixed router session TTLs, ensuring continuous data flow and clean logs during re-authentication events.
- **Recovery Visibility**: Implementing explicit reconnection logging. The coordinator logs an `INFO` message only when communication is restored after a failure, providing a clear "log once on loss, log once on recovery" signal.
- **Long-Term Statistics Alignment**: Consistent use of `state_class` (`MEASUREMENT`, `TOTAL`, `TOTAL_INCREASING`) across volume, duration, and signal metrics to ensure high-quality historical data and compatibility with Home Assistant's Energy and Statistics dashboards.
- **Abstracted Select Mappings**: Utilizing internal mapping dictionaries in `select.py` to decouple technical API codes from user-friendly UI labels, ensuring a professional configuration experience without exposing protocol-level strings.
- **Entity Category Optimization**: Strategically utilizing `EntityCategory.DIAGNOSTIC` for granular infrastructure metrics (e.g., secondary frequency bands, per-bank SMS capacity) while keeping actionable or highly readable metrics (e.g., Signal Bars, SMS Unread) in the primary entity list to balance depth with UI cleanliness.
- **Multi-Stage Quality Gate Pattern**: The `best_connection` binary sensor demonstrates deriving a stable composite quality indicator from multiple metrics rather than a single API field. A 3-stage AND gate (NR band assignment → LTE anchor health → 5G leg health) using OR-of-thresholds within each stage prevents false negatives when individual metrics are borderline. This pattern is robust to the H165-383's `network_type` reporting `"LTE"` even in active NSA 5G mode, and to `sc_band` returning null. Documented in `docs/best_connection_logic.md`.

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
- **Numeric vs. Multi-Carrier Ambiguity (v1.0.1-dev16)**: Standard numeric parsers like `parse_signal_value` are designed to extract the _first_ number found. This is dangerous for multi-carrier strings (e.g., `DL:500 UL:18500`) as it causes "partial-parsing" where only the first value is captured and the rest is discarded.
  - _Fix_: Implemented complexity detection in `helpers.py`. If a string contains colons or multiple segments, the parser bypasses numeric conversion entirely and returns the full raw string, preserving technical fidelity.
- **Background Task Mocking**: Standard tests can fail if background tasks aren't properly awaited.
  - _Fix_: Ensured all tests use `hass.async_block_till_done()` after setup to catch initialization tasks.
- **SMS API Parameter Constraints (v1.0.1-dev15)**: Modern 5G firmware is highly sensitive to the XML payload sent to `get_sms_list`. Including optional parameters like `sort_type` or `unread_preferred` can cause the router to reject the request with a "System Error" (110001) or return empty results.
  - _Fix_: Simplified the API call to the absolute minimum required parameters (`page` and `box_type`) to maximize compatibility.
- **Transient Notification Counters**: The `NewMsg` API key does not represent a persistent state (like "Unread"); it is a transient notification counter that resets as soon as a client fetches the message list.
  - _Fix_: Renamed the sensor to **"In Process"** and moved it to **Diagnostic** to prevent user confusion during polling cycles.
- **Library Enum Requirements**: Recent versions of `huawei-lte-api` expect `Enum` objects (like `BoxTypeEnum`) rather than literal integers for certain parameters. Passing an integer can trigger attribute errors (`'int' object has no attribute 'value'`) within the library's internal logic.
  - _Fix_: Explicitly import and utilize the library's Enum definitions for all box selection logic.
- **Invalid API Key Mismatch**: Technical storage metrics (e.g., `LocalInbox`, `SimInbox`) are often used in documentation but do not exist in the actual `sms_count` response for many models.
  - _Fix_: Corrected mappings to sum physical counters: `Inbox = Read + Unread`, `Outbox = Outbox + Sent`.
- **LTE Frequency Scaling Error (v1.0.1-dev18)**: The `lteulfreq` and `ltedlfreq` API fields are in **10ths of MHz** (e.g., raw 19700 = 1970 MHz), not 100ths. The initial `/100` divisor produced values 10× too small (e.g., 197 MHz instead of 1970 MHz).
  - _Fix_: Changed the `format_freq_mhz` helper divisor from `/100` to `/10`.
- **LTE Bandwidth Field Misidentification (v1.0.1-dev18)**: The `ulfrequency` and `dlfrequency` API fields are **carrier frequency fields in kHz** (e.g., 1970000 kHz = 1970 MHz), not bandwidth fields. Mapping them to bandwidth sensors produced 1970/2160 MHz instead of the correct 20 MHz. The correct bandwidth fields are `ulbandwidth` and `dlbandwidth`, which return the channel width directly in MHz (no scaling required), matching the pattern already used by the 5G bandwidth sensors (`nrulbandwidth`/`nrdlbandwidth`). The repurposed kHz fields are now correctly used by the new LTE Uplink/Downlink Frequency (Secondary) sensors.
  - _Fix_: Changed bandwidth sensors to read `ulbandwidth`/`dlbandwidth` with no scaling. Added secondary frequency sensors reading `ulfrequency`/`dlfrequency` via `format_khz_to_mhz` (÷1000).
- **LTE CA and 5G NR Band API Fields Absent (v1.0.1-dev18)**: On the H165-383 router, the dedicated `lte_ca` and `sc_band` API fields return null, causing both entities to permanently report "unknown". The required data is present but embedded in the composite `band` string (e.g., `"20MHz@500(B1) + 15MHz@1875(B3) + 10MHz@152690(N28)"`).
  - _Fix_: Replaced both with band-string parsers. `5g_nr_band` (sensor) extracts the `(NXX)` label from the last carrier segment. `lte_ca` was also converted from a string-valued sensor ("enabled"/"disabled") to a proper **binary sensor** (ON/OFF) — the underlying value is inherently boolean (`"+" in band`), and `binary_sensor` is the correct HA platform for this state.
- **Unit Selector Absence (v1.0.1-dev22)**: The eight `FREQUENCY` entities do not have the unit selector in home assistant (stuck on kHz or MHz). Data (MB/GB) and Duration (sec/hr/day) entities do. The frequency entities in the core component also have the unit selector.
  - _This is NOT fixed_: Be aware that investigating  this will results in incorrect analysis that the root cause is `diagnostic` vs `sensor` or the presence of `state_class` . This is wrong. Further investigation required, low priority.
- **IPv6 DNS Gaps (v1.0.1-dev22)**: While IPv4 DNS was tracked, IPv6 DNS was missing, leading to incomplete network visibility on modern dual-stack connections.
  - _Fix_: Added `primary_ipv6_dns` and `secondary_ipv6_dns` sensors reading from the `monitoring_status` endpoint.

## 6. Environment Constraints

- **Async Wrapper**: While `huawei-lte-api` is primarily synchronous, this integration wraps all calls in `hass.async_add_executor_job` or uses the library's async capabilities where available to ensure the HA event loop is never blocked.
- **XML/SOAP API**: The integration handles the heavy lifting of XML parsing and session token management required by Huawei's API.
- **Windows Testing**: The Home Assistant test suite (via `pytest-asyncio`) uses the `ProactorEventLoop` by default on Windows, which utilizes internal sockets that can be blocked by `pytest-socket`.
  - _Standard_: Use `WindowsSelectorEventLoopPolicy` and monkeypatch `pytest-socket.disable_socket` in `conftest.py` to ensure local tests pass without disabling security guards entirely.

## 7. Technical Debt & Future Work

- **Signal Guard Band Refinement**: Continue to tune min/max limits as more users provide data from different signal environments (e.g., extreme fringe areas).
- **Client Metadata**: Expand the "Clients" sub-device to include more detailed information like hostnames if supported by the router firmware.
- **Multi-SIM Support**: Investigate support for routers with dual SIM slots.
