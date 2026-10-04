# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

> **Read the shared conventions first:** `.shared/dev_std/agent_conventions.md` — commands (tests, lint, mypy, validation), the Windows-host `docker exec` workflow, devcontainer access, HAB/MCP for interrogating the running HA instance, the post-modification SCOPE table, code conventions, and the markdown/Python rules. That file is the single source of truth for everything shared across the integration projects; this file covers only what is specific to **ha-huawei-router-5g-monitor**.
>
> **[!] Note:** If you edit files inside directory junctions (`.notes/` or `.shared/`), do not run container validation on them. Validate them on the Windows host from the `shared/` folder.

---

> [!CAUTION]
>
> **Never run `git checkout`, `git restore`, `git reset`, `git stash` or `git clean`. Ask first, every time — no exceptions, whoever's changes you think they are.** Reading git (`status`, `diff`, `log`, `show`) is always fine. Full rule and the incident behind it: `agent_conventions.md` (`.shared/dev_std/agent_conventions.md`).

## What This Integration Does

A Home Assistant custom component (HACS integration) for monitoring Huawei LTE/5G routers. It wraps the `huawei-lte-api` library to provide signal metrics (RSRP, RSRQ, SINR), data usage tracking, SMS management, connected client device tracking, and polling controls. The component domain is `huawei_router_5g`.

Entities are grouped into six logical sub-devices: **System**, **Signal**, **Data**, **SMS**, **WiFi**, and **Clients**. It also exposes SMS service actions.

> **Entity and service inventory lives in [`docs/all_sensors.md`](docs/all_sensors.md)** — it is authoritative and synchronized from code descriptions via `python .workbench/check_sensor_manifest.py --sync-docs` (and validated against live HA via `--verify-ha`). This file deliberately carries no entity counts or service descriptions.

---

> **Home Assistant version compatibility lives in [`docs/ha_compatibility.md`](docs/ha_compatibility.md)** — supported version floors and active core API deprecation statuses for this integration are tracked there per `agent_conventions.md` §4 (`.shared/dev_std/agent_conventions.md`).

## Commands

Standard for all integration projects — see shared conventions §2 (`.shared/dev_std/agent_conventions.md`). Nothing about this project's commands differs.

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
  → inherit helpers.HuaweiDeviceEntity; it resolves the sub-device from the
    description's group, or from a class-level _device_group
