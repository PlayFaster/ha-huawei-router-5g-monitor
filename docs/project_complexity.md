# Project Complexity & Health: ha-huawei-router-5g-monitor

**Last Measured:** 2026-09-08T17:44:10.261640+00:00 · **Release:** `1.2.2` · **Dev Version:** `1.2.3-dev8`

## 1. Executive Summary

| Metric | Value | Verdict / Evaluation |
| :--- | :---: | :--- |
| **PlayFaster Health Index** | **`72` / 100** | `WARNING` ($\ge 90$ Excellent · $\ge 80$ Good · $\ge 70$ Warning) |
| **Max McCabe Complexity ($V(G)$)** | **16** | `PASS (<20)` in `get_data` ($< 20$ Pass · $20–23$ Warn · $\ge 24$ Fail) |
| **Mean Complexity per Routine** | **3.75** | Across 151 routines (Ideal $< 4.0$ per routine) |
| **Danger Routines ($\ge 20$)** | **0** | Zero tolerance (refactor or decompose) |
| **Elevated Routines ($10–19$)** | **6** | Monitor closely; candidate for cleanup |
| **Mean Routine Length** | **23.3 lines** | Target $\le 20$ lines ideal, $> 30$ warning |
| **Largest Routine Length** | **229 lines** | `_async_update_data` in `coordinator.py` (Target $\le 60$ ideal, $> 100$ warn, $> 200$ fail) |
| **Routines > 100 Lines** | **5** | Candidate for functional decomposition |
| **Largest Module** | **2,610 lines** | `sensor.py` (Warn $> 2,000$ lines module bloat) |
| **Modules > 2,000 Lines** | **1** | Candidate for module decomposition |
| **Code Suppressions (`# noqa`)** | **7** | Zero preferred; review regularly |
| **Type Suppressions (`# type: ignore`)** | **4** | Mypy strict compliance |
| **Source Python SLOC** | **9,665** | Across 16 files in custom_components/ |
| **Platform Declarations SLOC** | **4,902 lines** | Across 7 platform files |
| **Core Engine / Driver SLOC** | **4,763 lines** | Across 9 coordinator/API/helper files |
| **Static Entities** | **160 entities** | Scale indicator (`all_sensors.md`) |
| **Platform SLOC / Entity** | **30.6 lines/entity** | Target 20 – 45 lines/entity declarative efficiency |
| **Test-to-Source Ratio** | **1.98×** | 19,155 test lines ($\ge 1.5×$ recommended) |
| **Pytest Coverage** | **100%** | 1055 tests executed |
| **Pytest Duration** | **140.09s** | Full test suite wall-clock execution time |

## 2. High Complexity Routines ($\ge 10$)

| Score | Routine Symbol | Location | Status |
| :---: | :--- | :--- | :--- |
| **16** | `get_data` | `api.py:724` | `ELEVATED` |
| **16** | `_async_update_data` | `coordinator.py:525` | `ELEVATED` |
| **14** | `_compute_health` | `coordinator.py:336` | `ELEVATED` |
| **13** | `_fetch` | `api.py:729` | `ELEVATED` |
| **13** | `is_on` | `binary_sensor.py:609` | `ELEVATED` |
| **13** | `_sanitize` | `diagnostics.py:260` | `ELEVATED` |

## 3. Active Code Suppressions (`custom_components/`)

| Line | Rule Bypassed | File |
| :---: | :--- | :--- |
| 705 | `BLE001` | `api.py` |
| 974 | `SLF001` | `api.py` |
| 980 | `SLF001` | `api.py` |
| 1247 | `SLF001` | `api.py` |
| 1312 | `SLF001` | `api.py` |
| 377 | `BLE001` | `diagnostics.py` |
| 410 | `BLE001` | `diagnostics.py` |
