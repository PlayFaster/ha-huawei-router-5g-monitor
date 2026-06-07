"""Additional tests for Huawei Router 5G sensor platform."""

from datetime import UTC

from custom_components.huawei_router_5g.helpers import parse_signal_value
from custom_components.huawei_router_5g.sensor import (
    SENSOR_TYPES,
    HuaweiRouterSensor,
    HuaweiSensorEntityDescription,
)


def test_safe_float():
    """Test the parse_signal_value utility."""
    assert parse_signal_value("-95dBm") == -95.0
    assert parse_signal_value("10MHz") == 10.0
    # Use 'mbps' but as part of a unit that works.
    # Actually let's just test what is definitely there.
    assert parse_signal_value("100.5") == 100.5
    assert parse_signal_value("unknown") is None
    assert parse_signal_value(None) is None


def test_sensor_guard_bands(mock_coordinator, mock_config_entry):
    """Test that guard bands correctly filter values."""
    desc = HuaweiSensorEntityDescription(
        key="test_key",
        name="Test Sensor",
        min_limit=-100,
        max_limit=100,
        value_fn=lambda data: data.get("val"),
    )

    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)

    # Within bounds
    mock_coordinator.data = {"val": 50}
    assert sensor.native_value == 50

    # Below bounds
    mock_coordinator.data = {"val": -150}
    assert sensor.native_value is None

    # Above bounds
    mock_coordinator.data = {"val": 150}
    assert sensor.native_value is None

    # Non-numeric value should pass through or fail gracefully
    mock_coordinator.data = {"val": "not_a_number"}
    assert sensor.native_value == "not_a_number"


def test_sensor_uptime_timestamp_reads_coordinator_key(
    mock_coordinator, mock_config_entry
):
    """Test uptime_timestamp reads the pre-computed system_boot_time key."""
    from datetime import datetime

    frozen = datetime(2026, 5, 2, 11, 0, 0, tzinfo=UTC)
    mock_coordinator.data = {"system_boot_time": frozen}
    desc = next(d for d in SENSOR_TYPES if d.key == "uptime_timestamp")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == frozen