```

### Declarative Entity Pattern

All sensors are defined as `EntityDescription` dataclasses with a `value_fn: Callable[[dict], Any]` callback. No business logic lives in the entity class itself — adding a new sensor is a single-line entry in the descriptions list. Guard bands (e.g. RSRP range -150 to -30 dBm) are applied inside `value_fn` before the value is returned. The bands are listed per key in [`docs/value_min_max.md`](docs/value_min_max.md), which a test reconciles against the code in both directions.

### Sub-Device Organization

Entities are assigned to one of six sub-devices by **inheriting `HuaweiDeviceEntity` from `helpers.py`**, which resolves the group from the entity description and calls `build_device_info(coordinator, group)`. **No platform declares its own `device_info`**, and `test_device_info_is_declared_once` fails if one starts: seven platform bases each carried a copy, and in `zte_router_5g` the same shape produced an entity with none, which reached users. `device_tracker` has no entity description and sets `_device_group = "clients"` at class level. Every non-system sub-device links to the System sub-device as its parent, but **not via a hard-coded key** — the link goes through `_compat.via_device_link()`, which emits `via_device_id` on HA 2026.8+ and the legacy `via_device` tuple on 2026.7 and earlier. The tuple is deprecated in 2026.8 and **removed in 2027.8**; the shim keeps the integration floor-free.

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
- `HuaweiDeviceEntity`: the one `device_info` implementation — inherit it, never redeclare the property
- `build_device_info(coordinator, group)`: Builds `DeviceInfo` targeting the correct sub-device; called by the mixin, not by platforms
- `find_ssid_by_path` / `is_ssid_on`: Dynamic WiFi radio discovery by path fragment

## Key Patterns & Conventions

Shared conventions (ruff/mypy strictness, `PARALLEL_UPDATES`, `translation_key`, the centralized `icons.json` architecture, exception tuple syntax, `or 0` precedence, markdown emoji rules) are in shared conventions §4–5 (`.shared/dev_std/agent_conventions.md`). Project-specific additions:

### Frequency Field Scaling

- `lteulfreq` / `ltedlfreq` fields: divide by **10** to get MHz (raw 19700 → 1970.0 MHz)
- `ulfrequency` / `dlfrequency` fields: divide by **1000** to get MHz (kHz → MHz), handled by `format_khz_to_mhz`
- `ulbandwidth` / `dlbandwidth` fields: already in MHz, no scaling needed

### Windows Test Environment (unused)

`tests/conftest.py` carries two deliberate Windows-compatibility patches (a `WindowsSelectorEventLoopPolicy` switch and a `pytest_socket.disable_socket` no-op), both guarded by `sys.platform == "win32"`. They were added on purpose but are **not exercised** — tests run inside the Linux devcontainer via `docker exec`. Unique to this project; leave them alone, and don't treat them as a pattern to replicate.

### Entity Category Usage

- `EntityCategory.DIAGNOSTIC`: granular infrastructure metrics (secondary bands, per-bank SMS capacity, raw durations)
- No category (primary list): actionable or highly readable metrics (signal bars, SMS unread count, data rates)

### The hardware check, and what it now guarantees

`scripts/hardware_check.py` is not a test and never runs in CI — it needs the router and it writes to it. Two tiers: the default safe tier reads only; `--attended` offers each write with its cost stated and a typed confirmation.

Four things to know before editing it:

- **Every run files a report**, from a `finally`, in both tiers. `.reports/hardware_check_<ts>.md` carries verdicts and non-identifying evidence; `.notes/local_only/hardware_check_detail_<ts>.md` carries the identifying values and is written only when a check captured one. `Report.record()` takes the redacted form as `detail` and the identifying form as `sensitive` — it files what it is given and does not sanitize.
- **Skips are rows, not console lines.** A skip that leaves no row is indistinguishable later from a check nobody wrote.
- **`ha_contention` drives Home Assistant over REST**, not the API object, because a write contending with a live poll exists only inside a running instance. The token comes from `.notes/ha_restart/token.txt`; never read one from `.storage/auth`, and never let one reach either report.
- **`--debug` is console noise only.** The write-confirmation outcome is captured from the integration's own log records and reported as a check either way — a flag that changed what got _verified_ would make the default run the weaker one.

New checks must record evidence, not just a verdict, and must restore what they changed with the restore itself recorded as a row.

### The diagnostics check, and the one rule that governs sweeps

`scripts/diag_check.py` is the second script that needs the router and never runs in CI. It builds a real coordinator, calls the real `async_get_config_entry_diagnostics`, asserts over the **produced file** rather than the producer, and runs twice to diff. `--sabotage` ends the session mid-poll so a real expiry is classified by real firmware. It writes `.reports/diag_check.txt` and is wired into the shared `tasks.json` as **Hardware: Check Diagnostics Download**.

It exists because the unit suite asserts on what the API client holds while the user receives what `diagnostics.py` publishes. `zte_router_5g` shipped a field that five green tests asserted and no download ever carried.

Three things to know before editing it or anything it exercises:

- **Never sweep endpoints through `_execute_with_retry`.** `huawei-lte-api` raises `ResponseErrorLoginRequiredException` for `100003` and for no other code, and `100003` is a refusal on this firmware rather than an expiry — so that wrapper re-logs in on every refusal. Measured 2026-09-07: two logins per `100003` against one for any other outcome, and a 46-endpoint sweep through it left the router answering `LoginErrorAlreadyLoginException` and then refusing connections, turning the rest of the run into artefacts. `api.probe_diagnostic_endpoints` calls directly on one established session for this reason. `docs/huawei_how_to_access.md` carries the mechanism and had already warned that bulk sweeps produce false `100003` results — twice before this.
- **A probe publishes key names and counts, never values.** A value from an endpoint nobody here has seen has no entry in `diagnostics.py`'s key lists and would be published intact by a sanitizer that matches on exact key names.
- **An endpoint left out of the probe set says why**, in `api.PROBES_EXCLUDED`, so nobody adds it back blind. `system.onlinestate` is there because the endpoint returns a list and the library calls `.get()` on it; the two `diagnosis` calls are there because they make the router _perform_ a network operation rather than report one.

The stability comparison in the script tolerates values the device changes on its own — radio measurements, counters, timings, populated counts. **Widening that tolerance is a change to what the check can still catch**, so a new entry needs its reason beside it.

## Before you write a test for new behavior

Four questions, because the first six of the ten analysis categories are each scoped to one function and the defects that survive 100% branch coverage are not.

- **Does it accumulate?** Anything needing N consecutive cycles — `FETCH_STRIKE_LIMIT`, `HEALTH_DRIFT_STRIKE_LIMIT`, `REPAIR_CONN_STRIKE_LIMIT` — must be driven through N real polls. Setting the counter by hand proves the comparison, not that the code can reach it. And ask the killer question: after the first differing cycle, does the comparison still differ? If the code adopts the new value, the finding can never confirm.
- **Does it need cleaning up?** For everything created, prove it is destroyed across reload and restart, not only entry removal. A repair raised into the issue registry outlives the coordinator that raised it.
- **Can the outcome actually happen?** Every declared finding, repair key and severity value needs one test producing it end to end, driven through a real poll with the transport faked rather than the API object replaced. `Tests: Depth Check` sweeps this.
- **Is the value published?** Assert the string a user template compares against — `"ok"`, `"degraded"` — and prove its translation exists, not just the internal constant.

**Faking the transport here means `requests_mock`, not `aioclient_mock`.** This project reaches the network through `huawei-lte-api`, which holds its own `requests.Session`, so `async_get_clientsession` is never involved. The fake router is [`tests/transport.py`](tests/transport.py) and the worked examples are in [`tests/test_transport_seam.py`](tests/test_transport_seam.py); the design record is `.shared/issues/x_project/fault_injection_options.md` §3.

Long form, all ten categories: `.shared/dev_std/testing_when_writing.md` — these four are **SEQ / LIFE / REACH / PUB**.

## Tests that will stop you

These are **coverage sweeps**, not mechanism tests. Each asserts that every member of a set satisfies a property, so **it fails when the set grows** — which means the failure usually looks unrelated to whatever you just changed, and the reflex is to suppress it.

> [!IMPORTANT]
>
> **If one of these fails, it has found something. Do not reach for the allow-list first.** Every allow-list below is currently **empty**, and each entry is meant to be a reviewable act with a written reason. A sweep that has been quietly widened is worth less than no sweep at all.

| Add or change this | This fails | Do this |
| :-- | :-- | :-- |
| A sensor's state class | `test_no_sensor_uses_the_total_state_class` | Use `TOTAL_INCREASING`; `ALLOWED_TOTAL_STATE_CLASS` is deliberately empty. |
| Removing a sensor that has an allow-list, register or exclusion entry | `test_allowed_total_state_class_has_no_dead_entries`, `test_unguarded_allowlist_has_no_dead_entries`, `test_the_lts_exclusion_lists_have_no_dead_entries`, `test_the_disabled_by_decision_register_has_no_dead_entries`, `test_allowed_suppressions_has_no_dead_entries` | Remove its entry in the same change. |
| An entity that publishes attributes | `test_every_entity_publishing_attributes_declares_unrecorded`, `test_every_entity_publishing_attributes_keeps_the_about_note_unrecorded`, `test_no_live_entity_publishes_a_recorded_attribute`, `test_integration_health_attributes_are_all_unrecorded` | Add each key to the class's `_unrecorded_attributes`, repeating `"about"` if the class declares its own set. |
| An entity description | `test_every_entity_description_carries_an_about_note`, `test_every_live_entity_publishes_its_about_note` | Give it an `about` note that reaches the published attributes. |
| The device tracker class | `test_the_device_tracker_carries_a_class_level_note` | Keep its class-level `about` note; the description sweep cannot see this platform. |
| An entity with its own `extra_state_attributes` | `test_an_entity_with_its_own_attributes_still_emits_the_note` | Build the returned dict through `_with_about`. |
| Any entity, guard band or `about` note | `Sensor: Check Manifest` (`--check`) | Regenerate the documents with the manifest tool and commit the result. |
| An action, or removing one | `test_every_registered_action_has_an_icon`, `test_no_icon_entry_names_an_action_that_does_not_exist`, `test_action_icons_use_the_current_nested_form` | Add a `services` icon entry in the nested form, and remove it with the action. |
| A repair issue | `test_every_repair_issue_has_title_and_rendered_text`, `test_the_fixable_repair_is_the_one_with_a_fix_flow`, `test_no_orphan_issue_translations` | Add the key to `REPAIR_NAMES` and give it a `title` in **both** `strings.json` and `translations/en.json`, then **exactly one** of `description` or `fix_flow` — `hassfest` declares them `vol.Exclusive`, because a fixable issue renders its prose in the flow's step. |
| An entity class | `test_every_live_entity_belongs_to_a_device`, `test_device_info_is_declared_once` | Inherit the shared base entity; never declare `device_info` on a platform class. |
| Any entity | `test_every_entity_description_has_an_icon_or_a_device_class`, `test_every_live_entity_has_an_icon_or_derives_one` | Add an `icons.json` entry under its own platform, unless it has a `device_class`; `_attr_icon` does not count. |
| A platform, or a `PARALLEL_UPDATES` value | `test_parallel_updates_matches_the_recorded_decision`, `test_every_entity_platform_is_covered_by_the_decision` | Change the recorded decision in the test together with the constant. |
| A sensor with a unit or `state_class` | `test_every_numeric_sensor_has_a_guard_band` | Declare a guard band, or add the key to `UNGUARDED_ALLOWLIST` with a reason. |
| A guard band | `test_value_min_max_doc_matches_the_code` | Update `docs/value_min_max.md` to match. |
| A health attribute name | `test_integration_health_publishes_the_normative_attribute_names` | Keep the §19 published names; a rename breaks user templates. |
| A `translation_key`, or removing an entity | `test_translation_keys_resolve_in_both_files`, `test_no_translation_entry_is_dead`, `test_every_live_entity_resolves_its_name` | Add the key under the entity's own platform in both translation files, and remove it with the entity. |
| A write command | `test_every_write_is_classified`, `test_every_safe_write_is_exercised_by_the_hardware_check` | Classify it in `scripts/write_classification.py` with a reason; a `SAFE` write must run in `scripts/hardware_check.py`. |
| An identifier sensor | `test_no_lts_excluded_sensor_declares_a_state_class`, `test_identifier_sensors_are_declared_as_text` | Leave it without a `state_class` or unit, so it stays text and out of long-term statistics. |
| A read-back map entry | `test_every_read_back_endpoint_is_a_real_one` | Point it at a real endpoint. |
| `LIVE_OPTION_KEYS` | `test_the_live_keys_are_exactly_the_two_read_every_cycle` | Do not add to it; an option listed there is never re-read. |
| `_compat.py` | `test_compat.py` (all) | Test both branches by patching the detection flag. |
| A device-registry test | `assert_links_to_parent()` / `assert_is_root()` | Use these helpers; never assert `info["via_device"]` directly. |
| A `# type: ignore`, `# noqa` or `# pragma: no cover` | `test_every_suppression_is_on_the_reviewed_allow_list`, `test_every_allowed_suppression_states_a_reason` | Add it to the reviewed allow-list with a reason. |
| A sensor disabled by default by decision | `test_sensors_disabled_by_decision_are_still_disabled`, `test_every_disabled_by_decision_entry_carries_a_reason` | Change the register, with a reason, in the same change. |

