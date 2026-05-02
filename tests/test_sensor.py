"""Tests for the Huawei Router 5G sensors."""

from unittest.mock import MagicMock
from custom_components.huawei_router_5g.sensor import HuaweiRouterSensor, HuaweiSensorEntityDescription


async def test_sensor_native_value(mock_coordinator):
    """Test the sensor native value."""
    description = HuaweiSensorEntityDescription(
        key="test_sensor",
        name="Test Sensor",
        value_fn=lambda data: data.get("test_key"),
    )
    mock_coordinator.data = {"test_key": "test_value"}
    sensor = HuaweiRouterSensor(mock_coordinator, description)
    
    assert sensor.native_value == "test_value"
