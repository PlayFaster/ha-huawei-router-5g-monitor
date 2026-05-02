# Huawei Router 5G Integration - Entity Manifest

This document provides a comprehensive list of all 101 entities currently implemented in the Huawei Router 5G integration. It serves as a master reference for debugging, maintenance, and future development.

## Summary

| Sub-Device | Entity Count | Description |
| :-- | :-- | :-- |
| **System** | 24 | Core router info, WiFi status, and global integration settings. |
| **Signal** | 43 | Extensive cellular connectivity, LTE/5G signal strength, and network info. |
| **Data** | 16 | Traffic statistics, download/upload rates, and monthly usage. |
| **SMS** | 17 | Detailed message counts per storage bank and recent message content. |
| **Clients** | 1+ | Connected LAN/WLAN devices (dynamically discovered). |
| **Total** | **101** |  |

---

## 1. System Sub-Device (24 Entities)

_Group: `system`_

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Model Name | `model_name` | Sensor | - | Diagnostic |  |
| Software Version | `sw_version` | Sensor | - | Diagnostic |  |
| Last Updated | `last_updated` | Sensor | Timestamp | Diagnostic | Internal tracking of last successful poll. |
| WAN IP Address | `wan_ip` | Sensor | - | Diagnostic |  |
| WAN IPv6 Address | `wan_ipv6` | Sensor | - | Diagnostic |  |
| Uptime Duration | `uptime` | Sensor | s | Diagnostic | **Disabled by default.** |
| Uptime | `uptime_timestamp` | Sensor | Timestamp | - | Calculated as `now() - uptime_seconds`. |
| Current Connection Duration | `current_connection_duration` | Sensor | s | Diagnostic | **Disabled by default.** |
| Current Connection Uptime | `current_connection_timestamp` | Sensor | Timestamp | - | Calculated as `now() - current_connection_time`. |
| Total Connection Duration | `total_connection_time` | Sensor | s | Diagnostic | **Disabled by default.** |
| Total Connection Uptime | `total_connection_timestamp` | Sensor | Timestamp | - | Calculated as `now() - total_connection_time`. |
| Battery | `battery` | Sensor | % | Diagnostic | **Disabled by default.** |
| WiFi Users Connected | `wifi_users` | Sensor | - | Diagnostic |  |
| Primary DNS Server | `primary_dns` | Sensor | - | Diagnostic |  |
| Secondary DNS Server | `secondary_dns` | Sensor | - | Diagnostic |  |
| WiFi Status | `wifi_status` | Binary | - | Diagnostic | ON if global WiFi is enabled. |
| WiFi 2.4GHz Status | `wifi24g_status` | Binary | - | Diagnostic |  |
| WiFi 5GHz Status | `wifi5g_status` | Binary | - | Diagnostic |  |
| Reboot | `reboot` | Button | - | - |  |
| Polling Interval | `polling_interval` | Number | s | Config | Range: 30s - 3600s. Persists in options. |
| Pause Polling | `pause_polling` | Switch | - | Config | State persists in `ConfigEntry.options`. |
| Mobile Data | `mobile_data` | Switch | - | Config | Control for mobile data connection. |
| Guest WiFi | `wifi_guest_network` | Switch | - | Config | Control for guest WiFi network. |
| Preferred Network Mode | `network_mode` | Select | - | Config | Options: Auto, 4G Only, 5G Only, etc. |

---

## 2. Signal Sub-Device (43 Entities)

