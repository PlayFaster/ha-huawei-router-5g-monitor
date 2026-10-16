"""Install the preferred `huawei-lte-api` when no core `huawei_lte` entry needs 1.11.0.

Home Assistant core pins `huawei-lte-api==1.11.0` for its own `huawei_lte`
integration, and this integration accepts either 1.11.0 or 2.0.1 (the manifest
range). With a core entry configured the library must stay where core puts it.
With none, 2.0.1 is preferred: it carries two endpoints 1.11.0 lacks and encodes
supplementary-plane characters in SMS, and nothing else would ever move an
installation from 1.11.0 to 2.0.1 once core is gone.

The install takes effect at the next restart, because the library is imported
when this package loads. No repair asks for that restart: Home Assistant's
container image puts 1.11.0 back at every update, so a repair would ask for a
second restart after each one, and every sensor already works on 1.11.0 (the two
2.0.1 reads fall back to their router paths, `api._call_added_endpoint`). A
verified install is logged at INFO. A repair raised by an earlier version is
deleted at every start. The guard never fails setup: it runs as a
background task, every failure is logged with its traceback, and an outcome that
cannot be known (a timeout or a cancellation) creates no repair and is decided
from the disk at the next start.
"""

from __future__ import annotations

import asyncio
import importlib
from importlib import metadata
import logging

from packaging.version import InvalidVersion, Version

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.requirements import async_process_requirements

from .const import (
    CORE_DOMAIN,
    DOMAIN,
    LIBRARY_GUARD_TIMEOUT,
    LIBRARY_PACKAGE,
    LIBRARY_PREFERRED_VERSION,
    LIBRARY_REQUIREMENT,
    REPAIR_LIBRARY_RESTART,
)

_LOGGER = logging.getLogger(__name__)


def installed_library_version() -> Version | None:
    """Return the `huawei-lte-api` version on disk, or `None` when unreadable.

    Read through `importlib.metadata`, which reads the files and not the modules
    in memory: after an install the two differ until the next restart.
    """
    importlib.invalidate_caches()
    try:
        return Version(metadata.version(LIBRARY_PACKAGE))
    except (metadata.PackageNotFoundError, InvalidVersion):
        return None


# The version on disk as the guard last read it, in an executor job. Integration
# Health reports it (1.2.4-dev4 I7) rather than reading the metadata itself,
# because that read is file I/O and the attribute is computed on the event loop.
_SEEN: dict[str, Version | None] = {"installed": None}


def last_installed_version() -> Version | None:
    """Return the version on disk at the guard's last read, or None before it."""
    return _SEEN["installed"]


def clear_restart_issue(hass: HomeAssistant) -> None:
    """Delete the restart repair; deleting a missing issue is not an error."""
    ir.async_delete_issue(hass, DOMAIN, REPAIR_LIBRARY_RESTART)


async def async_ensure_library(hass: HomeAssistant) -> None:
    """Run the guard, logging every failure and never raising into setup."""
    try:
        await _async_ensure_library(hass)
    except Exception:
        _LOGGER.warning(
            "The %s guard failed; the library is left as it is and the next "
            "start decides again",
            LIBRARY_PACKAGE,
            exc_info=True,
        )


async def _async_ensure_library(hass: HomeAssistant) -> None:
    """Decide whether to install the preferred library, and log the outcome."""
    # Raised by versions before 1.2.4-dev4, after every Home Assistant update.
    clear_restart_issue(hass)
    installed = await hass.async_add_executor_job(installed_library_version)
    _SEEN["installed"] = installed
    if hass.config.skip_pip or LIBRARY_PACKAGE in (hass.config.skip_pip_packages or []):
        # `async_process_requirements` does not read `skip_pip`, so the guard
        # must, or it would install on a system that has forbidden installs.
        _LOGGER.warning(
            "Package installs are disabled in Home Assistant, so %s is not "
            "upgraded to %s",
            LIBRARY_PACKAGE,
            LIBRARY_PREFERRED_VERSION,
        )
        return

    if hass.config_entries.async_entries(CORE_DOMAIN):
        # Core's own integration needs its pinned version; leave the library.
        return

    preferred = Version(LIBRARY_PREFERRED_VERSION)
    if installed is not None and installed >= preferred:
        return

    outcome_known = False
    try:
        # The install is its own task and is shielded, so the timeout only
        # stops this guard waiting. Cancelling it would release core's pip lock
        # while the pip thread keeps running, and a second pip could start.
        install = hass.async_create_background_task(
            async_process_requirements(
                hass, DOMAIN, [LIBRARY_REQUIREMENT], is_built_in=False
            ),
            name=f"{DOMAIN} library install",
        )
        await asyncio.wait_for(asyncio.shield(install), LIBRARY_GUARD_TIMEOUT)
        outcome_known = True
    except TimeoutError:
        _LOGGER.warning(
            "Installing %s did not finish within %s s; it continues, and the "
            "next start decides from the installed version",
            LIBRARY_REQUIREMENT,
            LIBRARY_GUARD_TIMEOUT,
        )
    except asyncio.CancelledError:
        _LOGGER.warning(
            "Installing %s was cancelled; the next start decides from the "
            "installed version",
            LIBRARY_REQUIREMENT,
        )
        raise
    except Exception:
        _LOGGER.warning("Installing %s failed", LIBRARY_REQUIREMENT, exc_info=True)
    finally:
        after = await hass.async_add_executor_job(installed_library_version)
        _SEEN["installed"] = after

    if outcome_known and after is not None and after >= preferred:
        _LOGGER.info(
            "Installed %s %s; it takes effect at the next restart of Home "
            "Assistant. Until then %s runs, and every sensor works on it",
            LIBRARY_PACKAGE,
            after,
            installed,
        )
    elif outcome_known:
        _LOGGER.warning(
            "%s installed but the version read back is %s, not %s or later",
            LIBRARY_REQUIREMENT,
            after,
            LIBRARY_PREFERRED_VERSION,
        )
