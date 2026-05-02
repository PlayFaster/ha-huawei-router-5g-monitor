"""Fixtures and utilities for testing the Huawei Router integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.huawei_router_5g.const import DOMAIN


@pytest.fixture
def mock_config_entry():
    """Fixture to mock a ConfigEntry."""
    entry = MockConfigEntry(
        unique_id="huawei_unique_123",
        domain=DOMAIN,
        title="My Huawei Router",
        data={"model": "B535", "sw_version": "11.0.1.1"},
        options={
            CONF_HOST: "http://192.168.8.1",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
        },
    )
    return entry


@pytest.fixture
def mock_coordinator():
    """Fixture to mock a DataUpdateCoordinator."""
    coordinator = MagicMock()
    coordinator.data = {}
    coordinator.last_update_success_time = None
    coordinator.async_request_refresh = AsyncMock()
    coordinator.model = "B535"
    coordinator.sw_version = "11.0.1.1"
    coordinator.mac = "00:11:22:33:44:55"
    return coordinator
