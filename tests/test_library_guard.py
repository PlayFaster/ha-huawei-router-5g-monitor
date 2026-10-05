"""The startup guard that installs `huawei-lte-api` 2.0.1 when it is safe to.

The guard installs only when no core `huawei_lte` entry exists, because core pins
1.11.0 for its own integration. It cannot take effect in the process that runs
it, so a verified install raises one fixable repair that restarts Home Assistant.
It must never fail setup, never act on an outcome it cannot know, and never
install on a system that has forbidden installs.

Every case supplies its own fake installer and its own version reader. The
autouse fixture in `conftest.py` fails any other test that reaches the real
installer, because an exception raised by the installer would be caught by the
guard's own handler and the test would pass.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from huawei_lte_api.api.Monitoring import Monitoring
from huawei_lte_api.api.Voice import Voice
from packaging.version import Version
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import requests_mock as requests_mock_module

from custom_components.huawei_router_5g import (
    api as api_module,
    async_setup,
    library_guard,
)
from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI
from custom_components.huawei_router_5g.const import (
    CORE_DOMAIN,
    DOMAIN,
    HEALTH_DRIFT_STRIKE_LIMIT,
    LIBRARY_REQUIREMENT,
    REPAIR_LIBRARY_RESTART,
)
from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .transport import RouterTransport


class FakeLibrary:
    """A fake installer and version reader sharing one notion of what is on disk."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        installed: str | None,
        *,
        after: str | object | None = "2.0.1",
        raises: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        """Install the fakes; `after` is the version the installer leaves on disk."""
        self.version = Version(installed) if installed else None
        self.after = after
        self.raises = raises
        self.delay = delay
        self.calls: list[list[str]] = []
        self.finished = False
        monkeypatch.setattr(library_guard, "installed_library_version", self._read)
        monkeypatch.setattr(library_guard, "async_process_requirements", self._install)

    def _read(self) -> Version | None:
        return self.version

    async def _install(
        self,
        hass: HomeAssistant,
        name: str,
        requirements: list[str],
        is_built_in: bool = True,
    ) -> None:
        self.calls.append(list(requirements))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises is not None:
            raise self.raises
        if self.after != "unchanged":
            self.version = Version(self.after) if self.after else None
        self.finished = True


def _issue(hass: HomeAssistant) -> Any:
    return ir.async_get(hass).async_get_issue(DOMAIN, REPAIR_LIBRARY_RESTART)


@pytest.fixture(name="installs_allowed")
def installs_allowed_fixture(hass: HomeAssistant) -> None:
    """The test `hass` forbids installs; these cases choose when they are allowed."""
    hass.config.skip_pip = False
    hass.config.skip_pip_packages = []


def _core_entry(hass: HomeAssistant, **kwargs: Any) -> MockConfigEntry:
    entry = MockConfigEntry(domain=CORE_DOMAIN, title="Core Huawei LTE", **kwargs)
    entry.add_to_hass(hass)
    return entry


async def test_a_core_entry_leaves_the_library_alone(
    hass, installs_allowed, monkeypatch
):
    """Core needs 1.11.0, so nothing is installed and no repair is raised."""
    fake = FakeLibrary(monkeypatch, "1.11.0")
    _core_entry(hass)

    await library_guard.async_ensure_library(hass)

    assert fake.calls == []
    assert _issue(hass) is None


async def test_a_disabled_core_entry_also_leaves_the_library_alone(
    hass, installs_allowed, monkeypatch
):
    """Enabling the entry later would reinstall 1.11.0, so a disabled one counts."""
    fake = FakeLibrary(monkeypatch, "1.11.0")
    _core_entry(hass, disabled_by=ConfigEntryDisabler.USER)

    await library_guard.async_ensure_library(hass)

    assert fake.calls == []
    assert _issue(hass) is None


async def test_without_core_an_old_library_is_upgraded_and_a_repair_is_raised(
    hass, installs_allowed, monkeypatch
):
    """The install is verified by re-reading the version, then the repair appears."""
    fake = FakeLibrary(monkeypatch, "1.11.0", after="2.0.1")

    await library_guard.async_ensure_library(hass)

    assert fake.calls == [[LIBRARY_REQUIREMENT]]
    issue = _issue(hass)
    assert issue is not None
    assert issue.is_fixable is True
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_key == REPAIR_LIBRARY_RESTART


