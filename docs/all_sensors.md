# Huawei Router 5G Integration - Entity Manifest

This document provides a comprehensive list of all 118+ entities currently implemented in the Huawei Router 5G integration. It serves as a master reference for debugging, maintenance, and future development.

## Summary

| Sub-Device | Entity Count | Description |
| :-- | :-- | :-- |
| **System** | 22 | Core router info, WAN configuration, and global integration settings. |
| **Signal** | 49 | Extensive cellular connectivity, LTE/5G signal strength, and network info. |
| **Data** | 16 | Traffic statistics, download/upload rates, and monthly usage. |
| **SMS** | 18 | Detailed message counts per storage bank and recent message content. |
| **WiFi** | 7 | Wireless radio status, capacity, and guest network controls. |
| **Clients** | 4+ | Connected LAN/WLAN devices and aggregate connectivity counters. |
| **Total** | **112+** |  |

---

## 1. System Sub-Device (22 Entities)

_Group: `system`_

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Model Name | `model_name` | Sensor | - | Diagnostic |  |
| Software Version | `sw_version` | Sensor | - | Diagnostic |  |
| Last Updated | `last_updated` | Sensor | Timestamp | - | Promoted from Diagnostic. Internal tracking of last successful poll. |
| WAN IP Address | `wan_ip` | Sensor | - | Diagnostic |  |
| WAN IPv6 Address | `wan_ipv6` | Sensor | - | Diagnostic |  |
| Uptime Duration | `uptime` | Sensor | s | Diagnostic | **Disabled by default.** |
| Uptime | `uptime_timestamp` | Sensor | Timestamp | - | Calculated as `now() - uptime_seconds`. |
| Connection Duration | `current_connection_duration` | Sensor | s | Diagnostic | **Disabled by default.** |
| Connection Uptime | `current_connection_timestamp` | Sensor | Timestamp | - | Calculated as `now() - current_connection_time`. |
| Total Duration | `total_connection_time` | Sensor | s | Diagnostic | **Disabled by default.** |
| Total Uptime | `total_connection_timestamp` | Sensor | Timestamp | Diagnostic | Moved to Diagnostic. Calculated as `now() - total_connection_time`. |
| Battery | `battery` | Sensor | % | Diagnostic | **Disabled by default.** Data may not be available in all configurations. |
| Primary DNS Server | `primary_dns` | Sensor | - | Diagnostic |  |
| Secondary DNS Server | `secondary_dns` | Sensor | - | Diagnostic |  |
| Primary IPv6 DNS Server | `primary_ipv6_dns` | Sensor | - | Diagnostic |  |
| Secondary IPv6 DNS Server | `secondary_ipv6_dns` | Sensor | - | Diagnostic |  |
| Reboot | `reboot` | Button | - | - |  |
| Polling Interval | `polling_interval` | Number | s | Config | Range: 30s - 3600s. Persists in options. |
| Pause Polling | `pause_polling` | Switch | - | Config | State persists in `ConfigEntry.options`. |
| Mobile Data | `mobile_data` | Switch | — | Config | Toggle mobile data connection on/off. |
| Preferred Network Mode | `preferred_network_mode` | Select | — | Config | Control network mode selection. |
| SIM Card Status | `sim_card_status` | Binary Sensor | — | Diagnostic | ON if SIM card is detected and active. |

---

## 2. Signal Sub-Device (49 Entities)

