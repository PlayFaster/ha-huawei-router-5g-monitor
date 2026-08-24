"""Additional tests for the Huawei Router 5G integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from huawei_lte_api.exceptions import (
    ResponseErrorException,
    ResponseErrorLoginRequiredException,
)

from custom_components.huawei_router_5g.api import (
    HuaweiAuthError,
    HuaweiConnectionError,
    HuaweiRouter5GAPI,
)
from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)


@pytest.fixture(autouse=True)
def mock_report_usage():
    """Suppress 'Frame helper not set up' warnings from HA internals."""
    with patch("homeassistant.helpers.frame.report_usage"):
        yield


# ---------------------------------------------------------------------------
# api.py - mid-fetch session expiration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_data_mid_fetch_auth_error():
    """Test that a 125002 error mid-fetch raises HuaweiAuthError and resets client."""
    api = HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password")
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    # Success for first call, failure for second
    mock_client.device.information.return_value = {"SoftwareVersion": "1.0"}

    # Mock a ResponseErrorException with code 125002
    err = ResponseErrorException(message="session timeout", code=125002)
    mock_client.device.signal.side_effect = err

    # Mock to_thread to execute the fetch loop synchronously
    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())),
        pytest.raises(HuaweiAuthError),
    ):
        await api.get_data()

    assert api._client is None
    assert api._connection is None


@pytest.mark.asyncio
async def test_get_data_mid_fetch_login_required():
    """Test that ResponseErrorLoginRequiredException raises HuaweiAuthError."""
    api = HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password")
    api._client = MagicMock()
    api._connection = MagicMock()

    api._client.device.information.side_effect = ResponseErrorLoginRequiredException(
        message="login required", code=100002
    )

    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())),
        pytest.raises(HuaweiAuthError),
    ):
        await api.get_data()

    assert api._client is None


@pytest.mark.asyncio
async def test_get_data_critical_fetch_fail():
    """Test that failure in device_information raises HuaweiConnectionError."""
    api = HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password")
    api._client = MagicMock()
    api._connection = MagicMock()

    api._client.device.information.side_effect = Exception("Critical Fail")

    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())),
        pytest.raises(HuaweiConnectionError, match="Critical data fetch failed"),
    ):
        await api.get_data()


@pytest.mark.asyncio
async def test_get_data_exception_logging():
    """Test that get_data uses _LOGGER.exception on hard failures."""
    api = HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password")
    api._client = MagicMock()
    api._connection = MagicMock()

    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=Exception("Hard Fail"))),
        patch("custom_components.huawei_router_5g.api._LOGGER.exception") as mock_log,
        pytest.raises(HuaweiConnectionError),
    ):
        await api.get_data()

    mock_log.assert_called_once_with("Failed to fetch router data")


# ---------------------------------------------------------------------------
# coordinator.py - critical data guard & auth resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_critical_data_guard():
    """Test that missing device_information triggers a failure."""
    mock_entry = MagicMock()
    mock_entry.data = {"model": "Huawei", "mac": "AA:BB:CC"}
    mock_entry.options = {"scan_interval": 30}
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(return_value={"traffic_statistics": {}})

    coordinator = HuaweiRouter5GDataUpdateCoordinator(MagicMock(), mock_entry, mock_api)
    coordinator.data = {"old": "data"}
    coordinator.consecutive_failures = 3

    # Should raise UpdateFailed because device_information is missing
    with pytest.raises(UpdateFailed, match="Critical data missing"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_seamless_retry():
    """Test that coordinator retries once on HuaweiAuthError."""
    mock_entry = MagicMock()
    mock_entry.data = {"model": "Huawei", "mac": "AA:BB:CC"}
    mock_entry.options = {"scan_interval": 30}
    mock_api = MagicMock()

    # Fail first, succeed second
    mock_api.get_data = AsyncMock(
        side_effect=[
            HuaweiAuthError("Expired"),
            {"device_information": {"DeviceName": "Huawei"}},
        ]
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(MagicMock(), mock_entry, mock_api)

    result = await coordinator._async_update_data()

    assert result["device_information"]["DeviceName"] == "Huawei"
    assert coordinator.consecutive_failures == 0
    assert mock_api.get_data.call_count == 2


@pytest.mark.asyncio
async def test_coordinator_auth_error_resilience():
    """Test that HuaweiAuthError triggers 3-strike resilience."""
    mock_entry = MagicMock()
    mock_entry.data = {"model": "Huawei", "mac": "AA:BB:CC"}
    mock_entry.options = {"scan_interval": 30}
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(side_effect=HuaweiAuthError("Expired"))

    coordinator = HuaweiRouter5GDataUpdateCoordinator(MagicMock(), mock_entry, mock_api)
    coordinator.data = {"old": "data"}

    # First fail - returns old data
    result = await coordinator._async_update_data()
    assert result == {"old": "data"}
    assert coordinator.consecutive_failures == 1

    # Fourth fail - raises ConfigEntryAuthFailed
    coordinator.consecutive_failures = 3
    with pytest.raises(ConfigEntryAuthFailed, match="Authentication failed"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_log_exception_on_critical_failure():
    """Test that coordinator uses _LOGGER.exception for unknown errors."""
    mock_entry = MagicMock()
    mock_entry.data = {"model": "Huawei", "mac": "AA:BB:CC"}
    mock_entry.options = {"scan_interval": 30}
    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(side_effect=Exception("Unexpected"))
    # The general failure branch diagnoses which end is at fault before it
    # gives up, so the probe has to be awaitable here. It was not reached from
    # this branch until 2026-08-23.
    mock_api.probe_liveness = AsyncMock(return_value=False)
    mock_api.invalidate = AsyncMock()

    coordinator = HuaweiRouter5GDataUpdateCoordinator(MagicMock(), mock_entry, mock_api)
    coordinator.data = {"old": "data"}
    coordinator.consecutive_failures = 3

    with (
        patch(
            "custom_components.huawei_router_5g.coordinator._LOGGER.exception"
        ) as mock_log,
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    mock_log.assert_called_once()
