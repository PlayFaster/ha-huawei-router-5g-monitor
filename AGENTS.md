# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

> **Read the shared conventions first:** [`.shared/dev_std/agent_conventions.md`](.shared/dev_std/agent_conventions.md) — commands (tests, lint, mypy, validation), the Windows-host `docker exec` workflow, devcontainer access, HAB/MCP for interrogating the running HA instance, the post-modification SCOPE table, code conventions, and the markdown/Python rules. That file is the single source of truth for everything shared across the integration projects; this file covers only what is specific to **ha-huawei-router-5g-monitor**.
>
> **[!] Note:** If you edit files inside directory junctions (`.notes/` or `.shared/`), do not run container validation on them. Validate them on the Windows host from the `shared/` folder.

---

> [!CAUTION]
>
> **Never run `git checkout`, `git restore`, `git reset`, `git stash` or `git clean`. Ask first, every time — no exceptions, whoever's changes you think they are.** Reading git (`status`, `diff`, `log`, `show`) is always fine. Full rule and the incident behind it: [`agent_conventions.md`](.shared/dev_std/agent_conventions.md).

## What This Integration Does

A Home Assistant custom component (HACS integration) for monitoring Huawei LTE/5G routers. It wraps the `huawei-lte-api` library to provide signal metrics (RSRP, RSRQ, SINR), data usage tracking, SMS management, connected client device tracking, and polling controls. The component domain is `huawei_router_5g`.

Entities are grouped into six logical sub-devices: **System**, **Signal**, **Data**, **SMS**, **WiFi**, and **Clients**. It also exposes SMS service actions.

> **Entity and service inventory lives in [`docs/all_sensors.md`](docs/all_sensors.md)** — it is authoritative and kept current against live HA by `sensor_review.md`. This file deliberately carries no entity counts or service descriptions.

## Commands

Standard for all integration projects — see [shared conventions §2](.shared/dev_std/agent_conventions.md). Nothing about this project's commands differs.

## Architecture

### Core Data Flow

```text
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
  → PARALLEL_UPDATES set per write path: 1 on button/switch/select
    (they command the router), 0 elsewhere — see "Parallel Updates" below
  → use build_device_info() from helpers.py to target one of the six sub-devices
```

### Declarative Entity Pattern

All sensors are defined as `EntityDescription` dataclasses with a `value_fn: Callable[[dict], Any]` callback. No business logic lives in the entity class itself — adding a new sensor is a single-line entry in the descriptions list. Guard bands (e.g., RSRP range -140 to -30) are applied inside `value_fn` before the value is returned.

### Sub-Device Organization

Entities are assigned to one of six sub-devices via `build_device_info(coordinator, group)` in `helpers.py`. Every non-system sub-device links to the System sub-device as its parent, but **not via a hard-coded key** — the link goes through `_compat.via_device_link()`, which emits `via_device_id` on HA 2026.8+ and the legacy `via_device` tuple on 2026.7 and earlier. The tuple is deprecated in 2026.8 and **removed in 2027.8**; the shim keeps the integration floor-free.

**Never assert `info["via_device"]` in a test** — it is green only on the HA version that happens to take that branch. Use `assert_links_to_parent()` / `assert_is_root()` from `tests/conftest.py`, which assert the link's presence and exclusivity rather than which key carries it.

Device identifiers use the MAC address as the stable prefix (`{mac}_{group}`), falling back to `host_{url}_{group}`.

### Parallel Updates

`PARALLEL_UPDATES` follows **the write path**, not the platform's name:

| Platform | Value | Why |
| :-- | --: | :-- |
| `button`, `switch`, `select` | **1** | Issue commands with a real-world effect. `api.py` serializes every call behind an `asyncio.Lock` because concurrent calls answer "Busy" / `110001`; the lock is the real safety mechanism and `1` states the same intent at the platform boundary. |
| `number` | **0** | Deliberately unlike `zte_router_5g`, which sets `1` on every writable platform. The only number entity writes `ConfigEntry.options`, which HA owns — no session to tear down, no command to duplicate. |
| `sensor`, `binary_sensor`, `device_tracker` | **0** | Read-only, coordinator-driven; nothing to serialize. |

The table is pinned in `EXPECTED_PARALLEL_UPDATES` in `tests/test_entity_hygiene.py`, with a companion test that fails if a new platform appears the table does not cover. Change the constant and the test together.

### Startup Pattern (Zero-Blocking)

