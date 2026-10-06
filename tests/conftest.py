"""Fixtures and utilities for testing the Huawei Router 5G integration."""

import asyncio
from contextlib import asynccontextmanager
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.huawei_router_5g.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

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


@pytest.fixture(autouse=True)
def _no_unexpected_library_install(monkeypatch):
    """Fail a test that reaches the library installer without expecting to.

    The startup guard calls `async_process_requirements`, which installs a
    package and ignores `hass.config.skip_pip`. The test `hass` sets `skip_pip`,
    and the guard reads it, so the existing suite never reaches the installer.
    This fixture is the second layer: it replaces the installer with a recorder
    and fails the test at teardown if it was called. An exception raised from
    inside the installer would be caught by the guard's own handler and the test
    would pass, which is why the fixture records and asserts instead of raising.
    The guard tests patch their own fake over this one.
    """
    calls = []

    async def _recorder(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(
        "custom_components.huawei_router_5g.library_guard.async_process_requirements",
        _recorder,
    )
    yield calls
    assert not calls, f"the library installer was called unexpectedly: {calls}"


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


# ---------------------------------------------------------------------------
# Live-entity setup, shared by every sweep that needs the real entity list
#
# `_live_entities` and the three things it depends on live here rather than in
# one test module because two files now need them: `test_recorder_runtime.py`
# for the Section 14 and Section 12 runtime sweeps, and `test_entity_hygiene.py`
# for `test_every_live_entity_belongs_to_a_device`. The cross-project item
# names the hygiene file and the test name as elements that must be identical
# across projects; where the fixture *lives* is below that level, and this is
# already where the shared device-registry helpers sit.
#
# All four move together and none works without the others: the autouse
# `_enable_custom_integrations` is what stops `async_setup` answering
# "Integration not found", and `live_entry` carries the schema version HA
# checks before it will load the entry.
# ---------------------------------------------------------------------------

# A payload broad enough that most platforms produce a live entity with real
# attributes. It does not need to be complete: the sweep asserts a floor on how
# many entities it inspected, so a payload that stops producing attributes fails
# loudly rather than passing vacuously.
SWEEP_DATA: dict = {
    "device_information": {
        "DeviceName": "B535-232",
        "SoftwareVersion": "11.0.1.1(H192SP1C983)",
        "HardwareVersion": "Ver.A",
        "Imei": "860000000000000",
        "MacAddress1": "DC:71:96:11:22:33",
        "Uptime": "123456",
    },
    "device_signal": {
        "rsrp": "-95dBm",
        "rsrq": "-12dB",
        "sinr": "6dB",
        "cell_id": "12345678",
        "band": "3",
        "pci": "44",
    },
    "monitoring_status": {
        "ConnectionStatus": "901",
        "SignalIcon": "4",
        "CurrentNetworkType": "19",
        "WifiStatus": "1",
    },
    "traffic_statistics": {
        "CurrentDownload": "1073741824",
        "CurrentUpload": "536870912",
        "CurrentConnectTime": "3600",
        "TotalDownload": "10737418240",
        "TotalUpload": "5368709120",
    },
    "month_statistics": {
        "CurrentMonthDownload": "107374182400",
        "CurrentMonthUpload": "10737418240",
        "MonthDuration": "864000",
        "MonthLastClearTime": "2026-04-18",
    },
    "start_date": {
        "SetMonthData": "1",
        "StartDay": "1",
        "DataLimit": "2000GB",
        "MonthThreshold": "80",
    },
    "current_plmn": {"FullName": "Test Carrier", "Numeric": "27201"},
    "net_mode": {"NetworkMode": "03", "NetworkBand": "3FFFFFFF"},
    "sms_count": {
        "LocalUnread": "1",
        "LocalInbox": "3",
        "LocalOutbox": "2",
        "LocalMax": "500",
    },
    "sms_list": {
        "Messages": {
            "Message": [
                {
                    "Index": "1",
                    "Phone": "+353871234567",
                    "Content": "hello",
                    "Date": "2026-08-15 10:00:00",
                    "Smstat": "0",
                }
            ]
        }
    },
    "mobile_dataswitch": {"dataswitch": "1"},
    "lan_host_info": {"Hosts": {"Host": [{"MacAddress": "AA:BB:CC:DD:EE:01"}]}},
    "wlan_host_list": {"Hosts": {"Host": [{"MacAddress": "AA:BB:CC:DD:EE:02"}]}},
    "onekey_diag": {"connection_status": "2"},
    "voice_busy": "Idle",
    "voice_volte": {"VoLTEStatus": "1"},
}


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    """Make the custom component importable by the real `hass` fixture.

    Without it `async_setup` answers "Integration not found" and the sweep
    fails at setup rather than finding anything.
    """
    return


@pytest.fixture
def live_entry() -> MockConfigEntry:
    """Build a config entry at the current schema version.

    Separate from `mock_config_entry` above, which omits `version` and so
    defaults to 1. Every other test drives the
    coordinator directly and never reaches the migration check; this one sets
    the entry up for real, and HA refuses an entry whose version is older than
    the flow's with "Migration handler not found".
    """
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id="dc7196112233",
        title="My Huawei Router",
        data={
            "model": "B535s-232",
            "sw_version": "11.0.1.1(H192SP1C983)",
            "hw_version": "Ver.A",
            "mac": "dc7196112233",
        },
        options={
            CONF_HOST: "192.168.8.1",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
        },
    )


@asynccontextmanager
async def _live_entities(hass: HomeAssistant, entry):
    """Set the integration up for real and yield every entity it created.

    **Disabled-by-default entities are forced on.** A large part of this
    component's diagnostic surface — the identity sensors in particular — ships
    disabled, and those are precisely the entities most likely to publish an
    attribute nobody re-checked. Sweeping only the enabled set would skip them
    and report success.
    """
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
            property(lambda self: True),
        ),
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI") as api_class,
    ):
        api = api_class.return_value
        # A real string, not the MagicMock default: the root device is
        # registered with `configuration_url`, and HA validates it.
        api.url = "http://192.168.8.1"
        api.login = AsyncMock(return_value=None)
        api.logout = AsyncMock(return_value=None)
        api.get_data = AsyncMock(return_value=dict(SWEEP_DATA))

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        yield [
            entity
            for component in hass.data["entity_components"].values()
            for entity in component.entities
            if getattr(entity, "platform", None) is not None
            and entity.platform.platform_name == DOMAIN
        ]
