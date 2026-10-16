"""The two endpoints `huawei-lte-api` gained in 2.0.1 are read on any library.

`voice.volte` and `monitoring.onekey_diag` exist from library 2.0.1 and not in
1.11.0, which Home Assistant core pins and which Home Assistant's container image
puts back at every update. From 1.2.4-dev4 (plan I7, D7) an older library reads
the same router paths through its session, so VoLTE Status and Router
Self-Diagnosis read a value on either version and never wait for a restart.
Before, 1.11.0 skipped both as `unsupported`.

On 2.0.1 or later the library's own method is called, so a misspelt table entry
is still a reported defect rather than a silent path read: the gate is the
loaded library's version, not whether the method exists.

These tests simulate an old or a new library by patching the version the module
read at import and by removing or adding the two methods on the endpoint
classes, so they give the same result whichever library is installed.
"""

from __future__ import annotations

from huawei_lte_api.api.Monitoring import Monitoring
from huawei_lte_api.api.Voice import Voice
from packaging.version import Version
import pytest
import requests_mock as requests_mock_module

from custom_components.huawei_router_5g import api as api_module, library_guard
from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI
from custom_components.huawei_router_5g.const import (
    HEALTH_DRIFT_STRIKE_LIMIT,
    LIBRARY_ADDED_ENDPOINTS,
)
from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)

from .transport import RouterTransport

ROUTER_URL = "http://192.168.8.1"
ADDED_KEYS = ("voice_volte", "onekey_diag")


@pytest.fixture(name="transport")
def transport_fixture():
    """Serve a working router over the `requests` transport."""
    with requests_mock_module.Mocker() as mocker:
        yield RouterTransport(mocker)


def _simulate_library(
    monkeypatch: pytest.MonkeyPatch, version: str | None, *, has_methods: bool
) -> None:
    """Make the module believe it runs on `version`, with or without the methods."""
    monkeypatch.setattr(
        api_module, "_LIBRARY_VERSION", Version(version) if version else None
    )
    if has_methods:
        monkeypatch.setattr(
            Voice, "volte", lambda self: {"volte_enable": "1"}, raising=False
        )
        monkeypatch.setattr(
            Monitoring,
            "onekey_diag",
            lambda self: {"connection_status": "2"},
            raising=False,
        )
    else:
        monkeypatch.delattr(Voice, "volte", raising=False)
        monkeypatch.delattr(Monitoring, "onekey_diag", raising=False)


def _coordinator(hass, entry) -> HuaweiRouter5GDataUpdateCoordinator:
    """Build a coordinator over a real API client."""
    entry.add_to_hass(hass)
    api = HuaweiRouter5GAPI(ROUTER_URL, "admin", "password")
    return HuaweiRouter5GDataUpdateCoordinator(hass, entry, api)


async def test_an_old_library_reads_both_endpoints_by_path(
    hass, mock_config_entry, transport, monkeypatch
):
    """Below the first version both blocks are read by path and answered."""
    _simulate_library(monkeypatch, "1.11.0", has_methods=False)
    coordinator = _coordinator(hass, mock_config_entry)

    await coordinator.async_refresh()

    outcomes = coordinator.api.endpoint_outcomes
    for key in ADDED_KEYS:
        assert outcomes[key]["outcome"] == "answered"
        assert coordinator.data[key]
    assert coordinator.data["voice_volte"] == {"VolteStatus": "1"}
    assert coordinator.api.last_rejection is None


async def test_a_new_library_reads_both_endpoints_through_its_methods(
    hass, mock_config_entry, transport, monkeypatch
):
    """At or above the first version the library's own methods are called."""
    _simulate_library(monkeypatch, "2.0.1", has_methods=True)
    coordinator = _coordinator(hass, mock_config_entry)

    await coordinator.async_refresh()

    assert coordinator.data["voice_volte"] == {"volte_enable": "1"}
    assert coordinator.data["onekey_diag"] == {"connection_status": "2"}


