"""Install the preferred `huawei-lte-api` when no core `huawei_lte` entry needs 1.11.0.

Home Assistant core pins `huawei-lte-api==1.11.0` for its own `huawei_lte`
integration, and this integration accepts either 1.11.0 or 2.0.1 (the manifest
range). With a core entry configured the library must stay where core puts it.
With none, 2.0.1 is preferred: it carries two endpoints 1.11.0 lacks and encodes
supplementary-plane characters in SMS, and nothing else would ever move an
installation from 1.11.0 to 2.0.1 once core is gone.

The install cannot take effect in the process that runs it, because the library
is imported when this package loads, so a verified install raises one fixable
repair that restarts Home Assistant. The guard never fails setup: it runs as a
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
    """Decide whether to install the preferred library, and raise the repair."""
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
        clear_restart_issue(hass)
        return

    preferred = Version(LIBRARY_PREFERRED_VERSION)
    installed = await hass.async_add_executor_job(installed_library_version)
    if installed is not None and installed >= preferred:
        clear_restart_issue(hass)
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

    if outcome_known and after is not None and after >= preferred:
        ir.async_create_issue(
            hass,
            DOMAIN,
            REPAIR_LIBRARY_RESTART,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=REPAIR_LIBRARY_RESTART,
        )
    elif outcome_known:
        _LOGGER.warning(
            "%s installed but the version read back is %s, not %s or later",
            LIBRARY_REQUIREMENT,
            after,
            LIBRARY_PREFERRED_VERSION,
        )
