<!-- Generated from task queues by .workbench/generate_roadmap.py. Do not edit by hand. -->
# Roadmap: ha-huawei-router-5g-monitor

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

## To Be Done

### Router Ethernet mode support

Behavior on a router that takes its internet from its WAN Ethernet port and has no cellular link: setup succeeds, cellular entities read unknown without raising, and health reports no spurious drift.

## Maybe

### 5G Mode select, and a sensor to read it back

A dropdown select for 5G Mode (SA+NSA, NSA, SA) and a dedicated sensor to read back current mode.

### HTTPS routers with a self-signed certificate

Allow connection to routers over HTTPS with user-configurable certificate verification.

### New device alert

Notify the user when a client that has never been seen before joins the router.

### Opt out of client tracking at setup

A single toggle at setup and in Configure to turn off the Clients group completely for privacy and entity hygiene.

### Retire long-unseen device trackers

Mark device trackers unavailable when unseen for a user-set period rather than accumulating router-cached clients indefinitely.

### Separate 2.4GHz and 5GHz WiFi switches

Per-band 2.4GHz and 5GHz WiFi control switches and band-combine toggle.

## Blocked

### WLAN band locking write capability

Write commands to force specific 5G and LTE cellular bands.

**Reason:** Physical router hardware API validation. Releasing untested write commands to a cellular modem risks disconnecting the gateway permanently.

## Parked

### Guest WiFi SSID write validation

SSID write operations for guest network configurations in multi-SSID setups.

**Reason:** A second test unit with guest SSID hardware configurations is added to the dev setup.

### Variant API paths for other models

Fallback table of alternative API endpoint spellings when models reject primary resource paths.

**Reason:** A diagnostics download or sweep from a model other than the H165-383 shows a usual path refused and a variant answering.

## Declined

### Renaming entities that repeat their sub-device word

Renaming entities whose IDs duplicate their sub-device group word was declined to avoid breaking existing user automations and dashboards.

**Reason:** 2026-08-24: deliberately not renamed as all eight are keeps to prevent breaking existing entity IDs in user automations and dashboards.
