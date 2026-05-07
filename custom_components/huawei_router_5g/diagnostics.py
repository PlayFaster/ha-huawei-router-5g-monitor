"""Diagnostics support for Huawei Router 5G Monitor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import HuaweiRouter5GDataUpdateCoordinator

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "MacAddress1",
    "wan_mac_address",
    "WanMacAddress",
    "WanIPAddress",
    "WanIPv6Address",
    "PrimaryDns",
    "SecondaryDns",
    "PrimaryIpv6Dns",
    "SecondaryIpv6Dns",
    "Ssid",
    "WifiMac",
    "SmsNumber",
    "phone",
    "content",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[HuaweiRouter5GDataUpdateCoordinator]
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    return {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator_data": async_redact_data(coordinator.data, TO_REDACT),
    }
