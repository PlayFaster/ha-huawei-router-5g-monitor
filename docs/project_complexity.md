# Project Complexity & Health: ha-huawei-router-5g-monitor

**Last Measured:** 2026-10-09T20:25:09.810101+00:00 · **Release:** `1.2.4` · **Dev Version:** `1.2.4-dev1`

## 1. Executive Summary

| Metric | Value | Verdict / Evaluation |
| :-- | :-: | :-- |
| **PlayFaster Health Index** | **`78` / 100** | `WARNING` ($\ge 90$ Excellent · $\ge 80$ Good · $\ge 70$ Warning) |
| **Max McCabe Complexity ($V(G)$)** | **19** | `PASS (<20)` in `_async_update_data` ($< 20$ Pass · $20–23$ Warn · $\ge 24$ Fail) |
| **Mean Complexity per Routine** | **2.90** | Across 279 routines (Ideal $< 4.0$ per routine) |
| **Danger Routines ($\ge 20$)** | **0** | Zero tolerance (refactor or decompose) |
| **Elevated Routines ($10–19$)** | **6** | Monitor closely; candidate for cleanup |
| **Mean Routine Length** | **14.7 code lines** | Target $\le 15$ code lines ideal |
| **Largest Routine Length** | **182 code lines** | `_async_update_data` in `coordinator.py` (Target $\le 40$ ideal, $> 80$ warn, $> 150$ fail) |
| **Routines > 80 Code Lines** | **3** | Candidate for functional decomposition |
| **Largest Module** | **2,325 code lines** | `sensor.py` (Warn $> 1,500$ code lines module bloat) |
| **Modules > 1,500 Code Lines** | **1** | Candidate for module decomposition |
| **Code Suppressions (`# noqa`)** | **9** | Zero preferred; review regularly |
| **Type Suppressions (`# type: ignore`)** | **2** | Mypy strict compliance |
| **Source Python SLOC** | **7,376** | Across 17 files in custom_components/ (code statements) |
| **Docstring Volume** | **1,778 lines** | Interface and contract documentation |
| **Comment Density** | **17.8%** | 1,313 inline comment lines (Healthy implementation rationale) |
| **Platform Declarations SLOC** | **3,781 lines** | Across 7 platform files |
| **Core Engine / Driver SLOC** | **3,595 lines** | Across 10 coordinator/API/helper files |
| **Static Entities** | **160 entities** | Scale indicator (`all_sensors.md`) |
| **Platform SLOC / Entity** | **23.6 lines/entity** | Target 20 – 45 lines/entity declarative efficiency |
| **Test-to-Source Ratio** | **1.86×** | 13,731 test lines ($\ge 1.5×$ recommended) |
| **Pytest Coverage** | **100%** | 1390 tests executed |
| **Pytest Duration** | **518.67s** | Full test suite wall-clock execution time |

## 2. High Complexity Routines ($\ge 10$)

| Score | Routine Symbol | Location | Status |
| :-: | :-- | :-- | :-- |
| **19** | `_async_update_data` | `coordinator.py:682` | `ELEVATED` |
| **18** | `get_data` | `api.py:1107` | `ELEVATED` |
| **15** | └─ `_fetch` | `api.py:1112` | `ELEVATED (nested)` |
| **15** | `_compute_health` | `coordinator.py:466` | `ELEVATED` |
| **13** | `_probe_sweep` | `api.py:1054` | `ELEVATED` |
| **13** | `is_on` | `binary_sensor.py:609` | `ELEVATED` |
| **13** | `_sanitize` | `diagnostics.py:274` | `ELEVATED` |

## 3. Active Code Suppressions (`custom_components/`)

| Line | Rule Bypassed | File |
| :-: | :-- | :-- |
| 998 | `BLE001` | `api.py` |
| 1028 | `BLE001` | `api.py` |
| 1045 | `BLE001` | `api.py` |
| 1371 | `SLF001` | `api.py` |
| 1638 | `SLF001` | `api.py` |
| 1703 | `SLF001` | `api.py` |
| 1554 | `BLE001` | `coordinator.py` |
| 391 | `BLE001` | `diagnostics.py` |
| 466 | `BLE001` | `diagnostics.py` |

## 4. Comment Quality & Density Audits

### 4.1 High Comment Density Files (> 25% comments/code)

| Module | Rationale / Advisory |
| :-- | :-- |
| `const.py` | Inspect for commented-out dead code or procedural narration |
| `coordinator.py` | Inspect for commented-out dead code or procedural narration |
| `diagnostics.py` | Inspect for commented-out dead code or procedural narration |
| `select.py` | Inspect for commented-out dead code or procedural narration |

### 4.2 Contiguous Comment Blocks (> 8 lines)

| Location | Length | Advisory |
| :-- | :-: | :-- |
| `const.py:289` | 30 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:155` | 23 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:988` | 22 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:397` | 21 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:39` | 19 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:223` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:813` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:1686` | 18 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:179` | 16 lines | Long procedural block; consider moving architecture notes to docs |
| `__init__.py:536` | 15 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:205` | 15 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:514` | 15 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:1169` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:74` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:222` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:163` | 14 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:189` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:24` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:374` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:51` | 13 lines | Long procedural block; consider moving architecture notes to docs |
| `button.py:48` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:47` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:93` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:1991` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:2451` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:50` | 12 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:889` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `button.py:25` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `select.py:20` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:27` | 11 lines | Long procedural block; consider moving architecture notes to docs |
| `api.py:907` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `binary_sensor.py:218` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `coordinator.py:214` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `device_tracker.py:74` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:179` | 10 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:113` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `const.py:278` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `diagnostics.py:149` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `sensor.py:129` | 9 lines | Long procedural block; consider moving architecture notes to docs |
| `switch.py:267` | 9 lines | Long procedural block; consider moving architecture notes to docs |

### 4.3 Routines with Comments Exceeding Code Lines

| Routine | Location | Comments / Code | Advisory |
| :-- | :-- | :-: | :-- |
| `__init__` | `api.py:170` | 50 comm / 24 code | Comments exceed code statements; verify against procedural narration |
| `__init__` | `coordinator.py:155` | 70 comm / 65 code | Comments exceed code statements; verify against procedural narration |
| `__init__` | `switch.py:151` | 14 comm / 11 code | Comments exceed code statements; verify against procedural narration |
| `_async_background_setup` | `__init__.py:532` | 15 comm / 14 code | Comments exceed code statements; verify against procedural narration |
| `_record_login_metadata` | `api.py:531` | 7 comm / 6 code | Comments exceed code statements; verify against procedural narration |
