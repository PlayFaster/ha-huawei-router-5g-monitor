# Huawei Router 5G Integration - Entity Manifest

This document provides a comprehensive list of all 161 static entities currently implemented in the Huawei Router 5G integration. It serves as a master reference for debugging, maintenance, and future development.

## Summary

| Sub-Device | Entity Count | Description |
| :-- | :-- | :-- |
| **System** | 45 | Core router info, WAN configuration, and global integration settings. |
| **Signal** | 60 | Extensive cellular connectivity, LTE/5G signal strength, and network info. |
| **Data** | 24 | Traffic statistics, download/upload rates, and monthly usage. |
| **SMS** | 22 | Detailed message counts per storage bank and recent message content. |
| **WiFi** | 6 | Wireless radio status, capacity, and guest network controls. |
| **Clients** | 3 + trackers | Connected LAN/WLAN devices and aggregate connectivity counters. |
| **Total** | **161** | Plus one device tracker per discovered client. |

---

## 1. System Sub-Device (45 Entities)

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
| Integration Health | `integration_health` | Binary Sensor | — | Diagnostic | `dev_standards` Section 19. ON when the integration has a problem to report. **Never `unavailable`** — it stays up to explain why everything else went down. Attributes: `severity`, `issues`, `degraded_capabilities`, `drift`, `last_good_update` (all unrecorded). |
| Refresh Now | `refresh` | Button | - | Config | Forces an immediate poll cycle. **Fetches even while Pause Polling is on** — explicit actions always fetch. |
| Reboot | `reboot` | Button | - | - |  |
| Polling Interval | `polling_interval` | Number | s | Config | Range: 30s - 3600s. Persists in options. |
| Pause Polling | `pause_polling` | Switch | - | Config | State persists in `ConfigEntry.options`. |
| Mobile Data | `mobile_data` | Switch | — | Config | Toggle mobile data connection on/off. |
| Preferred Network Mode | `preferred_network_mode` | Select | — | Config | Control network mode selection. |
| SIM Card Status | `sim_card_status` | Binary Sensor | — | Diagnostic | ON if SIM card is detected and active. |

| IMEI | `imei` | Sensor | - | Diagnostic | **Disabled by default.** Text, not numeric - no state class, unit or precision. Excluded from long-term statistics. |
| IMSI | `imsi` | Sensor | - | Diagnostic | **Disabled by default.** As IMEI. |
| ICCID | `iccid` | Sensor | - | Diagnostic | **Disabled by default.** As IMEI. |
| SIM Number | `sim_number` | Sensor | - | Diagnostic | **Disabled by default.** The MSISDN. The router GUI calls it "My Number". |
| Serial Number | `serial_number` | Sensor | - | Diagnostic | **Disabled by default.** As IMEI. |
| MCC MNC | `mcc_mnc` | Sensor | - | Diagnostic | **Disabled by default.** Operator code. As IMEI. |
| Product Name | `product_name` | Sensor | - | Diagnostic | Marketing name, e.g. `5G CPE 6`. |
| Web UI Version | `web_ui_version` | Sensor | - | Diagnostic |  |
| Carrier Build | `carrier_build` | Sensor | - | Diagnostic | The `iniversion` customisation build. |
| Supported Modes | `supported_modes` | Sensor | - | Diagnostic | **Disabled by default.** Static capability list. |
| WAN DNS | `wan_dns` | Sensor | - | Diagnostic | **Disabled by default.** Comma-separated. |
| WAN DNS IPv6 | `wan_dns_ipv6` | Sensor | - | Diagnostic | **Disabled by default.** |
| Country Code | `country_code` | Sensor | - | Diagnostic | **Disabled by default.** From `converged_status`. |
| MTU | `mtu` | Sensor | - | Diagnostic | **Disabled by default.** A wrong MTU breaks VPNs while everything else works. |
| APN | `apn` | Sensor | - | Diagnostic | Resolved from `CurrentProfile` by matching `Index`, never by list position. |
| APN Profile | `apn_profile` | Sensor | - | Diagnostic | **Disabled by default.** The profile's name. |
| SIM Locked | `sim_locked` | Binary Sensor | - | Diagnostic | **Disabled by default.** Supersedes the undecodable `simlockStatus`. |
| Roaming Auto-Connect | `roaming_auto_connect` | Binary Sensor | - | Diagnostic | **Disabled by default.** Whether data connects automatically while roaming. |
| SIP ALG | `sip_alg` | Binary Sensor | - | Diagnostic | **Disabled by default.** The firewall's SIP helper, not VoIP status. The commonest cause of one-way audio behind a CPE. |
| UPnP | `upnp` | Binary Sensor | - | Diagnostic | **Disabled by default.** |
| Reconnect | `reconnect` | Button | - | - | Drops and re-establishes the data session. Separate from Reboot, which restarts the device. |
---

