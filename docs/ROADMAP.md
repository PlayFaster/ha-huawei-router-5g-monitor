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

## Maybe

### 5G Mode select, and a sensor to read it back

A select for 5G Mode (SA+NSA, NSA, SA) and a sensor reading it back, built only if the web interface mining identifies the request the router's own 5G Mode dropdown sends.

### New device alert

Raise an event entity when a client the integration has never tracked joins the router, using the entity registry as the record of known clients so that a restart raises no false alerts.

### WiFi band switches and combine toggles

Switches for the router's "5 GHz preferred" and "Wi-Fi band aggregation (MLO)" settings, and one switch per WiFi band, 2.4GHz and 5GHz, which are available only while the bands are separate.

## Blocked

### Router Ethernet mode support

Behavior on a Huawei router that takes its internet from its WAN Ethernet port and has no cellular link: setup succeeds, cellular entities read unknown without raising, health reports no spurious drift, and cellular endpoints are not polled.

**Reason:** A Huawei router can take its internet from its WAN Ethernet port instead of a cellular link.

## Parked

### Guest WiFi settings

Read sensors for the guest WiFi duration, security and time remaining; the Guest WiFi switch unavailable while the 2.4GHz radio is off; and an examination of whether the duration and security can be written.

**Reason:** an owner decision to schedule it.

### HTTPS routers with a router-issued certificate

Setup accepts an https:// address and connects over HTTPS without checking the router's certificate, with no fallback to HTTP, and a verify option for a router with a trusted certificate.

**Reason:** a user request for HTTPS, or a router found to serve HTTPS only.

### Opt out of client tracking at setup

A toggle at setup and in Configure that turns client tracking off completely, so that no client MAC, hostname or IP is collected.

**Reason:** a user request for a complete opt-out of client tracking.

### Remove client trackers unseen beyond a threshold

Remove a client tracker that the router still lists but has not reported connected for a user-set period, and keep it removed until it reconnects.

**Reason:** a user report of an unmanageable number of client trackers.

### Cellular band locking

Lock the router to chosen LTE and 5G bands and return it to automatic selection; whether the router supports it is unmeasured, and it is not planned, for Huawei or ZTE.

**Reason:** an owner decision to offer band locking.

## Declined

### Renaming entities that repeat their sub-device word

Renaming entities whose IDs duplicate their sub-device group word was declined to avoid breaking existing user automations and dashboards.

**Reason:** 2026-08-24: deliberately not renamed as all eight are keeps to prevent breaking existing entity IDs in user automations and dashboards.
