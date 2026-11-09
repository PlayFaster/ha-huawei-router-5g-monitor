# Home Assistant Compatibility

What Home Assistant versions this integration supports and the status of any changing core APIs.

**Reviewed 2026-11-01.**

> [!IMPORTANT]
>
> **Nothing in this integration requires action before Home Assistant 2027.8.** All version-sensitive Home Assistant APIs are either shimmed with dynamic fallbacks or pass explicit parameters.

---

## Supported versions

| Type | Version / Status | Note |
| :-- | :-- | :-- |
| **Minimum** | **2025.2.0** | Declared in `README.md` |
| **Tested against** | **2026.10.4** | `pytest-homeassistant-custom-component` 0.13.375 (development container) |
| **Enforced by** | `hacs.json` | `"homeassistant": "2025.2.0"` |
| **Functional floor** | `ConfigFlowResult`, `ConfigEntry.runtime_data` | Both introduced in HA 2024.6 |
| **Python** | 3.13 or later | Required by Home Assistant 2025.2.0. Tests run on Python 3.14 |
| **`huawei-lte-api`** | **1.11.0 or 2.0.1** | Range `>=1.11.0,<2.0.2` in `manifest.json`. Core pins 1.11.0 for its own `huawei_lte`, and a startup guard installs 2.0.1 when no core entry exists. See `docs/library_versions.md` |

---

## Deprecation & compatibility ledger

| API / Feature | Deprecated in | Removed in | Integration Exposure | Status |
| :-- | :-- | :-- | :-- | :-- |
| `DeviceInfo.via_device` identifier tuple (`HAC-012`) | 2026.8 | **2027.8** | Sub-device parent links | **Already Handled**: `_compat.via_device_link()` |
| `async_get_device(identifiers=…)` (`HAC-012`) | 2026.8 | **2027.8** | Sub-device lookups | **Already Handled**: `_compat.device_by_identifier()` |
| Implicit coordinator `config_entry` detection (`HAC-016`) | 2024.8 | **2026.8** | `DataUpdateCoordinator` | **Already Handled**: passed explicitly |
| `BaseTrackerEntity.battery_level` (`HAC-015`) | 2026.6 | **2027.7** | Client trackers | **Not Needed**: not overridden |
| `TrackerEntity.location_name` (`HAC-015`) | 2026.6 | **2027.7** | Client trackers | **Not Needed**: uses `ScannerEntity` |
| `voluptuous` imports (`HAC-009`) | N/A (replaced by probatio in 2026.9) | None announced | Config flow and schemas | **Held**: works through Home Assistant's `install_as_voluptuous()` alias. Done when HA removes or announces removal of the alias, which needs a 2026.9.0 floor (`HAC-009`, triage 2026-11-04). |
| Flow and service schema types (probatio) (`HAC-010`) | 2026.10, type hints only | None announced | `voluptuous` imports in the config flow, services and schemas | **Already Handled**: runtime is unaffected, and a shared `pyproject.toml` override makes Mypy treat `voluptuous` as untyped. Mypy Strict passes (C-037). |
| Device-class enums in `const` modules (`HAC-011`) | 2026.10, type hints only | None announced | `BinarySensorDeviceClass`, `ButtonDeviceClass` imported from the platform package | **Already Handled**: the package re-export still works, and a shared `pyproject.toml` override makes Mypy count it as an export. Mypy Strict passes (C-037). |
| `DeviceInfo` `TypedDict` on 2026.10, dataclass from 2026.11 (`HAC-002`) | 2026.11 (dataclass) | Not announced | Sub-device info merges `via_device_link` with `**link` (`helpers.py:417`) | **Queued**: cross-project item `device_info_dataclass_2026_11.md` |
| `ScannerEntity` default device info; trackers disabled by default (`HAC-003`) | 2026.11 | **2027.11** | Client trackers (`device_tracker.py`) | **Queued**: Huawei task `option_to_enable_or_disable_new_client_trackers_by_default.md` |
| Entity re-added on entity ID change without `async_entity_id_changed` (`HAC-004`) | 2026.11 | **2027.11** | `event.py`, `switch.py`, `number.py` lifecycle hooks | **Not Needed**: no lifecycle hook in this integration depends on the entity ID, so in-place renaming, the default from 2027.11, is correct for it. Checked by reading the hooks and every use of the entity ID; not live-tested (`HAC-004`, triage 2026-11-04). |
| `PERCENTAGE` as a unit of measurement (`HAC-005`) | 2026.7 | Not announced | 2 sensors | **Held**: `PERCENTAGE` and `UnitOfRatio.PERCENTAGE` give the same `"%"` value, so nothing can break. Done when HA rejects `PERCENTAGE` units or the floor reaches 2026.7.0 (`HAC-005`, triage 2026-11-04). |

---

## Upcoming milestones

- **Home Assistant 2027.8:** When core removes the legacy `via_device` tuple and `async_get_device` identifier lookups, the legacy branches in `_compat.py` can be retired. Until then, `_compat.py` provides transparent backward and forward compatibility without raising warnings.
- **Home Assistant 2026.10:** core types flow and service schemas as probatio and moves the device-class enums to `const` modules. This affects type checking only. The two Mypy overrides in the shared `pyproject.toml` are removed when the integration imports probatio directly or the floor passes the move.

---

## Version Control

| Version | Date | Author | Description |
| :-- | :-- | :-- | :-- |
| **v1.0.0** | 2026-08-14 | Antigravity | Initial creation. |
| **v1.0.1** | 2026-08-21 | PlayFaster | Updated version floor from 2025.1 to 2024.6 to match `README.md`, `hacs.json`, and the cross-project matrix. |
| **v1.1.0** | 2026-08-21 | Antigravity | Streamlined to standard lean project compatibility format (Option A). |
| **v1.2.0** | 2026-09-23 | Claude | Compatibility audit: tested-against updated to 2026.9.3; `voluptuous` → probatio row added. |
| **v1.2.1** | 2026-09-23 | Claude | Added Python row to supported versions; recorded the planned 2025.2.0 minimum for the next release. |
| **v1.3.0** | 2026-09-23 | Claude | Minimum raised from 2024.6.0 to 2025.2.0 (Python 3.13); planned-floor milestone removed. |
| **v1.4.0** | 2026-09-30 | Claude | Compatibility audit: tested-against updated to 2026.9.4 (`pytest-homeassistant-custom-component` 0.13.367); rows for probatio-typed schemas and `const`-module device classes; 2026.10 milestone. |
| **v1.5.0** | 2026-10-28 | Claude | Retroactive compatibility audit: tested-against 2026.10.2 (0.13.373); ledger rows cite `ha_compat_findings_register.md` IDs; rows added for this integration's new exposures. |
| **v1.5.2** | 2026-11-04 | Claude | `HAC-003`: default device info removal corrected from 2028.11 to 2027.11 (developer blog 2026-10-28); Status cells for `HAC-002` and `HAC-003` set by triage. |
| **v1.5.1** | 2026-11-01 | Claude | Compatibility audit: tested-against 2026.10.4 (`pytest-homeassistant-custom-component` 0.13.375). |
