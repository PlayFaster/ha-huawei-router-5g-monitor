"""Fixtures and utilities for testing the Huawei Router 5G integration."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.huawei_router_5g.const import DOMAIN

# Patch pytest-socket for Windows ProactorEventLoop compatibility
try:
    import pytest_socket

    # Monkeypatch to avoid SocketBlockedError from internal asyncio pipes on Windows
    _orig_disable = pytest_socket.disable_socket
    pytest_socket.disable_socket = lambda *args, **kwargs: None
except ImportError:
    pass

if sys.platform == "win32":
    # Use SelectorEventLoop on Windows tests to avoid ProactorEventLoop pipe issues
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


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
def mock_coordinator(mock_config_entry):
    """Fixture providing a mock DataUpdateCoordinator."""
    coordinator = MagicMock()
    coordinator.entry = mock_config_entry
    coordinator.api = MagicMock()
    coordinator.api.url = "http://192.168.8.1"
    coordinator.data = {}
    coordinator.last_update_success_time = None
    coordinator.async_request_refresh = AsyncMock()
    # Every explicit user action routes through `async_force_refresh` so it is
    # not swallowed while polling is paused (dev_standards Section 13). Both
    # are stubbed: a test asserting the wrong one would otherwise pass against
    # an auto-created MagicMock attribute and prove nothing.
    coordinator.async_force_refresh = AsyncMock()
    coordinator.model = "B535s-232"
    coordinator.sw_version = "11.0.1.1(H192SP1C983)"
    coordinator.hw_version = "Ver.A"
    coordinator.mac = "DC:71:96:11:22:33"
    return coordinator


# ---------------------------------------------------------------------------
# Device-registry link assertions — never assert a key name directly
# ---------------------------------------------------------------------------
#
# HA 2026.8 replaces the `via_device` identifier tuple with a resolved
# `via_device_id`; the tuple is removed in 2027.8. A test asserting
# `info["via_device"] == (DOMAIN, …)` is green only because the installed HA
# happens to take that branch, and goes red on an HA upgrade that changed
# nothing about this integration. These two helpers branch on the same probe
# `_compat` uses, and assert the link's **presence and exclusivity** rather
# than which key carries it.


def assert_links_to_parent(info, parent_identifier: str) -> None:
    """Assert `info` links to the named parent, whichever shape HA uses.

    `parent_identifier` is the bare identifier string, e.g. `"aabbcc_system"` —
    not the `(DOMAIN, …)` tuple, which is exactly the shape that is going away.
    """
    from custom_components.huawei_router_5g import _compat
    from custom_components.huawei_router_5g.const import DOMAIN

    if _compat._HAS_BY_IDENTIFIER:
        assert "via_device" not in info, (
            "the deprecated via_device tuple must not be emitted on HA 2026.8+"
        )
        # An unresolved parent yields no link at all, which is a real failure
        # here: the System device is registered before platforms are forwarded.
        assert info.get("via_device_id"), (
            f"no via_device_id linking to {parent_identifier!r} — the parent "
            "device was not registered before this DeviceInfo was built"
        )
    else:
        assert "via_device_id" not in info
        assert info.get("via_device") == (DOMAIN, parent_identifier)


def assert_is_root(info) -> None:
    """Assert `info` describes the root device — no parent link of either shape."""
    assert "via_device" not in info, "root device must not carry a via_device tuple"
    assert "via_device_id" not in info, "root device must not carry a via_device_id"


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


def without_about(attrs: dict | None) -> dict:
    """Return an entity's attributes with the `about` note removed.

    Every entity in this component publishes a static `about` note
    (`dev_standards` Section 14), so a test asserting an exact attribute dict
    would otherwise have to restate the prose and would break on every wording
    change. Tests that care about the note assert it directly; tests that care
    about the *data* attributes use this.
    """
    return {k: v for k, v in (attrs or {}).items() if k != "about"}


@pytest.fixture(name="router_transport")
def router_transport_fixture():
    """Serve a working router over the `requests` transport.

    The fake and the faults it can be armed with are in
    [`transport.py`](transport.py). Shared from here so the config flow and
    the coordinator tests drive the same router.
    """
    import requests_mock

    from tests.transport import RouterTransport

    with requests_mock.Mocker() as mocker:
        yield RouterTransport(mocker)
