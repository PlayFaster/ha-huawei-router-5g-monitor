# Roadmap: Huawei Router 5G Monitor

Forward plans, deferred decisions, and declined directions for the Huawei 5G Router integration. Structure follows `roadmap_format.md`.

**Reviewed 2026-08-14** against the PlayFaster Custom Component Development Standards.

> [!NOTE]
>
> **This file holds features only.**
>
> Chores — testing work, tooling, lint, refactors, version conventions, bug fixes — do **not** belong here at any stage, however large. They go to `x_proj_chores.md` /shared/SharedNotes/issues/x_project/x_proj_chores.md or to the project's `status_plan.md`. A chore that is already finished does not earn a place in **Done** by having been finished.
>
> **A roadmap item that gets done moves to the Done group below.** Work that was never on the roadmap is not added there once complete — that is what [`changelog_local.md`](changelog_local.md) is for, and it remains the authoritative history of everything shipped.

---

## Done

Items that were on this roadmap and were then built. **Membership is by provenance, not by shipping** — a feature that shipped without ever appearing here does not belong in this group.

| Item                            | Where it landed                                 |
| :------------------------------ | :---------------------------------------------- |
| Dynamic Polling Interval Slider | Shipped as the `polling_interval` number entity |

---

## Maybe

### Per-endpoint strike budgets

The coordinator holds a single failure counter for the whole fetch. `api.get_data()` already tolerates individual endpoint failures by omitting them, and the Integration Health sensor now reports that — but there is no per-endpoint backoff, so a permanently dead endpoint is retried on every poll forever.

Strengthened 2026-08-16 by the ecosystem review in `.notes/info/other_huawei_projects/analysis_and_learnings.md`, which reports ISP-customised firmwares (Three UK, Vodafone) locking whole endpoint families behind `100003: No rights`. Two things make this concrete rather than theoretical:

- The reference H165 already returns a permanent `100002: No support` for `monitoring.daily_data_limit`, and the fix was to **hand-remove it from the fetch list** — a manual, per-device answer to what is really a per-firmware problem. `api.py` says so in a comment.
- `100002` and `100003` are distinguishable from a transient failure, so suppression can key off the response code rather than guessing from a strike count. `_endpoint_strikes` in `coordinator.py` already counts consecutive per-endpoint misses; the counter exists, nothing consumes it for backoff.

Any suppression must re-probe periodically — `100003` can change with a firmware update or a re-login at a different auth level.

- **Value**: ⭐⭐
- **Effort**: Medium
- **Trigger**: Evidence that a persistently failing endpoint is costing meaningful poll time on real hardware, **or** a user report from an ISP-locked device where a hand-edit of the fetch list is not available to them.

### New device alert

Notify the user when a client that has never been seen before joins the router — an unrecognised device on the network is the security event a router integration is best placed to report.

The inputs already exist: `lan_host_info` and `wlan_host_list` are polled every cycle and `device_tracker` entities are created dynamically from them, so "first appearance of this MAC" is a question the coordinator can already answer. What is missing is the notion of **known**: without persisted state every restart is a cold start and every device looks new.

Shape to decide — a `binary_sensor`, an HA event for automations to catch, or a persistent notification. An event is the most composable and the least opinionated about how the user wants to be told.

- **Value**: ⭐⭐⭐
- **Effort**: Medium — the detection is easy, the persistence and the first-run behaviour are the work.
- **Trigger**: Agreement on the persistence mechanism, which is shared with the entry below.

### Retire long-unseen device trackers

**The router, not this integration, is why a user ends up with too many `device_tracker` entities.** It retains clients that have been away for **at least four months**, and HRM faithfully reports everything the router lists. Those stale clients are removable only by hand in the router's own web GUI.

This is the boundary of `cleanup_unused_entities`: that action and its button remove entities the **router** has already dropped. They cannot remove a client the router still lists, because from HRM's side it is a live, present record. A user with a crowded Clients device is looking at a router-side condition.

The proposal is a service that marks a tracker **unavailable** once it has gone unseen for a user-set period, without deleting anything.

Two things to settle first:

- **Persistence.** Last-seen times must survive a restart, so this needs stored state — the same requirement as the new-device alert above. Both entries should be designed together or neither.
- **Reappearance.** A retired device that comes back must recover cleanly. Unavailable is the right state precisely because it is reversible, but the transition needs deciding: silently restore, or treat it as a new arrival and alert.

- **Value**: ⭐⭐
- **Effort**: Medium — persistence is the bulk of it; the threshold comparison is trivial.
- **Trigger**: A user report of an unmanageable Clients device, **or** the new-device alert going ahead and paying for the stored state anyway.

### Separate 2.4GHz and 5GHz WiFi switches

All three controls exist in the router GUI: 2.4GHz on/off, 5GHz on/off, and the combine-bands toggle that puts both radios on one SSID.

