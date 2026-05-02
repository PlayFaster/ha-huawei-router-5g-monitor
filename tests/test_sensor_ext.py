"""Additional tests for Huawei Router 5G sensor platform."""

from datetime import UTC
from unittest.mock import patch

from custom_components.huawei_router_5g.helpers import parse_signal_value
from custom_components.huawei_router_5g.sensor import (
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
        value_fn=lambda data: data.get("val")
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

def test_sensor_timestamp_rounding(mock_coordinator, mock_config_entry):
    """Test timestamp rounding logic."""
    from datetime import datetime, timedelta
    # 12:00:00 UTC
    now = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)

    from custom_components.huawei_router_5g.sensor import _get_timestamp

    with patch("homeassistant.util.dt.now", return_value=now):
        # 1 hour uptime (3600s)
        ts = _get_timestamp("3600")
        assert ts == now - timedelta(hours=1)

        # 3650s -> round(3650/60)*60 = 61*60 = 3660s
        ts2 = _get_timestamp("3650")
        assert ts2 == now - timedelta(seconds=3660)
