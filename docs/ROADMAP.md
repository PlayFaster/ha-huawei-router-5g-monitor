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

Strengthened 2026-08-16 by the ecosystem review in `.notes/info/other_huawei_projects/analysis_and_learnings.md`, which reports ISP-customized firmwares (Three UK, Vodafone) locking whole endpoint families behind `100003: No rights`. Two things make this concrete rather than theoretical:

- The reference H165 already returns a permanent `100002: No support` for `monitoring.daily_data_limit`, and the fix was to **hand-remove it from the fetch list** — a manual, per-device answer to what is really a per-firmware problem. `api.py` says so in a comment.
- `100002` and `100003` are distinguishable from a transient failure, so suppression can key off the response code rather than guessing from a strike count. `_endpoint_strikes` in `coordinator.py` already counts consecutive per-endpoint misses; the counter exists, nothing consumes it for backoff.

Any suppression must re-probe periodically — `100003` can change with a firmware update or a re-login at a different auth level.

- **Value**: ⭐⭐
- **Effort**: Medium
- **Trigger**: Evidence that a persistently failing endpoint is costing meaningful poll time on real hardware, **or** a user report from an ISP-locked device where a hand-edit of the fetch list is not available to them.

### New device alert

Notify the user when a client that has never been seen before joins the router — an unrecognized device on the network is the security event a router integration is best placed to report.

The inputs already exist: `lan_host_info` and `wlan_host_list` are polled every cycle and `device_tracker` entities are created dynamically from them, so "first appearance of this MAC" is a question the coordinator can already answer. What is missing is the notion of **known**: without persisted state every restart is a cold start and every device looks new.

Shape to decide — a `binary_sensor`, an HA event for automations to catch, or a persistent notification. An event is the most composable and the least opinionated about how the user wants to be told.

- **Value**: ⭐⭐⭐
- **Effort**: Medium — the detection is easy, the persistence and the first-run behavior are the work.
- **Trigger**: Agreement on the persistence mechanism, which is shared with the entry below.

### Retire long-unseen device trackers

**The router, not this integration, is why a user ends up with too many `device_tracker` entities.** It keeps clients listed **long after they have gone**, and HRM faithfully reports everything the router lists. Those stale clients are removable only by hand in the router's own web GUI.

This is the boundary of `cleanup_unused_entities`: that action and its button remove entities the **router** has already dropped. They cannot remove a client the router still lists, because from HRM's side it is a live, present record. A user with a crowded Clients device is looking at a router-side condition.

The proposal is a service that marks a tracker **unavailable** once it has gone unseen for a user-set period, without deleting anything.

Two things to settle first:

- **Persistence.** Last-seen times must survive a restart, so this needs stored state — the same requirement as the new-device alert above. Both entries should be designed together or neither.
- **Reappearance.** A retired device that comes back must recover cleanly. Unavailable is the right state precisely because it is reversible, but the transition needs deciding: silently restore, or treat it as a new arrival and alert.

- **Value**: ⭐⭐
- **Effort**: Medium — persistence is the bulk of it; the threshold comparison is trivial.
- **Trigger**: A user report of an unmanageable Clients device, **or** the new-device alert going ahead and paying for the stored state anyway.

### Opt out of client tracking at setup

A single toggle, offered at setup and in Configure, that turns off the Clients group: no `device_tracker` entities, no Total/Wired/WiFi Connected sensors, and the `lan_host_info` and `wlan_host_list` fetches skipped.

**Why this group and not the others.** Every sub-device could in principle get a toggle, and most should not — Home Assistant's own per-device disable already hides entities, and the README documents it under _Tailoring What's Monitored_. A setup question is a tax on every first-time installer, so it has to buy something that disabling cannot.

**The endpoint saving is not that thing, and the numbers say so plainly.** Measured against the reference H165-383 on 2026-08-17, three consecutive polls:

| Measure               | Value                     |
| :-------------------- | :------------------------ |
| Endpoints per poll    | **26**, sequential        |
| Wall time per poll    | **1.05 / 1.06 / 1.07 s**  |
| Per endpoint          | **~41 ms**                |
| Default poll interval | 180 s                     |
| Duty cycle            | **~0.6%** of elapsed time |

