"""Fixtures and utilities for testing the Huawei Router 5G integration."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.huawei_router_5g.const import DOMAIN


@pytest.fixture
def mock_config_entry():
    """Fixture providing a mock ConfigEntry for a Huawei router."""
    entry = MockConfigEntry(
        unique_id="huawei_unique_123",
        domain=DOMAIN,
        title="My Huawei Router",
        data={
            "model": "B535s-232",
            "sw_version": "11.0.1.1(H192SP1C983)",
            "hw_version": "Ver.A",
            "mac": "DC:71:96:11:22:33",
        },
        options={
            CONF_HOST: "http://192.168.8.1",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
        },
    )

    def mock_create_background_task(hass, coro, name):
        from unittest.mock import Mock

        if hasattr(hass, "async_create_task") and not isinstance(
            hass.async_create_task, (Mock, MagicMock)
        ):
            return hass.async_create_task(coro, name)
        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(coro)
        except RuntimeError:
            coro.close()
            return MagicMock()

    entry.async_create_background_task = MagicMock(
        side_effect=mock_create_background_task
    )
    return entry


@pytest.fixture
def mock_coordinator():
    """Fixture providing a mock DataUpdateCoordinator."""
    coordinator = MagicMock()
    coordinator.data = {}
    coordinator.last_update_success_time = None
    coordinator.async_request_refresh = AsyncMock()
    coordinator.model = "B535s-232"
    coordinator.sw_version = "11.0.1.1(H192SP1C983)"
    coordinator.hw_version = "Ver.A"
    coordinator.mac = "DC:71:96:11:22:33"
    return coordinator


# Sample data that mirrors a real Huawei B535 API response
SAMPLE_ROUTER_DATA = {
    "device_information": {
        "DeviceName": "B535s-232",
        "SoftwareVersion": "11.0.1.1(H192SP1C983)",
        "HardwareVersion": "Ver.A",
        "Imei": "860123456789012",
        "MacAddress1": "DC:71:96:11:22:33",
        "WanIPAddress": "10.1.2.3",
        "LanIPAddress": "192.168.8.1",
    },
    "device_signal": {
        "pci": "123",
        "cell_id": "5A6B3",
        "rsrq": "-12dB",
        "rsrp": "-95dBm",
        "rssi": "-72dBm",
        "sinr": "6dB",
        "lte_ca": "1",
        "lte_bandwidth": "B20",
        "ltedl_earfcn": "9360",
        "sc_band": "n1",
        "sc_earfcn": "423130",
        "sc_cellid": "AB12",
    },
    "monitoring_status": {
        "ConnectionStatus": "901",
        "SignalIcon": "4",
        "CurrentNetworkType": "19",
        "WanIPAddress": "10.1.2.3",
        "SmsStorageFull": "0",
    },
    "traffic_statistics": {
        "CurrentDownloadRate": "102400",
        "CurrentUploadRate": "20480",
        "TotalDownload": "5368709120",
        "TotalUpload": "1073741824",
        "TotalConnectTime": "86400",
    },
    "month_statistics": {
        "CurrentMonthDownload": "2147483648",
        "CurrentMonthUpload": "536870912",
    },
    "current_plmn": {
        "FullName": "Three",
        "ShortName": "3",
        "Numeric": "27205",
    },
    "sms_count": {
        "LocalUnread": "2",
        "LocalRead": "8",
        "LocalSent": "0",
        "LocalDraft": "0",
        "LocalMax": "500",
        "SimUnread": "0",
        "SimRead": "0",
        "SimMax": "20",
        "NewMsg": "0",
    },
    "mobile_dataswitch": {
        "dataswitch": "1",
    },
}
