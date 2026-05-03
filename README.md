# Huawei Router 5G Monitor for Home Assistant

[![HACS Integration](https://img.shields.io/badge/HACS-Integration-orange.svg)](https://hacs.xyz/) [![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistant&logoColor=white)](https://hacs.xyz/docs/faq/custom_repositories) [![Latest Release](https://img.shields.io/github/v/release/PlayFaster/ha-huawei-router-5g-monitor?label=Release&logo=github)](https://github.com/PlayFaster/ha-huawei-router-5g-monitor/releases) [![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0) [![Validate](https://github.com/PlayFaster/ha-huawei-router-5g-monitor/actions/workflows/validate.yaml/badge.svg)](https://github.com/PlayFaster/ha-huawei-router-5g-monitor/actions/workflows/validate.yaml) ![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/PlayFaster/b5cb47f2b37e140da07eefd17ac19721/raw/coverage.json) [![Last Commit](https://img.shields.io/github/last-commit/PlayFaster/ha-huawei-router-5g-monitor?label=Last%20commit)](https://github.com/PlayFaster/ha-huawei-router-5g-monitor/commits/main)

A Home Assistant integration for **Huawei CPE6 LTE/5G routers**, providing extensive signal diagnostics, data tracking, SMS management, and connected client monitoring.

> [!NOTE] This project builds on the excellent work of [Salamek/huawei-lte-api](https://github.com/Salamek/huawei-lte-api). It is optimised to provide deep 5G/LTE metrics alongside SMS management and device tracking.

- If you have a Huawei LTE/5G router and want to closely monitor your connection, this integration is for you!
- If you are looking for a general-purpose Huawei LTE integration, the official [Huawei LTE](https://www.home-assistant.io/integrations/huawei_lte/) integration is also available.

## 🔧 Compatibility & Requirements

**Router Hardware:**

- **Supported**: **Huawei CP6**, and similar Huawei LTE/5G CPE and router models.
  - _Has been tested with the CP6. Compatibility with other models may vary._
  - Uses the `huawei-lte-api` library which supports a wide range of Huawei hardware.
- **Not Supported**: Non-Huawei hardware.

**Network:**

- Local network access to the router is required.

**Home Assistant Version:**

- Minimum: Home Assistant **2025.1**

---

## ✅ Features

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
- **SMS Management**: Unread SMS counts, last message content, **Send SMS** service, and HA event firing on new messages.
- **Preferred Network Mode**: Select between Auto, 4G Only, 5G Only, and other available modes.
- **100% Local**: No cloud account or internet access required.

### 💡 Useful Features

- **SMS Events**: Fires a `huawei_router_5g_sms_event` event when a new message is detected, enabling automations triggered by incoming texts.
- **Pause Polling**: Switch to halt polling when you need uninterrupted access to the router's web UI.
- **Configurable Update Interval**: From 30 seconds to 1 hour.

> [!TIP]
>
> **Polling Interval can be controlled dynamically, via automation**
>
> - Polling Interval is available as a number control within the device, you can change it via automation, if desired.
> - Set it to 30 seconds during periods of heavy use to examine connection quality and set it higher afterwards, to avoid taxing the router and your Home Assistant database.

### 🏗️ Under the Hood

- **Data Validation**: Router values are checked for validity (guard band limits), with out-of-range sensors being marked as unknown.
- **Zero-Blocking Startup**: Home Assistant starts instantly. Hardware identity is loaded from memory, while the first poll happens quietly in the background.
- **Flat Identity Pattern**: Device information (Model, MAC, Version) remains stable and visible even if the router is temporarily offline.
- **Native Resilience**: Built-in 3-strike logic masks transient network glitches and holds last-known-good data between retries.

---

## 📊 What You Get

This integration provides **101+ entities** grouped into five logical devices: **System**, **Signal**, **Data**, **SMS**, and **Clients**.

| Type | Count | Primary Functions |
| :-- | :-- | :-- |
| **Sensors** | 89 | Signal strength, data usage, uptime, SMS counts, device info |
| **Binary Sensors** | 7 | WiFi status, mobile connection, 5G NR active, SMS storage full |
| **Switches** | 3 | Pause Polling, Mobile Data, Guest WiFi |
| **Controls** | 5 | Reboot, Clear Traffic, Polling Interval, Network Mode, Send SMS service |
| **Device Trackers** | 1+ | Dynamically discovered per connected LAN/WLAN client |

> [!TIP]
>
> **Clean up your UI: Disable Unnecessary Devices or Entities**
>
> - If you are running in Bridge Mode you may not need the Clients sub-device or all Signal diagnostic entities.
> - Devices and their entities can be disabled from the main device page - (⋮ menu) "Disable Device".
> - Individual entities can be disabled via the entity properties, or in bulk on the entities list page.

---

## ❔ What's Missing?

- **SMS Inbox Browsing**: The integration provides the last received message content and unread counts. Browsing the full inbox or replying to specific messages requires the router's web interface.

---

## 📸 Screenshots

### Integration Overview

![Integration](.github/images/huawei_5g_integration_screen.png)

| Signal Data | Signal Diagnostics |
| :-: | :-: |
| ![Sensors](.github/images/huawei_5g_sensor_screen_mini.png) | ![Diagnostics](.github/images/huawei_5g_diagnostic_screen_mini.png) |

| System | Data | SMS Management |
| :-: | :-: | :-: |
| ![System](.github/images/huawei_5g_system_screen_mini.png) | ![Data](.github/images/huawei_5g_data_screen_mini.png) | ![SMS](.github/images/huawei_5g_sms_screen_mini.png) |

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
- **IP Address**: The local IP of your router (e.g., `192.168.8.1` — the Huawei default).
- **Username**: Usually `admin`.
- **Password**: Your local admin password.
- **Scan Interval** (optional, default 2 minutes, range 30s to 1 hour)

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

- Huawei routers limit concurrent sessions to one simultaneous login.
- Use the **Pause Polling** switch in Home Assistant to halt polling and free up the session.
- Resume polling when you are done with the web UI.

---

## 📝 Maintenance Status

This is a **personal project**. Support and updates are provided on a **"best-effort"** basis only. While I use this integration daily and aim to keep it functional with the latest Home Assistant releases, I cannot guarantee immediate fixes for issues or compatibility with all router firmware versions.

---

## 🤝 Contributors & Acknowledgements

- 🙏 Special Thanks: This project builds on the excellent work done by @Salamek and contributors on the [huawei-lte-api](https://github.com/Salamek/huawei-lte-api) library. A big thanks for the heavy lifting!
- This project was developed with the assistance of AI to ensure code quality and adherence to best practices.

---

## 📄 License [![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

This project is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

---

**For issues, feature requests, or contributions, please visit the [GitHub repository](https://github.com/PlayFaster/ha-huawei-router-5g-monitor).**