So dropping a two-endpoint group saves **about 80 ms every three minutes** — 0.04% of the interval. Twenty-six sounds alarming and is not: the router answers each call in the time a page takes to paint. **Any argument for a group toggle that rests on "fewer API calls" is arguing about 80 ms, and should be rejected on that basis.** For SMS and WiFi that is the whole case, and their entity counts are fixed at 18 and 7, so nothing grows.

**Clients is different in two ways that matter:**

- **It is the integration's privacy surface.** Each tracked client publishes a MAC address, a hostname and an IP. That is the one thing here a user might want never collected, rather than merely hidden — and disabling an entity does not stop it being created and populated.
- **It is the only group whose entity count is unbounded.** One entity per client the router has ever seen, and the router keeps clients listed long after they are gone. A user in bridge mode, or with another router handling DHCP, has no use for any of it.

Neither reason is about poll time. **If the endpoint saving were the only argument, this entry would not exist.**

**Settle this against _Retire long-unseen device trackers_ before building either.** Both address the same entity sprawl from opposite ends — one prevents creation, the other retires what exists — and shipping one without deciding the other risks two overlapping mechanisms.

The cleanup half is already in place: `cleanup_unused_entities` exists as both an action with `dry_run` and a button, so option-group orphans would extend the existing planner rather than needing a new module.

- **Value**: ⭐⭐
- **Effort**: Medium — a config-flow field, gating in two platforms, and a fetch skip. The interaction above is the decision, not the code.
- **Trigger**: A user who wants client tracking off entirely rather than hidden, **or** the tracker-retirement entry being taken up.

### Separate 2.4GHz and 5GHz WiFi switches

All three controls exist in the router GUI: 2.4GHz on/off, 5GHz on/off, and the combine-bands toggle that puts both radios on one SSID.

**Check the radio-versus-SSID distinction before estimating this.** HRM's master WiFi switch writes `wlan/status-switch-settings` and flips `wifienable` on **every** radio; it does not touch the per-SSID flags in `wlan/multi-basic-settings`, because those flags are gated by the radio and writing them while the radio is off changes nothing observable. Per-band control means writing that same block **selectively** rather than uniformly — a variation on a proven write path, not new ground. See `docs/huawei_how_to_access.md`.

Band-combine is the unknown: which block owns it has not been established, and `wlan.wlandbho` (`DbhoEnable`) is band steering, which is a related but different feature.

- **Value**: ⭐⭐
- **Effort**: Medium — two switches are a small extension of an existing write; the combine toggle needs a probe first.
- **Trigger**: A probe confirming which block owns band-combine, and that a selective radio write holds.

---

### 5G Mode select, and a sensor to read it back

The router GUI offers a **5G Mode** dropdown with three values — **SA+NSA**, **NSA**, **SA** — and it is available whether Preferred Network Mode is Auto or 5G Only, as long as the router is working in 5G. Setting **SA** can cause signal loss; the owner's expectation is that the router eventually falls back to 4G, which is an observation to confirm rather than a documented behavior.

**The write path does not exist yet, and neither does the read path.** Both were checked before this entry was written:

- **`huawei-lte-api` 2.0.1 has nothing for it.** A search of the whole installed package for `nrmode`, `nr5g`, `nsa` and `sa` returns no match, and `api/Net.py`'s thirteen methods cover `net-mode`, `network`, `register`, `plmn`, `cell_info`, `csps_state` and `reconnect` — none of them this.
- **The polled `net/net-mode` block does not carry it.** On the reference H165-383 it returns exactly `NetworkMode`, `NetworkBand`, `LTEBand`, `networkOption` and `LTEBandOption`. There is no SA/NSA field and no `NRBand`, so nothing in the current twenty-six-endpoint poll can populate a sensor either.

So the first task is **discovery, not implementation**: watch the router's own web interface make the change and record the endpoint and payload it posts. That is how `dialup/dial` with `Action: 0` and the `wlan/status-switch-settings` round-trip were both established, in each case after the library proved insufficient — and both now reach the router through `_session.post_set` under a reasoned `# noqa: SLF001`.

