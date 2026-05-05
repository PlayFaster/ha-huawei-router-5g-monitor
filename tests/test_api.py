"""Tests for the Huawei Router 5G API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from huawei_lte_api.enums.sms import BoxTypeEnum, SortTypeEnum
from huawei_lte_api.exceptions import (
    LoginErrorPasswordWrongException,
    LoginErrorUsernameWrongException,
    ResponseErrorException,
    ResponseErrorLoginRequiredException,
)

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
async def test_login_auth_error_password():
    """Test that a password error raises HuaweiAuthError."""
    api = _make_api()

    with (
        patch.object(
            api,
            "_create_connection_sync",
            side_effect=LoginErrorPasswordWrongException("Wrong password", "108003"),
        ),
        pytest.raises(HuaweiAuthError),
    ):
        await api.login()

    assert api._client is None


@pytest.mark.asyncio
async def test_login_auth_error_username():
    """Test that a username error raises HuaweiAuthError."""
    api = _make_api()

    with (
        patch.object(
            api,
            "_create_connection_sync",
            side_effect=LoginErrorUsernameWrongException("Wrong username", "108001"),
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
# _create_connection_sync()
# ---------------------------------------------------------------------------


def test_create_connection_sync():
    """Test the synchronous connection creation."""
    api = _make_api()

    mock_conn = MagicMock()
    mock_client = MagicMock()

    with (
        patch(
            "custom_components.huawei_router_5g.api.Connection", return_value=mock_conn
        ) as mock_conn_class,
        patch(
            "custom_components.huawei_router_5g.api.Client", return_value=mock_client
        ) as mock_client_class,
    ):
        conn, client = api._create_connection_sync()

        mock_conn_class.assert_called_once_with(
            api.url,
            username=api.username,
            password=api.password,
        )
        mock_client_class.assert_called_once_with(mock_conn)
        assert conn is mock_conn
        assert client is mock_client


# ---------------------------------------------------------------------------
# _reset_client()
# ---------------------------------------------------------------------------


def test_reset_client():
    """Test that _reset_client clears connection and client."""
    api = _make_api()
    api._connection = MagicMock()
    api._client = MagicMock()

    api._reset_client()

    assert api._connection is None
    assert api._client is None


# ---------------------------------------------------------------------------
# _ensure_client()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_client_with_existing_client():
    """Test _ensure_client when client already exists."""
    api = _make_api()
    api._client = MagicMock()

    with patch.object(api, "_login_internal", new=AsyncMock()) as mock_login:
        await api._ensure_client()
        mock_login.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_client_without_client():
    """Test _ensure_client when client doesn't exist."""
    api = _make_api()
    api._client = None

    with patch.object(api, "_login_internal", new=AsyncMock()) as mock_login:
        await api._ensure_client()
        mock_login.assert_called_once()


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


@pytest.mark.asyncio
async def test_logout_exception():
    """Test that logout handles exceptions gracefully."""
    api = _make_api()
    mock_conn = MagicMock()
    api._connection = mock_conn
    api._client = MagicMock()

    mock_conn.logout.side_effect = Exception("Logout failed")

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        await api.logout()

    assert api._connection is None
    assert api._client is None


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
        "sms_count": {"LocalInbox": "5", "SimInbox": "0"},
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
    # Mock other endpoints that are called
    mock_client.monitoring.check_notifications.return_value = {}
    mock_client.net.net_mode.return_value = {}
    mock_client.sms.get_sms_list.return_value = {}
    mock_client.lan.host_info.return_value = {}
    mock_client.wlan.host_list.return_value = {}
    mock_client.wlan.wifi_feature_switch.return_value = {}
    mock_client.wlan.wifi_guest_network_switch.return_value = {}
    mock_client.wlan.multi_basic_settings.return_value = {}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        data = await api.get_data()

    assert data["device_information"]["DeviceName"] == "B535s-232"
    assert data["device_signal"]["rsrp"] == "-95dBm"
    assert data["monitoring_status"]["SignalIcon"] == "4"


