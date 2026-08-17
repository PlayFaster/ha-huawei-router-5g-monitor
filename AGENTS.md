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

All sensors are defined as `EntityDescription` dataclasses with a `value_fn: Callable[[dict], Any]` callback. No business logic lives in the entity class itself — adding a new sensor is a single-line entry in the descriptions list. Guard bands (e.g. RSRP range -150 to -30 dBm) are applied inside `value_fn` before the value is returned. The bands are listed per key in [`docs/value_min_max.md`](docs/value_min_max.md), which a test reconciles against the code in both directions.

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

## Tests that will stop you

These are **coverage sweeps**, not mechanism tests. Each asserts that every member of a set satisfies a property, so **it fails when the set grows** — which means the failure usually looks unrelated to whatever you just changed, and the reflex is to suppress it.

> [!IMPORTANT]
>
> **If one of these fails, it has found something. Do not reach for the allow-list first.** Every allow-list below is currently **empty**, and each entry is meant to be a reviewable act with a written reason. A sweep that has been quietly widened is worth less than no sweep at all.

| Test | Guards | Why it exists |
| :-- | :-- | :-- |
| `test_no_sensor_uses_the_total_state_class` | `ALLOWED_TOTAL_STATE_CLASS` (empty) | Four resetting counters shipped as `SensorStateClass.TOTAL` with no `last_reset`, so every daily and billing-month rollover was recorded as a large negative delta and walked long-term statistics backwards. Nothing failed at runtime. |
| `test_total_state_class_sweep_is_not_vacuous` | the sweep above | The sweep passes trivially if `SENSOR_TYPES` stops carrying state classes. Pins that it inspected ≥20 sensors and that the four corrected counters are still `TOTAL_INCREASING`. |
| `test_allowed_total_state_class_has_no_dead_entries` | the allow-list | An exemption must not outlive its sensor, where it would silently pre-approve a future sensor reusing the key. |
| `test_every_entity_publishing_attributes_declares_unrecorded` | Section 14 | The component had **zero** `_unrecorded_attributes`, so every attribute of every entity hit the recorder on every state change — including each tracked client's SSID, once per client per poll. Discovers entity classes by inspection, so a new platform cannot slip past it. |
| `test_unrecorded_attribute_sweep_is_not_vacuous` | the sweep above | Fails if discovery stops finding classes (e.g. a refactor moving `extra_state_attributes` onto a shared base). |
| `test_every_entity_description_carries_an_about_note` | Section 14 | The same `x_proj_checks` row asked for `_unrecorded_attributes` **and** `about` notes; only the first was delivered, which left the row reading as closed. Without this sweep the notes written once stay correct and every entity added after them has none. A minimum length is enforced because a restatement of the entity name reports full coverage while carrying no information. |
| `test_the_device_tracker_carries_a_class_level_note` | the one platform with no description | A sweep over entity descriptions cannot see it, so it would be the single entity in the component with no note and nothing would fail. |
| `test_every_entity_publishing_attributes_keeps_the_about_note_unrecorded` | Section 14 | `_unrecorded_attributes` is resolved by ordinary attribute lookup and is **not** unioned across bases, so a subclass declaring its own set silently discards the mixin's `{"about"}` — and starts recording the note on that entity alone. Invisible in a diff of the subclass. |
| `test_an_entity_with_its_own_attributes_still_emits_the_note` | the mechanism, not the declaration | The declaration sweep passes while an entity's own `extra_state_attributes` returns a dict that never went through `_with_about`: the key is declared unrecorded and simply never emitted. |
| `test_about_attribute_list_doc_matches_the_code` | `docs/about_attribute_list.md` | A descriptive document nothing checks is what this whole file exists against. Compares **note text**, not just the key set — a note reworded in source while the document keeps the old wording is the same defect as an absent one, and the more likely of the two. |
| `test_every_registered_action_has_an_icon` | Section 12 | There was no `services` block at all while four actions were registered. Reads the action list from **`services.yaml`**, not from `icons.json` — reading the thing under test to build the expectation is how a bidirectional check goes vacuous. |
| `test_no_icon_entry_names_an_action_that_does_not_exist` | the other direction | A dead icon entry renders nothing and breaks nothing, so it accumulates unnoticed. |
| `test_action_icons_use_the_current_nested_form` | format drift | The flat form works, so nothing would ever fail; only the nested object can carry per-`section` icons. |
| `test_every_entity_description_has_an_icon_or_a_device_class` | Section 12 | Found `button.refresh` shipping with neither. Reads keys from **module source** across all seven platforms — two hand-maintained files can agree perfectly and both describe an entity that no longer exists. |
| `test_parallel_updates_matches_the_recorded_decision` | Section 22 | The rule is that the constant is set _deliberately_, which source cannot show: a considered `0` and a copy-pasted `0` are identical. Changing a value means changing the table and reading its reasoning. |
| `test_every_entity_platform_is_covered_by_the_decision` | the table above | Stops platform number eight shipping with whatever value it happened to get. |
| `test_every_numeric_sensor_has_a_guard_band` | `UNGUARDED_ALLOWLIST` (empty) | A sensor carrying a unit or a state class reaches long-term statistics, where an implausible reading is permanent. **Note the rule is narrow on purpose** — a wider draft on a sibling flagged 40 sensors that were right. |
| `test_value_min_max_doc_matches_the_code` | `docs/value_min_max.md` | The document had **never** been reconciled: it documented two bands that did not exist and omitted about twenty that did. A guard band is never published as a state or attribute, so **no live query can see one** — only this static check can. |
| `test_integration_health_publishes_the_normative_attribute_names` | Section 19 | `severity` / `issues` / `degraded_capabilities` / `drift` / `last_good_update` are a **published contract**. Users write templates against them, so a rename silently breaks every example written for a sibling project. |
| `test_translation_keys_resolve_in_both_files` | Section 12 check (a) | Nothing had ever compared `translation_key=` in source against the translation files. The only thing that ever had was an analysis pass run by hand, and when it ran it found two dead entity strings orphaned three months earlier. Compared against the **code**, not file-to-file: both files can carry the same stale entry and both can miss the same live entity. |
| `test_no_translation_entry_is_dead` | the other direction | `sensor.hw_version` and `sensor.imei` sat in `strings.json` for three months after the sensors were deleted, invisible to every count-based check — a file with more entries than the code has keys reads as healthy until the sets are diffed. |
| `test_no_live_entity_publishes_a_recorded_attribute` | Section 14, **at runtime** | The static sweep above can see a class declares _something_; it cannot see what a description-driven entity actually emits, because the keys come from a function on the description. Proven non-vacuous by adding an attribute inside the projection's `extra_state_attributes`: the static sweep passed, this one failed. Forces disabled-by-default entities on — the identity sensors ship disabled and are the most likely to publish something unreviewed. |
| `test_every_live_entity_publishes_its_about_note` | the note reaching runtime | A note that never reaches the state machine satisfies every static check and shows the user nothing. |
| `test_every_live_entity_resolves_its_name` | Section 12, **per platform** | A key filed under `sensor` while its entity is built on `binary_sensor` resolves fine to any check that flattens the file, and shows the user a raw key. Proven by filing a live key under the wrong platform: the source-reading check passed, this one failed. |
| `test_every_live_entity_has_an_icon_or_derives_one` | Section 12, live | Only an `icons.json` entry or a `device_class` counts — **`_attr_icon` is deliberately not accepted**, because it satisfies the eye while defeating the check and puts the icon somewhere untranslatable. |
| `test_every_write_is_classified` | `scripts/write_classification.py` | A write shipping with nobody having asked whether it could be exercised is how Clear Traffic reached users calling a method that does not exist. Every command must sit in exactly one tier with a written reason. |
| `test_every_safe_write_is_exercised_by_the_hardware_check` | the tier boundary | A write classified SAFE and never actually run is a claim, not a check. |
| `test_no_lts_excluded_sensor_declares_a_state_class` | long-term statistics | LTS is driven by `state_class`, not `device_class`. An identifier that acquires one starts accumulating statistics nobody wants and the recorder never gives that back. |
| `test_every_read_back_endpoint_is_a_real_one` | Section 22 | A typo in the read-back map surfaces only as a control that silently never confirms — no error, no failure, just a mechanism doing nothing. |
| `test_the_live_keys_are_exactly_the_two_read_every_cycle` | Section 9 | Adding a key to `LIVE_OPTION_KEYS` makes that setting silently stop working: written to the entry, skipped by the reload, never re-read by anything holding the old value. |
| `test_compat.py` (all) | `_compat.py` | Forces **both** branches of each shim by patching the detection flag. The suite runs against one HA version, so the other branch would never execute — and this integration must be correct on ≤2026.7 and post-2027.8 alike. |
| `assert_links_to_parent()` / `assert_is_root()` | device-registry link shape | **Never assert `info["via_device"]` directly.** Twelve tests did, and were green only because the installed HA took that branch. These assert the link's presence and exclusivity instead. |

## Remaining Work (Future — Separate Session)

**Forward work lives in [docs/ROADMAP.md](docs/ROADMAP.md)** — refer there for planned items, revisit parameters, and declined design decisions. Keep it there rather than here, so there is one place to look. That file holds **features only**; chores go to `.shared/issues/x_project/x_proj_chores.md` or the project's `status_plan.md`.

---

## Development Environment

Standard for all integration projects — see [shared conventions §3](.shared/dev_std/agent_conventions.md). Nothing about this project's environment differs.

## Known Open Issues

None currently recorded here. Forward work lives in [docs/ROADMAP.md](docs/ROADMAP.md); chores live in `.shared/issues/x_project/x_proj_chores.md`.

**The `FREQUENCY` unit selector issue that stood here is fixed.** It claimed the eight frequency and bandwidth entities could not show the HA unit selector and that `state_class` had been ruled out as a cause. `state_class` **was** the cause: `device_class=FREQUENCY` plus `state_class=MEASUREMENT` routes an entity through long-term statistics, and that path does not surface the selector. Removing `state_class` from all eight fixed it — see `changelog_local.md`, and chore `C-012`, which carries the same finding for the sibling projects with the warning that ZTE needs the opposite fix.