async def test_health_stays_ok_after_the_drift_budget_on_an_old_library(
    hass, mock_config_entry, transport, monkeypatch
):
    """Both reads answer on 1.11.0, so health stays ok past the drift budget."""
    _simulate_library(monkeypatch, "1.11.0", has_methods=False)
    coordinator = _coordinator(hass, mock_config_entry)

    for _ in range(HEALTH_DRIFT_STRIKE_LIMIT + 1):
        await coordinator.async_refresh()

    assert coordinator.health_snapshot["degraded_capabilities"] == []
    assert coordinator.health_snapshot["severity"] == "ok"


async def test_a_misspelt_table_entry_on_a_new_library_is_reported(
    hass, mock_config_entry, transport, monkeypatch
):
    """At or above the first version a missing method is a defect, not a skip.

    This is the test that fails if the gate is replaced by an existence check:
    that variant would find the misspelt method absent and read the path,
    hiding the defect.
    """
    _simulate_library(monkeypatch, "2.0.1", has_methods=True)
    monkeypatch.setitem(
        LIBRARY_ADDED_ENDPOINTS,
        "voice_volte",
        ("voice", "volte_typo", "2.0.1", "voice/volte"),
    )
    coordinator = _coordinator(hass, mock_config_entry)

    await coordinator.async_refresh()

    assert coordinator.api.endpoint_outcomes["voice_volte"]["outcome"] == "unavailable"
    assert coordinator.api.last_rejection["verdict"] == "unavailable"
    assert coordinator.api.last_rejection["error"] == "AttributeError"


async def test_the_loaded_version_decides_not_the_version_on_disk(
    hass, mock_config_entry, transport, monkeypatch
):
    """After a guard install the files change and the loaded classes do not.

    The guard reads the version on disk. If the gate did the same, the first
    poll after an install would call methods the loaded 1.11.0 classes lack.
    Reading the loaded version, the paths are read and both answer.
    """
    _simulate_library(monkeypatch, "1.11.0", has_methods=False)
    monkeypatch.setattr(
        library_guard, "installed_library_version", lambda: Version("2.0.1")
    )
    coordinator = _coordinator(hass, mock_config_entry)

    for _ in range(HEALTH_DRIFT_STRIKE_LIMIT):
        await coordinator.async_refresh()

    for key in ADDED_KEYS:
        assert coordinator.api.endpoint_outcomes[key]["outcome"] == "answered"
    assert coordinator.health_snapshot["severity"] == "ok"


async def test_an_unreadable_version_makes_the_call_and_reports_the_failure(
    hass, mock_config_entry, transport, monkeypatch
):
    """When the version is unknown the endpoint is never hidden."""
    _simulate_library(monkeypatch, None, has_methods=False)
    coordinator = _coordinator(hass, mock_config_entry)

    await coordinator.async_refresh()

    for key in ADDED_KEYS:
        assert coordinator.api.endpoint_outcomes[key]["outcome"] == "unavailable"


@pytest.mark.parametrize(
    ("version", "supported"),
    [
        ("1.11.0", False),
        ("2.0.0", False),
        ("2.0.1rc1", False),
        ("2.0.1", True),
        ("2.0.2", True),
        ("2.1.0", True),
    ],
)
def test_the_first_version_boundary(monkeypatch, version, supported):
    """The first version is inclusive, and a pre-release of it is older."""
    monkeypatch.setattr(api_module, "_LIBRARY_VERSION", Version(version))

    assert api_module.library_supports("2.0.1") is supported


def test_an_unparsable_version_constant_reads_as_unknown(monkeypatch):
    """`_read_library_version` returns `None` for a constant it cannot parse."""
    monkeypatch.setattr(api_module.huawei_lte_api, "__version__", "not-a-version")

    assert api_module._read_library_version() is None

    monkeypatch.delattr(api_module.huawei_lte_api, "__version__")

    assert api_module._read_library_version() is None