_Group: `signal`_

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Network Type | `network_type` | Sensor | - | - | Human-readable (e.g., LTE, 5G). |
| Operator | `operator` | Sensor | - | - | Network provider name. |
| Operator Code | `plmn` | Sensor | - | Diagnostic | Numeric PLMN code. |
| Operator Search Mode | `operator_search_mode` | Sensor | - | Diagnostic |  |
| LTE RSRP | `rsrp` | Sensor | dBm | - | Range: -140 to -44. |
| LTE RSRQ | `rsrq` | Sensor | dB | - | Range: -50 to 0. |
| LTE RSSI | `rssi` | Sensor | dBm | - | Range: -120 to -25. |
| LTE SINR | `sinr` | Sensor | dB | - | Range: -30 to 40. |
| Signal Bars | `signal_bars` | Sensor | - | Diagnostic | 0-5 scale. |
| LTE Cell ID | `cell_id` | Sensor | - | Diagnostic |  |
| LTE PCI | `pci` | Sensor | - | Diagnostic |  |
| LTE TAC | `tac` | Sensor | - | Diagnostic |  |
| LTE Band | `band` | Sensor | - | Diagnostic |  |
| LTE Carrier Aggregation | `lte_ca` | Sensor | - | Diagnostic |  |
| LTE Mode | `mode` | Sensor | - | Diagnostic | (2G, 3G, 4G). |
| LTE Transmit Power | `transmit_power` | Sensor | dBm | Diagnostic |  |
| LTE Uplink MCS | `uplink_mcs` | Sensor | - | Diagnostic |  |
| LTE Downlink MCS | `downlink_mcs` | Sensor | - | Diagnostic |  |
| LTE EARFCN | `earfcn` | Sensor | - | Diagnostic |  |
| LTE RRC Status | `rrc_status` | Sensor | - | Diagnostic |  |
| IMS Status | `ims` | Sensor | - | Diagnostic |  |
| LTE Uplink Frequency | `lte_uplink_frequency` | Sensor | MHz | Diagnostic |  |
| LTE Downlink Frequency | `lte_downlink_frequency` | Sensor | MHz | Diagnostic |  |
| LTE Transmission Mode | `transmission_mode` | Sensor | - | Diagnostic |  |
| eNodeB ID | `enodeb_id` | Sensor | - | Diagnostic |  |
| LTE CQI 0 | `cqi_0` | Sensor | - | Diagnostic |  |
| LTE Uplink Frequency (Sec) | `uplink_frequency` | Sensor | MHz | Diagnostic |  |
| LTE Downlink Frequency (Sec) | `downlink_frequency` | Sensor | MHz | Diagnostic |  |
| 5G NR Band | `nr5g_band` | Sensor | - | Diagnostic |  |
| 5G RSRP | `nr_rsrp` | Sensor | dBm | - | Range: -150 to -30. |
| 5G RSRQ | `nr_rsrq` | Sensor | dB | - | Range: -50 to 0. |
| 5G SINR | `nr_sinr` | Sensor | dB | - | Range: -30 to 40. |
| 5G Uplink Bandwidth | `5g_uplink_bandwidth` | Sensor | MHz | Diagnostic |  |
| 5G Downlink Bandwidth | `5g_downlink_bandwidth` | Sensor | MHz | Diagnostic |  |
| 5G Uplink MCS | `5g_uplink_mcs` | Sensor | - | Diagnostic |  |
| 5G Downlink MCS | `5g_downlink_mcs` | Sensor | - | Diagnostic |  |
| 5G Transmit Power | `5g_transmit_power` | Sensor | dBm | Diagnostic |  |
| 5G EARFCN | `5g_earfcn` | Sensor | - | Diagnostic |  |
| 5G Block Error Rate | `5g_block_error_rate` | Sensor | - | Diagnostic |  |
| 5G Rank | `5g_rank` | Sensor | - | Diagnostic |  |
| 5G CQI 0 | `5g_cqi_0` | Sensor | - | Diagnostic |  |
| Best Connection | `best_connection` | Binary | - | Diagnostic | ON if 5G NR is active. |
| Mobile Connection | `mobile_connection` | Binary | - | Diagnostic | ON if mobile data is connected. |

---

## 3. Data Sub-Device (16 Entities)

