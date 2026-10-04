# Project Complexity & Health: ha-huawei-router-5g-monitor

**Last Measured:** 2026-10-04T19:49:42.710268+00:00 · **Release:** `1.2.3` · **Dev Version:** `1.2.3-dev11`

## 1. Executive Summary

| Metric | Value | Verdict / Evaluation |
| :-- | :-: | :-- |
| **PlayFaster Health Index** | **`80` / 100** | `GOOD` ($\ge 90$ Excellent · $\ge 80$ Good · $\ge 70$ Warning) |
| **Max McCabe Complexity ($V(G)$)** | **17** | `PASS (<20)` in `_async_update_data` ($< 20$ Pass · $20–23$ Warn · $\ge 24$ Fail) |
| **Mean Complexity per Routine** | **2.80** | Across 251 routines (Ideal $< 4.0$ per routine) |
| **Danger Routines ($\ge 20$)** | **0** | Zero tolerance (refactor or decompose) |
| **Elevated Routines ($10–19$)** | **5** | Monitor closely; candidate for cleanup |
| **Mean Routine Length** | **14.5 code lines** | Target $\le 15$ code lines ideal |
| **Largest Routine Length** | **163 code lines** | `get_data` in `api.py` (Target $\le 40$ ideal, $> 80$ warn, $> 150$ fail) |
| **Routines > 80 Code Lines** | **2** | Candidate for functional decomposition |
| **Largest Module** | **2,328 code lines** | `sensor.py` (Warn $> 1,500$ code lines module bloat) |
| **Modules > 1,500 Code Lines** | **1** | Candidate for module decomposition |
| **Code Suppressions (`# noqa`)** | **7** | Zero preferred; review regularly |
| **Type Suppressions (`# type: ignore`)** | **2** | Mypy strict compliance |
| **Source Python SLOC** | **6,849** | Across 16 files in custom_components/ (code statements) |
| **Docstring Volume** | **1,568 lines** | Interface and contract documentation |
| **Comment Density** | **17.1%** | 1,173 inline comment lines (Healthy implementation rationale) |
| **Platform Declarations SLOC** | **3,767 lines** | Across 7 platform files |
| **Core Engine / Driver SLOC** | **3,082 lines** | Across 9 coordinator/API/helper files |
| **Static Entities** | **160 entities** | Scale indicator (`all_sensors.md`) |
| **Platform SLOC / Entity** | **23.5 lines/entity** | Target 20 – 45 lines/entity declarative efficiency |
| **Test-to-Source Ratio** | **1.69×** | 11,606 test lines ($\ge 1.5×$ recommended) |
| **Pytest Coverage** | **100%** | 1116 tests executed |
| **Pytest Duration** | **215.55s** | Full test suite wall-clock execution time |

## 2. High Complexity Routines ($\ge 10$)

| Score | Routine Symbol | Location | Status |
| :-: | :-- | :-- | :-- |
| **17** | `_async_update_data` | `coordinator.py:647` | `ELEVATED` |
| **16** | `get_data` | `api.py:724` | `ELEVATED` |
| **14** | `_compute_health` | `coordinator.py:458` | `ELEVATED` |
| **13** | └─ `_fetch` | `api.py:729` | `ELEVATED (nested)` |
| **13** | `is_on` | `binary_sensor.py:609` | `ELEVATED` |
| **13** | `_sanitize` | `diagnostics.py:260` | `ELEVATED` |

## 3. Active Code Suppressions (`custom_components/`)

| Line | Rule Bypassed | File |
| :-: | :-- | :-- |
| 705 | `BLE001` | `api.py` |
| 980 | `SLF001` | `api.py` |
| 1247 | `SLF001` | `api.py` |
| 1312 | `SLF001` | `api.py` |
| 1489 | `BLE001` | `coordinator.py` |
| 377 | `BLE001` | `diagnostics.py` |
| 410 | `BLE001` | `diagnostics.py` |

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
| `const.py:201` | 30 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:923` | 22 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:309` | 21 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:39` | 19 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:550` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:1295` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:174` | 16 lines | Long procedural block; consider moving architecture notes to docs |
| `__init__.py:455` | 15 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:123` | 15 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:786` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:60` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:134` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:458` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:163` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:107` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:24` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:286` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:46` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `button.py:48` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:47` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:93` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:1985` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:2445` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:50` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:625` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `button.py:25` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:20` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:27` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:643` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `binary_sensor.py:218` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `device_tracker.py:74` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:178` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:92` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:190` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:209` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:148` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:129` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:267` | 9 lines | Long procedural block; consider moving architecture notes to docs |

### 4.3 Routines with Comments Exceeding Code Lines

| Routine | Location | Comments / Code | Advisory |
| :-- | :-- | :-: | :-- |
| `__init__` | `api.py:88` | 31 comm / 17 code | Comments exceed code statements; verify against procedural narration |
| `__init__` | `coordinator.py:150` | 69 comm / 64 code | Comments exceed code statements; verify against procedural narration |
| `__init__` | `switch.py:151` | 14 comm / 11 code | Comments exceed code statements; verify against procedural narration |
| `_async_background_setup` | `__init__.py:451` | 15 comm / 14 code | Comments exceed code statements; verify against procedural narration |
| `_record_login_metadata` | `api.py:391` | 7 comm / 6 code | Comments exceed code statements; verify against procedural narration |