## 2. Signal Sub-Device (60 Entities)

_Group: `signal`_

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Network Type | `network_type` | Sensor | - | Diagnostic | Human-readable (e.g., LTE, 5G). |
| Preferred Network Mode | `preferred_network_mode` | Sensor | - | Diagnostic | Read-only state of the network mode. |
| Operator | `operator` | Sensor | - | Diagnostic | Network provider name. |
| Operator Code | `plmn` | Sensor | - | Diagnostic | Numeric PLMN code. |
| Operator Search Mode | `operator_search_mode` | Sensor | - | Diagnostic |  |
| LTE RSRP | `rsrp` | Sensor | dBm | - | Guard band -150 to -30. |
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

| Primary Band | `primary_band` | Sensor | - | Diagnostic | **Disabled by default.** The primary carrier only. `band` carries the full aggregation - the two are not in conflict. |
| Secondary Cell PCI | `secondary_cell_pci` | Sensor | - | Diagnostic | **Disabled by default.** An identifier despite reading as a small integer, so treated as text and excluded from long-term statistics. |
| Antenna 1 | `antenna_1` | Sensor | - | Diagnostic | `Internal` or `External`. Reports the antenna in use, not the configured mode. Unmapped codes pass through raw. |
| Antenna 2 | `antenna_2` | Sensor | - | Diagnostic | As Antenna 1. |
| Poor Signal | `poor_signal` | Binary Sensor | - | Diagnostic | The router's own verdict. Problem device class. |
| Speed Limited | `speed_limited` | Binary Sensor | - | Diagnostic | **Disabled by default.** The router's own verdict. No device class - a carrier limiting throughput is not a fault. |
| Data Service | `data_service` | Binary Sensor | - | Diagnostic | Packet-switched registration. Connectivity device class. |
| Voice Service | `voice_service` | Binary Sensor | - | Diagnostic | **Disabled by default.** Circuit-switched registration. Says nothing about a call in progress; no endpoint on this hardware does. |
---

## 3. Data Sub-Device (24 Entities)

_Group: `data`_

