"""Extended coverage tests — edge cases and branches not covered by other suites."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.huawei_router_5g.api import (
    HuaweiConnectionError,
    HuaweiRouter5GAPI,
)
from custom_components.huawei_router_5g.binary_sensor import (
    BEST_CONN_DESCRIPTION,
    HuaweiBestConnectionSensor,
)
from custom_components.huawei_router_5g.button import (
    REBOOT_DESCRIPTION,
    HuaweiRebootButton,
)
from custom_components.huawei_router_5g.const import DOMAIN
from custom_components.huawei_router_5g.helpers import (
    get_network_type_label,
    get_router_model,
    parse_signal_value,
)
from custom_components.huawei_router_5g.number import (
    POLLING_INTERVAL_DESCRIPTION,
    HuaweiPollingInterval,
)
from custom_components.huawei_router_5g.sensor import SENSOR_TYPES, HuaweiRouterSensor
from custom_components.huawei_router_5g.switch import (
    MOBILE_DATA_DESCRIPTION,
    HuaweiMobileDataSwitch,
)

# ---------------------------------------------------------------------------
# helpers — parse_signal_value edge cases
# ---------------------------------------------------------------------------


def test_parse_signal_value_various_units():
    """Ensure parse_signal_value correctly strips all known units."""
    assert parse_signal_value("100MHz") == 100.0
    assert parse_signal_value("20dB") == 20.0
    assert parse_signal_value("-80dBm") == -80.0


def test_parse_signal_value_whitespace():
    """Values with leading/trailing whitespace are handled."""
    assert parse_signal_value("  -95dBm  ") == -95.0


def test_parse_signal_value_zero():
    """Zero is a valid signal value."""
    assert parse_signal_value("0") == 0.0
    assert parse_signal_value(0) == 0.0


# ---------------------------------------------------------------------------
# helpers — get_router_model edge cases
# ---------------------------------------------------------------------------


def test_get_router_model_whitespace_only():
    """Whitespace-only DeviceName falls back to default."""
    assert get_router_model({"DeviceName": "   "}) == "Huawei Router"


# ---------------------------------------------------------------------------
# helpers — get_network_type_label edge cases
# ---------------------------------------------------------------------------


def test_get_network_type_label_all_known_5g_codes():
    """All 5G-related codes map to a non-None label."""
    for code in ("51", "52", "71"):
        label = get_network_type_label(code)
        assert label is not None
        assert "5G" in label or "NR" in label


def test_get_network_type_label_empty_string():
    """Empty string code returns an unknown label."""
    label = get_network_type_label("")
    assert label is not None  # returns "Unknown ()"


# ---------------------------------------------------------------------------
# sensor — guard band min/max for RSRQ and SINR
# ---------------------------------------------------------------------------


def test_sensor_rsrq_guard_band_min(mock_coordinator, mock_config_entry):
    """RSRQ values below -50 are filtered out."""
    mock_coordinator.data = {"device_signal": {"rsrq": "-60dB"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "rsrq")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value is None


def test_sensor_rsrq_guard_band_max(mock_coordinator, mock_config_entry):
    """RSRQ values above 0 are filtered out."""
    mock_coordinator.data = {"device_signal": {"rsrq": "5dB"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "rsrq")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value is None


def test_sensor_sinr_guard_band_min(mock_coordinator, mock_config_entry):
    """SINR values below -30 are filtered out."""
    mock_coordinator.data = {"device_signal": {"sinr": "-40dB"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "sinr")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value is None


# ---------------------------------------------------------------------------
# sensor — month total
# ---------------------------------------------------------------------------


def test_sensor_month_total(mock_coordinator, mock_config_entry):
    """Test month_total sums download and upload."""
    mock_coordinator.data = {
        "month_statistics": {
            "CurrentMonthDownload": "1073741824",
            "CurrentMonthUpload": "536870912",
        }
    }
    desc = next(d for d in SENSOR_TYPES if d.key == "month_total")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 1073741824 + 536870912


def test_sensor_month_upload_gb(mock_coordinator, mock_config_entry):
    """Test month_upload_gb converts bytes to GB."""
    mock_coordinator.data = {"month_statistics": {"CurrentMonthUpload": "1073741824"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "month_upload_gb")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == 1.0


# ---------------------------------------------------------------------------
# sensor — PLMN and operator fallback
# ---------------------------------------------------------------------------


def test_sensor_plmn(mock_coordinator, mock_config_entry):
    """Test PLMN numeric code is returned."""
    mock_coordinator.data = {"current_plmn": {"Numeric": "27205"}}
    desc = next(d for d in SENSOR_TYPES if d.key == "plmn")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value == "27205"


def test_sensor_operator_missing(mock_coordinator, mock_config_entry):
    """Return None when current_plmn has no FullName."""
    mock_coordinator.data = {"current_plmn": {}}
    desc = next(d for d in SENSOR_TYPES if d.key == "operator")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    assert sensor.native_value is None


# ---------------------------------------------------------------------------
# sensor — device info fallback when coordinator.mac is None
# ---------------------------------------------------------------------------


def test_sensor_device_info_fallback_host_signal_group(
    mock_coordinator, mock_config_entry
):
    """Signal group device_info uses host prefix when MAC is None."""
    mock_coordinator.mac = None
    desc = next(d for d in SENSOR_TYPES if d.key == "sinr")
    sensor = HuaweiRouterSensor(mock_coordinator, mock_config_entry, desc)
    info = sensor.device_info
    assert "host_http://192.168.8.1" in str(info["identifiers"])
    assert "via_device" in info


# ---------------------------------------------------------------------------
# binary_sensor — best connection icon when 5G active
# ---------------------------------------------------------------------------


def test_best_connection_icon_off(mock_coordinator, mock_config_entry):
    """Icon is cellular-1 when 5G is not active."""
    mock_coordinator.data = {"device_signal": {"band": "20MHz(B1)"}}
    sensor = HuaweiBestConnectionSensor(
        mock_coordinator, mock_config_entry, BEST_CONN_DESCRIPTION
    )
    assert sensor.icon == "mdi:signal-cellular-1"


def test_best_connection_icon_on(mock_coordinator, mock_config_entry):
    """Icon is 5g when all health gates pass."""
    mock_coordinator.data = {
        "device_signal": {
            "band": "20MHz(B1) + 10MHz(N78)",
            "rsrp": "-90dBm",
            "nrrsrp": "-95dBm",
        }
    }
    sensor = HuaweiBestConnectionSensor(
        mock_coordinator, mock_config_entry, BEST_CONN_DESCRIPTION
    )
    assert sensor.icon == "mdi:signal-5g"


# ---------------------------------------------------------------------------
# switch — mobile data device info
# ---------------------------------------------------------------------------


def test_mobile_data_switch_device_info(mock_coordinator, mock_config_entry):
    """Mobile data switch device_info is in the system group."""
    switch = HuaweiMobileDataSwitch(
        mock_coordinator, mock_config_entry, MOBILE_DATA_DESCRIPTION
    )
    mac = "DC:71:96:11:22:33"
    info = switch.device_info
    assert info["identifiers"] == {(DOMAIN, f"{mac}_system")}
    assert "via_device" not in info


# ---------------------------------------------------------------------------
# button — unique_id uses entry.unique_id
# ---------------------------------------------------------------------------


def test_reboot_button_unique_id(mock_coordinator, mock_config_entry):
    """Unique ID is composed from entry unique_id and description key."""
    button = HuaweiRebootButton(mock_coordinator, mock_config_entry, REBOOT_DESCRIPTION)
    assert button.unique_id == f"{mock_config_entry.unique_id}_reboot"


# ---------------------------------------------------------------------------
# number — device info uses MAC
# ---------------------------------------------------------------------------


def test_polling_interval_device_info_fallback(mock_coordinator, mock_config_entry):
    """Number device_info falls back to host prefix when MAC is None."""
    from unittest.mock import MagicMock

    my_entry = MagicMock()
    my_entry.options = {"host": "http://192.168.8.1"}
    my_entry.title = "My Huawei Router"
    my_entry.unique_id = "huawei_unique_123"
    mock_coordinator.mac = None
    mock_coordinator.entry = my_entry
    entity = HuaweiPollingInterval(
        mock_coordinator, my_entry, POLLING_INTERVAL_DESCRIPTION, 180
    )
    info = entity.device_info
    assert "host_http://192.168.8.1" in str(info["identifiers"])


# ---------------------------------------------------------------------------
# api — _create_connection_sync is the sync entry point
# ---------------------------------------------------------------------------


def test_api_initial_state():
    """Verify the API starts with no client or connection."""
    api = HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password")
    assert api._client is None
    assert api._connection is None


@pytest.mark.asyncio
async def test_api_get_data_no_client_triggers_login():
    """get_data with no client calls login before fetching."""
    api = HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password")
    assert api._client is None

    with patch.object(api, "_ensure_client", new=AsyncMock()) as mock_ensure:
        mock_ensure.side_effect = HuaweiConnectionError("offline")
        with pytest.raises(HuaweiConnectionError):
            await api.get_data()
        mock_ensure.assert_called_once()


@pytest.mark.asyncio
async def test_api_logout_is_noop_when_not_connected():
    """logout() should not raise when there is no active connection."""
    api = HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password")
    await api.logout()  # no exception


# ---------------------------------------------------------------------------
# coordinator — metadata update path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_updates_metadata_when_changed(mock_config_entry):
    """Test that coordinator writes new metadata to ConfigEntry when it changes."""
    from custom_components.huawei_router_5g.coordinator import (
        HuaweiRouter5GDataUpdateCoordinator,
    )

    hass = MagicMock()
    hass.config_entries = MagicMock()

    mock_api = MagicMock()
    mock_api.get_data = AsyncMock(
        return_value={
            "device_information": {
                "DeviceName": "NewModel",
                "SoftwareVersion": "2.0",
                "HardwareVersion": "Ver.B",
            }
        }
    )

    with patch("homeassistant.helpers.frame.report_usage"):
        coordinator = HuaweiRouter5GDataUpdateCoordinator(
            hass, mock_config_entry, mock_api
        )
    coordinator.data = None  # first run

    class _FakeTimeout:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

    with patch("asyncio.timeout", return_value=_FakeTimeout()):
        await coordinator._async_update_data()

    assert coordinator.model == "NewModel"
    assert coordinator.sw_version == "2.0"
    assert coordinator.hw_version == "Ver.B"
    hass.config_entries.async_update_entry.assert_called_once()
