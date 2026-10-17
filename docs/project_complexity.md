# Project Complexity & Health: ha-huawei-router-5g-monitor

**Last Measured:** 2026-10-17T13:08:30.035622+00:00 · **Release:** `1.2.4` · **Dev Version:** `1.2.4-dev5`

## 1. Executive Summary

| Metric | Value | Verdict / Evaluation |
| :-- | :-: | :-- |
| **PlayFaster Health Index** | **`80` / 100** | `GOOD` ($\ge 90$ Excellent · $\ge 80$ Good · $\ge 70$ Warning) |
| **Max McCabe Complexity ($V(G)$)** | **16** | `PASS (<20)` in `_compute_health` ($< 20$ Pass · $20–23$ Warn · $\ge 24$ Fail) |
| **Mean Complexity per Routine** | **2.79** | Across 347 routines (Ideal $< 4.0$ per routine) |
| **Danger Routines ($\ge 20$)** | **0** | Zero tolerance (refactor or decompose) |
| **Elevated Routines ($10–19$)** | **8** | Monitor closely; candidate for cleanup |
| **Mean Routine Length** | **13.5 code lines** | Target $\le 15$ code lines ideal |
| **Largest Routine Length** | **105 code lines** | `_async_update_data` in `coordinator.py` (Target $\le 40$ ideal, $> 80$ warn, $> 150$ fail) |
| **Routines > 80 Code Lines** | **2** | Candidate for functional decomposition |
| **Largest Module** | **2,470 code lines** | `sensor.py` (Warn $> 1,500$ code lines module bloat) |
| **Modules > 1,500 Code Lines** | **1** | Candidate for module decomposition |
| **Code Suppressions (`# noqa`)** | **17** | Zero preferred; review regularly |
| **Type Suppressions (`# type: ignore`)** | **1** | Mypy strict compliance |
| **Source Python SLOC** | **8,446** | Across 19 files in custom_components/ (code statements) |
| **Docstring Volume** | **2,142 lines** | Interface and contract documentation |
| **Comment Density** | **17.9%** | 1,515 inline comment lines (Healthy implementation rationale) |
| **Platform Declarations SLOC** | **3,990 lines** | Across 7 platform files |
| **Core Engine / Driver SLOC** | **4,456 lines** | Across 12 coordinator/API/helper files |
| **Static Entities** | **168 entities** | Scale indicator (`all_sensors.md`) |
| **Platform SLOC / Entity** | **23.8 lines/entity** | Target 20 – 45 lines/entity declarative efficiency |
| **Test-to-Source Ratio** | **1.78×** | 15,053 test lines ($\ge 1.5×$ recommended) |
| **Pytest Coverage** | **100%** | 1509 tests executed |
| **Test Decision Density** | **1.64 tests/branch** | 1509 tests across 922 branches (Target $\ge 0.80$ · Strong regression depth) |
| **Assertion Completeness** | **100.0%** | 1124 test functions, 0 unasserted (`test_assertions.txt`) |
| **Dynamic Sequence Depth** | **30 consecutive polls** | Deepest test lifecycle without stubbed seams (`test_depth.txt`) |
| **Pytest Duration** | **283.07s** | Full test suite wall-clock execution time |

## 2. High Complexity Routines ($\ge 10$)

| Score | Routine Symbol | Location | Status |
| :-: | :-- | :-- | :-- |
| **16** | `_compute_health` | `coordinator.py:548` | `ELEVATED` |
| **14** | `_async_update_data` | `coordinator.py:943` | `ELEVATED` |
| **13** | `_probe_sweep` | `api.py:1369` | `ELEVATED` |
| **13** | `_fetch_one` | `api.py:1534` | `ELEVATED` |
| **13** | `is_on` | `binary_sensor.py:609` | `ELEVATED` |
| **13** | `_sanitize` | `diagnostics.py:279` | `ELEVATED` |
| **10** | `async_setup` | `__init__.py:328` | `ELEVATED` |
| **10** | `extra_state_attributes` | `sensor.py:2697` | `ELEVATED` |

## 3. Active Code Suppressions (`custom_components/`)

| Line | Rule Bypassed | File |
| :-: | :-- | :-- |
| 97 | `SLF001` | `api.py` |
| 119 | `SLF001` | `api.py` |
| 284 | `SLF001` | `api.py` |
| 1313 | `BLE001` | `api.py` |
| 1343 | `BLE001` | `api.py` |
| 1360 | `BLE001` | `api.py` |
| 1809 | `SLF001` | `api.py` |
| 2091 | `SLF001` | `api.py` |
| 2157 | `SLF001` | `api.py` |
| 990 | `BLE001` | `coordinator.py` |
| 1748 | `BLE001` | `coordinator.py` |
| 396 | `BLE001` | `diagnostics.py` |
| 543 | `BLE001` | `diagnostics.py` |
| 109 | `BLE001, S112` | `observations.py` |
| 157 | `BLE001` | `observations.py` |
| 269 | `BLE001, S112` | `observations.py` |
| 320 | `BLE001` | `observations.py` |

## 4. Comment Quality & Density Audits

### 4.1 High Comment Density Files (> 25% comments/code)

| Module | Rationale / Advisory |
| :-- | :-- |
| `const.py` | Inspect for commented-out dead code or procedural narration |
| `diagnostics.py` | Inspect for commented-out dead code or procedural narration |
| `select.py` | Inspect for commented-out dead code or procedural narration |

### 4.2 Contiguous Comment Blocks (> 8 lines)

| Location | Length | Advisory |
| :-- | :-: | :-- |
| `const.py:155` | 23 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:1165` | 22 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:420` | 21 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:39` | 19 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:370` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:1095` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:2140` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:297` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:326` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:212` | 16 lines | Long procedural block; consider moving architecture notes to docs |
| `__init__.py:588` | 15 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:353` | 15 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:591` | 15 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:1474` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:74` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:230` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:165` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:334` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:24` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:397` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:62` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `reset_entities.py:215` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `button.py:53` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:53` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:99` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:1995` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:2591` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:52` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:1171` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `button.py:30` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:26` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:29` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:1221` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `binary_sensor.py:218` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:445` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:247` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `device_tracker.py:72` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:184` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:113` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:213` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:286` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:154` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:133` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:269` | 9 lines | Long procedural block; consider moving architecture notes to docs |

### 4.3 Routines with Comments Exceeding Code Lines

| Routine | Location | Comments / Code | Advisory |
| :-- | :-- | :-: | :-- |
| `__init__` | `api.py:315` | 56 comm / 26 code | Comments exceed code statements; verify against procedural narration |
| `__init__` | `coordinator.py:179` | 81 comm / 72 code | Comments exceed code statements; verify against procedural narration |
| `__init__` | `switch.py:153` | 14 comm / 11 code | Comments exceed code statements; verify against procedural narration |
| `_async_background_setup` | `__init__.py:584` | 15 comm / 14 code | Comments exceed code statements; verify against procedural narration |
| `_record_login_metadata` | `api.py:760` | 7 comm / 6 code | Comments exceed code statements; verify against procedural narration |
