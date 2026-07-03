"""Tests for the Huawei Router 5G Monitor __init__.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from huawei_lte_api.enums.sms import BoxTypeEnum

from custom_components.huawei_router_5g import (
    DOMAIN,
    async_delete_all_sms,
    async_delete_sms,
    async_get_sms_list,
    async_send_sms,
    async_setup,
)


@pytest.fixture
def mock_hass():
    """Mock Home Assistant."""
    hass = MagicMock(spec=HomeAssistant)
    hass.services = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock()
    return hass


@pytest.fixture
def mock_coordinator():
    """Mock Coordinator."""
    coordinator = MagicMock()
    coordinator.api = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


@pytest.fixture
def mock_config_entry(mock_coordinator):
    """Mock Config Entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.title = "Test Router"
    entry.domain = DOMAIN
    entry.runtime_data = mock_coordinator
    return entry


@pytest.mark.asyncio
async def test_async_setup_registers_services(mock_hass):
    """Test that async_setup registers all expected services."""
    mock_hass.services.has_service.return_value = False

    result = await async_setup(mock_hass, {})

    assert result is True
    assert mock_hass.services.async_register.call_count == 4

    # Check registration of specific services
    calls = mock_hass.services.async_register.call_args_list
    registered_services = [call[0][1] for call in calls]
    assert "send_sms" in registered_services
    assert "delete_sms" in registered_services
    assert "delete_all_sms" in registered_services
    assert "get_sms_list" in registered_services


@pytest.mark.asyncio
async def test_get_coordinator_by_id(mock_hass, mock_config_entry):
    """Test _get_coordinator when entry_id is provided."""
    from custom_components.huawei_router_5g import _get_coordinator

    mock_hass.config_entries.async_get_entry.return_value = mock_config_entry
    call_data = {"entry_id": "test_entry_id"}

    coordinator = _get_coordinator(mock_hass, call_data)

    assert coordinator == mock_config_entry.runtime_data
    mock_hass.config_entries.async_get_entry.assert_called_once_with("test_entry_id")


@pytest.mark.asyncio
async def test_get_coordinator_fallback(mock_hass, mock_config_entry):
    """Test _get_coordinator fallback when entry_id is missing."""
    from custom_components.huawei_router_5g import _get_coordinator

    mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
    call_data = {}

    coordinator = _get_coordinator(mock_hass, call_data)

    assert coordinator == mock_config_entry.runtime_data


@pytest.mark.asyncio
async def test_get_coordinator_not_found(mock_hass):
    """Test _get_coordinator raises error when no entries found."""
    from custom_components.huawei_router_5g import _get_coordinator

    mock_hass.config_entries.async_entries.return_value = []
    call_data = {}

    with pytest.raises(
        HomeAssistantError, match="No active Huawei Router 5G entries found"
    ):
        _get_coordinator(mock_hass, call_data)


@pytest.mark.asyncio
async def test_get_coordinator_multiple_entries(mock_hass):
    """Test _get_coordinator requires entry_id when more than one router is loaded."""
    from custom_components.huawei_router_5g import _get_coordinator

    entry_a = MagicMock()
    entry_a.runtime_data = MagicMock()
    entry_b = MagicMock()
    entry_b.runtime_data = MagicMock()
    mock_hass.config_entries.async_entries.return_value = [entry_a, entry_b]

    with pytest.raises(HomeAssistantError, match="specify entry_id"):
        _get_coordinator(mock_hass, {})


@pytest.mark.asyncio
async def test_async_send_sms_service(mock_hass, mock_coordinator, mock_config_entry):
    """Test the send_sms service handler."""
    mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
    mock_coordinator.api.send_sms = AsyncMock()

    call = MagicMock(spec=ServiceCall)
    call.data = {"target": ["+123"], "message": "hello"}

    await async_send_sms(mock_hass, call)

    mock_coordinator.api.send_sms.assert_awaited_once_with(["+123"], "hello")


