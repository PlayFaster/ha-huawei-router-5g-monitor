"""DataUpdateCoordinator for Huawei Router 5G."""

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import HuaweiAuthError, HuaweiRouter5GAPI
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_STOP_POLLING,
    CRITICAL_ENDPOINT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ENDPOINT_NAMES,
    FETCH_TIMEOUT,
    HEALTH_STRIKE_LIMIT,
    REPAIR_AUTH_FAILED,
    REPAIR_CONN_ERROR,
    REPAIR_NAMES,
    SIGNAL_CONTRACT_KEYS,
)
from .helpers import get_router_model, parse_sms_list

_LOGGER = logging.getLogger(__name__)

# Minimum drop in a router uptime counter (seconds) treated as a genuine reset.
# A real reboot/reconnect resets the counter to ~0, so this margin only rejects
# small downward blips from counter quantization or stale cached readings.
UPTIME_REBOOT_MARGIN = 30


class HuaweiRouter5GDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Huawei Router data with resilience and pausing."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: HuaweiRouter5GAPI,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.entry = entry
        self.consecutive_failures = 0
        self.last_update_success_time: datetime | None = None
        self.last_sms_timestamp: str | None = None
        self.fired_sms_hashes: set[str] = set()

        # One-shot flag set by async_force_refresh so an explicit user action
        # fetches even while polling is paused (dev_standards Section 13).
        self._force_refresh_once = False

        # Cancel handle for a follow-up refresh scheduled by a disruptive
        # button. Held so a second press replaces the first rather than
        # stacking, and so unload can cancel it - a timer that outlives the
        # entry fires against a coordinator whose API is already logged out.
        self._pending_refresh: CALLBACK_TYPE | None = None

        # Single-slot memo for the usage projection, held per entry.
        #
        # The projection has two consumers on the same state write — the
        # sensor's value and its `confidence` attribute — so without this it
        # is computed twice per poll to produce two halves of one answer.
        #
        # **Per coordinator rather than per module.** A module-level slot is
        # shared by every config entry, so two routers each replace the
        # other's entry on every poll and the memo never hits — it degrades
        # to no memo at all, silently, on exactly the installs that poll most.
        # It also survives between tests, which makes ordering matter.
        #
        # Keyed by identity, not equality: the payload is replaced wholesale
        # on each refresh, so `is` is correct and cheap. Holding the payload
        # is what makes identity safe — it cannot be collected and have its
        # `id()` reused while it is still the key.
        self.projection_cache: tuple[Any, Any] | None = None

        # The non-live options this entry was built with. The update listener
        # compares against it to tell a connection change, which must reload,
        # from a tuning change, which must not (Section 9). Set by
        # `async_setup_entry`; seeded here so the attribute always exists.
        self.reload_signature: dict[str, Any] = {}

        # Section 19 health state. Deliberately NOT stored in `self.data`,
        # which is None before the first success and frozen at last-good values
        # during an outage — a verdict held there could never describe the
        # failure that stopped it being updated.
        self._endpoint_strikes: dict[str, int] = {}
        self.health_snapshot: dict[str, Any] = {
            "severity": None,
            "issues": [],
            "degraded_capabilities": [],
            "drift": [],
            "last_good_update": None,
        }

        # Reboot-detection latches — frozen timestamps for uptime-derived sensors.
        # Each is recomputed exactly once per genuine counter reset and then held.
        self._system_boot_time: datetime | None = None
        self._last_system_uptime: int | None = None
        self._conn_start_time: datetime | None = None
        self._last_conn_uptime: int | None = None
        self._total_conn_start_time: datetime | None = None
        self._last_total_conn_time: int | None = None

        with contextlib.suppress(Exception):
            if v := entry.data.get("system_boot_time"):
                self._system_boot_time = dt_util.parse_datetime(v)
        with contextlib.suppress(ValueError, TypeError):
            if (v := entry.data.get("last_system_uptime")) is not None:
                self._last_system_uptime = int(v)
        with contextlib.suppress(Exception):
            if v := entry.data.get("conn_start_time"):
                self._conn_start_time = dt_util.parse_datetime(v)
        with contextlib.suppress(ValueError, TypeError):
            if (v := entry.data.get("last_conn_uptime")) is not None:
                self._last_conn_uptime = int(v)
        with contextlib.suppress(Exception):
            if v := entry.data.get("total_conn_start_time"):
                self._total_conn_start_time = dt_util.parse_datetime(v)
        with contextlib.suppress(ValueError, TypeError):
            if (v := entry.data.get("last_total_conn_time")) is not None:
                self._last_total_conn_time = int(v)

        # Load hardware identity from persistent ConfigEntry data.
        self.model = entry.data.get("model", "Huawei Router")
        self.sw_version = entry.data.get("sw_version")
        self.hw_version = entry.data.get("hw_version")
        self.mac = entry.data.get("mac")

        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{entry.title} Data",
            update_interval=timedelta(seconds=scan_interval),
        )

    def _healthy_snapshot(self) -> dict[str, Any]:
        """Return a snapshot describing a healthy integration."""
        return {
            "severity": None,
            "issues": [],
            "degraded_capabilities": [],
            "drift": [],
            "last_good_update": (
                self.last_update_success_time.isoformat()
                if self.last_update_success_time
                else None
            ),
        }

    def update_health(
        self, data: dict[str, Any] | None, *, failed: bool, cold_start: bool
    ) -> None:
        """Recompute the Section 19 health verdict.

        Held as a coordinator attribute rather than inside `self.data`, which is
        `None` before the first success and **frozen at the last good values**
        during an outage — a verdict living there could never describe the
        failure that stopped it being updated.

        Wrapped so a malformed payload can never crash the update it is
        diagnosing: on any internal error this degrades to "healthy/unknown"
        and logs at debug.
        """
        try:
            self.health_snapshot = self._compute_health(
                data, failed=failed, cold_start=cold_start
            )
        except Exception:
            _LOGGER.debug(
                "%s: Health computation failed; reporting unknown.",
                self.entry.title,
                exc_info=True,
            )
            self.health_snapshot = self._healthy_snapshot()

    def _compute_health(
        self, data: dict[str, Any] | None, *, failed: bool, cold_start: bool
    ) -> dict[str, Any]:
        """Build the health snapshot. See `update_health` for the guarantees."""
        snapshot = self._healthy_snapshot()

        if failed:
            # Cold start flags on the FIRST failure: there are no held values,
            # so waiting out the strike budget leaves the user with a wholly
            # unavailable integration and no explanation. At runtime the strike
            # budget applies, so one blip raises no alarm.
            if cold_start:
                snapshot["severity"] = "error"
                snapshot["issues"] = [
                    "The router has never answered since this integration "
                    "started. Check the host address and credentials."
                ]
            elif self.consecutive_failures >= HEALTH_STRIKE_LIMIT:
                snapshot["severity"] = "error"
                snapshot["issues"] = [
                    f"No successful update in {self.consecutive_failures} "
                    "consecutive attempts; the values shown are the last known "
                    "good ones."
                ]
            return snapshot

        if not data:
            return snapshot

        # 1. Capability degradation — an endpoint `api.get_data` silently
        #    dropped. Strike-budgeted so a one-poll blip is not reported.
        missing = [
            key
            for key in ENDPOINT_NAMES
            if key != CRITICAL_ENDPOINT and key not in data
        ]
        for key in ENDPOINT_NAMES:
            if key in missing:
                self._endpoint_strikes[key] = self._endpoint_strikes.get(key, 0) + 1
            else:
                self._endpoint_strikes.pop(key, None)

        degraded = sorted(
            ENDPOINT_NAMES[key]
            for key, strikes in self._endpoint_strikes.items()
            if strikes >= HEALTH_STRIKE_LIMIT
        )

        # 2. Contract drift — a non-empty response that parses to nothing
        #    meaningful. This is the direct catch for a firmware field rename,
        #    and it is the highest-value check here.
        drift: list[str] = []
        signal = data.get("device_signal")
        if isinstance(signal, dict) and signal:
            if all(signal.get(k) in (None, "") for k in SIGNAL_CONTRACT_KEYS):
                drift.append(
                    "The router returned a signal block containing none of "
                    f"{', '.join(SIGNAL_CONTRACT_KEYS)} — its firmware may have "
                    "renamed these fields."
                )

        issues = [f"{name} is not responding." for name in degraded] + drift
        snapshot["degraded_capabilities"] = degraded
        snapshot["drift"] = drift
        snapshot["issues"] = issues
        snapshot["severity"] = "warning" if issues else None
        return snapshot

    def clear_repairs(self) -> None:
        """Delete every repair issue this entry may have raised.

        Called on unload and on removal. After removal there is no coordinator
        left that could ever clear one, so a repair raised at deletion time
        would sit in the Repairs panel permanently — `auth_failed` is
        `is_fixable=True` and would offer a flow for an integration that no
        longer exists.

        `ir.async_delete_issue` is a no-op for an issue that was never created,
        so this is unconditional rather than tracked.
        """
        for name in REPAIR_NAMES:
            ir.async_delete_issue(self.hass, DOMAIN, f"{name}_{self.entry.entry_id}")

    @callback
    def async_schedule_refresh(self, delay: float) -> None:
        """Schedule one forced refresh `delay` seconds from now.

        For controls that take the router away and bring it back. The reading
        immediately after such a write is stale by definition, so without this
        the entities sit wrong until the next scheduled poll - twenty minutes
        by default.

        **A paused integration still gets the refresh**, and that is the point
        rather than an oversight. Section 13 holds that an explicit user action
        must not be swallowed by the pause, and the follow-up is part of the
        press rather than background polling - with polling paused it is the
        *only* way the user ever sees the result of the button they pushed.
        Every other write path in this integration already forces through the
        pause; this one was the exception until 2026-08-15. `unifi_network_monitor`
        reached the same conclusion first.

        The one case it declines is when a scheduled poll would arrive first
        anyway - which can only happen while polling is running.

        A second press replaces the pending refresh rather than queueing a
        second one.
        """
        paused = bool(self.entry.options.get(CONF_STOP_POLLING, False))
        interval = self.update_interval.total_seconds() if self.update_interval else 0
        if not paused and interval and delay >= interval:
            _LOGGER.debug(
                "%s: Poll interval %ss is shorter than the %ss follow-up; "
                "letting the scheduled poll cover it.",
                self.entry.title,
                interval,
                delay,
            )
            return

        self.async_cancel_scheduled_refresh()

        async def _fire(_now: datetime) -> None:
            self._pending_refresh = None
            await self.async_force_refresh()

        self._pending_refresh = async_call_later(self.hass, delay, _fire)

    @callback
    def async_cancel_scheduled_refresh(self) -> None:
        """Cancel a pending follow-up refresh, if there is one."""
        if self._pending_refresh is not None:
            self._pending_refresh()
            self._pending_refresh = None

    async def async_force_refresh(self) -> None:
        """Force an immediate fetch, even while polling is paused.

        Every explicit user action — Refresh Now, a control change, an SMS
        service — must route through here rather than calling
        ``async_request_refresh`` directly, or it is silently swallowed by the
        pause short-circuit at exactly the moment the user wanted a fetch
        (dev_standards Section 13). Scheduled polls still respect the pause.
        """
        self._force_refresh_once = True
        try:
            await self.async_request_refresh()
        except Exception:
            # The flag is consumed at the top of `_async_update_data`, so an
            # update that never runs would leave it set and the next
            # *scheduled* poll would fetch despite the pause. Self-correcting
            # after one cycle, but Section 13 asks that every path out clears
            # it.
            self._force_refresh_once = False
            raise

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the API with resilience and pause support."""
        # Consume the one-shot force flag before anything can short-circuit.
        forced = self._force_refresh_once
        self._force_refresh_once = False

        is_paused = self.entry.options.get(CONF_STOP_POLLING, False)
        is_first_run = self.data is None

        if is_paused and not is_first_run and not forced:
            _LOGGER.debug(
                "%s: Polling is paused; returning cached data.", self.entry.title
            )
            return self.data

        if forced and is_paused:
            _LOGGER.debug(
                "%s: Explicit user action; fetching despite paused polling.",
                self.entry.title,
            )

        data = None
        try:
            async with asyncio.timeout(FETCH_TIMEOUT):
                try:
                    data = await self.api.get_data()
                except HuaweiAuthError:
                    _LOGGER.debug(
                        "%s: Session expired mid-fetch, retrying once.",
                        self.entry.title,
                    )
                    data = await self.api.get_data()
        except (TimeoutError, HuaweiAuthError) as err:
            self.consecutive_failures += 1
            if self.data is not None and self.consecutive_failures <= 3:
                _LOGGER.warning(
                    "%s: Fetch failed due to %s (failure %d/3), "
                    "holding last known values.",
                    self.entry.title,
                    "session timeout"
                    if isinstance(err, HuaweiAuthError)
                    else "timeout",
                    self.consecutive_failures,
                )
                self.update_health(None, failed=True, cold_start=False)
                return self.data

            if isinstance(err, HuaweiAuthError):
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"{REPAIR_AUTH_FAILED}_{self.entry.entry_id}",
                    is_fixable=True,
                    is_persistent=True,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="auth_failed",
                    translation_placeholders={"entry_title": self.entry.title},
                    data={"entry_id": self.entry.entry_id},
                )
                self.update_health(None, failed=True, cold_start=self.data is None)
                raise ConfigEntryAuthFailed("Authentication failed") from err

            error_msg = "API request timed out"
            _LOGGER.exception("%s: %s", self.entry.title, error_msg)
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{REPAIR_CONN_ERROR}_{self.entry.entry_id}",
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="conn_error",
                translation_placeholders={"entry_title": self.entry.title},
            )
            self.update_health(None, failed=True, cold_start=self.data is None)
            raise UpdateFailed(error_msg) from err

        except Exception as err:
            self.consecutive_failures += 1
            if self.data is not None and self.consecutive_failures <= 3:
                _LOGGER.warning(
                    "%s: Fetch failed (failure %d/3), holding last known values: %s",
                    self.entry.title,
                    self.consecutive_failures,
                    err,
                )
                self.update_health(None, failed=True, cold_start=False)
                return self.data

            if is_paused:
                _LOGGER.warning(
                    "%s: Initial fetch failed while paused. Starting with empty data.",
                    self.entry.title,
                )
                self.update_health(None, failed=True, cold_start=True)
                return {}

            _LOGGER.exception(
                "%s: Connection lost. Marking entities unavailable.", self.entry.title
            )
            self.update_health(None, failed=True, cold_start=self.data is None)
            raise UpdateFailed(f"Communication error: {err}") from err

        # Post-Fetch Processing & Validation (Outside the main try block)
        if not data or "device_information" not in data:
            self.update_health(None, failed=True, cold_start=self.data is None)
            raise UpdateFailed("Critical data missing from fetch (e.g. device_info)")

        dev_info = data.get("device_information") or {}
        new_model = get_router_model(dev_info)
        new_sw = dev_info.get("SoftwareVersion")
        new_hw = dev_info.get("HardwareVersion")

        if (
            new_model != self.model
            or new_sw != self.sw_version
            or new_hw != self.hw_version
        ):
            _LOGGER.info(
                "%s: Hardware metadata updated: %s sw=%s hw=%s",
                self.entry.title,
                new_model,
                new_sw,
                new_hw,
            )
            self.model = new_model
            self.sw_version = new_sw
            self.hw_version = new_hw

            new_entry_data = dict(self.entry.data)
            new_entry_data.update(
                {
                    "model": new_model,
                    "sw_version": new_sw,
                    "hw_version": new_hw,
                }
            )
            self.hass.config_entries.async_update_entry(self.entry, data=new_entry_data)

        if self.consecutive_failures > 0:
            _LOGGER.info(
                "%s: Communication restored after %d failures.",
                self.entry.title,
                self.consecutive_failures,
            )
            ir.async_delete_issue(
                self.hass,
                DOMAIN,
                f"{REPAIR_CONN_ERROR}_{self.entry.entry_id}",
            )

        self.last_update_success_time = dt_util.now()
        self.consecutive_failures = 0

        # Section 19: a success clears the verdict in the SAME cycle — never
        # leave it `on` until some later poll.
        self.update_health(data, failed=False, cold_start=False)

        # SMS Event Logic
        if "sms_list" in data:
            _LOGGER.debug("%s: Raw SMS list: %s", self.entry.title, data["sms_list"])
        self._check_new_sms(data)

        # --- Uptime reboot-detection latches ---
        entry_data_updates: dict[str, Any] = {}
        # 1. System uptime
        sys_sec: int | None = None
        with contextlib.suppress(ValueError, TypeError):
            if (raw := dev_info.get("uptime")) is not None:
                sys_sec = int(float(raw))
        if sys_sec is None or sys_sec < 0:
            data["system_boot_time"] = self._system_boot_time
        else:
            if self._system_boot_time is None or (
                self._last_system_uptime is not None
                and sys_sec < self._last_system_uptime - UPTIME_REBOOT_MARGIN
            ):
                t = dt_util.now() - timedelta(seconds=sys_sec)
                self._system_boot_time = t.replace(microsecond=0)
                entry_data_updates["system_boot_time"] = (
                    self._system_boot_time.isoformat()
                )
                entry_data_updates["last_system_uptime"] = sys_sec
                _LOGGER.debug(
                    "%s: System boot time latched: %s",
                    self.entry.title,
                    self._system_boot_time,
                )
            self._last_system_uptime = sys_sec
            data["system_boot_time"] = self._system_boot_time

        # 2. Current connection time
        traffic = data.get("traffic_statistics") or {}
        conn_sec: int | None = None
        with contextlib.suppress(ValueError, TypeError):
            if (raw := traffic.get("CurrentConnectTime")) is not None:
                conn_sec = int(float(raw))
        if conn_sec is None or conn_sec < 0:
            data["conn_start_time"] = self._conn_start_time
        else:
            if self._conn_start_time is None or (
                self._last_conn_uptime is not None
                and conn_sec < self._last_conn_uptime - UPTIME_REBOOT_MARGIN
            ):
                t = dt_util.now() - timedelta(seconds=conn_sec)
                self._conn_start_time = t.replace(microsecond=0)
                entry_data_updates["conn_start_time"] = (
                    self._conn_start_time.isoformat()
                )
                entry_data_updates["last_conn_uptime"] = conn_sec
                _LOGGER.debug(
                    "%s: Connection start time latched: %s",
                    self.entry.title,
                    self._conn_start_time,
                )
            self._last_conn_uptime = conn_sec
            data["conn_start_time"] = self._conn_start_time

        # 3. Total connection time
        total_sec: int | None = None
        with contextlib.suppress(ValueError, TypeError):
            if (raw := traffic.get("TotalConnectTime")) is not None:
                total_sec = int(float(raw))
        if total_sec is None or total_sec < 0:
            data["total_conn_start_time"] = self._total_conn_start_time
        else:
            if self._total_conn_start_time is None or (
                self._last_total_conn_time is not None
                and total_sec < self._last_total_conn_time - UPTIME_REBOOT_MARGIN
            ):
                t = dt_util.now() - timedelta(seconds=total_sec)
                self._total_conn_start_time = t.replace(microsecond=0)
                entry_data_updates["total_conn_start_time"] = (
                    self._total_conn_start_time.isoformat()
                )
                entry_data_updates["last_total_conn_time"] = total_sec
                _LOGGER.debug(
                    "%s: Total connection start time latched: %s",
                    self.entry.title,
                    self._total_conn_start_time,
                )
            self._last_total_conn_time = total_sec
            data["total_conn_start_time"] = self._total_conn_start_time

        if entry_data_updates:
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, **entry_data_updates}
            )

        return data

    def _check_new_sms(self, data: dict[str, Any]) -> None:
        """Check for new SMS messages and fire events."""
        sms_list = parse_sms_list(data.get("sms_list"))
        if not sms_list:
            return

        # Sort by date ascending (oldest first) to ensure events fire in order
        sms_list.sort(key=lambda x: x["date"])

        # On first run, just set the baseline timestamp and hashes
        if self.last_sms_timestamp is None:
            self.last_sms_timestamp = sms_list[-1]["date"]
            self.fired_sms_hashes = {
                f"{msg['index']}_{msg['date']}"
                for msg in sms_list
                if msg["date"] == self.last_sms_timestamp
            }
            _LOGGER.debug(
                "%s: SMS tracking baseline established at %s",
                self.entry.title,
                self.last_sms_timestamp,
            )
            return

        new_messages = []
        for msg in sms_list:
            msg_hash = f"{msg['index']}_{msg['date']}"
            if msg["date"] > self.last_sms_timestamp or (
                msg["date"] == self.last_sms_timestamp
                and msg_hash not in self.fired_sms_hashes
            ):
                new_messages.append(msg)

        for msg in new_messages:
            _LOGGER.info("%s: New SMS from %s", self.entry.title, msg["phone"])
            self.hass.bus.async_fire(
                "huawei_router_5g_sms_received",
                {
                    "entry_id": self.entry.entry_id,
                    "phone": msg["phone"],
                    "content": msg["content"],
                    "date": msg["date"],
                    "index": msg["index"],
                },
            )

            # Update tracking state
            msg_hash = f"{msg['index']}_{msg['date']}"
            if msg["date"] > self.last_sms_timestamp:
                self.last_sms_timestamp = msg["date"]
                self.fired_sms_hashes = {msg_hash}
            else:
                self.fired_sms_hashes.add(msg_hash)
