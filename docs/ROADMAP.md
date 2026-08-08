# Roadmap: Huawei Router 5G Monitor

This document outlines the forward plans, deferred decisions, and declined directions for the Huawei 5G Router integration.

**Reviewed 2026-08-08** against the PlayFaster Custom Component Development Standards.

---

## Done

- **Project baseline** — added 2026-07-20. Initial publication of custom component integrations.

---

## To Be Done

### Static Test Sweeps Implementation
Standardize the testing architecture by porting static sweeps from other components to enforce recorder hygiene, icon coverage, and translation validations.
* **Value**: ⭐⭐⭐
* **Effort**: Low

---

## Maybe

### Dynamic Polling Interval Slider
Allow the user to dynamically adjust the API polling interval from the integrations configuration options flow.
* **Value**: ⭐⭐
* **Effort**: Medium
* **Trigger**: User requests for higher frequency updates of signal metrics.

---

## Blocked

### Wlan band locking write capability
Write commands for forcing specific 5G/LTE bands.
* **Value**: ⭐⭐⭐
* **Effort**: High once unblocked
* **Blocked by**: Physical router hardware API validation. Releasing untested write commands on cellular modems risks disconnecting the gateway permanently.

---

## Revisit

### Guest Wi-Fi SSID write validation
Revisit SSID write operations for guest network configurations when multi-SSID setups are present.
* **Trigger**: A second test unit with guest SSID hardware configurations is added to the dev setup.

---

## Declined

### Real-time SMS notifications via Webhooks
Not implementing. Home Assistant provides native automation triggers on state changes (such as `last_sms`). Routing these through an internal webhook system adds code complexity with no functional benefit over standard state triggers.

---

## Summary

| Item | Value | Effort |
| :--- | :--- | :--- |
| Static Test Sweeps Implementation | ⭐⭐⭐ | Low |
| Wlan band locking write capability | ⭐⭐⭐ | High (Blocked) |
| Dynamic Polling Interval Slider | ⭐⭐ | Medium |

---

## Version Control

- **v1.0.0** (2026-08-08) — Initial baseline version.