_Group: `signal`_

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Network Type | `network_type` | Sensor | - | Diagnostic | Human-readable (e.g., LTE, 5G). |
| Preferred Network Mode | `preferred_network_mode` | Sensor | - | Diagnostic | Read-only state of the network mode. |
| Operator | `operator` | Sensor | - | Diagnostic | Network provider name. |
| Operator Code | `plmn` | Sensor | - | Diagnostic | Numeric PLMN code. |
| Operator Search Mode | `operator_search_mode` | Sensor | - | Diagnostic |  |
| LTE RSRP | `rsrp` | Sensor | dBm | - | Range: -140 to -44. |
| LTE RSRQ | `rsrq` | Sensor | dB | - | Range: -50 to 0. |
| LTE RSSI | `rssi` | Sensor | dBm | - | Range: -120 to -25. |
| LTE SINR | `sinr` | Sensor | dB | - | Range: -30 to 40. |
| Signal Bars | `signal_bars` | Sensor | - | - | 0-5 scale. |
| 5G Signal Bars | `signal_bars_nr` | Sensor | - | - | 0-5 scale. New in v1.0.2-dev4. |
| LTE Cell ID | `cell_id` | Sensor | - | Diagnostic |  |
| LTE PCI | `pci` | Sensor | - | Diagnostic |  |
| LTE TAC | `tac` | Sensor | - | Diagnostic |  |
| LTE Band | `band` | Sensor | - | Diagnostic |  |
| LTE Carrier Aggregation | `lte_ca` | Binary | - | Diagnostic | ON when multiple carriers aggregated. Derived from `band` string. |
| LTE Mode | `mode` | Sensor | - | Diagnostic | (2G, 3G, 4G). |
| LTE Transmit Power | `transmit_power` | Sensor | dBm | Diagnostic |  |
| LTE Uplink MCS | `uplink_mcs` | Sensor | - | Diagnostic |  |
| LTE Downlink MCS | `downlink_mcs` | Sensor | - | Diagnostic |  |
| LTE EARFCN | `earfcn` | Sensor | - | Diagnostic |  |
| LTE RRC Status | `rrc_status` | Sensor | - | Diagnostic |  |
| IMS Status | `ims` | Sensor | - | Diagnostic |  |
| LTE Uplink Frequency | `lte_uplink_frequency` | Sensor | MHz | Diagnostic | `lteulfreq` field, scaled /10. |
| LTE Downlink Frequency | `lte_downlink_frequency` | Sensor | MHz | Diagnostic | `ltedlfreq` field, scaled /10. |
| LTE Uplink Bandwidth | `lte_uplink_bandwidth` | Sensor | MHz | Diagnostic | `ulbandwidth` field, no scaling. |
| LTE Downlink Bandwidth | `lte_downlink_bandwidth` | Sensor | MHz | Diagnostic | `dlbandwidth` field, no scaling. |
| LTE Transmission Mode | `transmission_mode` | Sensor | - | Diagnostic |  |
| eNodeB ID | `enodeb_id` | Sensor | - | Diagnostic |  |
| LTE CQI | `lte_cqi` | Sensor | - | - | Promoted from Diagnostic. |
| LTE Uplink Frequency (Secondary) | `uplink_frequency` | Sensor | MHz | Diagnostic | `ulfrequency` field in kHz, scaled /1000. |
| LTE Downlink Frequency (Secondary) | `downlink_frequency` | Sensor | MHz | Diagnostic | `dlfrequency` field in kHz, scaled /1000. |
| 5G NR Band | `5g_nr_band` | Sensor | - | Diagnostic | Parsed from `band` string (e.g. `N28`). |
| 5G RSRP | `5g_rsrp` | Sensor | dBm | - | Range: -150 to -30. |
| 5G RSRQ | `5g_rsrq` | Sensor | dB | - | Range: -50 to 0. |
| 5G SINR | `5g_sinr` | Sensor | dB | - | Range: -30 to 40. |
| 5G Uplink Bandwidth | `5g_uplink_bandwidth` | Sensor | MHz | Diagnostic |  |
| 5G Downlink Bandwidth | `5g_downlink_bandwidth` | Sensor | MHz | Diagnostic |  |
| 5G Uplink MCS | `5g_uplink_mcs` | Sensor | - | Diagnostic | Supports complex multi-carrier strings. |
| 5G Downlink MCS | `5g_downlink_mcs` | Sensor | - | Diagnostic | Supports complex multi-carrier strings. |
| 5G Transmit Power | `5g_transmit_power` | Sensor | dBm | Diagnostic | Supports complex multi-carrier strings. |
| 5G EARFCN | `5g_earfcn` | Sensor | - | Diagnostic | Supports complex multi-carrier strings. |
| 5G Block Error Rate | `5g_block_error_rate` | Sensor | - | Diagnostic |  |
| 5G Rank | `5g_rank` | Sensor | - | - | 1-4. |
| 5G CQI | `5g_cqi` | Sensor | - | - |  |
| Best Connection | `best_connection` | Binary | - | - | ON when NSA 5G NR band assigned AND LTE anchor healthy AND 5G leg healthy. |
| 5G ENDC Active | `endc_status` | Binary | - | - | Renamed from 5G Active. ON if EN-DC is active. |
| 5G Restricted | `endc_restricted` | Binary | - | Diagnostic | ON if 5G is restricted by the carrier. |
| Mobile Connection | `mobile_connection` | Binary | - | Diagnostic | ON if mobile data is connected. |
| Roaming Status | `roaming_status` | Binary Sensor | — | Diagnostic | ON if roaming is active. |
| 5G Uplink Frequency | `5g_uplink_frequency` | Sensor | MHz | Diagnostic | `nruplinkfrequency` field, scaled. |
| 5G Downlink Frequency | `5g_downlink_frequency` | Sensor | MHz | Diagnostic | `nrdownlinkfrequency` field, scaled. |

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
| Max Download Rate | `max_download_rate` | Sensor | B/s | - | **Disabled by default.** Not populated by H165-383 firmware. |
| Max Upload Rate | `max_upload_rate` | Sensor | B/s | - | **Disabled by default.** Not populated by H165-383 firmware. |
| Connection Upload | `current_connection_upload` | Sensor | Bytes | - | Upload in current session. Resets on reconnect. No LTS. |
| Connection Download | `current_connection_download` | Sensor | Bytes | - | Download in current session. Resets on reconnect. No LTS. |
| Day Used | `current_day_used` | Sensor | Bytes | - | Traffic used today. Other display units may be used (e.g. GB). |
| Month Download | `month_download` | Sensor | Bytes | - |  |
| Month Download (GB) | `month_download_gb` | Sensor | GB | - | Rounded to 2 decimals. No LTS (use `month_download` bytes sensor for LTS). |
| Month Upload | `month_upload` | Sensor | Bytes | - | Other display units may be used (e.g. GB). |
| Month Upload (GB) | `month_upload_gb` | Sensor | GB | - | Rounded to 2 decimals. No LTS (use `month_upload` bytes sensor for LTS). |
| Month Total | `month_total` | Sensor | Bytes | - |  |
| Clear Traffic Statistics | `clear_traffic` | Button | - | - | Resets traffic counters. |