@pytest.mark.parametrize("installed", ["2.0.1", "2.0.2"])
async def test_a_library_at_or_above_the_floor_clears_a_stale_repair(
    hass, installs_allowed, monkeypatch, installed
):
    """Nothing is installed, and a repair left from an earlier start is deleted."""
    fake = FakeLibrary(monkeypatch, installed)
    ir.async_create_issue(
        hass,
        DOMAIN,
        REPAIR_LIBRARY_RESTART,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=REPAIR_LIBRARY_RESTART,
    )

    await library_guard.async_ensure_library(hass)

    assert fake.calls == []
    assert _issue(hass) is None


async def test_a_core_entry_clears_a_stale_repair(hass, installs_allowed, monkeypatch):
    """A core entry added after the repair was raised makes the repair wrong."""
    FakeLibrary(monkeypatch, "1.11.0")
    ir.async_create_issue(
        hass,
        DOMAIN,
        REPAIR_LIBRARY_RESTART,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=REPAIR_LIBRARY_RESTART,
    )
    _core_entry(hass)

    await library_guard.async_ensure_library(hass)

    assert _issue(hass) is None


async def test_skip_pip_forbids_the_install(hass, monkeypatch, caplog):
    """The installer helper ignores `skip_pip`, so the guard must read it."""
    fake = FakeLibrary(monkeypatch, "1.11.0")
    hass.config.skip_pip = True

    with caplog.at_level(logging.WARNING, logger=library_guard.__name__):
        await library_guard.async_ensure_library(hass)

    assert fake.calls == []
    assert _issue(hass) is None
    assert "Package installs are disabled" in caplog.text


async def test_a_skipped_package_forbids_the_install(hass, monkeypatch, caplog):
    """`skip_pip_packages` naming the library is the same prohibition."""
    fake = FakeLibrary(monkeypatch, "1.11.0")
    hass.config.skip_pip = False
    hass.config.skip_pip_packages = ["huawei-lte-api"]

    with caplog.at_level(logging.WARNING, logger=library_guard.__name__):
        await library_guard.async_ensure_library(hass)

    assert fake.calls == []
    assert "Package installs are disabled" in caplog.text


async def test_an_install_that_raises_is_logged_and_creates_no_repair(
    hass, installs_allowed, monkeypatch, caplog
):
    """A failed install is a warning with its traceback, never a failed setup."""
    FakeLibrary(monkeypatch, "1.11.0", raises=RuntimeError("no network"))

    with caplog.at_level(logging.WARNING, logger=library_guard.__name__):
        await library_guard.async_ensure_library(hass)

    assert _issue(hass) is None
    failed = [r for r in caplog.records if "failed" in r.getMessage()]
    assert failed
    assert failed[0].exc_info is not None


async def test_an_install_that_changes_nothing_creates_no_repair(
    hass, installs_allowed, monkeypatch, caplog
):
    """The re-read is what decides: an install that returns but leaves 1.11.0 is not success."""
    FakeLibrary(monkeypatch, "1.11.0", after="unchanged")

    with caplog.at_level(logging.WARNING, logger=library_guard.__name__):
        await library_guard.async_ensure_library(hass)

    assert _issue(hass) is None
    assert "version read back" in caplog.text


async def test_an_install_whose_version_cannot_be_read_back_creates_no_repair(
    hass, installs_allowed, monkeypatch
):
    """A `None` re-read is not evidence that 2.0.1 is installed."""
    FakeLibrary(monkeypatch, "1.11.0", after=None)

    await library_guard.async_ensure_library(hass)

    assert _issue(hass) is None


async def test_a_timeout_stops_the_wait_and_does_not_cancel_the_install(
    hass, installs_allowed, monkeypatch, caplog
):
    """Cancelling would release core's pip lock while the pip thread keeps running."""
    fake = FakeLibrary(monkeypatch, "1.11.0", delay=0.3)
    monkeypatch.setattr(library_guard, "LIBRARY_GUARD_TIMEOUT", 0.05)

    with caplog.at_level(logging.WARNING, logger=library_guard.__name__):
        await library_guard.async_ensure_library(hass)

    assert fake.finished is False
    assert _issue(hass) is None
    assert "did not finish" in caplog.text

    await asyncio.sleep(0.4)

    assert fake.finished is True


