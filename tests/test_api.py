"""Tests for the Huawei Router 5G API client."""

from datetime import UTC, datetime, timedelta
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
    _normalize_router_url,
)
from custom_components.huawei_router_5g.const import REQUEST_TIMEOUT

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api() -> HuaweiRouter5GAPI:
    return HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password")


# ---------------------------------------------------------------------------
# _normalize_router_url()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        # Bare IP — scheme must be added
        ("192.168.8.1", "http://192.168.8.1"),
        # Already well-formed — unchanged
        ("http://192.168.8.1", "http://192.168.8.1"),
        # Trailing slash — stripped
        ("http://192.168.8.1/", "http://192.168.8.1"),
        # Uppercase scheme — lowercased
        ("HTTP://192.168.8.1", "http://192.168.8.1"),
        # Non-default port — preserved
        ("192.168.8.1:8080", "http://192.168.8.1:8080"),
        # Port already in URL — preserved
        ("http://192.168.8.1:8080/", "http://192.168.8.1:8080"),
        # Leading/trailing whitespace — stripped
        ("  http://192.168.8.1  ", "http://192.168.8.1"),
    ],
)
def test_normalize_router_url(host: str, expected: str) -> None:
    """_normalize_router_url produces a clean http(s) URL in all common forms."""
    assert _normalize_router_url(host) == expected


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
            timeout=REQUEST_TIMEOUT,
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

    mock_client = MagicMock()

    async def _mock_login():
        api._client = mock_client

    with patch.object(api, "_login_internal", new=AsyncMock(side_effect=_mock_login)):
        result = await api._ensure_client()
        assert result is mock_client


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
    """logout() with no connection must do nothing observable.

    "It does not raise" was the whole of this test, which passes if logout
    silently tears down state it should have left alone. Assert the no-op:
    the client and connection stay as they were, and nothing was dispatched
    to a thread.
    """
    api = _make_api()
    api._client = None

    with patch("asyncio.to_thread", new=AsyncMock()) as to_thread:
        await api.logout()

    to_thread.assert_not_called()
    assert api._connection is None
    assert api._client is None


@pytest.mark.asyncio
async def test_logout_calls_the_real_library_method():
    """Logout must call `client.user.logout()`.

    Asserting the **method that exists** is the whole point. The previous form
    called `connection.logout`, which `Connection` has never had, so the
    integration logged out of nothing on every unload and reload while the
    test passed against an auto-created `MagicMock` attribute.
    """
    api = _make_api()
    client = MagicMock()
    api._client = client
    api._connection = MagicMock()

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        await api.logout()

    client.user.logout.assert_called_once()
    assert api._connection is None
    assert api._client is None


@pytest.mark.asyncio
async def test_logout_exception():
    """A failed logout is swallowed, and the connection is discarded anyway.

    Teardown is best-effort: there is nothing useful to do with the error and
    the session is being abandoned regardless. What stops that swallow hiding
    a wrong method name again is the library contract test, not this one.
    """
    api = _make_api()
    client = MagicMock()
    api._client = client
    api._connection = MagicMock()

    client.user.logout.side_effect = Exception("Logout failed")

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
        "wlan_wifi_feature_switch": {"stafrequenceenable": "1"},
        "wlan_multi_basic_settings": {"DbhoEnable": "0"},
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
    mock_client.wlan.wifi_feature_switch.return_value = expected_data[
        "wlan_wifi_feature_switch"
    ]
    mock_client.wlan.multi_basic_settings.return_value = expected_data[
        "wlan_multi_basic_settings"
    ]

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        data = await api.get_data()

    assert data["device_information"]["DeviceName"] == "B535s-232"
    assert data["device_signal"]["rsrp"] == "-95dBm"
    assert data["monitoring_status"]["SignalIcon"] == "4"
    assert data["wlan_wifi_feature_switch"] == {"stafrequenceenable": "1"}
    assert data["wlan_multi_basic_settings"] == {"DbhoEnable": "0"}