---

## 4. SMS Sub-Device (18 Entities)

_Group: `sms`_

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Unread Msg | `sms_unread` | Sensor | - | - | Total unread (Device + SIM). |
| Total Msg | `sms_total_msg` | Sensor | - | - | Aggregate of all storage locations. |
| Last Msg | `last_sms` | Sensor | - | - | Content of the most recent message. |
| Total (Device) | `sms_total` | Sensor | - | Diagnostic | Total stored on device. |
| Unread (Device) | `sms_unread_device` | Sensor | - | Diagnostic |  |
| Inbox (Device) | `sms_inbox_device` | Sensor | - | Diagnostic |  |
| Outbox (Device) | `sms_outbox_device` | Sensor | - | Diagnostic |  |
| Drafts (Device) | `sms_drafts_device` | Sensor | - | Diagnostic |  |
| Deleted (Device) | `sms_deleted_device` | Sensor | - | Diagnostic |  |
| Capacity (Device) | `sms_capacity_device` | Sensor | - | Diagnostic |  |
| Unread (SIM) | `sms_unread_sim` | Sensor | - | Diagnostic |  |
| Inbox (SIM) | `sms_inbox_sim` | Sensor | - | Diagnostic |  |
| Outbox (SIM) | `sms_outbox_sim` | Sensor | - | Diagnostic |  |
| Drafts (SIM) | `sms_drafts_sim` | Sensor | - | Diagnostic |  |
| Capacity (SIM) | `sms_capacity_sim` | Sensor | - | Diagnostic |  |
| Total (SIM) | `total_sim` | Sensor | - | Diagnostic |  |
| In Process | `in_process` | Sensor | - | Diagnostic | Transient notification counter. |
| SMS Storage Full | `sms_storage_full` | Binary | - | Diagnostic |  |

---

## 5. WiFi Sub-Device (7 Entities)

_Group: `wifi`_

| Name | Key | Type | Category | Notes |
| :-- | :-- | :-- | :-- | :-- |
| Status | `wifi_status` | Binary | Diagnostic | ON if global WiFi is enabled. |
| 2.4GHz Status | `wifi24g_status` | Binary | Diagnostic |  |
| 5GHz Status | `wifi5g_status` | Binary | Diagnostic |  |
| Single SSID Mode | `single_ssid_mode` | Binary | Diagnostic | ON if 2.4GHz/5GHz merged. |
| User Capacity | `wifi_capacity` | Sensor | Diagnostic | Max supported users. |
| Single SSID Mode | `single_ssid_mode` | Switch | Config | Toggle Band Steering. |
| Main Switch | `wifi_main` | Switch | Config | Master toggle (Single SSID mode only). |
| 2.4GHz | `wifi_24g` | Switch | Config | 2.4GHz toggle (Separate mode only). |
| 5GHz | `wifi_5g` | Switch | Config | 5GHz toggle (Separate mode only). |
| Guest Network | `wifi_guest_network` | Switch | Config | Toggle for guest SSID. |

---

## 6. Clients Sub-Device (4+ Entities)

_Group: `clients`_

| Name | Key | Type | Category | Notes |
| :-- | :-- | :-- | :-- | :-- |
| WiFi Connected | `wifi_users` | Sensor | - | Current active WLAN users. Promoted from Diagnostic. |
| Total Connected | `total_connected` | Sensor | - | Sum of all active clients (LAN+WLAN). New in v1.0.2-dev4. |
| Wired Connected | `wired_connected` | Sensor | - | Active LAN clients. New in v1.0.2-dev4. |
| Tracked Device | `(mac_address)` | Device Tracker | - | Dynamically created for each discovered MAC. |

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

---

## Version Control

- **v1.0.0** (2026-05-25) - Initial version. Added 6 undocumented entities, fixed SMS key formatting, updated unit/unknown-state notes, entity counts synced with HA output.
- **v1.1.1-dev20** (2026-05-25) - Updated Connection Upload/Download, Month Download/Upload GB notes to reflect removal of state_class (No LTS).
