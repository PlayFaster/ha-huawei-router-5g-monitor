# Huawei Router 5G Integration - Entity Manifest

A complete list of the static entities and service actions provided by the integration, grouped by sub-device.

<!-- GENERATED:start -->

## Summary

| Sub-Device  | Entity Count | Description            |
| :---------- | :----------- | :--------------------- |
| **Clients** | 4            | Clients entities.      |
| **Data**    | 24           | Data entities.         |
| **SMS**     | 18           | SMS entities.          |
| **Signal**  | 58           | Signal entities.       |
| **System**  | 49           | System entities.       |
| **WiFi**    | 7            | WiFi entities.         |
| **Total**   | **160**      | Total static entities. |

## Clients Sub-Device (4 Entities)

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Clean up unused entities | `cleanup_unused_entities` | Button | - | Config | - |
| Total Connected | `total_connected` | Sensor | - | - | LTS: `measurement` |
| WiFi Connected | `wifi_users` | Sensor | - | - | LTS: `measurement` |
| Wired Connected | `wired_connected` | Sensor | - | - | LTS: `measurement` |

## Data Sub-Device (24 Entities)

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Data Plan Enabled | `data_plan_enabled` | Binary Sensor | - | Diagnostic | - |
| Clear Traffic Statistics | `clear_traffic` | Button | - | - | - |
| Alert Threshold | `alert_threshold` | Sensor | % | Diagnostic | - |
| Billing Cycle Day | `billing_cycle_day` | Sensor | - | Diagnostic | - |
| Counters Last Reset | `counters_last_reset` | Sensor | - | Diagnostic | - |
| Connection Download | `current_connection_download` | Sensor | B | - | - |
| Connection Upload | `current_connection_upload` | Sensor | B | - | - |
| Day Used | `current_day_used` | Sensor | B | - | LTS: `total_increasing` |
| Download Rate | `current_download_rate` | Sensor | B/s | - | **Disabled by default.** |
| Upload Rate | `current_upload_rate` | Sensor | B/s | - | **Disabled by default.** |
| Data Allowance | `data_allowance` | Sensor | B | Diagnostic | - |
| Day Connected Time | `day_connected_time` | Sensor | s | Diagnostic | **Disabled by default.** |
| Max Download Rate | `max_download_rate` | Sensor | B/s | - | **Disabled by default.** |
| Max Upload Rate | `max_upload_rate` | Sensor | B/s | - | **Disabled by default.** |
| Month Connected Time | `month_connected_time` | Sensor | s | Diagnostic | **Disabled by default.** |
| Month Download | `month_download` | Sensor | B | - | LTS: `total_increasing` |
| Month Download (GB) | `month_download_gb` | Sensor | GB | - | **Disabled by default.** |
| Month Total | `month_total` | Sensor | B | - | LTS: `total_increasing` |
| Month Upload | `month_upload` | Sensor | B | - | LTS: `total_increasing` |
| Month Upload (GB) | `month_upload_gb` | Sensor | GB | - | **Disabled by default.** |
| Projected Usage | `projected_usage` | Sensor | B | - | - |
| Total Data | `total_data` | Sensor | B | - | LTS: `total_increasing` |
| Total Download | `total_download` | Sensor | B | - | LTS: `total_increasing` |
| Total Upload | `total_upload` | Sensor | B | - | LTS: `total_increasing` |

