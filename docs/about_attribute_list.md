# `about` Attribute Notes: Huawei Router 5G

Every entity this integration creates publishes an `about` attribute: a short, static note saying what the reading means and, where it matters, what it does **not** mean. The note is visible in the More Info dialog and in Developer Tools.

> [!IMPORTANT]
>
> **This document is reconciled against the code by a test, in both directions.** `tests/test_entity_hygiene.py::test_about_attribute_list_doc_matches_the_code` fails if an entity ships without a note, if a note is edited in `custom_components/` without editing this table, and if this table names an entity that no longer exists. A descriptive document that nothing checks is the thing this whole family of sweeps exists to prevent.

## How it works

The note is an `about` field on the entity description. `HuaweiAboutEntity` in `helpers.py` exposes it as a state attribute and lists it in `_unrecorded_attributes`, so the recorder never writes it to history — the text is identical on every state change, and recording it would cost one copy per change forever (`dev_standards` Section 14).

An entity that defines its own `extra_state_attributes` must route the result through `_with_about`. That is the one failure mode here no type checker sees, so a sweep asserts it rather than a convention.

<!-- GENERATED:start -->

## Clients (4)

| Entity | Platform | Key | Note |
| :-- | :-- | :-- | :-- |
| Clean up unused entities | Button | `cleanup_unused_entities` | Removes tracker entities for clients the router no longer reports - it cannot remove a client the router still lists, and Huawei routers keep away devices for months. Commits immediately with no preview; run the Clean up unused entities action first for a dry run. Nothing is removed while the router has not answered. |
| Total Connected | Sensor | `total_connected` | Every client the router currently reports as connected, wired and wireless together. WiFi Connected and Wired Connected are its two halves. |
| WiFi Connected | Sensor | `wifi_users` | Clients currently associated over WiFi, across all radios and SSIDs including the guest network. |
| Wired Connected | Sensor | `wired_connected` | Clients currently connected over the wired LAN ports. Together with WiFi Connected it accounts for Total Connected, so a difference between the three is a client the router classifies as neither. |

## Data (24)

