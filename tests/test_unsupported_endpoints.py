"""The two endpoints an old `huawei-lte-api` lacks are skipped, and nothing else is.

`voice.volte` and `monitoring.onekey_diag` exist from library 2.0.1 and not in
1.11.0, which Home Assistant core pins. On 1.11.0 the integration must skip them
quietly: no rejection, no strike toward a degraded capability, no failed Diag
Check. It must **not** do that by asking whether the method exists, because that
would also tolerate a misspelt table entry or a method renamed in a later
release, which is the masked-error defect `test_library_contract` was written
to catch. The gate is the loaded library's version.

These tests simulate an old or a new library by patching the version the module
read at import and by removing or adding the two methods on the endpoint
classes, so they give the same result whichever library is installed.
"""

from __future__ import annotations

import logging

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


async def test_an_old_library_skips_both_endpoints_without_a_rejection(
    hass, mock_config_entry, transport, monkeypatch
):
    """Below the first version both blocks are `unsupported`, absent and unrejected."""
    _simulate_library(monkeypatch, "1.11.0", has_methods=False)
    coordinator = _coordinator(hass, mock_config_entry)

    await coordinator.async_refresh()

    outcomes = coordinator.api.endpoint_outcomes
    for key in ADDED_KEYS:
        assert outcomes[key]["outcome"] == "unsupported"
        assert key not in coordinator.data
    assert coordinator.api.last_rejection is None


async def test_health_stays_ok_after_the_drift_budget_on_an_old_library(
    hass, mock_config_entry, transport, monkeypatch
):
    """A skipped endpoint is not a lost capability, however many polls pass."""
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
    that variant would call the misspelt method, find it absent, and record
    `unsupported`, hiding the defect.
    """
    _simulate_library(monkeypatch, "2.0.1", has_methods=True)
    monkeypatch.setitem(
        LIBRARY_ADDED_ENDPOINTS, "voice_volte", ("voice", "volte_typo", "2.0.1")
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
    poll after an install would call methods the loaded 1.11.0 classes lack, and
    health would read degraded until the restart the repair asks for.
    """
    _simulate_library(monkeypatch, "1.11.0", has_methods=False)
    monkeypatch.setattr(
        library_guard, "installed_library_version", lambda: Version("2.0.1")
    )
    coordinator = _coordinator(hass, mock_config_entry)

    for _ in range(HEALTH_DRIFT_STRIKE_LIMIT):
        await coordinator.async_refresh()

    for key in ADDED_KEYS:
        assert coordinator.api.endpoint_outcomes[key]["outcome"] == "unsupported"
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


async def test_the_skip_is_logged_once(
    hass, mock_config_entry, transport, monkeypatch, caplog
):
    """One INFO line names the skipped endpoints, however many polls follow."""
    _simulate_library(monkeypatch, "1.11.0", has_methods=False)
    coordinator = _coordinator(hass, mock_config_entry)

    with caplog.at_level(logging.INFO, logger=api_module.__name__):
        for _ in range(3):
            await coordinator.async_refresh()

    lines = [r for r in caplog.records if "predates" in r.getMessage()]
    assert len(lines) == 1
    assert "voice_volte" in lines[0].getMessage()