**Two sensors are named in this item and only one is new.** A `preferred_network_mode` sensor already exists — a diagnostic reading `net_mode.NetworkMode` back, whose `about` note already says a disagreement with the control means the router refused or altered the request. A **5G Mode** sensor would be new, and is blocked on the same discovery as the select.

**Treat the write as ATTENDED when it is built.** It re-registers the radio, so it belongs in the same tier as Preferred Network Mode: `NET_MODE_SETTLE` before any read-back, confirmation from the entity rather than inside the API lock, and no assumption that the POST answers cleanly — the router sometimes replies `-1: Unknown` to a mode write it has applied, and sometimes does not.

- **Value**: ⭐⭐
- **Effort**: Medium — small once the endpoint is known; the whole cost is the probe.
- **Trigger**: A capture of the endpoint and payload the router's own GUI posts for this dropdown.

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

**Eight** entities restate their group in their name, so their entity IDs read `..._data_total_data` and so on. The list below is the complete scan, taken on 2026-08-24 across all 159 entity descriptions by matching each `strings.json` name against its group's `SUB_DEVICE_LABELS` label — the earlier count of four was a partial reading and named only the first, third, fourth and sixth rows.

| Entity key | Platform | Group | Name |
| :-- | :-- | :-- | :-- |
| `total_data` | Sensor | Data | Total Data |
| `data_allowance` | Sensor | Data | Data Allowance |
| `data_plan_enabled` | Binary sensor | Data | Data Plan Enabled |
| `signal_bars` | Sensor | Signal | Signal Bars |
| `signal_bars_nr` | Sensor | Signal | 5G Signal Bars |
| `poor_signal` | Binary sensor | Signal | Poor Signal |
| `sms_storage_full` | Binary sensor | SMS | SMS Storage Full |
| `wifi` | Switch | WiFi | WiFi |

**Deliberately not renamed — all eight are keeps.** Home Assistant never renames an existing `entity_id`, so the only beneficiary would be a new install, while anyone referencing the current friendly name in an automation or dashboard gets a silent break. `zte_router_5g` kept two doubled IDs for the same reason. The convention applies to **new** entities from here on.

Recorded against cross-project chore `C-030`, whose requirement is the scan and the recorded keeps rather than any rename.

---

## Summary

| Item                                   | Value  | Effort         |
| :------------------------------------- | :----- | :------------- |
| WLAN band locking write capability     | ⭐⭐⭐ | High (Blocked) |
| New device alert                       | ⭐⭐⭐ | Medium         |
| Per-endpoint strike budgets            | ⭐⭐   | Medium         |
| Retire long-unseen device trackers     | ⭐⭐   | Medium         |
| Opt out of client tracking at setup    | ⭐⭐   | Medium         |
| Separate 2.4GHz and 5GHz WiFi switches | ⭐⭐   | Medium         |
| 5G Mode select and read-back sensor    | ⭐⭐   | Medium         |

---

## Version Control

