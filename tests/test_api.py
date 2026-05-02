"""Tests for the Huawei Router 5G API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.huawei_router_5g.api import (
    HuaweiAuthError,
    HuaweiConnectionError,
    HuaweiRouter5GAPI,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api() -> HuaweiRouter5GAPI:
    return HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password")


# ---------------------------------------------------------------------------
# login()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success():
    """Test that login creates the connection and client."""
    api = _make_api()

    mock_conn = MagicMock()
    mock_client = MagicMock()

    with patch.object(
        api, "_create_connection_sync", return_value=(mock_conn, mock_client)
    ):
        await api.login()

    assert api._connection is mock_conn
    assert api._client is mock_client


@pytest.mark.asyncio
async def test_login_auth_error():
    """Test that a credentials-related error raises HuaweiAuthError."""
    api = _make_api()

    with (
        patch.object(
            api,
            "_create_connection_sync",
            side_effect=Exception("Wrong password"),
        ),
        pytest.raises(HuaweiAuthError),
    ):
        await api.login()

    assert api._client is None


@pytest.mark.asyncio
async def test_login_connection_error():
    """Test that a network error raises HuaweiConnectionError."""
    api = _make_api()

    with (
        patch.object(
            api,
            "_create_connection_sync",
            side_effect=Exception("Connection refused"),
        ),
        pytest.raises(HuaweiConnectionError),
    ):
        await api.login()

    assert api._client is None


# ---------------------------------------------------------------------------
# logout()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_clears_client():
    """Test that logout clears the stored connection."""
    api = _make_api()
    mock_conn = MagicMock()
    mock_client = MagicMock()
    api._connection = mock_conn
    api._client = mock_client

    with patch("asyncio.to_thread", new=AsyncMock()):
        await api.logout()

    assert api._connection is None
    assert api._client is None


@pytest.mark.asyncio
async def test_logout_no_connection():
    """Test that logout is a no-op when not connected."""
    api = _make_api()
    await api.logout()  # should not raise


# ---------------------------------------------------------------------------
# get_data()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_data_success():
    """Test successful data fetch returns expected keys."""
    api = _make_api()
    mock_conn = MagicMock()
    mock_client = MagicMock()
    api._connection = mock_conn
    api._client = mock_client

    expected_data = {
        "device_information": {"DeviceName": "B535s-232"},
        "device_signal": {"rsrp": "-95dBm"},
        "monitoring_status": {"SignalIcon": "4"},
        "traffic_statistics": {"CurrentDownloadRate": "1024"},
        "month_statistics": {"CurrentMonthDownload": "1073741824"},
        "current_plmn": {"FullName": "Three"},
        "sms_count": {"LocalUnread": "0"},
        "mobile_dataswitch": {"dataswitch": "1"},
    }

    # Map each endpoint to its expected return value
    mock_client.device.information.return_value = expected_data["device_information"]
    mock_client.device.signal.return_value = expected_data["device_signal"]
    mock_client.monitoring.status.return_value = expected_data["monitoring_status"]
    mock_client.monitoring.traffic_statistics.return_value = expected_data[
        "traffic_statistics"
    ]
    mock_client.monitoring.month_statistics.return_value = expected_data[
        "month_statistics"
    ]
    mock_client.net.current_plmn.return_value = expected_data["current_plmn"]
    mock_client.sms.sms_count.return_value = expected_data["sms_count"]
    mock_client.dial_up.mobile_dataswitch.return_value = expected_data[
        "mobile_dataswitch"
    ]

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        data = await api.get_data()

    assert data["device_information"]["DeviceName"] == "B535s-232"
    assert data["device_signal"]["rsrp"] == "-95dBm"
    assert data["monitoring_status"]["SignalIcon"] == "4"


@pytest.mark.asyncio
async def test_get_data_partial_failure():
    """Test that a single endpoint failure does not prevent other data from fetching."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    # device_information raises; everything else succeeds
    mock_client.device.information.side_effect = Exception("Device info unavailable")
    mock_client.device.signal.return_value = {"rsrp": "-95dBm"}
    mock_client.monitoring.status.return_value = {}
    mock_client.monitoring.traffic_statistics.return_value = {}
    mock_client.monitoring.month_statistics.return_value = {}
    mock_client.net.current_plmn.return_value = {}
    mock_client.sms.sms_count.return_value = {}
    mock_client.dial_up.mobile_dataswitch.return_value = {}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        data = await api.get_data()

    assert "device_information" not in data
    assert data.get("device_signal") == {"rsrp": "-95dBm"}


@pytest.mark.asyncio
async def test_get_data_ensures_client():
    """Test that get_data triggers login when no client exists."""
    api = _make_api()
    assert api._client is None

    with patch.object(api, "login", new=AsyncMock()) as mock_login:
        mock_login.side_effect = HuaweiConnectionError("No connection")
        with pytest.raises(HuaweiConnectionError):
            await api.get_data()
        mock_login.assert_called_once()


@pytest.mark.asyncio
async def test_get_data_connection_error_resets_client():
    """Test that a hard failure during get_data resets the client."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with (
        patch(
            "asyncio.to_thread",
            new=AsyncMock(side_effect=Exception("Network error")),
        ),
        pytest.raises(HuaweiConnectionError),
    ):
        await api.get_data()

    assert api._client is None
    assert api._connection is None


# ---------------------------------------------------------------------------
# reboot()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reboot_success():
    """Test successful reboot call."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
        await api.reboot()


@pytest.mark.asyncio
async def test_reboot_error_resets_client():
    """Test that a reboot failure clears the client."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=Exception("Reboot fail"))),
        pytest.raises(Exception, match="Reboot fail"),
    ):
        await api.reboot()

    assert api._client is None
    assert api._connection is None


# ---------------------------------------------------------------------------
# clear_traffic_statistics()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_traffic_success():
    """Test successful traffic stats clear."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
        await api.clear_traffic_statistics()


@pytest.mark.asyncio
async def test_clear_traffic_error():
    """Test that clear traffic failure propagates."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with (
        patch(
            "asyncio.to_thread",
            new=AsyncMock(side_effect=Exception("Clear fail")),
        ),
        pytest.raises(Exception, match="Clear fail"),
    ):
        await api.clear_traffic_statistics()


# ---------------------------------------------------------------------------
# set_mobile_data()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_mobile_data_on():
    """Test enabling mobile data."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
        await api.set_mobile_data(True)


@pytest.mark.asyncio
async def test_set_mobile_data_off():
    """Test disabling mobile data."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
        await api.set_mobile_data(False)


@pytest.mark.asyncio
async def test_set_mobile_data_error():
    """Test that a mobile data set failure propagates."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=Exception("Set fail"))),
        pytest.raises(Exception, match="Set fail"),
    ):
        await api.set_mobile_data(True)