## SMS Sub-Device (18 Entities)

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| SMS Storage Full | `sms_storage_full` | Binary Sensor | - | Diagnostic | - |
| Last Msg | `last_sms` | Sensor | - | - | - |
| Capacity (Device) | `sms_capacity_device` | Sensor | - | Diagnostic | - |
| Capacity (SIM) | `sms_capacity_sim` | Sensor | - | Diagnostic | - |
| Deleted (Device) | `sms_deleted_device` | Sensor | - | Diagnostic | - |
| Drafts (Device) | `sms_drafts_device` | Sensor | - | Diagnostic | - |
| Drafts (SIM) | `sms_drafts_sim` | Sensor | - | Diagnostic | - |
| Inbox (Device) | `sms_inbox_device` | Sensor | - | Diagnostic | - |
| Inbox (SIM) | `sms_inbox_sim` | Sensor | - | Diagnostic | - |
| Total (SIM) | `sms_messages_sim` | Sensor | - | Diagnostic | - |
| In Process | `sms_new` | Sensor | - | Diagnostic | - |
| Outbox (Device) | `sms_outbox_device` | Sensor | - | Diagnostic | - |
| Outbox (SIM) | `sms_outbox_sim` | Sensor | - | Diagnostic | - |
| Total (Device) | `sms_total` | Sensor | - | Diagnostic | LTS: `measurement` |
| Total Msg | `sms_total_msg` | Sensor | - | - | LTS: `measurement` |
| Unread Msg | `sms_unread` | Sensor | - | - | LTS: `measurement` |
| Unread (Device) | `sms_unread_device` | Sensor | - | Diagnostic | LTS: `measurement` |
| Unread (SIM) | `sms_unread_sim` | Sensor | - | Diagnostic | - |

## Signal Sub-Device (58 Entities)

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Best Connection | `best_connection` | Binary Sensor | - | - | - |
| Data Service | `data_service` | Binary Sensor | - | Diagnostic | - |
| 5G Restricted | `endc_restricted` | Binary Sensor | - | Diagnostic | - |
| 5G ENDC Active | `endc_status` | Binary Sensor | - | - | - |
| LTE Carrier Aggregation | `lte_ca` | Binary Sensor | - | Diagnostic | - |
| Mobile Connection | `mobile_connection` | Binary Sensor | - | Diagnostic | - |
| Poor Signal | `poor_signal` | Binary Sensor | - | Diagnostic | - |
| Roaming Status | `roaming` | Binary Sensor | - | Diagnostic | - |
| Speed Limited | `speed_limited` | Binary Sensor | - | Diagnostic | **Disabled by default.** |
| Voice Service | `voice_service` | Binary Sensor | - | Diagnostic | **Disabled by default.** |
| 5G Block Error Rate | `5g_block_error_rate` | Sensor | - | Diagnostic | - |
| 5G CQI | `5g_cqi_0` | Sensor | - | - | LTS: `measurement` |
| 5G Downlink Bandwidth | `5g_downlink_bandwidth` | Sensor | MHz | Diagnostic | - |
| 5G Downlink Frequency | `5g_downlink_frequency` | Sensor | MHz | Diagnostic | - |
| 5G Downlink MCS | `5g_downlink_mcs` | Sensor | - | Diagnostic | - |
| 5G EARFCN | `5g_earfcn` | Sensor | - | Diagnostic | - |
| 5G Rank | `5g_rank` | Sensor | - | - | LTS: `measurement` |
| 5G Transmit Power | `5g_transmit_power` | Sensor | - | Diagnostic | - |
| 5G Uplink Bandwidth | `5g_uplink_bandwidth` | Sensor | MHz | Diagnostic | - |
| 5G Uplink Frequency | `5g_uplink_frequency` | Sensor | MHz | Diagnostic | - |
| 5G Uplink MCS | `5g_uplink_mcs` | Sensor | - | Diagnostic | - |
| Antenna 1 | `antenna_1` | Sensor | - | Diagnostic | - |
| Antenna 2 | `antenna_2` | Sensor | - | Diagnostic | - |
| LTE Band | `band` | Sensor | - | Diagnostic | - |
| LTE Cell ID | `cell_id` | Sensor | - | Diagnostic | - |
| LTE CQI | `cqi_0` | Sensor | - | - | LTS: `measurement` |
| LTE Downlink MCS | `downlink_mcs` | Sensor | - | Diagnostic | - |
| LTE EARFCN | `earfcn` | Sensor | - | Diagnostic | - |
| eNodeB ID | `enodeb_id` | Sensor | - | Diagnostic | - |
| IMS Status | `ims` | Sensor | - | Diagnostic | - |
| LTE Downlink Bandwidth | `lte_downlink_bandwidth` | Sensor | MHz | Diagnostic | - |
| LTE Downlink Frequency | `lte_downlink_frequency` | Sensor | MHz | Diagnostic | - |
| LTE Uplink Bandwidth | `lte_uplink_bandwidth` | Sensor | MHz | Diagnostic | - |
| LTE Uplink Frequency | `lte_uplink_frequency` | Sensor | MHz | Diagnostic | - |
| LTE Mode | `mode` | Sensor | - | Diagnostic | - |
| Network Type | `network_type` | Sensor | - | Diagnostic | - |
| 5G NR Band | `nr5g_band` | Sensor | - | Diagnostic | - |
| 5G RSRP | `nr_rsrp` | Sensor | dBm | - | LTS: `measurement` |
| 5G RSRQ | `nr_rsrq` | Sensor | dB | - | LTS: `measurement` |
| 5G SINR | `nr_sinr` | Sensor | dB | - | LTS: `measurement` |
| Operator | `operator` | Sensor | - | Diagnostic | - |
| Operator Search Mode | `operator_search_mode` | Sensor | - | Diagnostic | - |
| LTE PCI | `pci` | Sensor | - | Diagnostic | - |
| Operator Code | `plmn` | Sensor | - | Diagnostic | - |
| Preferred Network Mode | `preferred_network_mode` | Sensor | - | Diagnostic | - |
| Primary Band | `primary_band` | Sensor | - | Diagnostic | **Disabled by default.** |
| LTE RRC Status | `rrc_status` | Sensor | - | Diagnostic | - |
| LTE RSRP | `rsrp` | Sensor | dBm | - | LTS: `measurement` |
| LTE RSRQ | `rsrq` | Sensor | dB | - | LTS: `measurement` |
| LTE RSSI | `rssi` | Sensor | dBm | - | LTS: `measurement` |
| Secondary Cell PCI | `secondary_cell_pci` | Sensor | - | Diagnostic | **Disabled by default.** |
| Signal Bars | `signal_bars` | Sensor | - | - | LTS: `measurement` |
| 5G Signal Bars | `signal_bars_nr` | Sensor | - | - | LTS: `measurement` |
| LTE SINR | `sinr` | Sensor | dB | - | LTS: `measurement` |
| LTE TAC | `tac` | Sensor | - | Diagnostic | - |
| LTE Transmission Mode | `transmission_mode` | Sensor | - | Diagnostic | - |
| LTE Transmit Power | `transmit_power` | Sensor | - | Diagnostic | - |
| LTE Uplink MCS | `uplink_mcs` | Sensor | - | Diagnostic | - |

