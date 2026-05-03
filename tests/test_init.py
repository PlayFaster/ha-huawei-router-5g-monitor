"""Tests for the Huawei Router 5G integration setup and coordinator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.huawei_router_5g import (
    PLATFORMS,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.huawei_router_5g.const import (
    CONF_STOP_POLLING,
    DOMAIN,
)
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
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_register = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_update_entry = MagicMock()
    return hass


# ---------------------------------------------------------------------------
# async_setup (Service Registration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_setup_registers_service(mock_hass):
    """Test async_setup registers send_sms service when not already registered."""
    mock_hass.services.has_service.return_value = False

    result = await async_setup(mock_hass, {})

    assert result is True
    mock_hass.services.async_register.assert_called_once()
    call_args = mock_hass.services.async_register.call_args
    assert call_args[0][0] == DOMAIN
    assert call_args[0][1] == "send_sms"
    # Check schema validation
    schema = call_args[1]["schema"]
    assert isinstance(schema, vol.Schema)
    # Test schema with valid data
    valid_data = {"target": "1234567890", "message": "Hello"}
    assert schema(valid_data) == valid_data
    # Test schema with invalid data (too long message)
    with pytest.raises(vol.Invalid):
        schema({"target": "123", "message": "x" * 161})


@pytest.mark.asyncio
async def test_async_setup_service_already_registered(mock_hass):
    """Test async_setup skips registration if service already exists."""
    mock_hass.services.has_service.return_value = True

    result = await async_setup(mock_hass, {})

    assert result is True
    mock_hass.services.async_register.assert_not_called()


@pytest.mark.asyncio
async def test_async_send_sms_service_integration(mock_hass, mock_config_entry):
    """Test the send_sms service call integration."""
    from custom_components.huawei_router_5g import async_send_sms

    mock_coordinator = MagicMock()
    mock_coordinator.api = MagicMock()
    mock_coordinator.api.send_sms = AsyncMock()

    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_config_entry])
    mock_config_entry.runtime_data = mock_coordinator

    service_call = MagicMock()
    service_call.data = {"target": "+441234567890", "message": "Test SMS"}

    await async_send_sms(mock_hass, service_call)

    mock_coordinator.api.send_sms.assert_called_once_with(["+441234567890"], "Test SMS")


@pytest.mark.asyncio
async def test_async_send_sms_service_no_entries(mock_hass):
    """Test send_sms service when no config entries exist."""
    from custom_components.huawei_router_5g import async_send_sms

    mock_hass.config_entries.async_entries = MagicMock(return_value=[])

    service_call = MagicMock()
    service_call.data = {"target": "123", "message": "test"}

    with pytest.raises(HomeAssistantError, match="No Huawei Router 5G entries found"):
        await async_send_sms(mock_hass, service_call)


@pytest.mark.asyncio
async def test_async_send_sms_service_entry_not_ready(mock_hass, mock_config_entry):
    """Test send_sms service when entry runtime_data is missing."""
    from custom_components.huawei_router_5g import async_send_sms

    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_config_entry])
    mock_config_entry.runtime_data = None

    service_call = MagicMock()
    service_call.data = {"target": "123", "message": "test"}

    with pytest.raises(
        HomeAssistantError,
        match=f"Integration entry {mock_config_entry.title} not ready",
    ):
        await async_send_sms(mock_hass, service_call)


@pytest.mark.asyncio
async def test_async_send_sms_service_api_error(mock_hass, mock_config_entry):
    """Test send_sms service when API call fails."""
    from custom_components.huawei_router_5g import async_send_sms

    mock_coordinator = MagicMock()
    mock_coordinator.api = MagicMock()
    mock_coordinator.api.send_sms = AsyncMock(side_effect=Exception("API error"))

    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_config_entry])
    mock_config_entry.runtime_data = mock_coordinator

    service_call = MagicMock()
    service_call.data = {"target": "123", "message": "test"}

    with pytest.raises(HomeAssistantError, match="Failed to send SMS"):
        await async_send_sms(mock_hass, service_call)


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


@pytest.mark.asyncio
async def test_setup_entry_no_mac(mock_hass, mock_config_entry):
    """Test that setup works even if MAC is missing (falls back to host prefix)."""
    # Create a new config entry without MAC in data
    from homeassistant.const import CONF_HOST, CONF_PASSWORD
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="No MAC Router",
        data={"model": "B535"},
        options={CONF_HOST: "http://192.168.8.100", CONF_PASSWORD: "password"},
    )

    # Use the same background task helper as the main fixture
    background_coros = []

    def mock_create_task(hass, coro, name):
        background_coros.append(coro)
        return MagicMock()

    entry.async_create_background_task = MagicMock(side_effect=mock_create_task)

    mock_dev_reg = MagicMock()

    with (
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI"),
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_dev_reg,
        ),
    ):
        await async_setup_entry(mock_hass, entry)

    # Clean up background tasks to avoid warnings
    for coro in background_coros:
        coro.close()

    # Verify identifiers use host prefix
    calls = mock_dev_reg.async_get_or_create.call_args_list
    assert any(
        "host_http://192.168.8.100_system" in str(c.kwargs["identifiers"])
        for c in calls
    )


@pytest.mark.asyncio
async def test_setup_entry_background_task_failure(mock_hass, mock_config_entry):
    """Test that a failure in the background initialization task is handled."""
    with (
        patch(
            "custom_components.huawei_router_5g.HuaweiRouter5GAPI", autospec=True
        ) as mock_api_cls,
        patch("homeassistant.helpers.device_registry.async_get"),
        patch("custom_components.huawei_router_5g._LOGGER") as mock_logger,
    ):
        mock_api = mock_api_cls.return_value
        mock_api.login = AsyncMock(side_effect=Exception("Background Fail"))

        background_coro = None

        def mock_create_task(hass, coro, name):
            nonlocal background_coro
            background_coro = coro
            return MagicMock()

        # Ensure we are replacing the MagicMock correctly
        mock_config_entry.async_create_background_task.side_effect = mock_create_task

        result = await async_setup_entry(mock_hass, mock_config_entry)

        if background_coro:
            await background_coro

    assert result is True
    # The error should be logged as a warning
    assert mock_logger.warning.called


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
    mock_hass.config_entries.async_unload_platforms.assert_called_once_with(
        mock_config_entry, PLATFORMS
    )


@pytest.mark.asyncio
async def test_unload_entry_logout_exception(mock_hass, mock_config_entry):
    """Test that logout exceptions during unload are suppressed."""
    coordinator = MagicMock()
    coordinator.api.logout = AsyncMock(side_effect=Exception("Logout Fail"))
    mock_config_entry.runtime_data = coordinator
    mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    result = await async_unload_entry(mock_hass, mock_config_entry)

    assert result is True  # still unloads successfully


@pytest.mark.asyncio
async def test_unload_entry_no_coordinator(mock_hass, mock_config_entry):
    """Test that unloading works even if coordinator is missing."""
    mock_config_entry.runtime_data = None
    mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    result = await async_unload_entry(mock_hass, mock_config_entry)

    assert result is True


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