@pytest.mark.asyncio
async def test_async_delete_sms_service(mock_hass, mock_coordinator, mock_config_entry):
    """Test the delete_sms service handler."""
    mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
    mock_coordinator.api.delete_sms = AsyncMock()

    call = MagicMock(spec=ServiceCall)
    call.data = {"index": 5}

    await async_delete_sms(mock_hass, call)

    mock_coordinator.api.delete_sms.assert_awaited_once_with(5)
    mock_coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_delete_all_sms_service(
    mock_hass, mock_coordinator, mock_config_entry
):
    """Test the delete_all_sms service handler."""
    mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
    mock_coordinator.api.get_sms_list = AsyncMock(
        return_value={
            "Messages": {"Message": [{"Index": "1"}, {"Index": "2"}, {"Index": "3"}]}
        }
    )
    mock_coordinator.api.delete_sms = AsyncMock()

    # Keep last 1, so delete 2 and 3
    # (messages are usually newest first in our parse_sms_list)
    call = MagicMock(spec=ServiceCall)
    call.data = {"keep_last": 1}

    await async_delete_all_sms(mock_hass, call)

    assert mock_coordinator.api.delete_sms.call_count == 2
    mock_coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_coordinator_by_id_invalid(mock_hass, mock_config_entry):
    """Test _get_coordinator when entry_id is invalid or not DOMAIN."""
    from custom_components.huawei_router_5g import _get_coordinator

    mock_hass.config_entries.async_get_entry.return_value = None
    call_data = {"entry_id": "bad_id"}

    with pytest.raises(
        HomeAssistantError, match="No active Huawei Router 5G entries found"
    ):
        _get_coordinator(mock_hass, call_data)


@pytest.mark.asyncio
async def test_get_coordinator_entry_not_ready(mock_hass):
    """Test _get_coordinator when entry has no runtime_data."""
    from custom_components.huawei_router_5g import _get_coordinator

    entry = MagicMock()
    entry.domain = DOMAIN
    entry.runtime_data = None
    mock_hass.config_entries.async_get_entry.return_value = entry
    call_data = {"entry_id": "test_entry_id"}

    with pytest.raises(HomeAssistantError, match=r"Router .* is not ready"):
        _get_coordinator(mock_hass, call_data)


@pytest.mark.asyncio
async def test_async_send_sms_service_error(
    mock_hass, mock_coordinator, mock_config_entry
):
    """Test the send_sms service error handling."""
    mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
    mock_coordinator.api.send_sms = AsyncMock(side_effect=Exception("API Error"))

    call = MagicMock(spec=ServiceCall)
    call.data = {"target": ["+123"], "message": "hello"}

    with pytest.raises(HomeAssistantError, match="Failed to send SMS"):
        await async_send_sms(mock_hass, call)


@pytest.mark.asyncio
async def test_async_delete_sms_service_error(
    mock_hass, mock_coordinator, mock_config_entry
):
    """Test the delete_sms service error handling."""
    mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
    mock_coordinator.api.delete_sms = AsyncMock(side_effect=Exception("API Error"))

    call = MagicMock(spec=ServiceCall)
    call.data = {"index": 5}

    with pytest.raises(HomeAssistantError, match="Failed to delete SMS"):
        await async_delete_sms(mock_hass, call)


@pytest.mark.asyncio
async def test_async_delete_all_sms_service_error(
    mock_hass, mock_coordinator, mock_config_entry
):
    """Test the delete_all_sms service error handling."""
    mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
    mock_coordinator.api.get_sms_list = AsyncMock(side_effect=Exception("API Error"))

    call = MagicMock(spec=ServiceCall)
    call.data = {"keep_last": 0}

    with pytest.raises(HomeAssistantError, match="Failed to delete all SMS"):
        await async_delete_all_sms(mock_hass, call)


@pytest.mark.asyncio
async def test_async_get_sms_list_service_error(
    mock_hass, mock_coordinator, mock_config_entry
):
    """Test the get_sms_list service error handling."""
    mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
    mock_coordinator.api.get_sms_list = AsyncMock(side_effect=Exception("API Error"))

    call = MagicMock(spec=ServiceCall)
    call.data = {"page": 1, "count": 20, "box_type": 1}

    with pytest.raises(HomeAssistantError, match="Failed to fetch SMS list"):
        await async_get_sms_list(mock_hass, call)


@pytest.mark.asyncio
async def test_async_get_sms_list_service_success(
    mock_hass, mock_coordinator, mock_config_entry
):
    """Test the get_sms_list service success path."""
    mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
    mock_coordinator.api.get_sms_list = AsyncMock(
        return_value={
            "Messages": {
                "Message": [
                    {
                        "Index": "1",
                        "Phone": "123",
                        "Content": "hi",
                        "Date": "now",
                        "Smstat": "1",
                    }
                ]
            }
        }
    )

    call = MagicMock(spec=ServiceCall)
    call.data = {"page": 1, "count": 20, "box_type": 1}

    response = await async_get_sms_list(mock_hass, call)

    assert "messages" in response
    assert len(response["messages"]) == 1
    assert response["messages"][0]["content"] == "hi"