## System Sub-Device (49 Entities)

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Integration Health | `integration_health` | Binary Sensor | - | Diagnostic | - |
| Roaming Auto-Connect | `roaming_auto_connect` | Binary Sensor | - | Diagnostic | **Disabled by default.** |
| Router Diagnostics | `router_diagnostics` | Binary Sensor | - | Diagnostic | - |
| SIM Locked | `sim_locked` | Binary Sensor | - | Diagnostic | **Disabled by default.** |
| SIM Card Status | `sim_status` | Binary Sensor | - | Diagnostic | - |
| SIP ALG | `sip_alg` | Binary Sensor | - | Diagnostic | **Disabled by default.** |
| UPnP | `upnp` | Binary Sensor | - | Diagnostic | **Disabled by default.** |
| VoLTE | `volte` | Binary Sensor | - | Diagnostic | **Disabled by default.** |
| Reboot | `reboot` | Button | - | - | - |
| Reconnect | `reconnect` | Button | - | - | - |
| Refresh Now | `refresh` | Button | - | Config | - |
| Client Device Tracker | `_attr_about` | Device Tracker | - | - | - |
| Polling Interval | `polling_interval` | Number | s | Config | - |
| Preferred Network Mode | `network_mode` | Select | - | Config | - |
| APN | `apn` | Sensor | - | Diagnostic | - |
| APN Profile | `apn_profile` | Sensor | - | Diagnostic | **Disabled by default.** |
| Battery | `battery` | Sensor | % | Diagnostic | **Disabled by default.** |
| Carrier Build | `carrier_build` | Sensor | - | Diagnostic | - |
| Country Code | `country_code` | Sensor | - | Diagnostic | **Disabled by default.** |
| Connection Duration | `current_connection_duration` | Sensor | s | Diagnostic | **Disabled by default.** |
| Connection Uptime | `current_connection_timestamp` | Sensor | - | - | - |
| ICCID | `iccid` | Sensor | - | Diagnostic | **Disabled by default.** |
| IMEI | `imei` | Sensor | - | Diagnostic | **Disabled by default.** |
| IMSI | `imsi` | Sensor | - | Diagnostic | **Disabled by default.** |
| Last Updated | `last_updated` | Sensor | - | - | - |
| Line State | `line_state` | Sensor | - | Diagnostic | **Disabled by default.** |
| MCC MNC | `mcc_mnc` | Sensor | - | Diagnostic | **Disabled by default.** |
| Model Name | `model_name` | Sensor | - | Diagnostic | - |
| MTU | `mtu` | Sensor | - | Diagnostic | **Disabled by default.** |
| Primary DNS Server | `primary_dns` | Sensor | - | Diagnostic | - |
| Primary IPv6 DNS Server | `primary_ipv6_dns` | Sensor | - | Diagnostic | - |
| Product Name | `product_name` | Sensor | - | Diagnostic | - |
| Secondary DNS Server | `secondary_dns` | Sensor | - | Diagnostic | - |
| Secondary IPv6 DNS Server | `secondary_ipv6_dns` | Sensor | - | Diagnostic | - |
| Serial Number | `serial_number` | Sensor | - | Diagnostic | **Disabled by default.** |
| SIM Number | `sim_number` | Sensor | - | Diagnostic | **Disabled by default.** |
| Supported Modes | `supported_modes` | Sensor | - | Diagnostic | **Disabled by default.** |
| Software Version | `sw_version` | Sensor | - | Diagnostic | - |
| Total Duration | `total_connection_time` | Sensor | s | Diagnostic | **Disabled by default.** |
| Total Uptime | `total_connection_timestamp` | Sensor | - | Diagnostic | - |
| Uptime Duration | `uptime` | Sensor | s | Diagnostic | **Disabled by default.** |
| Uptime | `uptime_timestamp` | Sensor | - | - | - |
| WAN DNS | `wan_dns` | Sensor | - | Diagnostic | **Disabled by default.** |
| WAN DNS IPv6 | `wan_dns_ipv6` | Sensor | - | Diagnostic | **Disabled by default.** |
| WAN IP Address | `wan_ip` | Sensor | - | Diagnostic | - |
| WAN IPv6 Address | `wan_ipv6` | Sensor | - | Diagnostic | - |
| Web UI Version | `web_ui_version` | Sensor | - | Diagnostic | - |
| Mobile Data | `mobile_data` | Switch | - | Config | - |
| Pause Polling | `pause_polling` | Switch | - | Config | - |