@pytest.mark.asyncio
async def test_get_data_wlan_endpoints_success():
    """Test that wlan_wifi_feature_switch and wlan_multi_basic_settings are included."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    # Mock all endpoints
    mock_client.device.information.return_value = {}
    mock_client.device.signal.return_value = {}
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
    mock_client.wlan.wifi_feature_switch.return_value = {"dbdc_enable": "1"}
    mock_client.wlan.multi_basic_settings.return_value = {"Ssids": {"Ssid": []}}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        data = await api.get_data()

    assert "wlan_wifi_feature_switch" in data
    assert data["wlan_wifi_feature_switch"] == {"dbdc_enable": "1"}
    assert "wlan_multi_basic_settings" in data
    assert data["wlan_multi_basic_settings"] == {"Ssids": {"Ssid": []}}


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
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    with patch(
        "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
    ):
        await api.reboot()

    # `set_control(REBOOT)`, not `reboot()`. Both exist in library 1.11.0;
    # 2.0.0 removes `reboot()`, so asserting the surviving spelling is what
    # makes this test outlive the bump.
    from huawei_lte_api.enums.device import ControlModeEnum

    mock_client.device.set_control.assert_called_once_with(ControlModeEnum.REBOOT)
    mock_client.device.reboot.assert_not_called()


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

    # `set_clear_traffic` — asserting the method that actually exists. The
    # previous assertion named `clear_traffic`, which does not exist in the
    # library, and passed because `MagicMock` creates any attribute on demand.
    api._client.monitoring.set_clear_traffic.assert_called_once()


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
        lteband=LTEBandEnum.ALL.value,
        networkband=NetworkBandEnum.ALL.value,
        networkmode=mode,
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

    # Deliberately `_session.post_set`, NOT `wlan.set_multi_basic_settings()`.
    #
    # The public setter exists, but it posts only
    # `{'Ssids': {'Ssid': clients}, 'WifiRestart': 1}` and discards every other
    # top-level key. Probed against a live B535 on 2026-08-14, the GET returns
    # `Ssids`, `DbhoEnable` and `modify_guest_ssid` — so swapping would
    # silently drop band-steering and guest-SSID state on every toggle.
    #
    # **If you are here because this assertion failed after switching to the
    # public setter: the switch is the bug, not this test.** Full reasoning is
    # at the call site in api.py and in docs/DEVELOPMENT.md.
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
# _create_connection_sync() — url is None (line 76)
# ---------------------------------------------------------------------------


def test_create_connection_sync_url_none():
    """Test that _create_connection_sync raises when url is None."""
    api = _make_api()
    api.url = None

    with pytest.raises(ValueError, match="Router URL is not initialized"):
        api._create_connection_sync()


# ---------------------------------------------------------------------------
# _ensure_client() — login fails to set client (line 137)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_client_login_leaves_client_none():
    """Test _ensure_client raises when _login_internal leaves client None."""
    api = _make_api()
    api._client = None

    with (
        patch.object(api, "_login_internal", new=AsyncMock()),
        pytest.raises(
            HuaweiConnectionError, match="Failed to establish API client connection"
        ),
    ):
        await api._ensure_client()


# ---------------------------------------------------------------------------
# get_data() — client is None inside _fetch (line 193)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_data_client_none_in_fetch():
    """Test get_data raises when client is None inside _fetch."""
    api = _make_api()
    api._client = None

    with (
        patch.object(api, "_ensure_client", new=AsyncMock()),
        pytest.raises(HuaweiConnectionError, match="API client not established"),
    ):
        await api.get_data()


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


@pytest.mark.asyncio
async def test_login_internal_success():
    """Test _login_internal creates client."""
    api = _make_api()
    mock_conn = MagicMock()
    mock_client = MagicMock()

    with patch.object(
        api, "_create_connection_sync", return_value=(mock_conn, mock_client)
    ):
        await api._login_internal()

    assert api._connection is mock_conn
    assert api._client is mock_client


@pytest.mark.asyncio
async def test_login_internal_auth_error():
    """Test _login_internal raises HuaweiAuthError on login failure."""
    api = _make_api()

    with (
        patch.object(
            api,
            "_create_connection_sync",
            side_effect=LoginErrorPasswordWrongException("Wrong password", "108003"),
        ),
        pytest.raises(HuaweiAuthError),
    ):
        await api._login_internal()

    assert api._client is None
    assert api._connection is None


@pytest.mark.asyncio
async def test_login_internal_connection_error():
    """Test _login_internal raises HuaweiConnectionError on network error."""
    api = _make_api()

    with (
        patch.object(
            api,
            "_create_connection_sync",
            side_effect=Exception("Network error"),
        ),
        pytest.raises(HuaweiConnectionError),
    ):
        await api._login_internal()

    assert api._client is None
    assert api._connection is None


@pytest.mark.asyncio
async def test_get_data_wlan_endpoints_exception():
    """Test exceptions in wlan_wifi_feature_switch and wlan_multi_basic_settings.

    This test checks that exceptions are correctly caught.
    """
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    # device_information succeeds
    mock_client.device.information.return_value = {"DeviceName": "Test"}
    # wlan_wifi_feature_switch raises exception
    mock_client.wlan.wifi_feature_switch.side_effect = Exception("Feature switch error")
    # wlan_multi_basic_settings raises exception
    mock_client.wlan.multi_basic_settings.side_effect = Exception(
        "Multi settings error"
    )
    # Other endpoints succeed
    mock_client.device.signal.return_value = {}
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

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        data = await api.get_data()

    # Ensure data contains device_information but not the wlan endpoints
    assert "device_information" in data
    assert "wlan_wifi_feature_switch" not in data
    assert "wlan_multi_basic_settings" not in data


@pytest.mark.asyncio
async def test_set_guest_wifi_attribute_error():
    """Test set_guest_wifi raises RuntimeError when post_set raises AttributeError."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    api._client.wlan.multi_basic_settings.return_value = {
        "Ssids": {
            "Ssid": [{"Index": "2", "WifiEnable": "0", "wifiisguestnetwork": "1"}]
        }
    }
    api._client.wlan._session.post_set.side_effect = AttributeError("API changed")

    with (
        patch(
            "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
        ),
        pytest.raises(RuntimeError, match="huawei_lte_api internal API changed"),
    ):
        await api.set_guest_wifi(True)