async def test_a_cancelled_guard_leaves_the_install_running_and_raises_no_repair(
    hass, installs_allowed, monkeypatch, caplog
):
    """Shutdown cancels the guard; the outcome is unknown and the next start decides."""
    fake = FakeLibrary(monkeypatch, "1.11.0", delay=0.3)
    task = hass.async_create_background_task(
        library_guard.async_ensure_library(hass), name="test guard"
    )
    await asyncio.sleep(0.05)

    with caplog.at_level(logging.WARNING, logger=library_guard.__name__):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert _issue(hass) is None
    assert "was cancelled" in caplog.text
    await asyncio.sleep(0.4)
    assert fake.finished is True


@pytest.mark.parametrize("failure", ["raises", "hangs"])
async def test_setup_registers_its_services_whatever_the_guard_does(
    hass, monkeypatch, failure
):
    """A slow or failing guard must not stop the services registering or setup finishing.

    Core returns False from setup on a timeout or an exception, which would leave
    the services unregistered and every entry unloaded. The guard is started last
    as a background task, so neither can reach setup.
    """

    async def _bad_guard(_hass: HomeAssistant) -> None:
        if failure == "raises":
            raise RuntimeError("guard blew up")
        await asyncio.sleep(3600)

    # The inner function, so that the real wrapper's handler is the one that
    # must absorb the exception.
    monkeypatch.setattr(library_guard, "_async_ensure_library", _bad_guard)

    assert await async_setup(hass, {}) is True

    for service in ("send_sms", "delete_sms", "delete_all_sms", "get_sms_list"):
        assert hass.services.has_service(DOMAIN, service)


def test_the_version_on_disk_is_read_from_the_package_metadata():
    """`installed_library_version` returns the version `importlib.metadata` reports."""
    version = library_guard.installed_library_version()

    assert isinstance(version, Version)


def test_a_missing_package_reads_as_no_version(monkeypatch):
    """No installed distribution is `None`, not an error."""

    def _missing(_name: str) -> str:
        raise library_guard.metadata.PackageNotFoundError

    monkeypatch.setattr(library_guard.metadata, "version", _missing)

    assert library_guard.installed_library_version() is None


def test_an_unparsable_version_on_disk_reads_as_no_version(monkeypatch):
    """A version string that is not a version is `None`, not an error."""
    monkeypatch.setattr(
        library_guard.metadata, "version", lambda _name: "not-a-version"
    )

    assert library_guard.installed_library_version() is None


@pytest.fixture(name="transport")
def transport_fixture():
    """Serve a working router over the `requests` transport."""
    with requests_mock_module.Mocker() as mocker:
        yield RouterTransport(mocker)


async def test_the_restart_repair_is_pending_while_polling_stays_healthy(
    hass, installs_allowed, mock_config_entry, transport, monkeypatch
):
    """Between the install and the restart the repair is shown and polls stay healthy.

    The guard has installed 2.0.1 on disk, while the loaded library is still
    1.11.0. The repair must be raised, and the polls that follow must read the
    two added endpoints as `unsupported` and keep Integration Health `ok`, so the
    only thing the user sees is the repair that asks for the restart.
    """
    monkeypatch.setattr(api_module, "_LIBRARY_VERSION", Version("1.11.0"))
    monkeypatch.delattr(Voice, "volte", raising=False)
    monkeypatch.delattr(Monitoring, "onekey_diag", raising=False)
    FakeLibrary(monkeypatch, "1.11.0", after="2.0.1")
    mock_config_entry.add_to_hass(hass)
    coordinator = HuaweiRouter5GDataUpdateCoordinator(
        hass,
        mock_config_entry,
        HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password"),
    )

    await library_guard.async_ensure_library(hass)
    for _ in range(HEALTH_DRIFT_STRIKE_LIMIT):
        await coordinator.async_refresh()

    assert _issue(hass) is not None
    assert _issue(hass).translation_key == REPAIR_LIBRARY_RESTART
    assert coordinator.health_snapshot["severity"] == "ok"
    assert coordinator.health_snapshot["degraded_capabilities"] == []