## WiFi Sub-Device (7 Entities)

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Single SSID Mode | `single_ssid_mode` | Binary Sensor | - | Diagnostic | - |
| 2.4GHz Status | `wifi24g_status` | Binary Sensor | - | Diagnostic | - |
| 5GHz Status | `wifi5g_status` | Binary Sensor | - | Diagnostic | - |
| Status | `wifi_status` | Binary Sensor | - | Diagnostic | - |
| User Capacity | `wifi_capacity` | Sensor | - | Diagnostic | **Disabled by default.** |
| WiFi | `wifi` | Switch | - | Config | - |
| Guest Network | `wifi_guest_network` | Switch | - | Config | - |

<!-- GENERATED:end -->

---

## Debugging & Maintenance Reference

### Identity Strategy

- **Base Unique ID**: The MAC address of the router (normalized to lowercase, no colons) or `host_{IP}` (fallback).
- **Entity Unique ID**: `{{base_id}}_{{key}}`.
- **Device Identifiers**: `{{DOMAIN}}_{{base_id}}_{{group}}` (e.g., `huawei_router_5g_001122334455_wifi`).

### Dynamic Radio Mapping (v1.0.2-dev4)

WiFi radio status is now derived using ID paths rather than hardcoded indices.

- **2.4GHz**: Mapped from path containing `Radio.1`.
- **5GHz**: Mapped from path containing `Radio.2`.

### SMS Attributes