| Name | Key | Type | Unit | Category | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Total Download | `total_download` | Sensor | Bytes | - | Lifetime total download. Other display units may be used (e.g. GB). |
| Total Upload | `total_upload` | Sensor | Bytes | - | Lifetime total upload. Other display units may be used (e.g. GB). |
| Total Data | `total_data` | Sensor | Bytes | - | Lifetime total traffic. Other display units may be used (e.g. GB). |
| Download Rate | `current_download_rate` | Sensor | B/s | - | Current download speed. Other display units may be used (e.g. Mbit/s). |
| Upload Rate | `current_upload_rate` | Sensor | B/s | - | Current upload speed. Other display units may be used (e.g. Mbit/s). |
| Max Download Rate | `max_download_rate` | Sensor | B/s | - | **Disabled by default.** Not populated by H165-383 firmware. |
| Max Upload Rate | `max_upload_rate` | Sensor | B/s | - | **Disabled by default.** Not populated by H165-383 firmware. |
| Connection Upload | `current_connection_upload` | Sensor | Bytes | - | Upload in current session. Resets on reconnect. No LTS. Other display units may be used (e.g. GB). |
| Connection Download | `current_connection_download` | Sensor | Bytes | - | Download in current session. Resets on reconnect. No LTS. Other display units may be used (e.g. GB). |
| Day Used | `current_day_used` | Sensor | Bytes | - | Traffic used today. Other display units may be used (e.g. GB). |
| Month Download | `month_download` | Sensor | Bytes | - | Other display units may be used (e.g. GB). |
| Month Download (GB) | `month_download_gb` | Sensor | GB | - | **Disabled by default.** Rounded to 2 decimals. No LTS (use `month_download` bytes sensor for LTS). |
| Month Upload | `month_upload` | Sensor | Bytes | - | Other display units may be used (e.g. GB). |
| Month Upload (GB) | `month_upload_gb` | Sensor | GB | - | **Disabled by default.** Rounded to 2 decimals. No LTS (use `month_upload` bytes sensor for LTS). |
| Month Total | `month_total` | Sensor | Bytes | - | Other display units may be used (e.g. GB). |
| Clear Traffic Statistics | `clear_traffic` | Button | - | - | Resets traffic counters. |

| Counters Last Reset | `counters_last_reset` | Sensor | Date | Diagnostic | When the counters were last cleared **by hand**. Not the billing boundary - that is Billing Cycle Day. |
| Month Connected Time | `month_connected_time` | Sensor | s | Diagnostic | **Disabled by default.** **Connected** time this cycle, not elapsed. Excluded from long-term statistics. |
| Day Connected Time | `day_connected_time` | Sensor | s | Diagnostic | **Disabled by default.** As above. |
| Data Allowance | `data_allowance` | Sensor | Bytes | Diagnostic | From `trafficmaxlimit`, already in bytes - not the `DataLimit` display string. A setting, so excluded from long-term statistics. |
| Billing Cycle Day | `billing_cycle_day` | Sensor | - | Diagnostic | Day of month the counters roll over. Excluded from long-term statistics. |
| Alert Threshold | `alert_threshold` | Sensor | % | Diagnostic | Excluded from long-term statistics. |
| Data Plan Enabled | `data_plan_enabled` | Binary Sensor | - | Diagnostic | Whether the monthly package is set. Decides whether the three above mean anything. |
| Projected Usage | `projected_usage` | Sensor | Bytes | - | End-of-cycle forecast. **No state class, deliberately** - it is an estimate, and the usage behind it is already in long-term statistics via Month Total. Carries a `confidence` attribute. |
---

## 4. SMS Sub-Device (22 Entities)

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
| SMS Storage Full | `sms_storage_full` | Binary | - | Diagnostic | **Disabled by default.** |
| Send Sms | `send_sms` | Service | — | — | Send an SMS message via the router. |
| Delete Sms | `delete_sms` | Service | — | — | Delete an SMS message by its index. |
| Delete All Sms | `delete_all_sms` | Service | — | — | Delete all SMS messages from the router inbox. |
| Get Sms List | `get_sms_list` | Service | — | — | Fetch a list of SMS messages from the router. |

---

## 5. WiFi Sub-Device (6 Entities)

_Group: `wifi`_

| Name | Key | Type | Category | Notes |
| :-- | :-- | :-- | :-- | :-- |
| Status | `wifi_status` | Binary | Diagnostic | ON if global WiFi is enabled. |
| 2.4GHz Status | `wifi24g_status` | Binary | Diagnostic |  |
| 5GHz Status | `wifi5g_status` | Binary | Diagnostic |  |
| Single SSID Mode | `single_ssid_mode` | Binary | Diagnostic | ON if 2.4GHz/5GHz merged. |
| User Capacity | `wifi_capacity` | Sensor | Diagnostic | **Disabled by default.** Max supported users. |
| Guest Network | `wifi_guest_network` | Switch | Config | Toggle for guest SSID. |

---

## 6. Clients Sub-Device (3 Entities + Trackers)

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
