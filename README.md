# Huawei Router 5G Monitor for Home Assistant

[![HACS Integration](https://img.shields.io/badge/HACS-Integration-orange.svg)](https://hacs.xyz/) [![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistant&logoColor=white)](https://hacs.xyz/docs/faq/custom_repositories) [![Latest Release](https://img.shields.io/github/v/release/PlayFaster/ha-huawei-router-5g-monitor?label=Release&logo=github)](https://github.com/PlayFaster/ha-huawei-router-5g-monitor/releases) [![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0) [![Validate](https://github.com/PlayFaster/ha-huawei-router-5g-monitor/actions/workflows/validate.yaml/badge.svg)](https://github.com/PlayFaster/ha-huawei-router-5g-monitor/actions/workflows/validate.yaml) ![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/PlayFaster/b5cb47f2b37e140da07eefd17ac19721/raw/coverage.json) [![Last Commit](https://img.shields.io/github/last-commit/PlayFaster/ha-huawei-router-5g-monitor?label=Last%20commit)](https://github.com/PlayFaster/ha-huawei-router-5g-monitor/commits/main)

A Home Assistant integration for **Huawei LTE/5G routers**, providing extensive signal diagnostics, data tracking, SMS management, and connected client monitoring.

> [!NOTE]
>
> **Is this the right integration for you?**
>
> - **Most users** with a Huawei LTE/5G router should use the official [Huawei LTE](https://www.home-assistant.io/integrations/huawei_lte/) core integration — it is well-maintained, broadly compatible, and fully supported.
> - **If you only want SMS features** on top of the core integration, consider pairing it with [@william-aqn's huawei_lte_extended](https://github.com/william-aqn/huawei_lte_extended) component.
> - **This integration is for you if** you want the core integration's features _plus_ any of the following:
>   - **Polling control** — pause polling and adjust the scan interval dynamically from the HA UI or via automation.
>   - **Connected client tracking** — dynamically created `device_tracker` entities for every discovered LAN/WLAN client.
>   - **SMS Management** — view the most recently received message content and attributes directly in HA.
>
> This project builds on the excellent work of [Salamek/huawei-lte-api](https://github.com/Salamek/huawei-lte-api) and the Home Assistant core [Huawei LTE](https://www.home-assistant.io/integrations/huawei_lte/) integration.

## 🔧 Compatibility & Requirements

**Router Hardware:**

- **Tested on**: **Huawei 5G CPE Pro 6 (H165-383)**
- **Expected compatible**: Any Huawei LTE/5G router supported by the `huawei-lte-api` library or the Home Assistant core Huawei LTE integration should work, but compatibility with untested models cannot be guaranteed.
- **Not Supported**: Non-Huawei hardware.

**Network:**

- Local network access to the router is required.

**Home Assistant Version:**

- Minimum: Home Assistant **2025.1**

---

## ✅ Features

> [!TIP]
>
> **What this adds over the Home Assistant core Huawei LTE integration:**
>
> - **Polling Control**: A Pause Polling switch and a configurable, dynamically adjustable scan interval — set it from the UI or drive it via automation.
> - **Connected Client Tracking**: Automatically creates `device_tracker` entities for every discovered LAN/WLAN client, dynamically updated as devices join and leave.
> - **SMS Management**: Most recent SMS as text sensor, all SMS inbox counts, services to read, send and delete SMS.

### 📡 Advanced 5G/LTE Diagnostics

- **Detailed Signal Metrics**: RSRP, RSRQ, RSSI, and SINR for both the 5G NR and the LTE anchor cell.
- **RF Engineering Data**: Monitor CQI, MCS, Transmit Power, and Carrier Aggregation status.
- **Frequency Tracking**: Active 5G/LTE bands, EARFCN, and uplink/downlink frequencies.

### 📊 Comprehensive Monitoring

- **Sub-Device Organisation**: Entities are automatically grouped into five logical devices: **System**, **Signal**, **Data**, **SMS**, and **Clients**.
  - **System**: Core router info, WAN IP addresses, uptime, WiFi status, and integration controls.
  - **Signal**: Extensive 5G NR and LTE signal data including RSRP, RSRQ, SINR, cell ID, and band info.
  - **Data**: Real-time download/upload rates, daily usage, monthly totals, and connection statistics.
  - **SMS**: Message counts per storage bank (Device & SIM), and last received message with full attributes.
  - **Clients**: Dynamically discovered and tracked LAN/WLAN connected devices.

### 📋 Essential Router Management

- **Data Usage Tracking**: Real-time rates, daily usage, and monthly download/upload totals.
- **Router Management**: Reboot button, Mobile Data toggle, WiFi and Guest WiFi controls.
- **Connected Clients**: Dynamic device tracking for every discovered LAN/WLAN client.
- **SMS Management**: Unread SMS counts, last message content, and advanced SMS services (Send, Delete, List).
- **Preferred Network Mode**: Select between Auto, 4G Only, 5G Only, and other available modes.
- **100% Local**: No cloud account or internet access required.

---

### 💡 Useful Features

- **Pause Polling**: Switch to halt polling when you need uninterrupted access to the router's web UI.
- **Configurable Update Interval**: From 30 seconds to 1 hour.
- **SMS Events & Services**: Fires a `huawei_router_5g_sms_received` event when a new message is detected, enabling automations triggered by incoming texts. Has services to send, delete and list SMS messages, see below.

> [!TIP]
>
> **Polling Interval can be controlled dynamically, via automation**
>
> - Polling Interval is available as a number control within the device, you can change it via automation, if desired.
> - Set it to 30 seconds during periods of heavy use to examine connection quality and set it higher afterwards, to avoid taxing the router and your Home Assistant database.

---

## 🛠️ SMS Services

This integration provides the following services for SMS management:

- **`huawei_router_5g.send_sms`**: Send an SMS message to one or more recipients.
- **`huawei_router_5g.delete_sms`**: Delete a specific SMS message by its storage index.
- **`huawei_router_5g.delete_all_sms`**: Bulk delete messages from the inbox. Includes a `keep_last` parameter to preserve recent messages for safety.
- **`huawei_router_5g.get_sms_list`**: Fetch a list of SMS messages from a specific storage bank (Local, SIM, Sent, or Draft). This service supports **Service Responses**, allowing you to use the output in Home Assistant automations and scripts.

---

## 💡 Example SMS Automations

### Forward Incoming SMS to Mobile

This automation fires when a new SMS is detected and forwards the content to your mobile phone via a notification service.

```yaml
alias: "SMS: Forward to Mobile"
trigger:
  - platform: event
    event_type: huawei_router_5g_sms_received
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "New SMS from {{ trigger.event.data.phone }}"
      message: "{{ trigger.event.data.content }}"
```

### Automated Inbox Maintenance

Keep your router's SMS storage clean by automatically deleting old messages while keeping the most recent ones for safety.

```yaml
alias: "SMS: Weekly Inbox Cleanup"
trigger:
  - platform: time
    at: "03:00:00"
condition:
  - condition: time
    weekday:
      - sun
action:
  - service: huawei_router_5g.delete_all_sms
    data:
      device_id: 01KQT9S47HN7R6PN3Y7A7NPRRA # Replace with your Device ID
      keep_last: 5
```

### Fetch and Process Inbox via Script

Example of using the `get_sms_list` service response in a script to count messages from a specific sender.

```yaml
alias: "SMS: Count OTP Messages"
sequence:
  - service: huawei_router_5g.get_sms_list
    data:
      device_id: 01KQT9S47HN7R6PN3Y7A7NPRRA
      count: 50
    response_variable: inbox
  - service: notify.persistent_notification
    data:
      message: >
        You have {{ inbox.messages | selectattr('phone', 'search', 'MY_BANK') | list | count }} 
        messages from your bank in the inbox.
```

---

## 📊 What You Get

This integration provides **106+ entities** grouped into five logical devices: **System**, **Signal**, **Data**, **SMS**, and **Clients**.

| Type | Count | Primary Functions |
| :-- | :-- | :-- |
| **Sensors** | 92 | Signal strength, data usage, uptime, SMS counts, device info |
| **Binary Sensors** | 7 | Best Connection, WiFi status, mobile connection, SMS storage full |
| **Switches** | 3 | Pause Polling, Mobile Data, Guest WiFi |
| **Buttons** | 2 | Reboot, Clear Traffic |
| **Inputs** | 2 | Polling Interval, Network Mode |
| **Services** | 4 | Send, Delete, and List SMS services |
| **Device Trackers** | 1+ | Dynamically discovered per connected LAN/WLAN client |

> [!TIP]
>
> **Clean up your UI: Disable Unnecessary Devices or Entities**
>
> - If you are running in Bridge Mode you may not need the Clients sub-device
> - If you never use the Routers SMS you may not need the SMS sub-device
> - Devices and their entities can be disabled from the main device page - (⋮ menu) "Disable Device".
> - Individual entities can be disabled via the entity properties, or in bulk on the entities list page.

---

### 🏗️ Under the Hood

- **Data Validation**: Router values are checked for validity (guard band limits), with out-of-range sensors being marked as unknown.
- **Zero-Blocking Startup**: Home Assistant starts instantly. Hardware identity is loaded from memory, while the first poll happens quietly in the background.
- **Flat Identity Pattern**: Device information (Model, MAC, Version) remains stable and visible even if the router is temporarily offline.
- **Native Resilience**: Built-in 3-strike logic masks transient network glitches and holds last-known-good data between retries.
- **Modern Integration Architecture**: A data coordinator-based structure and a full options flow.

---

## ❔ What's Missing?

- **SMS Inbox Browsing**: The integration provides the last received message content and unread counts. Browsing the full inbox or replying to specific messages requires the router's web interface.

---

## 📸 Screenshots

### Integration Overview

![Integration](.github/images/huawei_5g_integration_screen_mini.png)

| Signal | System |
| :-: | :-: |
| ![Signal](.github/images/huawei_5g_signal_info.png) | ![System](.github/images/huawei_5g_sensor_control_info.png) |

| Data | SMS |
| :-: | :-: |
| ![Data](.github/images/huawei_5g_data_info_mini.png) | ![SMS](.github/images/huawei_5g_sms_info.png) |

| Setup | Clients |
| :-: | :-: |
| ![Setup](.github/images/huawei_5g_setup_info.png) | ![Clients](.github/images/huawei_5g_device_info_mini.png) |

---

## ✨ Installation

### HACS (Recommended)

1. Add this repository as a **Custom Repository** in HACS:
   - Open HACS in Home Assistant
   - Click **Custom repositories** (⋮ menu)
   - Add repository URL and Type: `Integration`
2. Search for "Huawei Router 5G Monitor" and click **Download**
3. Restart Home Assistant
4. Go to **Settings > Devices & Services > Add Integration** and search for "Huawei Router 5G Monitor"

### Manual Installation

1. Download the [latest release](https://github.com/PlayFaster/ha-huawei-router-5g-monitor/releases).
2. Copy the `custom_components/huawei_router_5g` folder to your Home Assistant `custom_components` directory.
3. Restart Home Assistant.
4. Go to **Settings > Devices & Services > Add Integration** and search for "Huawei Router 5G Monitor"

---

## ⚙️ Configuration

Setup is handled entirely via the UI under **Settings > Devices & Services > Add Integration**. You will need:

- **Device Name**: A custom prefix for your devices and entities (e.g., "HomeRouter").
- **Router URL**: The local URL of your router (e.g., `http://192.168.8.1` — the Huawei default).
- **Username**: Often blank for Huawei, otherwise whatever you use in the Router WebUI.
- **Password**: Your local admin password.

After setup, you can modify options (e.g. a password change) anytime via: **Settings > Devices & Services > Huawei Router 5G Monitor > Options**

---

## ❓ FAQ & Troubleshooting

### **"Failed to connect to router" Error**

- Verify the IP address is correct (the Huawei default is `192.168.8.1`)
- Confirm the username is `admin`
- Verify the password is correct (case-sensitive)
- Ensure the router is powered on and not currently rebooting

### **Some sensors showing "Unknown"**

- Most sensors showing okay with some unknown **is expected behaviour**.
  - The integration fetches everything it can from the router API.
  - Not every metric is provided by every ISP or network configuration.
  - 5G NR sensors will show "Unknown" when the router is operating in LTE-only mode.
  - These sensors can be disabled to avoid clutter.

### **All sensors showing "Unavailable" or "Unknown"**

- This is normal during a router reboot or if the router is temporarily unreachable.
  - The integration will automatically recover once the connection is restored.
- If sensors do not recover, perform these checks:
  - Ensure you can log into the router's web UI (confirms it is up and the password is correct).
  - Check your Home Assistant logs for specific error messages.
  - Delete and re-add the integration.

### **Why can't I access the router web UI while this integration is running?**

- Huawei routers are generally tolerant of concurrent sessions (e.g. via the web UI and Home Assistant), but it can be an issue.
- Use the **Pause Polling** switch in Home Assistant to halt polling and free up the session.
- Resume polling when you are done with the web UI.

---

## 📝 Maintenance Status

This is a **personal project** that exists to fill a specific gap: polling control and connected client tracking on top of what the core Huawei LTE integration already does well. Users who do not need those specific features are encouraged to use the officially maintained [core integration](https://www.home-assistant.io/integrations/huawei_lte/) instead.

Support and updates are provided on a **"best-effort"** basis only. While I use this integration daily and aim to keep it functional with the latest Home Assistant releases, I cannot guarantee immediate fixes for issues or compatibility with all router firmware versions.

---

## 🤝 Contributors & Acknowledgements

This integration stands on the shoulders of several excellent open-source projects:

- 🙏 **Home Assistant Core — Huawei LTE Integration** (@scop, @fphammerle, @joostlek, and contributors): The architectural foundation this component builds upon. The core integration is the right choice for most users — this component extends it for a specific niche. A huge thanks for the years of work that went into it.
- 🙏 **[huawei-lte-api](https://github.com/Salamek/huawei-lte-api)** (@Salamek and contributors): The underlying API library that does the heavy lifting of communicating with Huawei hardware. None of this would be possible without it.
- 🙏 **[huawei_lte_extended](https://github.com/william-aqn/huawei_lte_extended)** (@william-aqn): The expanded SMS functionality in this integration is based on this work. If SMS features are what you need, this component paired with the core integration is an excellent option.
- **Personal prior work**: The structure and integration architecture draw on my own custom components for [TP-Link 5G](https://github.com/PlayFaster/ha-tplink-router-5g-monitor) and [ZTE 5G](https://github.com/PlayFaster/ha-zte-router-5g-monitor) routers.
- This project was developed with the assistance of AI to ensure code quality and adherence to best practices.

---

## 📄 License [![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

This project is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

---

**For issues, feature requests, or contributions, please visit the [GitHub repository](https://github.com/PlayFaster/ha-huawei-router-5g-monitor).**
