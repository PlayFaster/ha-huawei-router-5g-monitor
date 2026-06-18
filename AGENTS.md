# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## What This Integration Does

A Home Assistant custom component (HACS integration) for monitoring Huawei LTE/5G routers. It wraps the `huawei-lte-api` library to provide signal metrics (RSRP, RSRQ, SINR), data usage tracking, SMS management, connected client device tracking, and polling controls. The component domain is `huawei_router_5g`.

The integration provides 112+ entities grouped into six logical sub-devices: **System**, **Signal**, **Data**, **SMS**, **WiFi**, and **Clients**. It also exposes four SMS service actions (`send_sms`, `delete_sms`, `delete_all_sms`, `get_sms_list`).

## Commands

All commands assume the devcontainer environment (Python 3.14, `/workspaces/ha-huawei-router-5g-monitor`). The `.venv` in the repo root contains test dependencies.

### Tests

```bash
# Run all tests
PYTHONPATH=. pytest tests/

# Run a single test file
PYTHONPATH=. pytest tests/test_sensor.py

# Run a single test by name
PYTHONPATH=. pytest tests/test_sensor.py::test_sensor_state

# Run with coverage report
PYTHONPATH=. pytest --cov --cov-report=term-missing tests/
```

### Linting & Formatting

```bash
# Lint (check only)
ruff check .

# Lint with auto-fix
ruff check --fix .

# Format (check only)
ruff format --check .

# Format (auto-fix)
ruff format .

# Type check
mypy custom_components/

# Strict type check
mypy custom_components/ --strict

# Spell check
codespell .

# All pre-commit hooks on all files
pre-commit run --all-files
```

### Validation (requires devcontainer/Docker)

```bash
# YAML lint
yamllint -c .validate/.yamllint <file>

# HA hassfest (runs via Docker)
# Use the VS Code task: "HA: Hassfest Validation"

# Prettier formatting for JSON/YAML/Markdown
prettier --config .validate/.prettierrc.json --check .
prettier --config .validate/.prettierrc.json --write .
```

VS Code tasks in `.vscode/tasks.json` wrap all of these. The "Validate All" task runs the full suite sequentially. The "Fix All" task runs all auto-repair tools.

### Install Test Dependencies

```bash
pip install -r .validate/requirements_test.txt
```

### Running tools from a Windows host

These commands only work **inside** the devcontainer — HA imports `fcntl`, so `pytest` (and the other tools) cannot run on a Windows host directly. From Windows, run everything through `docker exec` against the running container. See [`.shared/prompts/devcon_run_gen.md`](.shared/prompts/devcon_run_gen.md) for the full mini-skill. Quick reference:

```bash
# Confirm the container is up first
docker ps --filter "name=<CONTAINER_NAME>" --format "{{.Names}}"

# Run a tool inside the container (-w sets the in-container working dir)
docker exec -w /workspaces/<PROJECT_DIR> <CONTAINER_NAME> bash -c "PYTHONPATH=. pytest tests/"
docker exec -w /workspaces/<PROJECT_DIR> <CONTAINER_NAME> bash -c "ruff check ."
```

Do not install or run these tools on the host as a workaround.

## Architecture

### Core Data Flow

```
api.py (HuaweiRouter5GAPI)
  → wraps huawei-lte-api (synchronous) using asyncio.to_thread / hass.async_add_executor_job
  → asyncio.Lock serializes all router calls (prevents "Busy" / 110001 errors)

coordinator.py (HuaweiRouter5GDataUpdateCoordinator)
  → calls api.get_data() on each poll interval
  → 3-strike resilience: holds last-known-good data for up to 3 consecutive failures
  → immediate retry on HuaweiAuthError (session TTL expiry masking)
  → fires huawei_router_5g_sms_received events; uses timestamp+hash deduplication
  → stored in entry.runtime_data (ConfigEntry.runtime_data pattern, no hass.data dict)

platform files (sensor.py, binary_sensor.py, switch.py, etc.)
  → all extend CoordinatorEntity
  → all set PARALLEL_UPDATES = 0 (coordinator handles scheduling)
  → use build_device_info() from helpers.py to target one of the six sub-devices
```

### Declarative Entity Pattern

All sensors are defined as `EntityDescription` dataclasses with a `value_fn: Callable[[dict], Any]` callback. No business logic lives in the entity class itself — adding a new sensor is a single-line entry in the descriptions list. Guard bands (e.g., RSRP range -140 to -30) are applied inside `value_fn` before the value is returned.

### Sub-Device Organization

Entities are assigned to one of six sub-devices via `build_device_info(coordinator, group)` in `helpers.py`. All non-system sub-devices use `via_device` pointing to the System sub-device. Device identifiers use the MAC address as the stable prefix (`{mac}_{group}`), falling back to `host_{url}_{group}`.

### Startup Pattern (Zero-Blocking)

`async_setup_entry` in `__init__.py`:
1. Creates `HuaweiRouter5GAPI` and `HuaweiRouter5GDataUpdateCoordinator`
2. Pre-registers the System and Clients sub-devices in the device registry
3. Forwards all platforms immediately (entities appear in HA at startup using metadata from `entry.data`)
4. Spawns a background task via `entry.async_create_background_task` for the initial login + data fetch

Hardware identity (model, MAC, version) is loaded from `entry.data` at startup so entities display correctly even if the router is offline at boot.

### Service Registration

SMS services (`send_sms`, `delete_sms`, `delete_all_sms`, `get_sms_list`) are registered in `async_setup` (domain-level), not `async_setup_entry`. This ensures they are registered exactly once regardless of how many router instances exist. Service handlers are explicit `async def` wrappers — using lambdas with async functions causes unawaited coroutine bugs for services with responses.