When you add a guard test, add its row here and its rationale to [`docs/test_guards.md`](docs/test_guards.md).

## Mutation testing — what is on the list, and why

**Scoped by `.validate/mutmut_modules.txt`** — currently `*/helpers.py`, `*/diagnostics.py`, `*/device_tracker.py`, `*/coordinator.py`, `*/sensor.py`. A module earns a place when its tests exercise real code: a mutation of a call into a mocked object cannot be detected by any test, so it survives every run and is never a defect.

`api.py`, `config_flow.py`, `switch.py`, `number.py`, `button.py`, `select.py`, `__init__.py`, `_compat.py` and `const.py` are excluded, each with its reason recorded. `coordinator.py` is a deliberate departure from `zte_router_5g`, which excludes it: the API is mocked here too, but the strike budget, the per-endpoint counters, the health snapshot, the uptime latches and the SMS dedup are real code with real boundaries.

**The reasoning lives in `.notes/test_pytest_issues/mutation_covered_not_covered.md`** — included modules with their measured results, rejected modules with the reason each, candidates with the case for and against, and the rule for deciding the next one. Read it before adding or removing a module, and record the decision there. This project has the largest mutation surface in the family at roughly 1,633 mutants and 70 minutes, so an addition is a real cost.

**Do not project survivor volume from the source.** `sensor.py` was excluded on a count of string literals predicting over a thousand `about` note survivors, and measured at 53 survivors with no note among them. Measure the module.