@pytest.mark.asyncio
async def test_get_data_sms_list_local_inbox():
    """Test SMS list fetches LocalInbox when LocalInbox > 0."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    # Setup SMS count with LocalInbox > 0
    mock_client.sms.sms_count.return_value = {"LocalInbox": "5", "SimInbox": "0"}
    mock_client.sms.get_sms_list.return_value = {"Messages": []}

    # Mock other endpoints
    mock_client.device.information.return_value = {}
    mock_client.device.signal.return_value = {}
    mock_client.monitoring.status.return_value = {}
    mock_client.monitoring.traffic_statistics.return_value = {}
    mock_client.monitoring.month_statistics.return_value = {}
    mock_client.net.current_plmn.return_value = {}
    mock_client.dial_up.mobile_dataswitch.return_value = {}
    mock_client.monitoring.check_notifications.return_value = {}
    mock_client.net.net_mode.return_value = {}
    mock_client.lan.host_info.return_value = {}
    mock_client.wlan.host_list.return_value = {}
    mock_client.wlan.wifi_feature_switch.return_value = {}
    mock_client.wlan.wifi_guest_network_switch.return_value = {}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        await api.get_data()

    # Check that get_sms_list was called with LOCAL_INBOX and the new parameters
    mock_client.sms.get_sms_list.assert_called_once_with(
        page=1,
        box_type=BoxTypeEnum.LOCAL_INBOX,
        read_count=20,
        sort_type=SortTypeEnum.DATE,
        ascending=False,
        unread_preferred=True,
    )


@pytest.mark.asyncio
async def test_get_data_sms_list_sim_inbox():
    """Test SMS list fetches SimInbox when LocalInbox is 0."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    # Setup SMS count with LocalInbox = 0
    mock_client.sms.sms_count.return_value = {"LocalInbox": "0", "SimInbox": "3"}
    mock_client.sms.get_sms_list.return_value = {"Messages": []}

    # Mock other endpoints
    mock_client.device.information.return_value = {}
    mock_client.device.signal.return_value = {}
    mock_client.monitoring.status.return_value = {}
    mock_client.monitoring.traffic_statistics.return_value = {}
    mock_client.monitoring.month_statistics.return_value = {}
    mock_client.net.current_plmn.return_value = {}
    mock_client.dial_up.mobile_dataswitch.return_value = {}
    mock_client.monitoring.check_notifications.return_value = {}
    mock_client.net.net_mode.return_value = {}
    mock_client.lan.host_info.return_value = {}
    mock_client.wlan.host_list.return_value = {}
    mock_client.wlan.wifi_feature_switch.return_value = {}
    mock_client.wlan.wifi_guest_network_switch.return_value = {}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        await api.get_data()

    # Check that get_sms_list was called with SIM_INBOX and the new parameters
    mock_client.sms.get_sms_list.assert_called_once_with(
        page=1,
        box_type=BoxTypeEnum.SIM_INBOX,
        read_count=20,
        sort_type=SortTypeEnum.DATE,
        ascending=False,
        unread_preferred=True,
    )


@pytest.mark.asyncio
async def test_get_data_response_error_login_required():
    """Test that ResponseErrorLoginRequiredException triggers HuaweiAuthError."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    mock_client.device.information.side_effect = ResponseErrorLoginRequiredException(
        "Login required", "100001"
    )

    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())),
        pytest.raises(HuaweiAuthError),
    ):
        await api.get_data()


@pytest.mark.asyncio
async def test_get_data_response_error_codes():
    """Test that specific ResponseErrorException codes trigger HuaweiAuthError."""
    api = _make_api()
    mock_client = MagicMock()
    api._connection = MagicMock()

    # Note: 100002 is removed as it's used for "Not Supported"
    for error_code in ("125002", "125003"):
        api._client = mock_client
        mock_client.device.information.side_effect = ResponseErrorException(
            f"Error {error_code}", error_code
        )

        with (
            patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())),
            pytest.raises(HuaweiAuthError),
        ):
            await api.get_data()


@pytest.mark.asyncio
async def test_get_data_critical_fetch_failure():
    """Test that device_information failure raises HuaweiConnectionError."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    mock_client.device.information.side_effect = Exception("Critical failure")

    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())),
        pytest.raises(HuaweiConnectionError),
    ):
        await api.get_data()