| Entity | Platform | Key | Note |
| :-- | :-- | :-- | :-- |
| Data Plan Enabled | Binary sensor | `data_plan_enabled` | Whether the router's monthly data plan is switched on. With it off the monthly counters never roll over, so Projected Usage reports nothing rather than projecting against a cycle the router is not keeping. |
| Clear Traffic Statistics | Button | `clear_traffic` | Resets the router's traffic statistics to zero. Irreversible - the lifetime and monthly counters are held on the router, not here, so nothing in Home Assistant can restore them. It sets Counters Last Reset; it does not change Billing Cycle Day. |
| Alert Threshold | Sensor | `alert_threshold` | The percentage of the allowance at which the router raises its own usage warning. A router-side setting; it does not affect this integration's entities. |
| Billing Cycle Day | Sensor | `billing_cycle_day` | Day of the month the router rolls its monthly counters over. This is the billing boundary; Counters Last Reset is the separate, manual clear and the two are routinely months apart. |
| Counters Last Reset | Sensor | `counters_last_reset` | When the traffic counters were last cleared manually. This is not the billing boundary - Billing Cycle Day is - and a date here months old alongside a monthly counter days old is the normal state, not a contradiction. |
| Connection Download | Sensor | `current_connection_download` | Bytes downloaded during the current data session. It resets whenever the connection drops and reconnects, which is more often than the monthly counters reset. |
| Connection Upload | Sensor | `current_connection_upload` | Bytes uploaded during the current data session, resetting with each reconnection. |
| Day Used | Sensor | `current_day_used` | Total bytes used today, as the router counts a day. Recorded as a `total_increasing` counter so its daily reset is understood as a rollover rather than as a large negative step. |
| Download Rate | Sensor | `current_download_rate` | Instantaneous download rate as the router reports it at the moment of the poll. It is a sample, not an average, so between polls it sees nothing - short bursts of traffic can pass entirely unrecorded. |
| Upload Rate | Sensor | `current_upload_rate` | Instantaneous upload rate sampled at the moment of the poll. As with the download rate, traffic between polls is not seen. |
| Data Allowance | Sensor | `data_allowance` | The monthly data allowance configured on the router, in bytes. It is whatever was typed into the router's own data-plan page, not anything the operator confirms, so it is only as accurate as that entry. |
| Day Connected Time | Sensor | `day_connected_time` | Connected time so far today. Like Month Connected Time it counts link-up seconds, not elapsed seconds. |
| Max Download Rate | Sensor | `max_download_rate` | The highest download rate the router has recorded. Not populated by the H165-383 firmware, which is why the entity is disabled by default rather than removed. |
| Max Upload Rate | Sensor | `max_upload_rate` | The highest upload rate the router has recorded. Like Max Download Rate it is unpopulated on current firmware and disabled by default. |
| Month Connected Time | Sensor | `month_connected_time` | Connected time this billing cycle, not elapsed time. It stops advancing while the link is down, so it is not the denominator behind Projected Usage - that uses wall-clock time from the cycle start. The two agree only on a connection that never drops. |
| Month Download | Sensor | `month_download` | Bytes downloaded in the current billing cycle, counted by the router against the cycle start day it has been configured with - not against the calendar month. |
| Month Download (GB) | Sensor | `month_download_gb` | Month Download expressed in GB for convenience. The same underlying counter as Month Download, rounded - not a second measurement, so the two can never disagree by more than the rounding. |
| Month Total | Sensor | `month_total` | Download plus upload for the current billing cycle. This is the figure a data allowance is usually measured against, and it is the input to Projected Usage. |
| Month Upload | Sensor | `month_upload` | Bytes uploaded in the current billing cycle, counted by the router against its configured cycle start day rather than the calendar month. |
| Month Upload (GB) | Sensor | `month_upload_gb` | Month Upload expressed in GB. The same counter as Month Upload, rounded. |
| Projected Usage | Sensor | `projected_usage` | An estimate of where this cycle's usage will finish, not a measurement. Early in a cycle it rests mostly on the previous cycle's rate and later mostly on this one's - the `confidence` attribute is how to judge which. It deliberately carries no state class, so nothing about a forecast enters long-term statistics; the usage behind it is already there via Month Total. |
| Total Data | Sensor | `total_data` | Lifetime download plus upload since the traffic statistics were last cleared. The Clear Traffic Statistics button is what resets it. |
| Total Download | Sensor | `total_download` | Lifetime bytes downloaded, as counted since the router's traffic statistics were last cleared - not since manufacture. |
| Total Upload | Sensor | `total_upload` | Lifetime bytes uploaded since the traffic statistics were last cleared. |

## SMS (18)

| Entity | Platform | Key | Note |
| :-- | :-- | :-- | :-- |
| SMS Storage Full | Binary sensor | `sms_storage_full` | On when message storage has no room left. A full store makes the network stop delivering new messages, and nothing else in the integration reports that - which is the whole reason this entity exists. |
| Last Msg | Sensor | `last_sms` | The text of the most recent message. Its sender, timestamp and index are attributes, all excluded from the recorder: republishing a phone number on every poll is both a storage cost and a privacy one. |
| Capacity (Device) | Sensor | `sms_capacity_device` | How many messages the router's own memory can hold. Compare with Total (Device): reaching it is what makes SMS Storage Full turn on, and a full store silently drops incoming messages. |
| Capacity (SIM) | Sensor | `sms_capacity_sim` | How many messages the SIM card can hold. SIM storage is typically an order of magnitude smaller than the router's own, so it fills first and is usually what triggers SMS Storage Full. |
| Deleted (Device) | Sensor | `sms_deleted_device` | Messages marked deleted but not yet purged from the router's memory. They can still occupy storage until the router reclaims it. |
| Drafts (Device) | Sensor | `sms_drafts_device` | Unsent drafts held in the router's memory. They occupy the same storage as received messages, so drafts left behind reduce the room available for incoming ones. |
| Drafts (SIM) | Sensor | `sms_drafts_sim` | Unsent drafts held on the SIM card. As with the device store, drafts consume the same space that incoming messages need. |
| Inbox (Device) | Sensor | `sms_inbox_device` | Received messages held in the router's own memory, read and unread together. Unread (Device) is the subset still waiting to be looked at. |
| Inbox (SIM) | Sensor | `sms_inbox_sim` | Received messages held on the SIM card, read and unread together. Where a message lands depends on the router's storage preference, not on the sender. |
| Total (SIM) | Sensor | `sms_messages_sim` | Messages stored on the SIM card across every folder - inbox, outbox and drafts. The SIM-side counterpart to Total (Device). |
| In Process | Sensor | `sms_new` | Messages the router reports as newly arrived and not yet filed. A transient count that normally settles to zero within a poll or two - it is not the same as Unread Msg, which persists until the message is read. |
| Outbox (Device) | Sensor | `sms_outbox_device` | Sent messages retained in the router's memory. These occupy the same storage as received ones, so a full outbox blocks incoming messages just as effectively. |
| Outbox (SIM) | Sensor | `sms_outbox_sim` | Sent messages retained on the SIM card. Retained copies occupy the same limited storage as received messages, so an unpruned outbox can block delivery. |
| Total (Device) | Sensor | `sms_total` | Messages stored in the router's own memory. Its attributes break the same storage down by read, unread, sent, outbox and draft, which is what makes a filling mailbox diagnosable before it is full. |
| Total Msg | Sensor | `sms_total_msg` | Every message in every storage location - inbox, outbox and drafts, on both the device and the SIM. The widest of the SMS counts. |
| Unread Msg | Sensor | `sms_unread` | Unread messages across both the device and the SIM. The two per-location entities add up to this one. |
| Unread (Device) | Sensor | `sms_unread_device` | Unread messages stored in the router's own memory. Part of the Unread Msg total, which adds this to the SIM-side count. |
| Unread (SIM) | Sensor | `sms_unread_sim` | Unread messages stored on the SIM card. Part of the Unread Msg total, which adds this to the device-side count. |

