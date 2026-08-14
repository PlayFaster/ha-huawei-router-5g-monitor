# Signal Metric Guard Bands: Huawei Router 5G

Guard bands keep implausible router readings out of Home Assistant. If a value falls outside its band the sensor reports `Unavailable` rather than the value, so a transient spike or a "ghost" zero cannot pollute long-term statistics.

> [!IMPORTANT]
>
> **The table below is reconciled against the code by a test, in both directions.** `tests/test_entity_hygiene.py::test_value_min_max_doc_matches_the_code` fails if a band is changed in `sensor.py` without changing this table, **and** if this table names a sensor that does not exist or omits one that has bounds.
>
> This matters because the previous version of this document was never reconciled at all, and had drifted: it documented guard bands on **Transmit Power** and **5G Transmit Power** that **did not exist in the code**, and omitted roughly twenty bands that did — every frequency, every bandwidth, the data rates, 5G rank and CQI. A guard band is never published as a state or an attribute, so no live query can observe one; only a static check can.

## How it works

Limits are declared on each `HuaweiSensorEntityDescription` as `min_limit` / `max_limit`, and enforced by `native_value` in the base sensor class before the value reaches Home Assistant:

```python
HuaweiSensorEntityDescription(
    key="rsrp",
    translation_key="rsrp",
    min_limit=-150,
    max_limit=-30,
    value_fn=lambda data: parse_signal_value(_get_signal_value(data, "rsrp")),
)
```

```python
val = self.entity_description.value_fn(self.coordinator.data)
min_limit = self.entity_description.min_limit
max_limit = self.entity_description.max_limit

if val is not None and (min_limit is not None or max_limit is not None):
    try:
        num_val = float(val)
        if min_limit is not None and num_val < min_limit:
            return None
        if max_limit is not None and num_val > max_limit:
            return None
    except (ValueError, TypeError):
        pass
return val
```

Two consequences worth knowing:

- **A non-numeric value passes through untouched.** `float()` raises and the guard falls through. That is deliberate: `_parse_complex_float` returns the raw string for multi-carrier readings such as `"PPusch:12dBm PPucch:5dBm"`, and a band must not blank those.
- **A missing bound is not a bug.** `—` in the Max column means the quantity has no plausible ceiling. Uptime, connection duration and error counts only ever grow; **inventing a ceiling for them would suppress real data**, which is a worse failure than the one guard bands exist to prevent.

## Bands, as implemented