@pytest.mark.asyncio
async def test_get_data_non_critical_fetch_failure():
    """Test that non-critical endpoint failures are logged but don't stop the fetch."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    # device_information succeeds
    mock_client.device.information.return_value = {"DeviceName": "Test"}
    # device_signal fails
    mock_client.device.signal.side_effect = Exception("Non-critical failure")
    # Other endpoints succeed
    mock_client.monitoring.status.return_value = {}
    mock_client.monitoring.traffic_statistics.return_value = {}
    mock_client.monitoring.month_statistics.return_value = {}
    mock_client.net.current_plmn.return_value = {}
    mock_client.sms.sms_count.return_value = {"LocalInbox": "0", "SimInbox": "0"}
    mock_client.dial_up.mobile_dataswitch.return_value = {}
    mock_client.monitoring.check_notifications.return_value = {}
    mock_client.net.net_mode.return_value = {}
    mock_client.sms.get_sms_list.return_value = {}
    mock_client.lan.host_info.return_value = {}
    mock_client.wlan.host_list.return_value = {}
    mock_client.wlan.wifi_feature_switch.return_value = {}
    mock_client.wlan.wifi_guest_network_switch.return_value = {}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        data = await api.get_data()

    assert "device_signal" not in data
    assert data["device_information"]["DeviceName"] == "Test"


@pytest.mark.asyncio
async def test_get_data_partial_failure():
    """Test that a single endpoint failure does not prevent other data from fetching."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    # device_signal raises; device_information succeeds
    mock_client.device.information.return_value = {"SoftwareVersion": "1.0"}
    mock_client.device.signal.side_effect = Exception("Signal unavailable")
    mock_client.monitoring.status.return_value = {"ConnectionStatus": "901"}
    mock_client.monitoring.traffic_statistics.return_value = {}
    mock_client.monitoring.month_statistics.return_value = {}
    mock_client.net.current_plmn.return_value = {}
    mock_client.sms.sms_count.return_value = {"LocalInbox": "0", "SimInbox": "0"}
    mock_client.dial_up.mobile_dataswitch.return_value = {}
    mock_client.monitoring.check_notifications.return_value = {}
    mock_client.net.net_mode.return_value = {}
    mock_client.sms.get_sms_list.return_value = {}
    mock_client.lan.host_info.return_value = {}
    mock_client.wlan.host_list.return_value = {}
    mock_client.wlan.wifi_feature_switch.return_value = {}
    mock_client.wlan.wifi_guest_network_switch.return_value = {}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        data = await api.get_data()

    assert "device_signal" not in data
    assert data.get("device_information") == {"SoftwareVersion": "1.0"}
    assert data.get("monitoring_status") == {"ConnectionStatus": "901"}


@pytest.mark.asyncio
async def test_get_data_response_error_non_session():
    """Test non-session ResponseErrorException triggers HuaweiConnectionError."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    mock_client.device.information.side_effect = ResponseErrorException(
        "Other error", "1"
    )

    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())),
        pytest.raises(HuaweiConnectionError),
    ):
        await api.get_data()


@pytest.mark.asyncio
async def test_get_data_sms_list_response_error():
    """Test that ResponseErrorException during sms_list is handled."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    mock_client.device.information.return_value = {"DeviceName": "Test"}
    mock_client.sms.sms_count.return_value = {"LocalInbox": "1", "SimInbox": "0"}
    mock_client.sms.get_sms_list.side_effect = ResponseErrorException("SMS error", "1")

    # Mock all other endpoints to avoid errors
    mock_client.device.signal.return_value = {}
    mock_client.monitoring.status.return_value = {}
    mock_client.monitoring.traffic_statistics.return_value = {}
    mock_client.monitoring.month_statistics.return_value = {}
    mock_client.net.current_plmn.return_value = {}
    mock_client.dial_up.mobile_dataswitch.return_value = {}
    mock_client.monitoring.check_notifications.return_value = {}
    mock_client.net.net_mode.return_value = {}
    mock_client.lan.host_info.return_value = {}
    mock_client.wlan.host_list.return_value = {}
    mock_client.wlan.wifi_feature_switch.return_value = {}
    mock_client.wlan.wifi_guest_network_switch.return_value = {}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        data = await api.get_data()

    assert "sms_list" not in data
    assert data["device_information"]["DeviceName"] == "Test"


