"""Tests for the Huawei Router 5G Monitor __init__.py."""

from unittest.mock import AsyncMock, MagicMock

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
    """Test _get_coordinator when device_id is provided."""
    from custom_components.huawei_router_5g import _get_coordinator

    mock_hass.config_entries.async_get_entry.return_value = mock_config_entry
    call_data = {"device_id": "test_entry_id"}

    coordinator = _get_coordinator(mock_hass, call_data)

    assert coordinator == mock_config_entry.runtime_data
    mock_hass.config_entries.async_get_entry.assert_called_once_with("test_entry_id")


@pytest.mark.asyncio
async def test_get_coordinator_fallback(mock_hass, mock_config_entry):
    """Test _get_coordinator fallback when device_id is missing."""
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
    """Test _get_coordinator when device_id is invalid or not DOMAIN."""
    from custom_components.huawei_router_5g import _get_coordinator

    mock_hass.config_entries.async_get_entry.return_value = None
    call_data = {"device_id": "bad_id"}

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
    call_data = {"device_id": "test_entry_id"}

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