@pytest.mark.asyncio
async def test_get_data_sms_count_safe_int_zero():
    """Test get_data uses _safe_int for SMS count selection when LocalInbox is 0."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    # SMS count with LocalInbox = 0, SimInbox = 3
    mock_client.sms.sms_count.return_value = {"LocalInbox": "0", "SimInbox": "3"}
    mock_client.sms.get_sms_list.return_value = {"Messages": []}
    # Other endpoints
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
    mock_client.wlan.multi_basic_settings.return_value = {}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        await api.get_data()

    # Verify get_sms_list called with SIM_INBOX
    mock_client.sms.get_sms_list.assert_called_once_with(
        page=1,
        box_type=BoxTypeEnum.SIM_INBOX,
        read_count=20,
        sort_type=SortTypeEnum.DATE,
        ascending=False,
        unread_preferred=True,
    )


@pytest.mark.asyncio
async def test_get_data_sms_count_safe_int_none():
    """Test get_data uses _safe_int when SMS count values are None."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    # SMS count with missing keys
    mock_client.sms.sms_count.return_value = {}
    mock_client.sms.get_sms_list.return_value = {"Messages": []}
    # Other endpoints
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
    mock_client.wlan.multi_basic_settings.return_value = {}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
        await api.get_data()

    # Since LocalInbox is None (or missing), _safe_int returns None -> treated as 0,
    # and SimInbox is None -> also 0, so box_type should be LOCAL_INBOX (default)
    mock_client.sms.get_sms_list.assert_called_once_with(
        page=1,
        box_type=BoxTypeEnum.LOCAL_INBOX,
        read_count=20,
        sort_type=SortTypeEnum.DATE,
        ascending=False,
        unread_preferred=True,
    )