@pytest.mark.asyncio
async def test_get_data_sms_list_generic_exception():
    """Test that generic Exception during sms_list is handled."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    mock_client.device.information.return_value = {"DeviceName": "Test"}
    mock_client.sms.sms_count.return_value = {"LocalInbox": "1", "SimInbox": "0"}
    mock_client.sms.get_sms_list.side_effect = Exception("Generic SMS error")

    # Mock all other endpoints to avoid errors
    mock_client.device.signal.return_value = {}
    mock_client.monitoring.status.return_value = {}
    mock_client.monitoring.traffic_statistics.return_value = {}
    mock_client.monitoring.month_statistics.return_value = {}
    mock_client.net.current_plmn.return_value = {}
    mock_client.dial_up.mobile_dataswitch.return_value = {}
    mock_client.monitoring.check_notifications.return_value = {}
    mock_client.net.net_mode.return_value = {}
    mock_client.lan.host_info.return_value = {}
    mock_client.wlan.host_list.return_value = {}
    mock_client.wlan.wifi_feature_switch.return_value = {}
    mock_client.wlan.wifi_guest_network_switch.return_value = {}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        data = await api.get_data()

    assert "sms_list" not in data
    assert data["device_information"]["DeviceName"] == "Test"


@pytest.mark.asyncio
async def test_get_data_other_endpoint_response_error():
    """Test that ResponseErrorException during non-critical endpoint is handled."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    mock_client.device.information.return_value = {"DeviceName": "Test"}
    mock_client.device.signal.side_effect = ResponseErrorException("Signal error", "1")

    # Mock all other endpoints
    mock_client.monitoring.status.return_value = {}
    mock_client.monitoring.traffic_statistics.return_value = {}
    mock_client.monitoring.month_statistics.return_value = {}
    mock_client.net.current_plmn.return_value = {}
    mock_client.sms.sms_count.return_value = {"LocalInbox": "0", "SimInbox": "0"}
    mock_client.dial_up.mobile_dataswitch.return_value = {}
    mock_client.monitoring.check_notifications.return_value = {}
    mock_client.net.net_mode.return_value = {}
    mock_client.sms.get_sms_list.return_value = {}
    mock_client.lan.host_info.return_value = {}
    mock_client.wlan.host_list.return_value = {}
    mock_client.wlan.wifi_feature_switch.return_value = {}
    mock_client.wlan.wifi_guest_network_switch.return_value = {}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        data = await api.get_data()

    assert "device_signal" not in data
    assert data["device_information"]["DeviceName"] == "Test"


@pytest.mark.asyncio
async def test_get_data_ensures_client():
    """Test that get_data triggers _ensure_client when called."""
    api = _make_api()

    with patch.object(api, "_ensure_client", new=AsyncMock()) as mock_ensure:
        mock_ensure.side_effect = HuaweiConnectionError("No connection")
        with pytest.raises(HuaweiConnectionError):
            await api.get_data()
        mock_ensure.assert_called_once()


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

    with patch(
        "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
    ):
        await api.reboot()

    api._client.device.reboot.assert_called_once()


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

    with patch(
        "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
    ):
        await api.clear_traffic_statistics()

    api._client.monitoring.clear_traffic.assert_called_once()


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

    with patch(
        "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
    ):
        await api.set_mobile_data(True)

    api._client.dial_up.set_mobile_dataswitch.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_set_mobile_data_off():
    """Test disabling mobile data."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with patch(
        "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
    ):
        await api.set_mobile_data(False)

    api._client.dial_up.set_mobile_dataswitch.assert_called_once_with(0)


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


# ---------------------------------------------------------------------------
# set_net_mode()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_net_mode_success():
    """Test successful net mode setting."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    from huawei_lte_api.enums.net import LTEBandEnum, NetworkBandEnum

    mode = "03"
    with patch(
        "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
    ):
        await api.set_net_mode(mode)

    api._client.net.set_net_mode.assert_called_once_with(
        lte_band=LTEBandEnum.ALL.value,
        network_band=NetworkBandEnum.ALL.value,
        network_mode=mode,
    )


@pytest.mark.asyncio
async def test_set_net_mode_error():
    """Test that net mode set failure propagates."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=Exception("Set fail"))),
        pytest.raises(Exception, match="Set fail"),
    ):
        await api.set_net_mode("auto")


# ---------------------------------------------------------------------------
# set_guest_wifi()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_guest_wifi_on_manual():
    """Test enabling guest WiFi using the manual path with multiple SSIDs."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    # Setup multi_basic_settings to return multiple SSIDs
    api._client.wlan.multi_basic_settings.return_value = {
        "Ssids": {
            "Ssid": [
                {"Index": "0", "WifiEnable": "1", "wifiisguestnetwork": "0"},
                {"Index": "2", "WifiEnable": "0", "wifiisguestnetwork": "1"},
            ]
        }
    }

    with patch(
        "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
    ):
        await api.set_guest_wifi(True)

    # Should call post_set with BOTH SSIDs
    api._client.wlan._session.post_set.assert_called_once()
    path, args = api._client.wlan._session.post_set.call_args[0]
    assert path == "wlan/multi-basic-settings"
    ssids = args["Ssids"]["Ssid"]
    assert len(ssids) == 2
    # Guest one (Index 2) should be ON
    guest = next(s for s in ssids if s["Index"] == "2")
    assert guest["WifiEnable"] == "1"
    assert guest["wifiisguestnetwork"] == "1"
    # Main one (Index 0) should remain unchanged
    main = next(s for s in ssids if s["Index"] == "0")
    assert main["WifiEnable"] == "1"
    assert args["WifiRestart"] == "1"