### Config Entry Data vs. Options

- **`entry.data`**: Immutable-ish identity — MAC address (normalized to lowercase, no colons), model, sw_version, hw_version. Used as the unique_id base.
- **`entry.options`**: Runtime-mutable settings — host URL, username, password, scan_interval, stop_polling flag.

The unique_id for the config entry is the normalized MAC (`001122aabbcc` format). All entity `unique_id`s derive from this: `{entry.unique_id}_{sensor_key}`.

### WiFi Radio Discovery

Rather than hardcoded radio indices, `switch.py` / `binary_sensor.py` fetch all SSIDs via `wlan_multi_basic_settings` and locate radios by their `ID` path fragment (e.g., `"Radio.1"` for 2.4GHz, `"Radio.2"` for 5GHz). This handles the firmware "Index 5 bug" where Huawei routers shift radio indices between firmware versions.

### Key Helpers (`helpers.py`)

- `parse_signal_value(val)`: Strips unit suffixes (dBm, dB, MHz, etc.) before numeric conversion
- `_parse_complex_int` / `_parse_complex_float`: Returns raw string for multi-carrier values like `"DL:500 UL:18500"` to avoid partial-parse errors
- `parse_sms_list(data)`: Handles varied router response structures (list vs. dict, metadata offset)
- `build_device_info(coordinator, group)`: Builds `DeviceInfo` targeting the correct sub-device
- `find_ssid_by_path` / `is_ssid_on`: Dynamic WiFi radio discovery by path fragment

## Key Patterns & Conventions

### Exception Tuple Syntax — Settled Decision

Always use `except (A, B):` with explicit parentheses for multi-exception catches. Never use the bare-tuple form `except A, B:`.

- **Do not flag or change this** — it has been researched and decided.
- `except A, B:` silently catches only `A` on Python 3.12–3.13 (what HA runs on in production), making it a correctness issue, not just style.
- `except (A, B):` is correct and unambiguous across Python 2.6 through 3.14+.
- Full background: `shared/SharedNotes/info/py_exception_tuple_syntax/issue_summary.md`

### Operator Precedence with `or 0`

When using `or 0` as a None-guard before a numeric comparison: use `(val or 0) > threshold`, not `val or 0 > threshold` (which evaluates as `val or (0 > threshold)` = `val or False`).

### Icon Architecture

All entity icons are centralized in `custom_components/huawei_router_5g/icons.json` using HA's icon translation engine. Do not add hardcoded `icon="..."` arguments to `EntityDescription` objects. Use `default`, `state`, and `range` mappings in the JSON file instead.

### Frequency Field Scaling

- `lteulfreq` / `ltedlfreq` fields: divide by **10** to get MHz (raw 19700 → 1970.0 MHz)
- `ulfrequency` / `dlfrequency` fields: divide by **1000** to get MHz (kHz → MHz), handled by `format_khz_to_mhz`
- `ulbandwidth` / `dlbandwidth` fields: already in MHz, no scaling needed

### Windows Test Environment

`conftest.py` applies two patches for Windows compatibility:
- `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` — avoids ProactorEventLoop pipe issues with pytest
- Monkeypatches `pytest_socket.disable_socket` to a no-op — avoids `SocketBlockedError` from internal asyncio pipes

### Entity Category Usage

- `EntityCategory.DIAGNOSTIC`: granular infrastructure metrics (secondary bands, per-bank SMS capacity, raw durations)
- No category (primary list): actionable or highly readable metrics (signal bars, SMS unread count, data rates)

## Development Environment

The project uses a VS Code devcontainer (`.devcontainer/`) running a Home Assistant instance for live testing. The devcontainer's `.devconfig/` folder contains a pre-configured HA instance that loads the integration automatically.

### MCP Access (ha-mcp-dev)

When the devcontainer is running, the `ha-mcp-dev` MCP server automatically connects to the HA instance inside it (`http://localhost:8123`). Use it to verify integration changes without leaving the editor.

**After any modification, follow the post-modification process** — see [`.shared/prompts/post_mod_process.md`](.shared/prompts/post_mod_process.md). Specify a `SCOPE` when invoking it:

| SCOPE | What runs |
| :------- | :-------- |
| `None` | Changes only — no validation |
| `Basic` | HA restart + error check + lint/format fixes |
| `Full` | Basic + mypy (standard) + pytest (fix failing tests only) |
| `Complete` | Full + pre-commit --all-files + mypy --strict |

Additional tools useful during development:
- `ha_get_state` / `ha_search_entities` — verify entity states and attributes after a reload
- `ha_call_service` — trigger service calls (e.g. `homeassistant.update_entity`) to exercise platform callbacks directly

Test dependencies are in `.validate/requirements_test.txt`. The primary test library is `pytest-homeassistant-custom-component`, which provides HA fixtures (`hass`, `MockConfigEntry`, etc.).

Validation reports are written to the `.reports/` directory (gitignored outputs from lint/test runs).

### Skill Prompts

Three reusable prompts are available via `.shared/prompts/` for working within this devcontainer:

| Prompt | Purpose |
| :-- | :-- |
| `devcon_run_gen.md` | Run any single command inside the container |
| `devcon_run_and_fix.md` | Full test + lint cycle: pytest, ruff, prettier, validate — with auto-fix |
| `devcon_coverage.md` | Coverage report, target file selection, and new test writing |

Container identity values (`CONTAINER_NAME`, `PROJECT_DIR`) are in `.devcontainer/.env`.

## Known Open Issue

The eight `FREQUENCY` entities do not show the unit selector in the HA UI (stuck on kHz or MHz). This is a known gap — investigation has ruled out `diagnostic` vs `sensor` category and presence of `state_class` as root causes. Further investigation is needed; treat as low priority.