## Signal (58)

| Entity | Platform | Key | Note |
| :-- | :-- | :-- | :-- |
| Best Connection | Binary sensor | `best_connection` | On when both the LTE anchor and the 5G leg are healthy at once - the state this hardware performs best in. Off does not mean a problem; it means the router is running on one of the two rather than both. |
| Data Service | Binary sensor | `data_service` | Whether the packet-switched (data) side of the network registration is attached. Voice Service reports the circuit-switched side, and on a data-only plan the two differ permanently. |
| 5G Restricted | Binary sensor | `endc_restricted` | On when the network is withholding 5G from this router. It is a network-side restriction rather than a fault at this end, and it is the usual explanation for good signal with no 5G leg. |
| 5G ENDC Active | Binary sensor | `endc_status` | On when EN-DC is active, meaning the router has a 5G leg attached alongside its LTE anchor. This is what 'connected to 5G' means on a non-standalone network. |
| LTE Carrier Aggregation | Binary sensor | `lte_ca` | On when LTE carrier aggregation is combining more than one carrier. LTE Band lists which; Primary Band names only the anchor. |
| Mobile Connection | Binary sensor | `mobile_connection` | On when the mobile data connection is established. This is the router's link to the operator, not the router's link to the local network - the LAN keeps working while this is off. |
| Poor Signal | Binary sensor | `poor_signal` | The router's own verdict that its signal is poor, from a single firmware flag rather than computed here. The threshold it uses is not published, so read it as a hint - judge signal by LTE RSRP and SINR. |
| Roaming Status | Binary sensor | `roaming` | On when the router is registered to a network other than the SIM's home operator. Compare MCC MNC with Operator Code to see which network that is. |
| Speed Limited | Binary sensor | `speed_limited` | The router's own flag saying its throughput is being capped. The conditions it uses are not published, so it is a hint rather than a measurement. |
| Voice Service | Binary sensor | `voice_service` | Whether the circuit-switched (voice) side of the network registration is attached. Off on a data-only plan is expected, not a fault. |
| 5G Block Error Rate | Sensor | `5g_block_error_rate` | The share of 5G transport blocks that failed and had to be resent. Low single figures are normal. A persistently high value means the link is being pushed harder than it can carry, which signal strength alone does not reveal. |
| 5G CQI | Sensor | `5g_cqi_0` | The 5G Channel Quality Indicator for the first codeword - the modem's own summary of how much the 5G channel can carry. Higher is better and it is not a percentage. |
| 5G Downlink Bandwidth | Sensor | `5g_downlink_bandwidth` | Width of the 5G downlink carrier in MHz. Capacity, not speed. |
| 5G Downlink Frequency | Sensor | `5g_downlink_frequency` | Center frequency of the 5G downlink carrier in MHz. Which band it falls in decides the trade-off in play: low frequencies travel and penetrate, high ones carry more. |
| 5G Downlink MCS | Sensor | `5g_downlink_mcs` | Modulation and Coding Scheme index chosen for the 5G downlink - the network's judgment of how densely it can encode, given the channel. |
| 5G EARFCN | Sensor | `5g_earfcn` | The NR-ARFCN channel number of the 5G carrier. An identifier for a position in the spectrum, not a quantity. |
| 5G Rank | Sensor | `5g_rank` | Number of independent 5G MIMO layers in use, 1 to 4. Two or more means the antennas are receiving genuinely different paths and the link can carry proportionally more; rank 1 is common on a very clean line of sight, where there is nothing to separate. |
| 5G Transmit Power | Sensor | `5g_transmit_power` | The router's own 5G transmit power, with the same reading as LTE Transmit Power: it describes the uplink effort, not the downlink, and is reported as a compound per-channel string. |
| 5G Uplink Bandwidth | Sensor | `5g_uplink_bandwidth` | Width of the 5G uplink carrier in MHz. Capacity upward, not the rate in use, and typically much narrower than the downlink. |
| 5G Uplink Frequency | Sensor | `5g_uplink_frequency` | Center frequency of the 5G uplink carrier in MHz. On a paired band it sits a fixed distance from the downlink frequency; on a shared one the two are the same. |
| 5G Uplink MCS | Sensor | `5g_uplink_mcs` | Modulation and Coding Scheme index chosen for the 5G uplink. |
| Antenna 1 | Sensor | `antenna_1` | Whether antenna port 1 is using the `Internal` or an `External` antenna. Reported per port, so this and Antenna 2 disagreeing is how a mixed setup shows itself - there is deliberately no third 'Mix' value. An unrecognized code is passed through raw rather than guessed at. |
| Antenna 2 | Sensor | `antenna_2` | Whether antenna port 2 is using the `Internal` or an `External` antenna. See Antenna 1: the pair is what expresses a mixed setup. |
| LTE Band | Sensor | `band` | The full set of LTE carriers in use, including every aggregated secondary carrier. Primary Band reports only the anchor carrier, so the two reading differently is expected whenever carrier aggregation is active - it is not a contradiction. |
| LTE Cell ID | Sensor | `cell_id` | Identifier of the LTE cell the router is attached to. An identifier, not a measurement: a change means the router moved to a different cell, and the number itself has no ordering. |
| LTE CQI | Sensor | `cqi_0` | LTE Channel Quality Indicator for the first codeword. The modem's own summary of how much data the channel can carry, so it moves with interference as well as with signal strength. Higher is better; it is not a percentage. |
| LTE Downlink MCS | Sensor | `downlink_mcs` | Modulation and Coding Scheme index chosen for the LTE downlink. A scheduler decision rather than a measurement: it rises as the channel improves, and is the closest single number to 'bits per symbol currently in use'. |
| LTE EARFCN | Sensor | `earfcn` | The E-ARFCN channel number of the LTE carrier: where in the spectrum the carrier sits. An identifier, so arithmetic on it means nothing. |
| eNodeB ID | Sensor | `enodeb_id` | Identifier of the LTE base station hosting the current cell, derived from the cell ID. Several cells usually share one base station, so this changes less often than LTE Cell ID and is the better one to watch for 'has the router moved sites'. |
| IMS Status | Sensor | `ims` | Whether the router is registered with the operator's IMS core, which is what carries VoLTE and SMS over LTE. `Unregistered` is expected on a data-only plan and is not a fault by itself. |
| LTE Downlink Bandwidth | Sensor | `lte_downlink_bandwidth` | Width of the LTE downlink carrier in MHz. A capacity figure, not a speed: a wide carrier with poor signal can be slower than a narrow one with good signal. |
| LTE Downlink Frequency | Sensor | `lte_downlink_frequency` | Center frequency of the LTE downlink carrier, converted to MHz from the raw value the router reports. |
| LTE Uplink Bandwidth | Sensor | `lte_uplink_bandwidth` | Width of the LTE uplink carrier in MHz - the capacity available upward, not the rate in use. |
| LTE Uplink Frequency | Sensor | `lte_uplink_frequency` | Center frequency of the LTE uplink carrier, converted to MHz from the raw value the router reports. |
| LTE Mode | Sensor | `mode` | The radio access technology in use, as the router's own signal block names it. Network Type answers the same question from a different field and with a fuller vocabulary. |
| Network Type | Sensor | `network_type` | The radio access technology currently in use, decoded from the router's numeric code - `19` becomes `LTE`, `51` becomes `5G NR NSA`. A code with no known name is published as `Unknown (n)` rather than hidden, so an unfamiliar reading is information and not a bug. |
| 5G NR Band | Sensor | `nr5g_band` | The 5G NR band or bands the router is using. Blank or unavailable when no 5G leg is attached, which is normal on an LTE-only connection. |
| 5G RSRP | Sensor | `nr_rsrp` | The 5G NR equivalent of LTE RSRP, in dBm. On a non-standalone network the 5G leg carries the data while LTE remains the anchor, so this and LTE RSRP describe two live radio links, not one. |
| 5G RSRQ | Sensor | `nr_rsrq` | The 5G NR equivalent of LTE RSRQ, in dB: 5G reference signal power relative to the total power on the 5G carrier. |
| 5G SINR | Sensor | `nr_sinr` | The 5G NR equivalent of LTE SINR, in dB. On a non-standalone connection this is usually the figure that decides 5G throughput, with LTE SINR governing the anchor. |
| Operator | Sensor | `operator` | Name of the mobile network the router is registered to, as the network reports it. |
| Operator Search Mode | Sensor | `operator_search_mode` | Whether the router chooses its network automatically or has been pinned to one manually. |
| LTE PCI | Sensor | `pci` | Physical Cell Identity of the serving LTE cell, 0 to 503. The short identifier the radio uses to tell neighboring cells apart. It is not a quality figure and neighboring cells reuse the numbers. |
| Operator Code | Sensor | `plmn` | The numeric operator code (MCC plus MNC) of the registered network - the machine-readable twin of Operator. Useful when a network changes its display name but not its identity. |
| Preferred Network Mode | Sensor | `preferred_network_mode` | The network mode the router reports as being in force. The Preferred Network Mode control writes it; this sensor reads it back, so a disagreement between the two means the router refused or altered the request. |
| Primary Band | Sensor | `primary_band` | The primary LTE carrier on its own. LTE Band carries the full aggregation, so `B1` here beside `B1+B3+B7` there is the same radio state described at two levels of detail. |
| LTE RRC Status | Sensor | `rrc_status` | Whether the LTE radio connection is `Connected` (actively exchanging data) or `Idle` (attached but dormant). Idle is normal when nothing is being transferred and is not a fault. |
| LTE RSRP | Sensor | `rsrp` | LTE Reference Signal Received Power, in dBm: how strong the serving cell's reference signal is at the router. This is the primary 'how good is my signal' figure. Better than -80 is excellent, worse than -100 is weak. Readings outside -150 to -30 dBm are discarded as implausible rather than published, so a gap here is a rejected reading, not a dead radio. |
| LTE RSRQ | Sensor | `rsrq` | LTE Reference Signal Received Quality, in dB: reference signal power relative to everything else the router hears on the channel. It falls as the cell gets busier even when RSRP has not moved, so it answers a different question from RSRP and is read alongside it, not instead. |
| LTE RSSI | Sensor | `rssi` | Total received power across the whole LTE channel in dBm, including noise and other cells. Higher is not automatically better: a strong RSSI beside a weak RSRP means most of what the router hears is not its own cell. |
| Secondary Cell PCI | Sensor | `secondary_cell_pci` | Physical Cell Identity of the aggregated secondary cell. An identifier, not a measurement, despite reading as a small integer: a rise or fall means a different cell, not a better or worse one. It deliberately carries no unit and no state class so Home Assistant keeps it out of long-term statistics. |
| Signal Bars | Sensor | `signal_bars` | The LTE signal bars the router's own web interface shows, 0 to 5. It is the router's summarized verdict rather than a measurement, so it is stable and readable but too coarse to trend. Use LTE RSRP, RSRQ and SINR when comparing over time. |
| 5G Signal Bars | Sensor | `signal_bars_nr` | The 5G signal bars the router's own web interface shows, 0 to 5. As with Signal Bars this is a summarized verdict, not a measurement. |
| LTE SINR | Sensor | `sinr` | LTE Signal to Interference plus Noise Ratio, in dB, and the single best predictor of achievable throughput. Above 20 dB is excellent; below 0 dB the wanted signal is quieter than everything competing with it. |
| LTE TAC | Sensor | `tac` | Tracking Area Code of the current LTE cell - the group of cells the network pages the router within. It changes only when the router moves between tracking areas, so it is far more stable than LTE Cell ID. |
| LTE Transmission Mode | Sensor | `transmission_mode` | The LTE MIMO transmission mode the network has assigned. It is the network's choice, not a setting on the router. |
| LTE Transmit Power | Sensor | `transmit_power` | The router's LTE transmit power. High values indicate higher transmission power due to distance or obstruction on the uplink, and say nothing about downlink quality. Reports per-channel power readings (e.g. `PPusch:10dBm PPucch:11dBm`). |
| LTE Uplink MCS | Sensor | `uplink_mcs` | Modulation and Coding Scheme index chosen for the LTE uplink. As with the downlink figure it is a scheduler decision, not a measurement. |