The `Total (Device)` sensor contains detailed attributes for storage analysis:

- `local_unread`, `local_read`, `local_sent`, `local_outbox`, `local_draft`, `local_max`
- `sim_unread`, `sim_read`, `sim_max`

The `Last Msg` sensor contains:

- `phone`: Sender phone number.
- `date`: Timestamp from the router.
- `index`: Internal router message index.
- `unread`: Boolean flag.

### Suggested Display Units & Precision

Sensors are stored in their canonical **native** unit (so long-term statistics and guard bands are stable) but carry a display hint via `suggested_unit_of_measurement` / `suggested_display_precision`. The value shown in the UI can still be overridden per-entity.

| Sensors | Native | Suggested display | Precision |
| :-- | :-- | :-- | :-- |
| `total_download`, `total_upload`, `total_data`, `month_download`, `month_upload`, `month_total` | Bytes | GB | 1 |
| `current_day_used`, `current_connection_upload`, `current_connection_download` | Bytes | GB | 2 |
| `current_download_rate`, `current_upload_rate`, `max_download_rate`, `max_upload_rate` | B/s | Mbit/s | 2 |
| `uptime`, `current_connection_duration`, `total_connection_time` | s | h | 1 |
| LTE/5G uplink & downlink **frequency** and **bandwidth** (8 sensors) | MHz | MHz (unchanged) | 0 |
| `rsrp`, `rssi`, `nr_rsrp` | dBm | dBm (unchanged) | 0 |

> The legacy `month_download_gb` / `month_upload_gb` sensors already report GB (disabled by default) and are intentionally left unchanged.

---

## Version Control

- **v1.2.0** (2026-08-15) - **38 entities added** by `status_plan.md` §T-4: six identity sensors, nine further System sensors and four System binary sensors, the Reconnect button, eight Signal entities, and the data-plan block with the Projected Usage forecast. Counts corrected in three places that must move together - the opening line, the summary table and each sub-device header - because `unifi_network_monitor` shipped `[1.0.1-dev12]` with three stale section headers after adding rows only. Thirteen of the 38 are enabled by default; the identifiers and settings are all disabled. **Long-term statistics exclusions are noted per row** and enforced by a sweep in `tests/test_entity_hygiene.py` rather than by these notes.

  **Two pre-existing count errors were found while reconciling and are corrected here.** SMS carried 22 rows under a header of 18, and Clients carried 4 rows under a header of 6. Neither was introduced by this change — both are visible in the document as committed before it — and the header/row check that surfaced them is the same one this entry cites UniFi for failing. The Clients count is now stated as **3 + trackers**, because `Tracked Device` is one row standing for a dynamically created entity per discovered MAC, and folding a variable number into a fixed count is what made that header wrong in the first place. Whole-document total: 122 → **161** static entities, of which 37 are the addition and 2 the correction.

- **v1.0.0** (2026-05-25) - Initial version. Added 6 undocumented entities, fixed SMS key formatting, updated unit/unknown-state notes, entity counts synced with HA output.
- **v1.1.1-dev20** (2026-05-25) - Updated Connection Upload/Download, Month Download/Upload GB notes to reflect removal of state_class (No LTS).
- **v1.1.2-dev5** (2026-07-02) - Added the "Refresh Now" button (System sub-device) for on-demand coordinator refresh, raising System count from 22 to 23 and total from 112+ to 113+.
- **v1.1.2-dev6** (2026-07-02) - Added suggested display units/precision to 23 sensors (data size → GB, data rate → Mbit/s, duration → hours, frequency/bandwidth and dBm → 0 dp). No entity count change. Added the "Suggested Display Units & Precision" reference table.
- **v1.1.2-dev7** (2026-07-03) - Added `**Disabled by default.**` markers to the remaining registry-disabled sensors (`wifi_capacity`, `month_download_gb`, `month_upload_gb`, `sms_storage_full`). Added SMS services.
- **v1.1.2-dev8** (2026-07-03) - Fixed summary totals and sub-device header counts (121 total entities). Removed stale WiFi switch entities (`wifi_main`, `wifi_24g`, `wifi_5g`, and switch `single_ssid_mode`) from the manifest.
