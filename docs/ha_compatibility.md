# Home Assistant Compatibility

What Home Assistant versions this integration supports and the status of any changing core APIs.

**Reviewed 2026-08-21.**

> [!IMPORTANT]
>
> **Nothing in this integration requires action before Home Assistant 2027.8.** All version-sensitive Home Assistant APIs are either shimmed with dynamic fallbacks or pass explicit parameters.

---

## Supported versions

| Type | Version / Status | Note |
| :-- | :-- | :-- |
| **Minimum** | **2024.6.0** | Declared in `README.md` |
| **Tested against** | **2026.8.0** | Development container environment |
| **Enforced by** | `hacs.json` | `"homeassistant": "2024.6.0"` |
| **Functional floor** | `ConfigFlowResult`, `ConfigEntry.runtime_data` | Both introduced in HA 2024.6 |

---

## Deprecation & compatibility ledger

| API / Feature | Deprecated in | Removed in | Integration Exposure | Status |
| :-- | :-- | :-- | :-- | :-- |
| `DeviceInfo.via_device` identifier tuple | 2026.8 | **2027.8** | Sub-device parent links | **Shimmed** — `_compat.via_device_link()` |
| `async_get_device(identifiers=…)` | 2026.8 | **2027.8** | Sub-device lookups | **Shimmed** — `_compat.device_by_identifier()` |
| Implicit coordinator `config_entry` detection | 2024.8 | **2026.8** | `DataUpdateCoordinator` | **Done** — passed explicitly |
| `BaseTrackerEntity.battery_level` | 2026.6 | **2027.7** | Client trackers | **N/A** — not overridden |
| `TrackerEntity.location_name` | 2026.6 | **2027.7** | Client trackers | **N/A** — uses `ScannerEntity` |

---

## Upcoming milestones

- **Home Assistant 2027.8:** When core removes the legacy `via_device` tuple and `async_get_device` identifier lookups, the legacy branches in `_compat.py` can be retired. Until then, `_compat.py` provides transparent backward and forward compatibility without raising warnings.

---

## Version Control

| Version | Date | Author | Description |
| :-- | :-- | :-- | :-- |
| **v1.0.0** | 2026-08-14 | Antigravity | Initial creation. |
| **v1.0.1** | 2026-08-21 | PlayFaster | Updated version floor from 2025.1 to 2024.6 to match `README.md`, `hacs.json`, and the cross-project matrix. |
| **v1.1.0** | 2026-08-21 | Antigravity | Streamlined to standard lean project compatibility format (Option A). |