@pytest.mark.asyncio
async def test_set_guest_wifi_off_manual():
    """Test disabling guest WiFi using the manual path with multiple SSIDs."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    # Setup multi_basic_settings to return multiple SSIDs
    api._client.wlan.multi_basic_settings.return_value = {
        "Ssids": {
            "Ssid": [
                {"Index": "0", "WifiEnable": "1", "wifiisguestnetwork": "0"},
                {"Index": "2", "WifiEnable": "1", "wifiisguestnetwork": "1"},
            ]
        }
    }

    with patch(
        "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
    ):
        await api.set_guest_wifi(False)

    api._client.wlan._session.post_set.assert_called_once()
    path, args = api._client.wlan._session.post_set.call_args[0]
    assert path == "wlan/multi-basic-settings"
    ssids = args["Ssids"]["Ssid"]
    assert len(ssids) == 2
    # Guest one (Index 2) should be OFF
    guest = next(s for s in ssids if s["Index"] == "2")
    assert guest["WifiEnable"] == "0"
    assert args["WifiRestart"] == "1"


@pytest.mark.asyncio
async def test_set_guest_wifi_error():
    """Test that guest WiFi set failure propagates."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    api._client.wlan.multi_basic_settings.side_effect = Exception("Fetch fail")

    with (
        patch(
            "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
        ),
        pytest.raises(Exception, match="Fetch fail"),
    ):
        await api.set_guest_wifi(True)


# ---------------------------------------------------------------------------
# send_sms()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_sms_success():
    """Test successful SMS sending."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    phone_numbers = ["+1234567890"]
    message = "Test message"

    with patch(
        "asyncio.to_thread",
        new=AsyncMock(side_effect=lambda fn, **kwargs: fn(**kwargs)),
    ):
        await api.send_sms(phone_numbers, message)

    api._client.sms.send_sms.assert_called_once_with(
        phone_numbers=phone_numbers, message=message
    )


@pytest.mark.asyncio
async def test_send_sms_error():
    """Test that SMS send failure propagates."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    phone_numbers = ["+1234567890"]
    message = "Test message"

    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=Exception("Send fail"))),
        pytest.raises(Exception, match="Send fail"),
    ):
        await api.send_sms(phone_numbers, message)


# ---------------------------------------------------------------------------
# delete_sms()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_sms_success():
    """Test successful SMS deletion."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    index = 1

    with patch(
        "asyncio.to_thread",
        new=AsyncMock(side_effect=lambda fn, **kwargs: fn(**kwargs)),
    ):
        await api.delete_sms(index)

    api._client.sms.delete_sms.assert_called_once_with(sms_id=index)


@pytest.mark.asyncio
async def test_delete_sms_error():
    """Test that SMS delete failure propagates."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    index = 1

    with (
        patch("asyncio.to_thread", new=AsyncMock(side_effect=Exception("Delete fail"))),
        pytest.raises(Exception, match="Delete fail"),
    ):
        await api.delete_sms(index)


# ---------------------------------------------------------------------------
# Extra Coverage Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_guest_wifi_dict_ssids():
    """Test set_guest_wifi when Ssids is a dict instead of a list."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    api._client.wlan.multi_basic_settings.return_value = {
        "Ssids": {"Ssid": {"Index": "2", "WifiEnable": "0", "wifiisguestnetwork": "1"}}
    }

    with patch(
        "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
    ):
        await api.set_guest_wifi(True)

    api._client.wlan._session.post_set.assert_called_once()


@pytest.mark.asyncio
async def test_set_guest_wifi_not_found():
    """Test set_guest_wifi raises RuntimeError when no guest SSID is found."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    api._client.wlan.multi_basic_settings.return_value = {
        "Ssids": {
            "Ssid": [{"Index": "0", "WifiEnable": "1", "wifiisguestnetwork": "0"}]
        }
    }

    with (
        patch(
            "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
        ),
        pytest.raises(RuntimeError, match="No guest SSID found in router response"),
    ):
        await api.set_guest_wifi(True)


@pytest.mark.asyncio
async def test_get_sms_list_success():
    """Test successful get_sms_list."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    api._client.sms.get_sms_list.return_value = {"Messages": []}

    with patch(
        "asyncio.to_thread",
        new=AsyncMock(side_effect=lambda fn, **kwargs: fn(**kwargs)),
    ):
        result = await api.get_sms_list(page=1)

    assert result == {"Messages": []}
    api._client.sms.get_sms_list.assert_called_once()


@pytest.mark.asyncio
async def test_get_sms_list_error():
    """Test get_sms_list error propagates."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with (
        patch(
            "asyncio.to_thread", new=AsyncMock(side_effect=Exception("Get SMS fail"))
        ),
        pytest.raises(Exception, match="Get SMS fail"),
    ):
        await api.get_sms_list(page=1)
