"""Tests for the organization and grouping of entities."""

from homeassistant.helpers.entity import EntityCategory

from custom_components.huawei_router_5g.binary_sensor import (
    SINGLE_SSID_MODE_DESCRIPTION,
    WIFI_5G_STATUS_DESCRIPTION,
    WIFI_24G_STATUS_DESCRIPTION,
    WIFI_STATUS_DESCRIPTION,
    HuaweiBinarySensor,
)
from custom_components.huawei_router_5g.const import DOMAIN
from custom_components.huawei_router_5g.sensor import (
    SENSOR_TYPES,
    HuaweiRouterSensor,
)
from custom_components.huawei_router_5g.switch import (
    GUEST_WIFI_DESCRIPTION,
    HuaweiSwitch,
)


def test_wifi_grouping_binary_sensors(mock_coordinator, mock_config_entry):
    """Test that WiFi binary sensors belong to the 'wifi' group."""
    mac = "DC:71:96:11:22:33"

    for desc in [
        WIFI_STATUS_DESCRIPTION,
        WIFI_24G_STATUS_DESCRIPTION,
        WIFI_5G_STATUS_DESCRIPTION,
        SINGLE_SSID_MODE_DESCRIPTION,
    ]:
        sensor = HuaweiBinarySensor(mock_coordinator, mock_config_entry, desc)
        info = sensor.device_info
        assert info["identifiers"] == {(DOMAIN, f"{mac}_wifi")}
        assert info["name"] == "My Huawei Router WiFi"
        assert info["via_device"] == (DOMAIN, f"{mac}_system")


def test_wifi_grouping_sensors(mock_coordinator, mock_config_entry):
    """Test that WiFi sensors belong to the 'wifi' group."""
    mac = "DC:71:96:11:22:33"

    desc = next(d for d in SENSOR_TYPES if d.key == "wifi_capacity")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    info = sensor.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_wifi")}
    assert info["name"] == "My Huawei Router WiFi"
    assert info["via_device"] == (DOMAIN, f"{mac}_system")
    assert sensor.entity_description.state_class is None


def test_wifi_grouping_switch(mock_coordinator, mock_config_entry):
    """Test that WiFi switches belong to the 'wifi' group."""
    mac = "DC:71:96:11:22:33"

    switch = HuaweiSwitch(mock_coordinator, mock_config_entry, GUEST_WIFI_DESCRIPTION)
    info = switch.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_wifi")}
    assert info["name"] == "My Huawei Router WiFi"
    assert info["via_device"] == (DOMAIN, f"{mac}_system")


def test_wifi_users_sensor_category(mock_coordinator, mock_config_entry):
    """Test that 'WiFi Connected' (wifi_users) is a regular sensor (not diagnostic)."""
    desc = next(d for d in SENSOR_TYPES if d.key == "wifi_users")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)

    assert sensor.entity_description.entity_category is None
    assert sensor.entity_description.group == "clients"

    info = sensor.device_info
    mac = "DC:71:96:11:22:33"
    assert info["identifiers"] == {(DOMAIN, f"{mac}_clients")}
    assert info["name"] == "My Huawei Router Clients"


def test_system_sensor_categories(mock_coordinator, mock_config_entry):
    """Test that system sensor categories are correct."""
    # Last Updated should be a regular sensor
    desc = next(d for d in SENSOR_TYPES if d.key == "last_updated")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.entity_description.entity_category is None

    # Total Uptime should be a diagnostic sensor
    desc = next(d for d in SENSOR_TYPES if d.key == "total_connection_timestamp")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.entity_description.entity_category == EntityCategory.DIAGNOSTIC