| Sub-device | Sensor key                    |    Min |               Max | Unit |
| :--------- | :---------------------------- | -----: | ----------------: | :--- |
| Clients    | `total_connected`             |    `0` |             `512` | —    |
| Clients    | `wifi_users`                  |    `0` |             `255` | —    |
| Clients    | `wired_connected`             |    `0` |             `512` | —    |
| Data       | `current_connection_download` |    `0` | `109951162777600` | B    |
| Data       | `current_connection_upload`   |    `0` | `109951162777600` | B    |
| Data       | `current_day_used`            |    `0` | `109951162777600` | B    |
| Data       | `current_download_rate`       |    `0` |      `1250000000` | B/s  |
| Data       | `current_upload_rate`         |    `0` |      `1250000000` | B/s  |
| Data       | `max_download_rate`           |    `0` |      `1250000000` | B/s  |
| Data       | `max_upload_rate`             |    `0` |      `1250000000` | B/s  |
| Data       | `month_download`              |    `0` | `109951162777600` | B    |
| Data       | `month_download_gb`           |    `0` |          `100000` | GB   |
| Data       | `month_total`                 |    `0` | `109951162777600` | B    |
| Data       | `month_upload`                |    `0` | `109951162777600` | B    |
| Data       | `month_upload_gb`             |    `0` |          `100000` | GB   |
| Data       | `total_data`                  |    `0` | `109951162777600` | B    |
| Data       | `total_download`              |    `0` | `109951162777600` | B    |
| Data       | `total_upload`                |    `0` | `109951162777600` | B    |
| SMS        | `sms_capacity_device`         |    `0` |           `10000` | —    |
| SMS        | `sms_capacity_sim`            |    `0` |           `10000` | —    |
| SMS        | `sms_deleted_device`          |    `0` |           `10000` | —    |
| SMS        | `sms_drafts_device`           |    `0` |           `10000` | —    |
| SMS        | `sms_drafts_sim`              |    `0` |           `10000` | —    |
| SMS        | `sms_inbox_device`            |    `0` |           `10000` | —    |
| SMS        | `sms_inbox_sim`               |    `0` |           `10000` | —    |
| SMS        | `sms_messages_sim`            |    `0` |           `10000` | —    |
| SMS        | `sms_new`                     |    `0` |           `10000` | —    |
| SMS        | `sms_outbox_device`           |    `0` |           `10000` | —    |
| SMS        | `sms_outbox_sim`              |    `0` |           `10000` | —    |
| SMS        | `sms_total`                   |    `0` |           `10000` | —    |
| SMS        | `sms_total_msg`               |    `0` |           `10000` | —    |
| SMS        | `sms_unread`                  |    `0` |           `10000` | —    |
| SMS        | `sms_unread_device`           |    `0` |           `10000` | —    |
| SMS        | `sms_unread_sim`              |    `0` |           `10000` | —    |
| Signal     | `5g_block_error_rate`         |    `0` |                 — | —    |
| Signal     | `5g_cqi_0`                    |    `0` |              `16` | —    |
| Signal     | `5g_downlink_bandwidth`       |    `0` |             `100` | MHz  |
| Signal     | `5g_downlink_frequency`       |    `0` |            `7125` | MHz  |
| Signal     | `5g_rank`                     |    `1` |               `4` | —    |
| Signal     | `5g_transmit_power`           |  `-30` |              `40` | —    |
| Signal     | `5g_uplink_bandwidth`         |    `0` |             `100` | MHz  |
| Signal     | `5g_uplink_frequency`         |    `0` |            `7125` | MHz  |
| Signal     | `cqi_0`                       |    `0` |              `16` | —    |
| Signal     | `enodeb_id`                   |    `0` |                 — | —    |
| Signal     | `lte_downlink_bandwidth`      |    `0` |              `20` | MHz  |
| Signal     | `lte_downlink_frequency`      |    `0` |            `3800` | MHz  |
| Signal     | `lte_uplink_bandwidth`        |    `0` |              `20` | MHz  |
| Signal     | `lte_uplink_frequency`        |    `0` |            `3800` | MHz  |
| Signal     | `nr_rsrp`                     | `-150` |             `-30` | dBm  |
| Signal     | `nr_rsrq`                     |  `-50` |               `0` | dB   |
| Signal     | `nr_sinr`                     |  `-30` |              `50` | dB   |
| Signal     | `rsrp`                        | `-150` |             `-30` | dBm  |
| Signal     | `rsrq`                        |  `-50` |               `0` | dB   |
| Signal     | `rssi`                        | `-120` |             `-20` | dBm  |
| Signal     | `signal_bars`                 |    `0` |               `5` | —    |
| Signal     | `signal_bars_nr`              |    `0` |               `5` | —    |
| Signal     | `sinr`                        |  `-30` |              `50` | dB   |
| Signal     | `transmit_power`              |  `-30` |              `40` | —    |
| System     | `battery`                     |    `0` |             `100` | %    |
| System     | `current_connection_duration` |    `0` |                 — | s    |
| System     | `total_connection_time`       |    `0` |                 — | s    |
| System     | `uptime`                      |    `0` |                 — | s    |
| WiFi       | `wifi_capacity`               |    `0` |             `512` | —    |

## What deliberately has no band

Roughly a third of the sensors carry no bounds, and that is correct. None of them is numeric: model and firmware strings, IP and DNS addresses, network type, operator, PLMN, cell id, PCI, TAC, band and mode labels, EARFCN identifiers, RRC status, the last SMS body, and the four timestamp sensors.

**The rule this project enforces is narrower than "every sensor needs bounds":** a sensor is required to declare a band only when it carries a **unit** or a **state class** — i.e. when Home Assistant will treat it as a measurement. That rule is asserted by `test_every_numeric_sensor_has_a_guard_band` with an exemption allow-list, currently empty.

The wider rule was tried on a sibling project and was wrong: it demanded an upper bound on every numeric sensor and flagged forty, most of them counts and byte totals whose sensors were right. Narrow the rule to where it is true.

## Version Control

| Version | Date | Change |
| :-- | :-- | :-- |
| v2.0.0 | 2026-08-14 | **First reconciliation against the code, in both directions** — the document had never been checked since it was written. Two documented bands did not exist (`transmit_power`, `5g_transmit_power`, both -30 to 40); they are now implemented. Around twenty implemented bands were undocumented; all are now listed. `cqi_0` carried a minimum but no maximum while its 5G twin `5g_cqi_0` carried `[0, 16]` — the same quantity on different radios, disagreeing only because nobody had compared them; aligned to `[0, 16]`. Replaced the grouped prose table with a per-key table generated from source and pinned by a test, so the document cannot drift again. Recorded which sensors deliberately have no band, and why inventing a ceiling is a worse failure than omitting one. |
| v1.0.0 | 2026-05-03 | Initial. Grouped summary of the signal guard bands introduced with the eight frequency sensors. |
