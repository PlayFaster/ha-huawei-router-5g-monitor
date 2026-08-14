# Roadmap: Huawei Router 5G Monitor

Forward plans, deferred decisions, and declined directions for the Huawei 5G Router integration. Structure follows `roadmap_format.md`.

**Reviewed 2026-08-14** against the PlayFaster Custom Component Development Standards.

> [!NOTE]
>
> There is no **Done** group. Completed work is recorded in [`changelog_local.md`](changelog_local.md), which is the authoritative history; backfilling a second copy here gives it somewhere to rot.

---

## To Be Done

### Write-classification register and hardware check

A register of every control that commands the router, classified by reversibility, plus a `scripts/hardware_check.py` able to exercise the safe tier against real hardware. `zte_router_5g` is the model — it exists there because two controls shipped broken for weeks purely because nobody used them. Huawei's write surface is wider than UniFi's: SMS send and delete, reboot, mobile-data switch, guest-WiFi switch, network-mode select and the polling-interval number.

- **Value**: ⭐⭐⭐
- **Effort**: Medium for the register and its unit tests; the attended hardware tier needs a real router and an owner's decision.
- **Note**: the moment a `scripts/` directory exists, `also_copy = scripts/` in the shared `setup.cfg` stops being inert — mutmut copies only `source_paths` and `tests` into `mutants/`, so a test importing from `scripts/` fails to collect there without it.

### Mutation testing — first run and triage

`.validate/mutmut_modules.txt` decided by measurement, then a run and a triage pass. `helpers.py` (99 statements, 46 branches, pure functions with no injected collaborator) is the obvious first candidate.

- **Value**: ⭐⭐⭐
- **Effort**: Medium — the module list is the decision, the run is mechanical.
- **Note**: run it exactly twice per cycle. Editing any test file invalidates the whole cached run.

---

## Maybe

### Per-endpoint strike budgets

The coordinator holds a single failure counter for the whole fetch. `api.get_data()` already tolerates individual endpoint failures by omitting them, and the Integration Health sensor now reports that — but there is no per-endpoint backoff, so a permanently dead endpoint is retried on every poll forever.

- **Value**: ⭐⭐
- **Effort**: Medium
- **Trigger**: Evidence that a persistently failing endpoint is costing meaningful poll time on real hardware.

---

## Blocked

### WLAN band locking write capability

Write commands to force specific 5G/LTE bands.

- **Value**: ⭐⭐⭐
- **Effort**: High once unblocked
- **Blocked by**: Physical router hardware API validation. Releasing untested write commands to a cellular modem risks disconnecting the gateway permanently.

### Diagnostics verified against a real download

`diagnostics.py` was rewritten in `[1.1.3-dev12]` from key-name redaction to a layered recursive scrubber, and is unit-tested against a realistic synthetic payload. It is **not yet verified against a regenerated download containing real router data**.

- **Value**: ⭐⭐⭐ — this is a privacy surface, and the family's known blind spot.
- **Effort**: Low once unblocked.
- **Blocked by**: Access to a live instance configured against a real router, with the optional data (SMS, connected clients) actually populated. `unifi_network_monitor` held `diagnostics: done` across two full IQS scans while leaking identifiers, and **reading the code is what produced both clean verdicts** — so this stays open until a real capture has been inspected.

---

## Revisit

### Guest WiFi SSID write validation

SSID write operations for guest network configurations where multi-SSID setups are present.

- **Trigger**: A second test unit with guest SSID hardware configurations is added to the dev setup.

### The `manifest.json` / changelog version convention

`manifest.json` reads `1.1.3-dev7` while the changelog is at `[1.1.3-dev14]`. The two sibling projects resolved the same divergence in opposite directions — `zte_router_5g` bumps the manifest mid-cycle deliberately, `unifi_network_monitor` sets the manifest to the release version with no dev tracking — so there is no default to fall back on.

- **Trigger**: An owner decision on which convention this project follows.

### The eight `FREQUENCY` entities and the unit selector

They do not show the HA unit selector, staying fixed on kHz or MHz. Investigation has ruled out `diagnostic` vs `sensor` category and the presence of `state_class` as causes.

- **Trigger**: A Home Assistant release note touching unit conversion for frequency, or a user report that makes it more than cosmetic.

---

## Declined

### Real-time SMS notifications via webhooks

Not implementing. Home Assistant provides native automation triggers on state changes (such as `last_sms`) and this integration fires a `huawei_router_5g_sms_received` event. Routing these through an internal webhook system adds code complexity with no functional benefit over standard state and event triggers.

### Renaming entities that repeat their sub-device word

Four entities restate their group in their name — `total_data` in Data, `signal_bars` and `signal_bars_nr` in Signal, and `sms_storage_full` in SMS — so their entity IDs read `..._data_total_data` and so on.

**Deliberately not renamed.** Home Assistant never renames an existing `entity_id`, so the only beneficiary would be a new install, while anyone referencing the current friendly name in an automation or dashboard gets a silent break. `zte_router_5g` kept two doubled IDs for the same reason. The convention applies to **new** entities from here on.

---

## Summary

| Item | Value | Effort |
| :-- | :-- | :-- |
| Write-classification register and hardware check | ⭐⭐⭐ | Medium (hardware tier blocked) |
| Mutation testing — first run and triage | ⭐⭐⭐ | Medium |
| WLAN band locking write capability | ⭐⭐⭐ | High (Blocked) |
| Diagnostics verified against a real download | ⭐⭐⭐ | Low (Blocked) |
| Per-endpoint strike budgets | ⭐⭐ | Medium |

---

## Version Control

| Version | Date | Change |
| :-- | :-- | :-- |
| v2.0.0 | 2026-08-14 | Reconciled against the code and against `roadmap_format.md`. Removed the **Done** group, per the format's direction not to backfill one from the changelog. **Two entries were stale and are removed:** "Dynamic Polling Interval Slider" had already shipped as the `polling_interval` number entity, and "Static Test Sweeps Implementation" landed in `[1.1.3-dev10]`–`[1.1.3-dev14]`. Added the write-classification register, the first mutation run, per-endpoint strike budgets, the blocked diagnostics verification, the manifest/changelog version convention, and the `FREQUENCY` unit-selector issue previously recorded only in `AGENTS.md`. Recorded the deliberate decision **not** to rename the four entities that repeat their sub-device word. Converted asterisk bullets to dashes so the file passes `markdownlint`, which it had never done. |
| v1.0.0 | 2026-08-08 | Initial baseline version. |