## System (49)

| Entity | Platform | Key | Note |
| :-- | :-- | :-- | :-- |
| Integration Health | Binary sensor | `integration_health` | Reports the health of the integration itself, flagging when polling succeeds but specific capabilities or endpoints are missing or degraded. Provides `severity`, `issues`, `degraded_capabilities`, `drift`, and `last_good_update` attributes, and never goes unavailable. |
| Roaming Auto-Connect | Binary sensor | `roaming_auto_connect` | Whether the router will bring up data automatically while roaming. A setting on the router, and the one that decides whether roaming charges can be incurred without anyone acting. |
| Router Diagnostics | Binary sensor | `router_diagnostics` | The router's built-in connection diagnostic. Reports whether the router can reach the mobile network, with specific failure causes listed in the `reasons` attribute. Compare with Integration Health to distinguish router- level outages from integration polling issues. |
| SIM Locked | Binary sensor | `sim_locked` | Whether SIM lock is enabled on the router. A configuration state, not an alarm: it says the router will demand a PIN, not that it is currently blocked. |
| SIM Card Status | Binary sensor | `sim_status` | On when the SIM is not usable - missing, locked out, or failing to initialize. It is a problem sensor, so on means something is wrong; that is deliberately the opposite polarity to reading it as 'SIM present'. |
| SIP ALG | Binary sensor | `sip_alg` | Whether the router's SIP application-layer gateway is enabled. It rewrites VoIP signaling in transit, which helps some phone systems and breaks others; there is no universally right setting. |
| UPnP | Binary sensor | `upnp` | Whether UPnP port forwarding is enabled, letting devices on the LAN open inbound ports without being asked. Convenient for games and consoles, and a real attack surface. |
| VoLTE | Binary sensor | `volte` | Whether VoLTE - voice carried over the LTE data channel - is available. It depends on the operator provisioning it as well as on the router supporting it, so off can be entirely correct. |
| Reboot | Button | `reboot` | Restarts the router. Everything on the network loses its connection for a minute or two. A follow-up refresh is scheduled about sixty seconds later so the entities recover without waiting for the next poll. |
| Reconnect | Button | `reconnect` | Drops the mobile data session and dials it again, which often re-homes the router to a different cell. The LAN and WiFi stay up. The router refuses the library's dedicated reconnect call, so this issues a disconnect followed by a connect, and schedules a follow-up refresh about twenty seconds later. |
| Refresh Now | Button | `refresh` | Fetches from the router immediately instead of waiting for the next poll. It works even while Pause Polling is on - an explicit action by a person overrides the pause, while the next scheduled poll still respects it. |
| Client Device Tracker | Device tracker | `_attr_about` | One entity per client the router has seen on the LAN or WiFi, keyed by MAC address. `home` means the router currently lists it as connected. Entities are created on first sighting and are not removed automatically, so a one-off guest device leaves a permanent entity — use the Clean up unused entities action to clear them. |
| Polling Interval | Number | `polling_interval` | How often this integration asks the router for data, in seconds. It is saved to the config entry, so it survives a restart. Changes are debounced for two seconds so dragging the slider does not fire a poll per step; a pending change is flushed if the entity is removed mid-debounce rather than silently discarded. |
| Preferred Network Mode | Select | `network_mode` | Restricts which radio technologies the router may use. `Auto` lets it choose. Pinning to a single mode can stabilize a marginal connection or can strand it entirely if that mode is unavailable where the router sits. Preferred Network Mode, the sensor, reads back what the router says is in force. |
| APN | Sensor | `apn` | The access point name the active data profile is dialing. Different APNs on the same SIM can mean different addressing and different traffic treatment. |
| APN Profile | Sensor | `apn_profile` | The name of the dial-up profile the APN comes from. The router returns its profiles out of order, so the active one is resolved by matching its index rather than by list position. |
| Battery | Sensor | `battery` | Battery charge, on the models that have one. This router family is mains-powered in most variants, so the entity is disabled by default and stays unavailable where there is no battery. |
| Carrier Build | Sensor | `carrier_build` | The operator-specific build identifier baked into the firmware. It identifies which carrier customization is loaded, which is what decides whether a given feature or endpoint exists at all. |
| Country Code | Sensor | `country_code` | The country the router believes it is operating in, which governs which radio and WiFi channels it will use. |
| Connection Duration | Sensor | `current_connection_duration` | How long the current mobile data session has been up, in seconds. Disabled by default in favor of Connection Uptime, which says the same thing as a fixed point in time. |
| Connection Uptime | Sensor | `current_connection_timestamp` | The moment the current mobile data session was established. A reset here without a router restart means the data connection dropped and came back - the router itself stayed up. |
| ICCID | Sensor | `iccid` | The SIM card's own serial number, which stays with the card when it moves between routers. Disabled by default and redacted from diagnostics. |
| IMEI | Sensor | `imei` | The modem's IMEI - the identifier of the radio hardware, not of the SIM. Deliberately declared as text: given a unit or a device class, fifteen digits become scientific notation. |
| IMSI | Sensor | `imsi` | The subscriber identity stored on the SIM. It identifies the subscription, unlike IMEI which identifies the hardware. Disabled by default and redacted from diagnostics downloads. |
| Last Updated | Sensor | `last_updated` | When this integration last completed a successful poll. It reports the integration's health rather than the router's: a value going stale means polling has stopped, whatever the individual sensors still show. |
| Line State | Sensor | `line_state` | The voice subsystem's own status string, read from the router's `voicebusy` block. `Idle` means no call is in progress. This is the one block in the payload that returns a bare string rather than a record. |
| MCC MNC | Sensor | `mcc_mnc` | The mobile country and network codes of the SIM's home operator. This is the SIM's home network, which is not necessarily the network the router is registered to right now - compare with Operator Code to see roaming. |
| Model Name | Sensor | `model_name` | The router's model as it reports it. Read once at setup and stored on the config entry, so it stays correct even when the router is unreachable. |
| MTU | Sensor | `mtu` | Maximum transmission unit of the mobile data connection. Relevant when tunneling or when large packets stall; the operator usually sets it. |
| Primary DNS Server | Sensor | `primary_dns` | First IPv4 DNS server the operator handed the router. Devices on the LAN are usually pointed at the router itself, which forwards here, so this is what resolves names in practice unless something overrides it. |
| Primary IPv6 DNS Server | Sensor | `primary_ipv6_dns` | First IPv6 DNS server the operator handed the router. Blank wherever the operator provides no IPv6 service, which is the usual case on a mobile data plan. |
| Product Name | Sensor | `product_name` | The marketing product name the firmware carries, which is often longer and friendlier than Model Name and occasionally disagrees with it. |
| Secondary DNS Server | Sensor | `secondary_dns` | Second IPv4 DNS server the operator handed the router, used when the first does not answer. A blank value is common and is not a fault. |
| Secondary IPv6 DNS Server | Sensor | `secondary_ipv6_dns` | Second IPv6 DNS server the operator handed the router, used when the first does not answer. Blank wherever there is no IPv6 service. |
| Serial Number | Sensor | `serial_number` | The router's hardware serial number. An identifier: it carries no unit, no device class and no display precision, deliberately, because any one of those makes Home Assistant treat the digits as a quantity and reformat them. |
| SIM Number | Sensor | `sim_number` | The phone number the SIM reports, where the operator has written one to the card. Many data SIMs leave this blank, which is not a fault. |
| Supported Modes | Sensor | `supported_modes` | The radio modes this hardware and firmware combination can offer. It is the ceiling on what Preferred Network Mode can be set to, not a statement of what is in use. |
| Software Version | Sensor | `sw_version` | Firmware version running on the router. Huawei ships the firmware and the web interface separately, so this and Web UI Version move independently and disagreeing versions are not a fault. |
| Total Duration | Sensor | `total_connection_time` | Lifetime total of all connected time, in seconds, as the router counts it. Connected time, not elapsed time: it does not advance while the link is down. Disabled by default. |
| Total Uptime | Sensor | `total_connection_timestamp` | Total Duration expressed as a point in time. It is not the date the router was first used - it is now minus the accumulated connected time, so any offline period shifts it forward. |
| Uptime Duration | Sensor | `uptime` | How long the router has been powered on, in seconds. Disabled by default because Uptime, which expresses the same fact as a timestamp, is the better one to display. |
| Uptime | Sensor | `uptime_timestamp` | The moment the router last started, derived by subtracting its uptime from the current time. A timestamp rather than a counter, so it stays still while the router runs instead of ticking - which is what makes it readable in history. |
| WAN DNS | Sensor | `wan_dns` | The full IPv4 DNS server list as the WAN block reports it. Primary and Secondary DNS Server split the same information into two readable entities; this one is the unsplit source. |
| WAN DNS IPv6 | Sensor | `wan_dns_ipv6` | The full IPv6 DNS server list as the WAN block reports it - the unsplit source behind the two IPv6 DNS entities. |
| WAN IP Address | Sensor | `wan_ip` | The IPv4 address the operator has assigned to the router's WAN. Usually a carrier-grade NAT address rather than a publicly reachable one. |
| WAN IPv6 Address | Sensor | `wan_ipv6` | The IPv6 address assigned to the router's WAN, where the operator provides IPv6 at all. |
| Web UI Version | Sensor | `web_ui_version` | Version of the router's own web interface, which Huawei ships and updates separately from the firmware - the two versions moving independently is normal. |
| Mobile Data | Switch | `mobile_data` | Turns the mobile data connection on or off. The LAN and WiFi are unaffected, so this does not disconnect local devices from each other - only from the internet. A refusal by the router raises an error rather than reporting an unearned success. |
| Pause Polling | Switch | `pause_polling` | Stops the scheduled polling without removing the integration. Entities hold their last values rather than going unavailable. Explicit actions - Refresh Now, and the refresh after a control change - still reach the router while this is on. |

