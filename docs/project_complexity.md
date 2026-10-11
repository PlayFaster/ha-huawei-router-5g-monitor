# Project Complexity & Health: ha-huawei-router-5g-monitor

**Last Measured:** 2026-10-11T11:51:06.082439+00:00 · **Release:** `1.2.4` · **Dev Version:** `1.2.4-dev2`

## 1. Executive Summary

| Metric | Value | Verdict / Evaluation |
| :-- | :-: | :-- |
| **PlayFaster Health Index** | **`80` / 100** | `GOOD` ($\ge 90$ Excellent · $\ge 80$ Good · $\ge 70$ Warning) |
| **Max McCabe Complexity ($V(G)$)** | **15** | `PASS (<20)` in `_compute_health` ($< 20$ Pass · $20–23$ Warn · $\ge 24$ Fail) |
| **Mean Complexity per Routine** | **2.81** | Across 308 routines (Ideal $< 4.0$ per routine) |
| **Danger Routines ($\ge 20$)** | **0** | Zero tolerance (refactor or decompose) |
| **Elevated Routines ($10–19$)** | **6** | Monitor closely; candidate for cleanup |
| **Mean Routine Length** | **13.8 code lines** | Target $\le 15$ code lines ideal |
| **Largest Routine Length** | **104 code lines** | `_async_update_data` in `coordinator.py` (Target $\le 40$ ideal, $> 80$ warn, $> 150$ fail) |
| **Routines > 80 Code Lines** | **2** | Candidate for functional decomposition |
| **Largest Module** | **2,325 code lines** | `sensor.py` (Warn $> 1,500$ code lines module bloat) |
| **Modules > 1,500 Code Lines** | **1** | Candidate for module decomposition |
| **Code Suppressions (`# noqa`)** | **11** | Zero preferred; review regularly |
| **Type Suppressions (`# type: ignore`)** | **2** | Mypy strict compliance |
| **Source Python SLOC** | **7,715** | Across 17 files in custom_components/ (code statements) |
| **Docstring Volume** | **1,938 lines** | Interface and contract documentation |
| **Comment Density** | **17.8%** | 1,376 inline comment lines (Healthy implementation rationale) |
| **Platform Declarations SLOC** | **3,826 lines** | Across 7 platform files |
| **Core Engine / Driver SLOC** | **3,889 lines** | Across 10 coordinator/API/helper files |
| **Static Entities** | **160 entities** | Scale indicator (`all_sensors.md`) |
| **Platform SLOC / Entity** | **23.9 lines/entity** | Target 20 – 45 lines/entity declarative efficiency |
| **Test-to-Source Ratio** | **1.85×** | 14,305 test lines ($\ge 1.5×$ recommended) |
| **Pytest Coverage** | **100%** | 1439 tests executed |
| **Pytest Duration** | **561.07s** | Full test suite wall-clock execution time |

## 2. High Complexity Routines ($\ge 10$)

| Score | Routine Symbol | Location | Status |
| :-: | :-- | :-- | :-- |
| **15** | `_compute_health` | `coordinator.py:501` | `ELEVATED` |
| **14** | `_async_update_data` | `coordinator.py:896` | `ELEVATED` |
| **13** | `_probe_sweep` | `api.py:1273` | `ELEVATED` |
| **13** | `_fetch_one` | `api.py:1438` | `ELEVATED` |
| **13** | `is_on` | `binary_sensor.py:609` | `ELEVATED` |
| **13** | `_sanitize` | `diagnostics.py:274` | `ELEVATED` |

## 3. Active Code Suppressions (`custom_components/`)

| Line | Rule Bypassed | File |
| :-: | :-- | :-- |
| 260 | `SLF001` | `api.py` |
| 1217 | `BLE001` | `api.py` |
| 1247 | `BLE001` | `api.py` |
| 1264 | `BLE001` | `api.py` |
| 1723 | `SLF001` | `api.py` |
| 2005 | `SLF001` | `api.py` |
| 2071 | `SLF001` | `api.py` |
| 943 | `BLE001` | `coordinator.py` |
| 1689 | `BLE001` | `coordinator.py` |
| 391 | `BLE001` | `diagnostics.py` |
| 466 | `BLE001` | `diagnostics.py` |

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
| `coordinator.py:1106` | 22 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:412` | 21 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:39` | 19 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:344` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:1031` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:2054` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:289` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:318` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:205` | 16 lines | Long procedural block; consider moving architecture notes to docs |
| `__init__.py:543` | 15 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:326` | 15 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:514` | 15 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:1378` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:74` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:222` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:164` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:310` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:24` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:389` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:58` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `button.py:48` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:48` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:94` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:1991` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:2451` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:51` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:1107` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `button.py:25` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:21` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:28` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:1125` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `binary_sensor.py:218` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:437` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:240` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `device_tracker.py:74` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:179` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:113` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:278` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:149` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:129` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:268` | 9 lines | Long procedural block; consider moving architecture notes to docs |

### 4.3 Routines with Comments Exceeding Code Lines

| Routine | Location | Comments / Code | Advisory |
| :-- | :-- | :-: | :-- |
| `__init__` | `api.py:291` | 54 comm / 26 code | Comments exceed code statements; verify against procedural narration |
| `__init__` | `coordinator.py:175` | 79 comm / 71 code | Comments exceed code statements; verify against procedural narration |
| `__init__` | `switch.py:152` | 14 comm / 11 code | Comments exceed code statements; verify against procedural narration |
| `_async_background_setup` | `__init__.py:539` | 15 comm / 14 code | Comments exceed code statements; verify against procedural narration |
| `_record_login_metadata` | `api.py:701` | 7 comm / 6 code | Comments exceed code statements; verify against procedural narration |