`async_setup_entry` in `__init__.py`:

1. Creates `HuaweiRouter5GAPI` and `HuaweiRouter5GDataUpdateCoordinator`
2. Pre-registers the System and Clients sub-devices in the device registry
3. Forwards all platforms immediately (entities appear in HA at startup using metadata from `entry.data`)
4. Spawns a background task via `entry.async_create_background_task` for the initial login + data fetch

Hardware identity (model, MAC, version) is loaded from `entry.data` at startup so entities display correctly even if the router is offline at boot.

### Service Registration

SMS services are registered in `async_setup` (domain-level), not `async_setup_entry`. This ensures they are registered exactly once regardless of how many router instances exist. Service handlers are explicit `async def` wrappers — using lambdas with async functions causes unawaited coroutine bugs for services with responses.

### Config Entry Data vs. Options

- **`entry.data`**: Immutable-ish identity — MAC address (normalized to lowercase, no colons), model, sw_version, hw_version. Used as the unique_id base.
- **`entry.options`**: Runtime-mutable settings — host URL, username, password, scan_interval, stop_polling flag.

The unique*id for the config entry is the normalized MAC (`001122aabbcc` format). All entity `unique_id`s derive from this: `{entry.unique_id}*{sensor_key}`.

### WiFi Radio Discovery

Rather than hardcoded radio indices, `switch.py` / `binary_sensor.py` fetch all SSIDs via `wlan_multi_basic_settings` and locate radios by their `ID` path fragment (e.g., `"Radio.1"` for 2.4GHz, `"Radio.2"` for 5GHz). This handles the firmware "Index 5 bug" where Huawei routers shift radio indices between firmware versions.

### Key Helpers (`helpers.py`)

- `parse_signal_value(val)`: Strips unit suffixes (dBm, dB, MHz, etc.) before numeric conversion
- `_parse_complex_int` / `_parse_complex_float`: Returns raw string for multi-carrier values like `"DL:500 UL:18500"` to avoid partial-parse errors
- `parse_sms_list(data)`: Handles varied router response structures (list vs. dict, metadata offset)
- `build_device_info(coordinator, group)`: Builds `DeviceInfo` targeting the correct sub-device
- `find_ssid_by_path` / `is_ssid_on`: Dynamic WiFi radio discovery by path fragment

## Key Patterns & Conventions

Shared conventions (ruff/mypy strictness, `PARALLEL_UPDATES`, `translation_key`, the centralized `icons.json` architecture, exception tuple syntax, `or 0` precedence, markdown emoji rules) are in [shared conventions §4–5](.shared/dev_std/agent_conventions.md). Project-specific additions:

### Frequency Field Scaling

- `lteulfreq` / `ltedlfreq` fields: divide by **10** to get MHz (raw 19700 → 1970.0 MHz)
- `ulfrequency` / `dlfrequency` fields: divide by **1000** to get MHz (kHz → MHz), handled by `format_khz_to_mhz`
- `ulbandwidth` / `dlbandwidth` fields: already in MHz, no scaling needed

### Windows Test Environment (unused)

`tests/conftest.py` carries two deliberate Windows-compatibility patches (a `WindowsSelectorEventLoopPolicy` switch and a `pytest_socket.disable_socket` no-op), both guarded by `sys.platform == "win32"`. They were added on purpose but are **not exercised** — tests run inside the Linux devcontainer via `docker exec`. Unique to this project; leave them alone, and don't treat them as a pattern to replicate.

### Entity Category Usage

- `EntityCategory.DIAGNOSTIC`: granular infrastructure metrics (secondary bands, per-bank SMS capacity, raw durations)
- No category (primary list): actionable or highly readable metrics (signal bars, SMS unread count, data rates)

## Remaining Work (Future — Separate Session)

**Forward work lives in [docs/ROADMAP.md](docs/ROADMAP.md)** — refer there for planned items (such as the frequency unit selector open issue below), revisit parameters, and declined design decisions. Keep it there rather than here, so there is one place to look.

---

## Development Environment

Standard for all integration projects — see [shared conventions §3](.shared/dev_std/agent_conventions.md). Nothing about this project's environment differs.

## Known Open Issue

The eight `FREQUENCY` entities do not show the unit selector in the HA UI (stuck on kHz or MHz). This is a known gap — investigation has ruled out `diagnostic` vs `sensor` category and presence of `state_class` as root causes. Further investigation is needed; treat as low priority.