## WiFi (7)

| Entity | Platform | Key | Note |
| :-- | :-- | :-- | :-- |
| Single SSID Mode | Binary sensor | `single_ssid_mode` | On when both bands share one network name, so clients pick a band themselves. Convenient, but it removes the ability to pin a device to 2.4 GHz for range. |
| 2.4GHz Status | Binary sensor | `wifi24g_status` | Whether the 2.4 GHz radio is broadcasting. Off while WiFi Status is on means that band alone has been disabled. |
| 5GHz Status | Binary sensor | `wifi5g_status` | Whether the 5 GHz radio is broadcasting. The lookup deliberately steps past the guest network when matching, because a guest SSID on the same radio would otherwise be mistaken for the main one. |
| Status | Binary sensor | `wifi_status` | Whether the router's WiFi is on overall. It follows the radio, not the individual SSID flags: with the radio off, the per-SSID settings still read as enabled and mean nothing. |
| User Capacity | Sensor | `wifi_capacity` | The maximum number of WiFi clients the router will admit. A firmware limit, not a license - reaching it means new clients are refused. |
| WiFi | Switch | `wifi` | Turns the router's WiFi radios on or off. It switches the radios themselves, not the individual SSIDs - with the radio off, the per-SSID settings still read as enabled and mean nothing. |
| Guest Network | Switch | `wifi_guest_network` | Turns the guest network on or off. The `ssid` attribute names the network being controlled. Worth knowing before leaving it on: on this hardware the guest SSID is configured open, so an unattended `on` is an unauthenticated network on air. |

<!-- GENERATED:end -->

## Version Control

| Version | Date | Change |
| :-- | :-- | :-- |
| v1.0.0 | 2026-08-15 | Initial. One note per entity across all seven platforms — 159 descriptions plus the device tracker — with the both-directions reconciliation test that keeps the set from decaying. |