**Never delete `mutants/`** — it is the incremental cache and the results store, and changing the module list does not require it. **`only_mutate` must be an indented newline list**; the comma-separated form in the mutmut documentation generates zero mutants and reports no error.

## Remaining Work (Future — Separate Session)

**Forward work lives in [docs/ROADMAP.md](docs/ROADMAP.md)** — refer there for planned items, revisit parameters, and declined design decisions. Keep it there rather than here, so there is one place to look. That file holds **features only**; chores go to `.shared/issues/x_project/x_proj_chores.md` or the project's `status_plan.md`.

---

## Development Environment

Standard for all integration projects — see shared conventions §3 (`.shared/dev_std/agent_conventions.md`). Nothing about this project's environment differs.

## Known Open Issues

**Nothing is recorded here, and nothing should be.** This project's open work lives in `.notes/todo.md`, `.notes/tasks/`, the cross-project chore register, the cross-project queue and [`docs/ROADMAP.md`](docs/ROADMAP.md). One command reads all of them, from `dev-workbench/`:

```bash
uv run python scripts/check_queue_format.py --open ha-huawei-router-5g-monitor
```

**Which one a new item belongs in, and how to add, check and close it, is `issue_tracking_workflow.md` (`.shared/issues/issue_tracking_workflow.md`)** — authoritative, with the summary at shared conventions §8 (`.shared/dev_std/agent_conventions.md`).

**The `FREQUENCY` unit selector issue that stood here is fixed** — the eight frequency and bandwidth entities show the selector. **The cause recorded for it was wrong and has been corrected**: the selector is controlled by the `device_class`, not by `state_class`. Checked against the installed Home Assistant on 2026-08-26 — `sensor/device_class_convertible_units` supplies the selector's units and takes `device_class` alone, `FREQUENCY` is convertible, and `DEVICE_CLASS_STATE_CLASSES[FREQUENCY]` is `{MEASUREMENT}`. Do not remove a `state_class` expecting it to restore a selector. Cross-project detail: chore `C-012`.