# ---------------------------------------------------------------------------
# _ensure_client() — session expiry path (lines 114-115)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_client_resets_on_inactivity():
    """Test _ensure_client resets client when last_activity >100s ago."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()
    api._last_activity = datetime.now(UTC) - timedelta(seconds=200)

    new_client = MagicMock()

    async def _mock_login():
        api._client = new_client

    with patch.object(api, "_login_internal", new=AsyncMock(side_effect=_mock_login)):
        result = await api._ensure_client()

    assert result is new_client


# ---------------------------------------------------------------------------
# _execute_with_retry() — retry and re-raise paths (lines 150-163)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_with_retry_retries_on_login_required():
    """Test _execute_with_retry retries after ResponseErrorLoginRequiredException."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    call_count = 0

    def mock_fn(client):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ResponseErrorLoginRequiredException("Login required", "100001")
        return "retried_ok"

    with (
        patch.object(api, "_ensure_client", return_value=mock_client),
        patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())),
    ):
        result = await api._execute_with_retry(mock_fn)

    assert result == "retried_ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_execute_with_retry_retries_on_expiry_error_code():
    """Test _execute_with_retry retries on ResponseErrorException with expiry code."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    call_count = 0

    def mock_fn(client):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ResponseErrorException("Session expired", "125002")
        return "retried_ok"

    with (
        patch.object(api, "_ensure_client", return_value=mock_client),
        patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())),
    ):
        result = await api._execute_with_retry(mock_fn)

    assert result == "retried_ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_execute_with_retry_raises_non_expiry_error():
    """Test _execute_with_retry re-raises non-expiry ResponseErrorException."""
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    def mock_fn(client):
        raise ResponseErrorException("Other error", "1")

    with (
        patch.object(api, "_ensure_client", return_value=mock_client),
        patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())),
        pytest.raises(ResponseErrorException, match="Other error"),
    ):
        await api._execute_with_retry(mock_fn)


# ---------------------------------------------------------------------------
# Reconnect (§T-4e)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnect_uses_net_reconnect_not_dial():
    """`net.reconnect()`, not `dial_up.dial()`.

    They are not alternatives. `dial()` posts `Action: 1` hardcoded, which is
    connect-only: it has no disconnect, is a no-op on a live session, and its
    one real use is already covered by the Mobile Data switch. Only
    `net.reconnect()` drops and re-establishes, which is what the router GUI's
    Reconnect does.
    """
    api = _make_api()
    mock_client = MagicMock()
    api._client = mock_client
    api._connection = MagicMock()

    with patch(
        "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
    ):
        await api.reconnect()

    mock_client.net.reconnect.assert_called_once_with()
    mock_client.dial_up.dial.assert_not_called()


@pytest.mark.asyncio
async def test_reconnect_resets_the_client_on_success():
    """The held session is against a connection that has just gone away.

    Reusing it would fail the next read on a stale handle rather than simply
    reconnecting, which is the same reasoning as `reboot`.
    """
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with patch(
        "asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))
    ):
        await api.reconnect()

    assert api._client is None
    assert api._connection is None


@pytest.mark.asyncio
async def test_reconnect_error_resets_client_and_raises():
    """A failed reconnect must not report success — §22, and §O-4."""
    api = _make_api()
    api._client = MagicMock()
    api._connection = MagicMock()

    with (
        patch(
            "asyncio.to_thread",
            new=AsyncMock(side_effect=Exception("Reconnect fail")),
        ),
        pytest.raises(Exception, match="Reconnect fail"),
    ):
        await api.reconnect()

    assert api._client is None
