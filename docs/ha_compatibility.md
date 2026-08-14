# Home Assistant Compatibility

What Home Assistant versions this integration supports, which HA APIs it depends on that are changing, and when each one actually bites.

**Reviewed 2026-08-14.**

> [!IMPORTANT]
>
> **Nothing in this document requires action before HA 2027.7.** Everything already deprecated is either unused here or already shimmed. This file exists so that stays true by review rather than by luck — a deprecation with a two-year runway is exactly the kind that gets discovered at removal.

---

## Supported versions

| Type | Note |
| :-- | :-- |
| **Minimum** | 2025.1 (declared in `README.md`) |
| **Tested against** | 2026.8.0 — the version in the development container |
| **Enforced by** | `hacs.json` → `"homeassistant": "2025.1.0"`. HACS refuses the install below it. Added 2026-08-14; before that the README claim was advisory only. |
| **Verified at the minimum?** | **No.** The 2025.1 floor has never been tested. It is a claim, not a measurement. |

**The floor is set by `ConfigEntry.runtime_data` and `ConfigFlowResult`** (both 2024.6), not by anything newer. Every version-sensitive device-registry call is feature-detected in `_compat.py` rather than gated on a version, so the integration is deliberately **floor-free** on that axis: it behaves correctly on 2026.7 and on post-2027.8 alike.

---

## Deprecation ledger

Every HA behavior this integration depends on that is deprecated, moving, or newly available. **"Removed" is the date that matters** — deprecation alone changes nothing at runtime here.

| API / behavior | Deprecated | **Removed** | Our exposure | State |
| :-- | :-- | :-- | :-- | :-- |
| `DeviceInfo.via_device` identifier tuple | 2026.8 | **2027.8** | Sub-device parent links | **Shimmed** — `_compat.via_device_link()` |
| `async_get_device(identifiers=…)` | 2026.8 | **2027.8** | Device lookup | **Shimmed** — `_compat.device_by_identifier()` |
| Implicit coordinator `config_entry` detection | 2024.8 | 2026.8 | `DataUpdateCoordinator` | **Done** — passed explicitly |
| `BaseTrackerEntity.battery_level` | 2026.6 | **2027.7** | None — never overridden | **N/A** |
| `TrackerEntity.location_name` | 2026.6 | **2027.7** | None — we use `ScannerEntity`, which has no such property | **N/A** |
| `ScannerEntity.device_info` returning `None` | **Never deprecated** | **No date** | We override it deliberately | **Decision, not a deadline** — see below |

### New in 2026.6+, arriving for free

These need no code. `ScannerEntity` inherits them from `BaseScannerEntity`:

- **`in_zones` state attribute** — computed automatically for scanner entities.
- **`tracking_type` capability attribute** — reports `connection` for scanner entities.
- **Zone association** — users may associate a tracker with any zone via entity-registry options, not just Home.

The `wittypluck/ha-unifi-network` project needed a migration and an HA ≥ 2026.6 floor for this. **That does not transfer to us**: they were on `TrackerEntity` and moved to `BaseScannerEntity`. This integration has been on `ScannerEntity` — already a `BaseScannerEntity` subclass — since it was written.

---

## Why no deprecation warnings are expected

**The shims do not merely avoid breakage; they avoid the warnings too, by construction rather than by timing.**

- **`via_device`** — HA raises only when **both** `via_device` and `via_device_id` are passed (`device_registry.py`). Passing the tuple alone logs nothing today. `_compat.via_device_link()` returns exactly one of the two, never both.
- **The legacy branch becomes unreachable before it becomes invalid.** Both shims select their path from `_HAS_BY_IDENTIFIER`, a probe of the installed HA:

  | Installed HA | Probe | Branch taken | Status of that API |
  | :-- | :-- | :-- | :-- |
  | ≤ 2026.7 | `False` | Legacy (`via_device` tuple) | Still present |
  | 2026.8 – 2027.7 | `True` | Modern (`via_device_id`) | Legacy deprecated but unused by us |
  | ≥ 2027.8 | `True` | Modern | Legacy removed — **and we never call it** |

  The removed code path is only reachable on versions where it has not been removed. There is no window in which the shim calls something that no longer exists.

- **The device-tracker deprecations cannot warn**, because the properties are never overridden. HA reports these via `__init_subclass__` inspection of overriding subclasses; a class that does not override is not inspected.

**The real risk here is not a warning — it is the shim outliving its purpose.** Once the supported floor reaches 2026.8, the legacy branch is dead code that `test_compat.py` will keep green forever by patching the flag. Retirement condition is recorded below.

---

## Deliberate deviations

### `ScannerEntity.device_info` is overridden

`ScannerEntity.device_info` is decorated `@final` and returns `None` — since 2022. This integration overrides it (`device_tracker.py`, with `# type: ignore[misc]`) so that every tracked client attaches to the **Clients** sub-device.

`@final` is a typing-only constraint; Python does not enforce it, and there is **no deprecation and no removal date**.

**Why it is kept**, and it is not primarily about grouping:

```python
entity_registry_enabled_default = (
    self.mac_address is None
    or self.device_info is not None  # ← our override lands here
    or self._async_mac_address_registered()
)
```

Remove the override and every client tracker becomes **disabled by default** unless that MAC is already registered by another integration — so a Shelly known to HA would appear, while an ordinary laptop would not. That is not the intended behavior.

It also matters from **2026.9**, which makes scanner entities register their own MAC-keyed device _unless_ `device_info` is set. The override opts us out of that, keeping clients on the Clients sub-device.

---

## Retirement conditions

Things to delete when a condition is met, recorded here so they are not carried indefinitely.

| Remove | When |
| :-- | :-- |
| The legacy branch of `_compat.via_device_link()` and `_compat.device_by_identifier()`, plus their `test_compat.py` legacy-branch tests | The supported minimum reaches **2026.8** |
| `_compat.py` entirely | Only if HA reintroduces a single stable API — not expected |
| This ledger's `N/A` rows (`battery_level`, `location_name`) | After **2027.7**, once the properties no longer exist to be avoided |

---

## How to re-check this document

It is not self-maintaining. Re-check when the development container's HA is upgraded, and at minimum when a new HA major arrives:

1. Read the HA developer blog entries since the date at the top.
2. Grep the component for each API in the ledger and confirm the exposure column is still true.
3. Confirm the removal dates against HA source rather than the blog — source carries the authoritative _"will be removed in Home Assistant X"_ strings, and blog posts are not updated when a date slips.
4. Update the **Reviewed** date even when nothing changed. An unchanged date is indistinguishable from an un-reviewed document.

---

## Version Control

| Version | Date | Change |
| :-- | :-- | :-- |
| v1.0.0 | 2026-08-14 | Initial. Created after a review of the HA device-tracker changes (developer blog, 2026-06-15) established that **none of them require action here** — both deprecated properties belong to classes this integration does not use, and the new `in_zones` / `tracking_type` / zone-association features arrive automatically through `ScannerEntity`. Records the two shimmed device-registry APIs with their **2027.8** removal dates, and why neither will emit a warning: the legacy branch is unreachable on every version where the API has been removed. Records the `ScannerEntity.device_info` override as a deliberate deviation rather than a deprecation, with the `entity_registry_enabled_default` consequence that makes removing it the wrong move. Notes that the declared 2025.1 minimum is **unenforced and untested**. |