**Check the radio-versus-SSID distinction before estimating this.** HRM's master WiFi switch writes `wlan/status-switch-settings` and flips `wifienable` on **every** radio; it does not touch the per-SSID flags in `wlan/multi-basic-settings`, because those flags are gated by the radio and writing them while the radio is off changes nothing observable. Per-band control means writing that same block **selectively** rather than uniformly — a variation on a proven write path, not new ground. See `docs/huawei_how_to_access.md`.

Band-combine is the unknown: which block owns it has not been established, and `wlan.wlandbho` (`DbhoEnable`) is band steering, which is a related but different feature.

- **Value**: ⭐⭐
- **Effort**: Medium — two switches are a small extension of an existing write; the combine toggle needs a probe first.
- **Trigger**: A probe confirming which block owns band-combine, and that a selective radio write holds.

---

## Blocked

### WLAN band locking write capability

Write commands to force specific 5G/LTE bands.

- **Value**: ⭐⭐⭐
- **Effort**: High once unblocked
- **Blocked by**: Physical router hardware API validation. Releasing untested write commands to a cellular modem risks disconnecting the gateway permanently.

---

## Revisit

### Guest WiFi SSID write validation

SSID write operations for guest network configurations where multi-SSID setups are present.

- **Trigger**: A second test unit with guest SSID hardware configurations is added to the dev setup.

---

## Declined

### Renaming entities that repeat their sub-device word

Four entities restate their group in their name — `total_data` in Data, `signal_bars` and `signal_bars_nr` in Signal, and `sms_storage_full` in SMS — so their entity IDs read `..._data_total_data` and so on.

**Deliberately not renamed.** Home Assistant never renames an existing `entity_id`, so the only beneficiary would be a new install, while anyone referencing the current friendly name in an automation or dashboard gets a silent break. `zte_router_5g` kept two doubled IDs for the same reason. The convention applies to **new** entities from here on.

---

## Summary

| Item                                   | Value  | Effort         |
| :------------------------------------- | :----- | :------------- |
| WLAN band locking write capability     | ⭐⭐⭐ | High (Blocked) |
| New device alert                       | ⭐⭐⭐ | Medium         |
| Per-endpoint strike budgets            | ⭐⭐   | Medium         |
| Retire long-unseen device trackers     | ⭐⭐   | Medium         |
| Separate 2.4GHz and 5GHz WiFi switches | ⭐⭐   | Medium         |

---

## Version Control

| Version | Date | Change |
| :-- | :-- | :-- |
| v3.0.0 | 2026-08-16 | **Scope corrected to features only, and the file cleared of everything else.** Two rules were wrong here and both are fixed: this is not a chore register, and there **is** a **Done** group — a roadmap item that ships moves into it, by provenance. `roadmap_format.md` was not the source of either error; it defines Done as the first of six groups and sets membership by provenance. The misreadings were local to this file. **Four entries deleted as chores, not features:** _Mutation testing_ (complete; belongs in `x_proj_chores.md`), _The `manifest.json` / changelog version convention_ (no convention needed — the manifest is pegged to the working version with no dev tracking), _The eight `FREQUENCY` entities and the unit selector_ (fixed; `state_class` removal is recorded in `changelog_local.md`, and a ZTE chore was raised for the same class of problem) and _Real-time SMS notifications via webhooks_ (the router pushes nothing, and the integration already fires an event — the entry was noise). **Done** holds only _Dynamic Polling Interval Slider_; the three chores briefly restored earlier the same day were removed again under the features-only rule. **To Be Done** is omitted, having no members. **Three feature entries added under Maybe** from `.notes/todo.md`: _New device alert_, _Retire long-unseen device trackers_ and _Separate 2.4GHz and 5GHz WiFi switches_ — the first two share a persistence requirement and are marked to be designed together, and the tracker entry records that away clients are retained by the router for four months or more, which is outside what `cleanup_unused_entities` can reach. **_Per-endpoint strike budgets_ strengthened** with ISP-lockout evidence and a widened trigger. |
| v2.1.0 | 2026-08-14 | **Two entries removed as shipped**, per the format's direction not to keep a Done group. _Write-classification register and hardware check_ landed in `51835b6`. _Diagnostics verified against a real download_ closed in `023ace4`, after a live capture audit found four leaks the rewrite had not. |
| v2.0.0 | 2026-08-14 | Reconciled against the code and against `roadmap_format.md`. Removed the **Done** group, per the format's direction not to backfill one from the changelog. **Two entries were stale and are removed:** "Dynamic Polling Interval Slider" had already shipped as the `polling_interval` number entity, and "Static Test Sweeps Implementation" landed in `[1.1.3-dev10]`–`[1.1.3-dev14]`. Added the write-classification register, the first mutation run, per-endpoint strike budgets, the blocked diagnostics verification, the manifest/changelog version convention, and the `FREQUENCY` unit-selector issue previously recorded only in `AGENTS.md`. Recorded the deliberate decision **not** to rename the four entities that repeat their sub-device word. Converted asterisk bullets to dashes so the file passes `markdownlint`, which it had never done. |
| v1.0.0 | 2026-08-08 | Initial baseline version. |
