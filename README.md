# Huawei Router 5G Monitor

A Home Assistant custom component to monitor Huawei LTE/5G routers.

This project is a modern implementation for Huawei routers, inspired by the ZTE and TP-Link monitor projects.

## Features

- High frequency polling (configurable)
- Signal metrics (RSRP, RSRQ, RSSI, SINR)
- Network status and operator info
- Traffic statistics
- SMS notifications (coming soon)

## Installation

1. Copy `custom_components/huawei_router_5g` to your `custom_components` folder.
2. Restart Home Assistant.
3. Add the integration via the UI.

## Credits

Based on the [huawei-lte-api](https://github.com/Salamek/huawei-lte-api) library.
Inspired by [ha-zte-router-5g-monitor](https://github.com/PlayFaster/ha-zte-router-5g-monitor).
