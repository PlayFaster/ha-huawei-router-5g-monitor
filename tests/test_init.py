"""Tests for the Huawei Router 5G integration setup and coordinator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.huawei_router_5g import async_setup_entry, async_unload_entry
from custom_components.huawei_router_5g.const import CONF_STOP_POLLING, DOMAIN
from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)


@pytest.fixture(autouse=True)
def mock_report_usage():
    """Suppress 'Frame helper not set up' warnings from HA internals."""
    with patch("homeassistant.helpers.frame.report_usage"):
        yield


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance with the async methods needed for setup."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_update_entry = MagicMock()
    return hass


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_entry_success(mock_hass, mock_config_entry):
    """Test that setup creates the coordinator and registers the system device."""
    with (
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI"),
        patch("homeassistant.helpers.device_registry.async_get"),
    ):
        result = await async_setup_entry(mock_hass, mock_config_entry)

    assert result is True
    assert mock_config_entry.runtime_data is not None
    coordinator = mock_config_entry.runtime_data
    assert isinstance(coordinator, HuaweiRouter5GDataUpdateCoordinator)
    mock_hass.config_entries.async_forward_entry_setups.assert_called_once()
    mock_config_entry.async_create_background_task.assert_called_once()


@pytest.mark.asyncio
async def test_setup_entry_creates_system_device(mock_hass, mock_config_entry):
    """Test that setup registers the root system device in the device registry."""
    mock_dev_reg = MagicMock()

    with (
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI"),
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_dev_reg,
        ),
    ):
        await async_setup_entry(mock_hass, mock_config_entry)

    assert mock_dev_reg.async_get_or_create.call_count == 2

    mac = "DC:71:96:11:22:33"
    calls = mock_dev_reg.async_get_or_create.call_args_list

    # Check System device call
    system_call = next(
        c for c in calls if (DOMAIN, f"{mac}_system") in c.kwargs["identifiers"]
    )
    assert system_call.kwargs["name"] == f"{mock_config_entry.title} System"

    # Check Clients device call
    clients_call = next(
        c for c in calls if (DOMAIN, f"{mac}_clients") in c.kwargs["identifiers"]
    )
    assert clients_call.kwargs["name"] == f"{mock_config_entry.title} Clients"
    assert clients_call.kwargs["via_device"] == (DOMAIN, f"{mac}_system")


# ---------------------------------------------------------------------------
# async_unload_entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unload_entry_success(mock_hass, mock_config_entry):
    """Test that unloading calls logout and unloads platforms."""
    coordinator = MagicMock()
    mock_config_entry.runtime_data = coordinator
    mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    result = await async_unload_entry(mock_hass, mock_config_entry)

    assert result is True
    coordinator.api.logout.assert_called_once()


# ---------------------------------------------------------------------------
# Coordinator — _async_update_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_update_data_success(mock_hass, mock_config_entry):
    """Test that a successful fetch resets consecutive_failures and timestamps."""
    with (
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI") as mock_api_cls,
        patch("homeassistant.helpers.device_registry.async_get"),
    ):
        mock_api = mock_api_cls.return_value
        mock_api.get_data = AsyncMock(
            return_value={"device_information": {"DeviceName": "B535s-232"}}
        )

        await async_setup_entry(mock_hass, mock_config_entry)
        coordinator = mock_config_entry.runtime_data

        data = await coordinator._async_update_data()

    assert data["device_information"]["DeviceName"] == "B535s-232"
    assert coordinator.consecutive_failures == 0
    assert coordinator.last_update_success_time is not None


@pytest.mark.asyncio
async def test_async_update_data_paused_returns_cache(mock_hass, mock_config_entry):
    """Test that a paused coordinator returns cached data without fetching."""
    new_options = dict(mock_config_entry.options)
    new_options[CONF_STOP_POLLING] = True
    object.__setattr__(mock_config_entry, "options", new_options)

    with (
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI"),
        patch("homeassistant.helpers.device_registry.async_get"),
    ):
        await async_setup_entry(mock_hass, mock_config_entry)
        coordinator = mock_config_entry.runtime_data
        coordinator.data = {"cached": "data"}

        data = await coordinator._async_update_data()

    assert data == {"cached": "data"}


@pytest.mark.asyncio
async def test_async_update_data_paused_first_run_returns_empty(
    mock_hass, mock_config_entry
):
    """Test that a paused coordinator on first run returns empty dict (not raises)."""
    new_options = dict(mock_config_entry.options)
    new_options[CONF_STOP_POLLING] = True
    object.__setattr__(mock_config_entry, "options", new_options)

    with (
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI") as mock_api_cls,
        patch("homeassistant.helpers.device_registry.async_get"),
    ):
        mock_api = mock_api_cls.return_value
        mock_api.get_data = AsyncMock(side_effect=Exception("No connection"))

        await async_setup_entry(mock_hass, mock_config_entry)
        coordinator = mock_config_entry.runtime_data
        coordinator.data = None  # first run

        data = await coordinator._async_update_data()

    assert data == {}


@pytest.mark.asyncio
async def test_async_update_data_resilience(mock_hass, mock_config_entry):
    """Test that up to 3 failures hold cached data; 4th raises UpdateFailed."""
    with (
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI") as mock_api_cls,
        patch("homeassistant.helpers.device_registry.async_get"),
    ):
        mock_api = mock_api_cls.return_value
        mock_api.get_data = AsyncMock(side_effect=Exception("Persistent Fail"))

        await async_setup_entry(mock_hass, mock_config_entry)
        coordinator = mock_config_entry.runtime_data
        coordinator.data = {"old": "data"}

        # Failures 1-3: return cached data
        for n in range(1, 4):
            data = await coordinator._async_update_data()
            assert data == {"old": "data"}
            assert coordinator.consecutive_failures == n

        # Failure 4: raise UpdateFailed
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator.consecutive_failures == 4


@pytest.mark.asyncio
async def test_async_update_data_timeout_resilience(mock_hass, mock_config_entry):
    """Test that TimeoutError counts toward resilience the same way as other errors."""
    with (
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI") as mock_api_cls,
        patch("homeassistant.helpers.device_registry.async_get"),
    ):
        mock_api = mock_api_cls.return_value
        mock_api.get_data = AsyncMock(side_effect=TimeoutError)

        await async_setup_entry(mock_hass, mock_config_entry)
        coordinator = mock_config_entry.runtime_data
        coordinator.data = {"old": "data"}

        for n in range(1, 4):
            data = await coordinator._async_update_data()
            assert data == {"old": "data"}
            assert coordinator.consecutive_failures == n

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_background_setup_failure_is_handled(mock_hass, mock_config_entry):
    """Test that a background initialization failure is silently logged (no crash)."""
    with (
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI") as mock_api_cls,
        patch("homeassistant.helpers.device_registry.async_get"),
    ):
        mock_api = mock_api_cls.return_value
        mock_api.login = AsyncMock(side_effect=Exception("Login fail"))

        background_coro = None

        def capture_task(hass, coro, name):
            nonlocal background_coro
            background_coro = coro
            return MagicMock()

        mock_config_entry.async_create_background_task = capture_task

        await async_setup_entry(mock_hass, mock_config_entry)

        if background_coro:
            await background_coro  # should not raise