_Group: `data`_

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Total Download | `total_download` | Sensor | Bytes | - | Lifetime total download. |
| Total Upload | `total_upload` | Sensor | Bytes | - | Lifetime total upload. |
| Total Data | `total_data` | Sensor | Bytes | - | Lifetime total traffic. |
| Download Rate | `current_download_rate` | Sensor | B/s | - | Current download speed. |
| Upload Rate | `current_upload_rate` | Sensor | B/s | - | Current upload speed. |
| Max Download Rate | `max_download_rate` | Sensor | B/s | - |  |
| Max Upload Rate | `max_upload_rate` | Sensor | B/s | - |  |
| Connection Upload | `current_connection_upload` | Sensor | Bytes | - | Upload in current session. |
| Connection Download | `current_connection_download` | Sensor | Bytes | - | Download in current session. |
| Day Used | `current_day_used` | Sensor | Bytes | - | Traffic used today. |
| Month Download | `month_download` | Sensor | Bytes | - |  |
| Month Download (GB) | `month_download_gb` | Sensor | GB | - | Rounded to 2 decimals. |
| Month Upload | `month_upload` | Sensor | Bytes | - |  |
| Month Upload (GB) | `month_upload_gb` | Sensor | GB | - | Rounded to 2 decimals. |
| Month Total | `month_total` | Sensor | Bytes | - |  |
| Clear Traffic Statistics | `clear_traffic` | Button | - | - | Resets traffic counters. |

---

## 4. SMS Sub-Device (17 Entities)

_Group: `sms`_

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| SMS Unread | `sms_unread` | Sensor | - | - | Total unread (Device + SIM). |
| SMS Total (Device) | `sms_total` | Sensor | - | - | Total stored on device. |
| SMS Unread (Device) | `sms_unread_device` | Sensor | - | - |  |
| SMS Inbox (Device) | `sms_inbox_device` | Sensor | - | - |  |
| SMS Outbox (Device) | `sms_outbox_device` | Sensor | - | - |  |
| SMS Drafts (Device) | `sms_drafts_device` | Sensor | - | - |  |
| SMS Deleted (Device) | `sms_deleted_device` | Sensor | - | - |  |
| SMS Capacity (Device) | `sms_capacity_device` | Sensor | - | - |  |
| SMS Unread (SIM) | `sms_unread_sim` | Sensor | - | - |  |
| SMS Inbox (SIM) | `sms_inbox_sim` | Sensor | - | - |  |
| SMS Outbox (SIM) | `sms_outbox_sim` | Sensor | - | - |  |
| SMS Drafts (SIM) | `sms_drafts_sim` | Sensor | - | - |  |
| SMS Capacity (SIM) | `sms_capacity_sim` | Sensor | - | - |  |
| SMS Messages (SIM) | `sms_messages_sim` | Sensor | - | - |  |
| SMS New | `sms_new` | Sensor | - | - |  |
| Last SMS | `last_sms` | Sensor | - | - | Content of the most recent message. |
| SMS Storage Full | `sms_storage_full` | Binary | - | Diagnostic |  |

---

## 5. Clients Sub-Device (1+ Entities)

_Group: `clients`_

| Name | Key | Type | Category | Notes |
| :-- | :-- | :-- | :-- | :-- |
| Tracked Device | `(mac_address)` | Device Tracker | - | Dynamically created for each discovered MAC. |

---

## Debugging & Maintenance Reference

### Identity Strategy

- **Base Unique ID**: The MAC address of the router (normalized to lowercase, no colons) or `host_{IP}` (fallback).
- **Entity Unique ID**: `{{base_id}}_{{key}}`.
- **Device Identifiers**: `{{DOMAIN}}_{{base_id}}_{{group}}` (e.g., `huawei_router_5g_001122334455_signal`).

### SMS Attributes

The `SMS Total (Device)` sensor contains detailed attributes for storage analysis:

- `local_unread`, `local_read`, `local_sent`, `local_draft`, `local_max`
- `sim_unread`, `sim_read`, `sim_max`

The `Last SMS` sensor contains:

- `phone`: Sender phone number.
- `date`: Timestamp from the router.
- `index`: Internal router message index.
- `unread`: Boolean flag.