@pytest.mark.asyncio
async def test_async_setup_registers_and_calls_services(mock_hass):
    """Test that async_setup registers services and they can be called."""
    mock_hass.services.has_service.return_value = False

    result = await async_setup(mock_hass, {})
    assert result is True

    registered_callbacks = {}
    for call_args in mock_hass.services.async_register.call_args_list:
        service_name = call_args[0][1]
        callback = call_args[0][2]
        registered_callbacks[service_name] = callback

    with (
        patch("custom_components.huawei_router_5g.async_send_sms") as mock_send,
        patch("custom_components.huawei_router_5g.async_delete_sms") as mock_delete,
        patch(
            "custom_components.huawei_router_5g.async_delete_all_sms"
        ) as mock_delete_all,
        patch("custom_components.huawei_router_5g.async_get_sms_list") as mock_get_list,
    ):
        mock_call = MagicMock()

        await registered_callbacks["send_sms"](mock_call)
        mock_send.assert_called_once_with(mock_hass, mock_call)

        await registered_callbacks["delete_sms"](mock_call)
        mock_delete.assert_called_once_with(mock_hass, mock_call)

        await registered_callbacks["delete_all_sms"](mock_call)
        mock_delete_all.assert_called_once_with(mock_hass, mock_call)

        await registered_callbacks["get_sms_list"](mock_call)
        mock_get_list.assert_called_once_with(mock_hass, mock_call)


@pytest.mark.asyncio
async def test_async_setup_entry_and_unload(mock_hass):
    """Test async_setup_entry and async_unload_entry."""
    from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

    from custom_components.huawei_router_5g import async_setup_entry, async_unload_entry

    mock_entry = MagicMock()
    mock_entry.options = {
        CONF_HOST: "192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "pw",
    }
    mock_entry.data = {
        "mac": "00:11:22:33:44:55",
        "model": "B535",
        "sw_version": "1.0",
        "hw_version": "2.0",
    }
    mock_entry.entry_id = "test_id"
    mock_entry.title = "My Router"

    mock_registry = MagicMock()
    with (
        patch(
            "custom_components.huawei_router_5g.dr.async_get",
            return_value=mock_registry,
        ),
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI") as mock_api_class,
        patch(
            "custom_components.huawei_router_5g.HuaweiRouter5GDataUpdateCoordinator"
        ) as mock_coord_class,
    ):
        # Test setup
        result = await async_setup_entry(mock_hass, mock_entry)
        assert result is True
        assert mock_registry.async_get_or_create.call_count == 2
        mock_hass.config_entries.async_forward_entry_setups.assert_called_once()
        mock_entry.async_create_background_task.assert_called_once()

        # Extract the background task
        bg_task_coro = mock_entry.async_create_background_task.call_args[0][1]

        # Run background task
        mock_api_instance = mock_api_class.return_value
        mock_coord_instance = mock_coord_class.return_value
        mock_api_instance.login = AsyncMock()
        mock_coord_instance.async_refresh = AsyncMock()

        await bg_task_coro
        mock_api_instance.login.assert_called_once()
        mock_coord_instance.async_refresh.assert_called_once()

        # Test unload
        mock_entry.runtime_data = mock_coord_instance
        mock_coord_instance.api.logout = AsyncMock()
        mock_hass.config_entries.async_unload_platforms.return_value = True

        unload_result = await async_unload_entry(mock_hass, mock_entry)
        assert unload_result is True
        mock_coord_instance.api.logout.assert_called_once()
        mock_hass.config_entries.async_unload_platforms.assert_called_once()

        # Run background task with exception by doing a fresh setup
        mock_entry2 = MagicMock()
        mock_entry2.options = mock_entry.options
        mock_entry2.data = mock_entry.data
        mock_entry2.entry_id = "test_id2"
        mock_entry2.title = "My Router 2"

        await async_setup_entry(mock_hass, mock_entry2)
        bg_task_coro2 = mock_entry2.async_create_background_task.call_args[0][1]
        mock_api_instance.login.side_effect = Exception("Background Error")
        await bg_task_coro2


@pytest.mark.parametrize("box_type", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
@pytest.mark.asyncio
async def test_async_get_sms_list_box_types(
    mock_hass, mock_coordinator, mock_config_entry, box_type
):
    """Test that all supported box types are accepted."""
    mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
    mock_coordinator.api.get_sms_list = AsyncMock(return_value={})

    call = MagicMock(spec=ServiceCall)
    call.data = {"page": 1, "count": 20, "box_type": box_type}

    # Should not raise vol.Invalid
    await async_get_sms_list(mock_hass, call)
    mock_coordinator.api.get_sms_list.assert_called_with(
        page=1, box_type=BoxTypeEnum(box_type), read_count=20
    )
