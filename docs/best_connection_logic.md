# Best Connection Sensor — Logic Reference

## Overview

The **Best Connection** binary sensor (`best_connection`) evaluates whether the router is delivering a high-quality NSA (Non-Standalone) 5G connection. It replaces a simple "is 5G NR active?" flag with a 3-stage gate that checks NR band assignment, LTE anchor health, and 5G leg health independently.

Entity: `binary_sensor.<device>_signal_best_connection`

---

## Why Not a Simple 5G Active Check?

The original stub checked `sc_band` and `nrrsrp` for presence. Two problems on the H165-383:

1. **`sc_band` returns null** — always null on this firmware; caused the sensor to be permanently OFF.
2. **`network_type` reports `"LTE"` in NSA mode** — the H165-383 returns `"LTE"` as `network_type` even when a 5G NR carrier is actively in use alongside the LTE anchor. Any logic gated on `network_type contains "5G"` will permanently fail on this hardware.

---

## Stage 1 — NR Band Assignment Gate

```python
band = signal.get("band") or ""
if "(N" not in str(band):
    return False
```

**What it checks:** Whether the composite band string contains an NR band label (e.g., `(N28)`).

**Example band string:** `"20MHz@500(B1) + 15MHz@1875(B3) + 10MHz@6200(B20) + 10MHz@152690(N28)"`

**Why this field:** The `band` field is populated consistently on the H165-383. LTE-only segments use the form `(BXX)`; NR segments use `(NXX)`. The presence of `(N` is a stable, configuration-level indicator that an NR band is assigned — more idle-stable than instantaneous signal metrics (`nrrsrp`, etc.) that may go `None` when the NR carrier briefly sleeps.

**False positive risk:** None — LTE band labels like `(B20)` contain `(B`, not `(N`.

---

## Stage 2 — LTE Anchor Health

```python
lte_ok = (
    (rsrp is not None and rsrp > -100)
    or (sinr is not None and sinr > 15)
    or (rsrq is not None and rsrq > -12)
)
```

| Metric   | API field | Threshold  | Rationale                 |
| :------- | :-------- | :--------- | :------------------------ |
| LTE RSRP | `rsrp`    | > -100 dBm | "Fair" signal floor       |
| LTE SINR | `sinr`    | > 15 dB    | "Very good" quality       |
| LTE RSRQ | `rsrq`    | > -12 dB   | "Acceptable" load/quality |

**Why RSRQ is load-bearing here:** On observed H165-383 live data, RSRP was -103 dBm and SINR was 13 dB — both just below their thresholds — while the router showed 4 signal bars and was actively streaming data. RSRQ at -9 dB was the only metric that passed. Without RSRQ as a third axis, Stage 2 would falsely report OFF on a healthy working connection.

---

## Stage 3 — 5G Leg Health

```python
return (
    (nr_rsrp is not None and nr_rsrp > -105)
    or (nr_sinr is not None and nr_sinr > 10)
    or (nr_rsrq is not None and nr_rsrq > -12)
    or (nr_cqi is not None and nr_cqi >= 7)
    or (nr_bler is not None and nr_bler < 10)
)
```

| Metric  | API field | Threshold  | Rationale                                 |
| :------ | :-------- | :--------- | :---------------------------------------- |
| 5G RSRP | `nrrsrp`  | > -105 dBm | Slightly more lenient than LTE anchor     |
| 5G SINR | `nrsinr`  | > 10 dB    | "Good" quality                            |
| 5G RSRQ | `nrrsrq`  | > -12 dB   | Same load/quality floor as LTE            |
| 5G CQI  | `nrcqi0`  | >= 7       | Decent modulation order (16QAM or higher) |
| 5G BLER | `nrbler`  | < 10%      | Low block error rate                      |

**Note on CQI / BLER:** These are active-traffic metrics. On the H165-383 they are populated even at idle (CQI = 5, BLER = 0.0%), so they do not produce spurious `None` states at rest.

---

## Full Logic Summary

```text
Stage 1 PASS  →  NR band label present in composite band string
     AND
Stage 2 PASS  →  at least one LTE metric above its threshold
     AND
Stage 3 PASS  →  at least one 5G metric above its threshold
     ↓
     ON

Any stage FAIL  →  OFF
No coordinator data  →  None (unavailable)
```

---

## Entity Configuration

| Property            | Value                                       |
| :------------------ | :------------------------------------------ |
| Key                 | `best_connection`                           |
| Platform            | `binary_sensor`                             |
| Device class        | `CONNECTIVITY`                              |
| Entity category     | None (primary entity, visible in main list) |
| Disabled by default | No                                          |
| Group               | `signal`                                    |
| Icon (ON)           | `mdi:signal-5g`                             |
| Icon (OFF)          | `mdi:signal-cellular-1`                     |

---

## Hardware Notes (H165-383)

| API field | Behaviour on H165-383 |
| :-- | :-- |
| `sc_band` | Always null — unusable as NR indicator |
| `network_type` | Returns `"LTE"` in NSA 5G mode — unusable as 5G gate |
| `band` | Composite string including NR segments — used for Stage 1 |
| `nrrsrp` | Populated when 5G leg active; -95 dBm observed |
| `nrrsrq` | Populated; -11 dB observed |
| `nrsinr` | Populated; 6 dB observed (below 10 threshold, hence RSRP/RSRQ carry Stage 3) |