| Version | Date | Change |
| :-- | :-- | :-- |
| v3.3.0 | 2026-08-24 | **The _Renaming entities that repeat their sub-device word_ entry corrected from four entities to eight**, and the keeps recorded as a table. The entry had named `total_data`, `signal_bars`, `signal_bars_nr` and `sms_storage_full` since v2.0.0. A full scan on 2026-08-24 — every one of the 159 entity descriptions, matching its `strings.json` name against its group's `SUB_DEVICE_LABELS` label rather than against the description key — found four more: `data_allowance`, `data_plan_enabled`, `poor_signal` and the `wifi` switch, whose name is the label itself. **The decision is unchanged**; all eight are keeps for the same reason, and nothing is renamed. This is the deliverable of cross-project chore `C-030`, which asks for the scan and the recorded keeps rather than a rename, and it is what let that chore's Huawei cell settle. |
| v3.2.0 | 2026-08-19 | **Added _5G Mode select, and a sensor to read it back_** under Maybe, at the owner's request. The router GUI offers SA+NSA / NSA / SA and exposes it whether Preferred Network Mode is Auto or 5G Only. **The write path was validated before the entry was written and does not exist**: `huawei-lte-api` 2.0.1 has no method for it anywhere in the package, and the polled `net/net-mode` block returns only `NetworkMode`, `NetworkBand`, `LTEBand`, `networkOption` and `LTEBandOption` — so there is no read path either, and no sensor could be populated from the current poll. The entry therefore leads with discovery: capture what the router's own web interface posts, the method that established `dialup/dial` and `wlan/status-switch-settings` once the library proved insufficient. **One correction to the request as made**: it asked for read-back sensors for both Preferred Network Mode and 5G Mode, and the first already exists — a diagnostic reading `net_mode.NetworkMode` whose `about` note already covers the control-versus-state disagreement. Only the 5G Mode sensor is new. |
| v3.1.0 | 2026-08-17 | **Added _Opt out of client tracking at setup_** under Maybe, from the `setup_cleanup_options.md` assessment. That guide predicted Huawei was "likely most applicable" for sensor-group toggles; on inspection only one group qualifies. SMS and WiFi fail the tax-on-every-installer test — Home Assistant's own per-device disable already hides them, and the saving is two endpoints out of twenty-six on a poll measured at about one second. Clients passes on two counts a toggle can serve and disabling cannot: it is the integration's privacy surface (MAC, hostname and IP per client) and the only group whose entity count is unbounded. The entry records its dependency on _Retire long-unseen device trackers_, since both address the same sprawl from opposite ends. |
| v3.0.0 | 2026-08-16 | **Scope corrected to features only, and the file cleared of everything else.** Two rules were wrong here and both are fixed: this is not a chore register, and there **is** a **Done** group — a roadmap item that ships moves into it, by provenance. `roadmap_format.md` was not the source of either error; it defines Done as the first of six groups and sets membership by provenance. The misreadings were local to this file. **Four entries deleted as chores, not features:** _Mutation testing_ (complete; belongs in `x_proj_chores.md`), _The `manifest.json` / changelog version convention_ (no convention needed — the manifest is pegged to the working version with no dev tracking), _The eight `FREQUENCY` entities and the unit selector_ (fixed; `state_class` removal is recorded in `changelog_local.md`, and a ZTE chore was raised for the same class of problem) and _Real-time SMS notifications via webhooks_ (the router pushes nothing, and the integration already fires an event — the entry was noise). **Done** holds only _Dynamic Polling Interval Slider_; the three chores briefly restored earlier the same day were removed again under the features-only rule. **To Be Done** is omitted, having no members. **Three feature entries added under Maybe** from `.notes/todo.md`: _New device alert_, _Retire long-unseen device trackers_ and _Separate 2.4GHz and 5GHz WiFi switches_ — the first two share a persistence requirement and are marked to be designed together, and the tracker entry records that away clients are retained by the router for four months or more, which is outside what `cleanup_unused_entities` can reach. **_Per-endpoint strike budgets_ strengthened** with ISP-lockout evidence and a widened trigger. |
| v2.1.0 | 2026-08-14 | **Two entries removed as shipped**, per the format's direction not to keep a Done group. _Write-classification register and hardware check_ landed in `51835b6`. _Diagnostics verified against a real download_ closed in `023ace4`, after a live capture audit found four leaks the rewrite had not. |
| v2.0.0 | 2026-08-14 | Reconciled against the code and against `roadmap_format.md`. Removed the **Done** group, per the format's direction not to backfill one from the changelog. **Two entries were stale and are removed:** "Dynamic Polling Interval Slider" had already shipped as the `polling_interval` number entity, and "Static Test Sweeps Implementation" landed in `[1.1.3-dev10]`–`[1.1.3-dev14]`. Added the write-classification register, the first mutation run, per-endpoint strike budgets, the blocked diagnostics verification, the manifest/changelog version convention, and the `FREQUENCY` unit-selector issue previously recorded only in `AGENTS.md`. Recorded the deliberate decision **not** to rename the four entities that repeat their sub-device word. Converted asterisk bullets to dashes so the file passes `markdownlint`, which it had never done. |
| v1.0.0 | 2026-08-08 | Initial baseline version. |
