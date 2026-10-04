"""DataUpdateCoordinator for Huawei Router 5G."""

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
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
    FETCH_STRIKE_LIMIT,
    FETCH_TIMEOUT,
    HEALTH_DRIFT_STRIKE_LIMIT,
    REPAIR_AUTH_FAILED,
    REPAIR_CONN_ERROR,
    REPAIR_CONN_STRIKE_LIMIT,
    REPAIR_NAMES,
    SIGNAL_CONTRACT_KEYS,
)
from .helpers import get_router_model, parse_sms_list

_LOGGER = logging.getLogger(__name__)

# Minimum drop in a router uptime counter (seconds) treated as a genuine reset.
# A real reboot/reconnect resets the counter to ~0, so this margin only rejects
# small downward blips from counter quantization or stale cached readings.
UPTIME_REBOOT_MARGIN = 30

# ---------------------------------------------------------------------------
# Drift hardening — the hardware counter only
#
# The values and their reasoning are shared across the family and settled in
# `.shared/info/uptime_timestamp/uptime_drift_analyzed.md` §11. They are
# reproduced here rather than imported because each project ships standalone;
# a change belongs in that document first.
#
# **This device does not drift.** Measured 2026-09-08 at 0.00% over eleven
# minutes, against the reference ZTE MC7010's 4.34%. The machinery ships
# regardless: the rate is learned per installation precisely because it is a
# property of the hardware in front of the user, not of the model.
# ---------------------------------------------------------------------------

# Cold-start bound and the clamp on a learned rate. One bound, two uses.
MAX_DRIFT = 0.20
# A host with no battery-backed clock starts in 1970; defer rather than latch
# a boot instant decades adrift.
CLOCK_FLOOR_YEAR = 2024
# A counter beyond this is rejected rather than believed.
MAX_PLAUSIBLE_UPTIME = 10 * 365 * 24 * 3600
# Below this interval the counter's whole-second resolution dominates.
DRIFT_MIN_INTERVAL = 60
# Nothing is claimed about the rate until this much wall time has accumulated.
# Checked **before** the division, which is also what stops a fresh install
# dividing by a zero denominator.
DRIFT_MIN_ACCUMULATED = 3600
# Scale both accumulators down past this, so the estimate can follow a
# firmware fix to the timer rather than being anchored to history.
DRIFT_ACCUMULATOR_CAP = 30 * 24 * 3600
# Shortfall margin: a floor for quantization and poll latency, plus a
# proportional term because the rate-estimate error it absorbs scales with
# the gap.
SHORTFALL_MARGIN_FLOOR = 300
SHORTFALL_MARGIN_RATE = 0.02
# Noise budget for the every-poll backstop. Only independent of the device
# because the anchor is corrected for drift when it is latched.
PLAUSIBILITY_TOLERANCE = 0.05

# Additive fields only, so the version is deliberately not bumped: a missing
# field already means "nothing learned yet", which needs no migration.
UPTIME_STORAGE_VERSION = 1
UPTIME_WRITE_INTERVAL = timedelta(minutes=20)
UPTIME_SAVE_DELAY = 60

# Written by versions before the store existed and restored at construction,
# which is the defect: `entry.data` is written only at a latch, so the counter
# froze and the reset comparison could never fire again. Dropped at the first
# latch and never read.
LEGACY_COUNTER_KEYS = frozenset(
    {"last_system_uptime", "last_conn_uptime", "last_total_conn_time"}
)


@dataclass
class _UptimeLatch:
    """One counter, its anchor, and everything learned about its rate.

    Three of these exist and **nothing is shared between them**. Their
    counters reset on different events — a hardware reboot, a WAN reconnect,
    a statistics clear — so a rate, a stored counter or a reconciliation flag
    borrowed from one would be evidence about a different question.

    `pauses` is the property that decides which mechanism applies:

    - `uptime` and `CurrentConnectTime` advance whenever they exist at all.
      A dropped link ends the session and resets `CurrentConnectTime` rather
      than freezing it, so within one session it tracks wall time exactly —
      measured across a real reconnect, 9 s to 216 s over 207 s of wall. Both
      can therefore be asked "did you continue across that gap at wall rate?"
      and both carry the full mechanism.
    - `TotalConnectTime` accumulates across reboots and **stops whenever the
      session is down**. A real reconnect cost it exactly the 2.3 s the link
      was out, and it has lost 3.8 hours to downtime since April
      (`tests/fixtures/huawei_reconnect_trace.json`). Legitimate downtime
      makes it under-run wall time with nothing wrong, so no rate-based
      expectation can be asked of it. It carries the floor rule alone: it
      moves backwards only on a statistics clear.
    """

    label: str
    boot_key: str
    counter_key: str
    pauses: bool = False

    boot_time: datetime | None = None
    last_counter: int | None = None
    last_poll_at: datetime | None = None
    startup_reconciled: bool = False

    stored_counter: int | None = None
    stored_written_at: datetime | None = None
    last_counter_write: datetime | None = None

    drift_sum_wall: float = 0.0
    drift_sum_counter: float = 0.0
    drift_interval_count: int = 0
    drift_rate_min: float | None = None
    drift_rate_max: float | None = None


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

        # One-shot latch so a persistently failing health computation warns
        # once per session rather than once per poll. Reset on the first
        # success, so a fault that returns is reported again.
        self._health_compute_failed = False

        # Section 19 health state. Deliberately NOT stored in `self.data`,
        # which is None before the first success and frozen at last-good values
        # during an outage — a verdict held there could never describe the
        # failure that stopped it being updated.
        self._endpoint_strikes: dict[str, int] = {}

        # Liveness-probe state. `_fault_is_local` is None until a probe has
        # run, True when a fresh connection succeeded while the pooled one kept
        # failing (our fault), False when both failed (the router's). The latch
        # keeps the probe to once per exhausted strike budget — this router
        # permits one login, so a probe per poll would cause outages rather
        # than diagnose them.
        # `True` the fault is ours, `False` the router is unreachable, and
        # `None` either not yet probed or the router refused a second session —
        # alive, but with nothing to say about which end is at fault.
        self._fault_is_local: bool | None = None
        self._probe_done = False
        # Mode codes the router says it accepts, populated once after login.
        # `None` means not yet known, which is not the same as "none accepted" —
        # the select falls back to its full list rather than showing nothing.
        self.supported_net_modes: list[str] | None = None
        self.health_snapshot: dict[str, Any] = {
            # Cold start: nothing has been fetched, so no verdict is possible.
            # Section 19 forbids `None` here — see `_healthy_snapshot`.
            "severity": "unknown",
            "issues": [],
            "degraded_capabilities": [],
            "drift": [],
            "last_good_update": None,
        }

        # Reboot-detection latches - frozen timestamps for uptime-derived
        # sensors. Each is recomputed exactly once per genuine counter reset
        # and then held.
        #
        # **Nothing is shared between the three.** Their counters reset on
        # different events, so a rate, a stored counter or a reconciliation
        # flag borrowed from one is evidence about a different question.
        self._system_latch = _UptimeLatch(
            label="System boot time",
            boot_key="system_boot_time",
            counter_key="last_system_uptime",
        )
        self._conn_latch = _UptimeLatch(
            label="Connection start time",
            boot_key="conn_start_time",
            counter_key="last_conn_uptime",
        )
        self._total_latch = _UptimeLatch(
            label="Total connection start time",
            boot_key="total_conn_start_time",
            counter_key="last_total_conn_time",
            # The one counter that stops when the session does.
            pauses=True,
        )
        self._latches = (self._system_latch, self._conn_latch, self._total_latch)

        # Populated by `async_load_stored_uptime` during setup.
        self._store: Store[dict[str, Any]] | None = None

        # The anchors are restored from `entry.data`, where they have always
        # lived and where the sensors' own restore path expects them. The
        # **counters** are not: they used to be restored from there too, and
        # that is the defect. `entry.data` is written only when a latch
        # happens, so the stored counter froze at whatever the router read
        # one poll after a boot - 61 s on the instance this was written
        # against - and the reset comparison could never fire again. The
        # counters now come from the store, which is written on an interval.
        for latch in self._latches:
            with contextlib.suppress(Exception):
                if v := entry.data.get(latch.boot_key):
                    parsed = dt_util.parse_datetime(v)
                    # Naive values raise on subtraction from an aware `now()`.
                    # Treated as absent, which routes to an unconditional
                    # latch. Nothing this integration writes is naive; an old
                    # test fixture is where one comes from.
                    if parsed is not None and parsed.tzinfo is not None:
                        latch.boot_time = parsed

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
        """Return a snapshot describing a healthy integration.

        **`severity` is `"ok"`, never `None`.** The other three attributes are
        legitimately empty when healthy and Home Assistant renders an empty list
        as a blank cell, so `None` showed the user "Unknown" beside three blanks
        — indistinguishable from a sensor that never populated. A literal `"ok"`
        beside three blanks is unambiguous. Section 19 makes this normative;
        putting placeholder text into the lists instead would break any
        automation filtering them on `| count > 0`.
        """
        return {
            "severity": "ok",
            "issues": [],
            "degraded_capabilities": [],
            "drift": [],
            "last_good_update": (
                self.last_update_success_time.isoformat()
                if self.last_update_success_time
                else None
            ),
        }

    async def _async_report_unreachable(self) -> None:
        """Diagnose which end is at fault, and raise the repair once it is due.

        **Called from both failure branches, and that is the point.** Until
        2026-08-23 the probe and the `conn_error` repair sat on the
        `TimeoutError` branch alone, so they were unreachable for the most
        ordinary failure this integration has: a router that is powered off or
        has changed address refuses the connection, which arrives as
        `HuaweiConnectionError` and takes the general branch. The repair's own
        text asks the user to check the router is powered on and reachable —
        the one case that could never raise it. `zte_router_5g` keys its
        equivalent on the failure count alone, and this now matches.

        The strike limit is what keeps it quiet: at the default interval it is
        about half an hour of continuous failure, long past the point where the
        user has already seen every entity go unavailable.
        """
        await self._async_diagnose_fault()
        if self.consecutive_failures >= REPAIR_CONN_STRIKE_LIMIT:
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

    async def _async_diagnose_fault(self) -> None:
        """Ask which end is at fault, once per exhausted strike budget.

        Every path to the router was reachable during the 2026-08-17 lockup —
        web GUI, host, container — while the integration reported everything
        unavailable and blamed the router. One cheap call on a **brand-new**
        connection separates the two cases, which is exactly how the fault was
        diagnosed by hand.

        The timing is logged beside the failing path on purpose: "a fresh
        connection answered in 0.04s while the pooled one timed out at 30s" is
        the whole diagnosis in one line, and it was the absence of that line
        that made the original fault take an hour to find.
        """
        if self._probe_done:
            return
        self._probe_done = True

        started = time.monotonic()
        alive = await self.api.probe_liveness()
        elapsed = time.monotonic() - started
        self._fault_is_local = alive

        if alive is None:
            # The router refused a second session. It is answering — it has to
            # be, to refuse — but nothing here can say whether the established
            # path is at fault. Rebuild anyway: a connection we cannot vouch
            # for is worth replacing, and the next poll re-establishes it.
            _LOGGER.warning(
                "%s: the router refused a second session after %.2fs, so which "
                "end is at fault is undetermined. Rebuilding the connection.",
                self.entry.title,
                elapsed,
            )
            await self.api.invalidate()
            return

        if not alive:
            _LOGGER.warning(
                "%s: a fresh connection to the router also failed after %.2fs; "
                "the router is genuinely unreachable.",
                self.entry.title,
                elapsed,
            )
            return

        _LOGGER.warning(
            "%s: a fresh connection answered in %.2fs while the established "
            "session kept failing. The fault is on this side; rebuilding the "
            "connection.",
            self.entry.title,
            elapsed,
        )
        await self.api.invalidate()

    def update_health(
        self, data: dict[str, Any] | None, *, failed: bool, cold_start: bool
    ) -> None:
        """Recompute the Section 19 health verdict.

        Held as a coordinator attribute rather than inside `self.data`, which is
        `None` before the first success and **frozen at the last good values**
        during an outage — a verdict living there could never describe the
        failure that stopped it being updated.

        Wrapped so a malformed payload can never crash the update it is
        diagnosing. **The wrapper stays; where the failure goes changed.**

        It previously logged at DEBUG and then set a *healthy* snapshot — so a
        verdict that had stopped working reported "no problems" for ever, at a
        level nobody runs. This sensor exists to explain an outage; the one
        state it must never report cleanly is its own failure. Found by
        `masked_errors_check` on 2026-08-16 as a Class A finding.

        The first failure per session warns; the rest are debug, because a
        broken computation is broken on every poll and one warning per poll is
        how a warning stops being read. The snapshot now carries the failure
        rather than hiding it.
        """
        try:
            self.health_snapshot = self._compute_health(
                data, failed=failed, cold_start=cold_start
            )
            self._health_compute_failed = False
        except Exception:
            if not self._health_compute_failed:
                self._health_compute_failed = True
                _LOGGER.warning(
                    "%s: Health computation failed; the Integration Health "
                    "verdict is unavailable until this is fixed.",
                    self.entry.title,
                    exc_info=True,
                )
            else:
                _LOGGER.debug(
                    "%s: Health computation still failing.",
                    self.entry.title,
                    exc_info=True,
                )
            snapshot = self._healthy_snapshot()
            # `error`, not `warning`: Section 19 defines `error` as a total
            # outage *or* a verdict that cannot be computed, and this sensor
            # failing to assess itself is the second of those.
            snapshot["severity"] = "error"
            snapshot["issues"] = ["health_verdict_unavailable"]
            self.health_snapshot = snapshot

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
            elif self.consecutive_failures >= FETCH_STRIKE_LIMIT:
                snapshot["severity"] = "error"
                snapshot["issues"] = [
                    f"No successful update in {self.consecutive_failures} "
                    "consecutive attempts; the values shown are the last known "
                    "good ones."
                ]

            # Name which end is at fault when the probe has an answer. Without
            # this the sensor says "no successful update" for both a wedged
            # session and a router that is switched off, which is the one
            # distinction a user needs to act on.
            if self._fault_is_local is True:
                snapshot["issues"].append(
                    "The router answered a fresh connection while this "
                    "integration's own session did not; the connection has "
                    "been rebuilt."
                )
            elif self._fault_is_local is False:
                snapshot["issues"].append(
                    "A fresh connection to the router also failed; the router "
                    "is not reachable from Home Assistant."
                )
            elif self._probe_done:
                # Probed, and the router refused a second session. Reported
                # rather than dropped: "it refused us" is a different fact from
                # "we never asked", and only the latch tells them apart.
                snapshot["issues"].append(
                    "The router refused a second connection, so which end is "
                    "at fault could not be determined."
                )
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
            if strikes >= HEALTH_DRIFT_STRIKE_LIMIT
        )

        # 2. Missing router data — a non-empty response that parses to nothing
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
        # Section 19's five-value enum, and the two middle values are not
        # interchangeable: `degraded` means a capability was lost while the core
        # still works, `warning` means the data that did arrive may be wrong.
        # Drift outranks degradation — doubting a reading is worse than knowing
        # one is missing.
        if drift:
            snapshot["severity"] = "warning"
        elif degraded:
            snapshot["severity"] = "degraded"
        else:
            snapshot["severity"] = "ok"
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

            if isinstance(err, TimeoutError):
                # `asyncio.timeout` cancels the await from out here, so none of
                # `api.py`'s own `except` blocks run and its client is never
                # reset. Without this the next poll reuses the same wedged
                # connection, for ever — the reason a single deadlock survived
                # until Home Assistant was restarted.
                await self.api.invalidate()
            # `<=` against the same constant `_compute_health` uses `>=` on,
            # so the two sit one poll apart on purpose: health reports `error`
            # on the third failure, entities go unavailable on the fourth.
            if (
                self.data is not None
                and self.consecutive_failures <= FETCH_STRIKE_LIMIT
            ):
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

            await self._async_report_unreachable()

            error_msg = "API request timed out"
            _LOGGER.exception("%s: %s", self.entry.title, error_msg)
            self.update_health(None, failed=True, cold_start=self.data is None)
            raise UpdateFailed(error_msg) from err

        except Exception as err:
            self.consecutive_failures += 1
            # `<=` against the same constant `_compute_health` uses `>=` on,
            # so the two sit one poll apart on purpose: health reports `error`
            # on the third failure, entities go unavailable on the fourth.
            if (
                self.data is not None
                and self.consecutive_failures <= FETCH_STRIKE_LIMIT
            ):
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

            await self._async_report_unreachable()

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
            # Re-arm the probe. A fault that returns must be diagnosed again.
            self._probe_done = False
            self._fault_is_local = None

        self.last_update_success_time = dt_util.now()
        self.consecutive_failures = 0

        # Section 19: a success clears the verdict in the SAME cycle — never
        # leave it `on` until some later poll.
        self.update_health(data, failed=False, cold_start=False)

        # SMS Event Logic
        if "sms_list" in data:
            self._log_sms_shape(data["sms_list"])
        self._check_new_sms(data)

        # --- Uptime reboot-detection latches ---
        #
        # Three counters, three reset events, three independent latches. The
        # routing is identical for all three; what differs is whether the
        # counter can be treated as a clock, which `_UptimeLatch.pauses`
        # records and the mechanism below acts on.
        entry_data_updates: dict[str, Any] = {}
        traffic = data.get("traffic_statistics") or {}

        for latch, raw in (
            (self._system_latch, dev_info.get("uptime")),
            (self._conn_latch, traffic.get("CurrentConnectTime")),
            (self._total_latch, traffic.get("TotalConnectTime")),
        ):
            self._apply_uptime(latch, raw, entry_data_updates)
            data[latch.boot_key] = latch.boot_time

        if entry_data_updates:
            # The legacy counter keys are dropped here. They are no longer
            # read - the counters come from the store, which is written on an
            # interval rather than only at a latch - and leaving them invites
            # a future reader to wire the frozen copy back in.
            kept = {
                key: value
                for key, value in self.entry.data.items()
                if key not in LEGACY_COUNTER_KEYS
            }
            self.hass.config_entries.async_update_entry(
                self.entry, data={**kept, **entry_data_updates}
            )

        return data

    # ------------------------------------------------------------------
    # State views
    #
    # The six attribute names below predate the latch objects and are read
    # across the platforms, the diagnostic scripts and the test suite. They
    # stay as views rather than as a second copy: the latch holds the state,
    # and these say where to find it.
    # ------------------------------------------------------------------

    @property
    def _system_boot_time(self) -> datetime | None:
        """The anchor for the hardware uptime counter."""
        return self._system_latch.boot_time

    @_system_boot_time.setter
    def _system_boot_time(self, value: datetime | None) -> None:
        self._system_latch.boot_time = value

    @property
    def _last_system_uptime(self) -> int | None:
        """The last hardware counter reading this coordinator saw."""
        return self._system_latch.last_counter

    @_last_system_uptime.setter
    def _last_system_uptime(self, value: int | None) -> None:
        self._system_latch.last_counter = value

    @property
    def _conn_start_time(self) -> datetime | None:
        """The anchor for the current session's counter."""
        return self._conn_latch.boot_time

    @_conn_start_time.setter
    def _conn_start_time(self, value: datetime | None) -> None:
        self._conn_latch.boot_time = value

    @property
    def _last_conn_uptime(self) -> int | None:
        """The last current-session counter reading this coordinator saw."""
        return self._conn_latch.last_counter

    @_last_conn_uptime.setter
    def _last_conn_uptime(self, value: int | None) -> None:
        self._conn_latch.last_counter = value

    @property
    def _total_conn_start_time(self) -> datetime | None:
        """The anchor for the cumulative connected-time counter."""
        return self._total_latch.boot_time

    @_total_conn_start_time.setter
    def _total_conn_start_time(self, value: datetime | None) -> None:
        self._total_latch.boot_time = value

    @property
    def _last_total_conn_time(self) -> int | None:
        """The last cumulative counter reading this coordinator saw."""
        return self._total_latch.last_counter

    @_last_total_conn_time.setter
    def _last_total_conn_time(self, value: int | None) -> None:
        self._total_latch.last_counter = value

    # ------------------------------------------------------------------
    # Boot-time latches
    #
    # A counter is a good reset detector and a poor clock. Comparing a
    # counter with its own previous value needs no clock at all and cannot
    # drift; deriving a timestamp as `now - counter` inherits the divergence
    # between the router's oscillator and the host's. The anchor is therefore
    # latched once and held, and re-derived only when something says it must
    # be.
    #
    # Four paths, in the order they are evaluated:
    #
    #   1. Guards         - a reading or a clock that cannot be trusted.
    #   2. Counter drop   - conclusive, vetoed by nothing.
    #   3. Startup        - did the counter continue across a gap Home
    #                       Assistant did not observe?
    #   4. Plausibility   - is the anchor still credible? Every poll.
    #
    # The design, the drift measurement behind the constants and the nine
    # decisions are in
    # `.shared/info/uptime_timestamp/uptime_drift_analyzed.md`.
    # ------------------------------------------------------------------

    def _drift_rate(self, latch: _UptimeLatch) -> float | None:
        """Return the fraction of wall time this counter loses, once trustworthy.

        `None` until enough has accumulated. The minimum is checked **before**
        the division, which is also what stops a fresh install dividing by a
        zero denominator.
        """
        if latch.pauses or latch.drift_sum_wall < DRIFT_MIN_ACCUMULATED:
            return None
        rate = 1.0 - (latch.drift_sum_counter / latch.drift_sum_wall)
        # Clamped at both ends for opposite reasons. An unbounded high rate
        # lowers the expected counter until a real shortfall stops
        # registering, suppressing detection; an unbounded low one raises it
        # and produces false alarms.
        return max(-MAX_DRIFT, min(MAX_DRIFT, rate))

    def _record_drift_sample(
        self, latch: _UptimeLatch, seconds: int, now: datetime
    ) -> None:
        """Fold one poll-to-poll interval into this latch's accumulators.

        Duration-weighted, so an interval spanning a long pause carries
        proportionally more evidence than one spanning three minutes. The
        measurement makes no reference to the anchor - the anchor is what the
        rate is used to judge, and deriving one from the other would be
        circular.
        """
        if latch.pauses or latch.last_counter is None or latch.last_poll_at is None:
            return
        wall = (now - latch.last_poll_at).total_seconds()
        advance = seconds - latch.last_counter
        if wall < DRIFT_MIN_INTERVAL or advance <= 0:
            # Too short for the counter's whole-second resolution, or a
            # reset. Neither says anything about the rate.
            return

        latch.drift_sum_wall += wall
        latch.drift_sum_counter += advance
        sample = 1.0 - (advance / wall)
        latch.drift_rate_min = (
            sample
            if latch.drift_rate_min is None
            else min(latch.drift_rate_min, sample)
        )
        latch.drift_rate_max = (
            sample
            if latch.drift_rate_max is None
            else max(latch.drift_rate_max, sample)
        )
        latch.drift_interval_count += 1

        if latch.drift_sum_wall > DRIFT_ACCUMULATOR_CAP:
            # Scale both down together: the ratio survives, but newer
            # evidence can move it, so a firmware fix to the timer is
            # followed rather than averaged away against history.
            scale = DRIFT_ACCUMULATOR_CAP / latch.drift_sum_wall
            latch.drift_sum_wall *= scale
            latch.drift_sum_counter *= scale

    def _derived_boot(
        self, latch: _UptimeLatch, seconds: int, now: datetime
    ) -> datetime:
        """Return the instant this counter started, corrected for its drift.

        `now - counter` is late by exactly the drift the counter has
        accumulated. Dividing by `(1 - rate)` recovers the wall time the
        counter represents. It matters twice: a latch taken long after the
        event is accurate, and the plausibility check can use a tight
        tolerance - without the correction a fresh anchor sits a full `rate`
        from the ratio that check predicts, so any device drifting past the
        tolerance would re-latch on every poll.

        Falls back to the uncorrected instant before a rate is known, where
        the error is bounded by the short accumulation that implies.
        """
        rate = self._drift_rate(latch)
        elapsed = seconds if rate is None else seconds / (1.0 - rate)
        return now - timedelta(seconds=elapsed)

    def _apply_uptime(
        self,
        latch: _UptimeLatch,
        raw: Any,
        entry_data_updates: dict[str, Any],
    ) -> None:
        """Route one counter reading through its latch."""
        seconds: int | None = None
        with contextlib.suppress(ValueError, TypeError):
            if raw is not None:
                seconds = int(float(raw))

        if seconds is None or seconds < 0:
            # Bad-reading guard: missing, unparsable or negative changes
            # nothing at all. Advancing the last-seen counter to a rejected
            # reading would move the reset comparison to a value the router
            # never reported.
            return

        now = dt_util.now()
        if now.year < CLOCK_FLOOR_YEAR:
            # The host has no battery-backed clock and NTP has not completed.
            # Defer rather than latch an instant decades adrift.
            _LOGGER.debug(
                "%s: system clock reads %s; deferring %s reconciliation",
                self.entry.title,
                now.isoformat(),
                latch.label,
            )
            return
        if seconds > MAX_PLAUSIBLE_UPTIME:
            _LOGGER.warning(
                "%s: implausible %s counter %s s; keeping the stored anchor",
                self.entry.title,
                latch.label,
                seconds,
            )
            return

        self._record_drift_sample(latch, seconds, now)

        if latch.startup_reconciled:
            self._apply_runtime_uptime(latch, seconds, now, entry_data_updates)
        else:
            self._reconcile_startup_uptime(latch, seconds, now, entry_data_updates)

        self._check_anchor_plausible(latch, seconds, now, entry_data_updates)

        latch.last_counter = seconds
        latch.last_poll_at = now
        self._maybe_persist_counter(latch, seconds, now)

    def _apply_runtime_uptime(
        self,
        latch: _UptimeLatch,
        seconds: int,
        now: datetime,
        entry_data_updates: dict[str, Any],
    ) -> None:
        """Compare the counter against itself during an unbroken session.

        Exact, and the reason the anchor is stable: no clock enters the
        comparison, so no drift can reach the timestamp. A drop beyond the
        margin is a reset, and nothing vetoes it.
        """
        if latch.last_counter is None:
            return
        if seconds < latch.last_counter - UPTIME_REBOOT_MARGIN:
            self._latch_boot_time(
                latch,
                self._derived_boot(latch, seconds, now),
                seconds,
                now,
                entry_data_updates,
            )
        elif seconds < latch.last_counter:
            # Inside the margin, so not a reset. Logged rather than absorbed
            # in silence: nothing has established that these counters never
            # step backwards, and the margin would otherwise hide the
            # evidence that they do.
            _LOGGER.info(
                "%s: %s counter stepped back %s s (%s to %s), within the %s s "
                "margin and not treated as a reset",
                self.entry.title,
                latch.label,
                latch.last_counter - seconds,
                latch.last_counter,
                seconds,
                UPTIME_REBOOT_MARGIN,
            )

    def _reconcile_startup_uptime(
        self,
        latch: _UptimeLatch,
        seconds: int,
        now: datetime,
        entry_data_updates: dict[str, Any],
    ) -> None:
        """Decide, on the first usable poll, whether a gap contained a reset.

        This is the boundary the running comparison cannot see. The stored
        counter is what makes it answerable, and the defect this mechanism
        replaces was that the stored counter was written **only at a latch**:
        one instance held 61 s against a live 213,412 s, frozen for nineteen
        days, so the comparison could never fire again.
        """
        if latch.stored_counter is not None:
            if latch.pauses or latch.stored_written_at is None:
                self._floor_test(latch, seconds, now, entry_data_updates)
            else:
                self._shortfall_test(
                    latch,
                    seconds,
                    now,
                    latch.stored_counter,
                    latch.stored_written_at,
                    entry_data_updates,
                )
            self._finish_startup(latch)
            return

        # Nothing stored: a fresh install, or the first start after this
        # upgrade. The only evidence is the anchor against the counter,
        # judged with the wide universal bound.
        if latch.boot_time is None or self._cold_start_implausible(latch, seconds, now):
            self._log_reconciliation(latch, "cold start, re-latching", seconds, now)
            self._latch_boot_time(
                latch,
                self._derived_boot(latch, seconds, now),
                seconds,
                now,
                entry_data_updates,
            )
        else:
            self._log_reconciliation(latch, "cold start, anchor retained", seconds, now)
        self._finish_startup(latch)

    def _floor_test(
        self,
        latch: _UptimeLatch,
        seconds: int,
        now: datetime,
        entry_data_updates: dict[str, Any],
    ) -> None:
        """Ask whether a counter that may legitimately pause moved backwards.

        The only question available for `TotalConnectTime`. It stops whenever
        the session is down, so under-running wall time across a gap says
        nothing - a week offline and a week disconnected look identical. It
        moves backwards for exactly one reason, a statistics clear, and that
        is what this detects.
        """
        stored = latch.stored_counter
        if stored is not None and seconds < stored:
            self._log_reconciliation(
                latch,
                f"counter reset during the gap (stored {stored} s)",
                seconds,
                now,
            )
            self._latch_boot_time(
                latch,
                self._derived_boot(latch, seconds, now),
                seconds,
                now,
                entry_data_updates,
            )
        else:
            self._log_reconciliation(
                latch,
                f"counter continued (stored {stored} s)",
                seconds,
                now,
            )

    def _shortfall_test(
        self,
        latch: _UptimeLatch,
        seconds: int,
        now: datetime,
        stored_counter: int,
        written_at: datetime,
        entry_data_updates: dict[str, Any],
    ) -> None:
        """Ask whether the counter continued across the gap as this device does.

        The stored pair is passed in rather than read from the latch: the
        caller has already established both are present, and passing them
        says so.
        """
        elapsed = (dt_util.as_utc(now) - written_at).total_seconds()
        if elapsed < 0:
            # The stored write is dated after now. Nothing useful can be said
            # about the gap, so fall back to the anchor comparison.
            _LOGGER.warning(
                "%s: stored %s write is dated ahead of now; using the "
                "cold-start comparison instead",
                self.entry.title,
                latch.label,
            )
            if latch.boot_time is None or self._cold_start_implausible(
                latch, seconds, now
            ):
                self._latch_boot_time(
                    latch,
                    self._derived_boot(latch, seconds, now),
                    seconds,
                    now,
                    entry_data_updates,
                )
            return

        rate = self._drift_rate(latch) or 0.0
        expected = stored_counter + elapsed * (1.0 - rate)
        # The margin scales because the error it absorbs scales: the dominant
        # term is rate-estimate error multiplied by the gap. The floor covers
        # quantization and poll latency on short gaps.
        margin = max(SHORTFALL_MARGIN_FLOOR, elapsed * SHORTFALL_MARGIN_RATE)

        if seconds < expected - margin:
            self._log_reconciliation(
                latch,
                f"reset during the gap (expected {expected:.0f} s, "
                f"margin {margin:.0f} s)",
                seconds,
                now,
            )
            self._latch_boot_time(
                latch,
                self._derived_boot(latch, seconds, now),
                seconds,
                now,
                entry_data_updates,
            )
        else:
            self._log_reconciliation(
                latch,
                f"counter continued (expected {expected:.0f} s, margin {margin:.0f} s)",
                seconds,
                now,
            )

    def _cold_start_implausible(
        self, latch: _UptimeLatch, seconds: int, now: datetime
    ) -> bool:
        """Judge the anchor with the universal bound, nothing having been learned.

        Two-sided for a counter that tracks wall time. The low side catches
        an anchor that is too early, which is the observed failure; the high
        side catches one that is too late, and exists because no counter has
        been measured running fast.

        **One-sided for a counter that pauses.** Downtime makes the ratio
        arbitrarily small with nothing wrong, so only the high side means
        anything: a counter cannot have run for longer than the anchor says
        has elapsed.
        """
        if latch.boot_time is None:
            return True
        elapsed = (
            dt_util.as_utc(now) - dt_util.as_utc(latch.boot_time)
        ).total_seconds()
        if elapsed <= 0:
            return True
        ratio = seconds / elapsed
        if latch.pauses:
            return ratio > (1.0 + MAX_DRIFT)
        return ratio < (1.0 - MAX_DRIFT) or ratio > (1.0 + MAX_DRIFT)

    def _check_anchor_plausible(
        self,
        latch: _UptimeLatch,
        seconds: int,
        now: datetime,
        entry_data_updates: dict[str, Any],
    ) -> None:
        """Backstop: is the anchor still credible against the counter?

        The startup tests run once and the runtime comparison only sees drops
        as they happen. Neither watches for an anchor that has *become*
        wrong, and retaining a stale anchor indefinitely is the failure this
        design exists to prevent.

        Compared against the counter's own measured rate rather than a
        universal constant, so no guess decides whether an unseen device
        works. A pausing counter has no rate and is not checked here at all:
        its ratio falls legitimately with every outage.
        """
        rate = self._drift_rate(latch)
        if rate is None or latch.boot_time is None:
            return
        elapsed = (
            dt_util.as_utc(now) - dt_util.as_utc(latch.boot_time)
        ).total_seconds()
        if elapsed <= 0:
            return
        if abs(seconds / elapsed - (1.0 - rate)) <= PLAUSIBILITY_TOLERANCE:
            return

        candidate = self._derived_boot(latch, seconds, now)
        if candidate <= latch.boot_time:
            # A reset moves the start instant forward: the anchor can only be
            # ahead of the true start by drift accumulated within the epoch
            # that produced it, and a few percent of an interval cannot
            # exceed the interval. A backward move is therefore not a reset.
            _LOGGER.warning(
                "%s: %s anchor implausible against the counter but the "
                "candidate instant is earlier (%s vs %s); not treating as a reset",
                self.entry.title,
                latch.label,
                candidate.isoformat(),
                latch.boot_time.isoformat(),
            )
            return

        self._log_reconciliation(
            latch, "anchor implausible against the counter", seconds, now
        )
        self._latch_boot_time(latch, candidate, seconds, now, entry_data_updates)

    def _finish_startup(self, latch: _UptimeLatch) -> None:
        """Mark this latch's startup reconciliation complete."""
        latch.startup_reconciled = True

    def _log_reconciliation(
        self, latch: _UptimeLatch, outcome: str, seconds: int, now: datetime
    ) -> None:
        """Record every input to a latch decision, and the decision.

        The absence of this is a substantial part of why the equivalent fault
        took five days of forensics on the sibling project rather than
        showing on the first restart.
        """
        rate = self._drift_rate(latch)
        _LOGGER.info(
            "%s: %s reconciliation - %s (live %s s, stored counter %s, "
            "written at %s, rate %s, stored anchor %s, derived anchor %s)",
            self.entry.title,
            latch.label,
            outcome,
            seconds,
            latch.stored_counter,
            latch.stored_written_at.isoformat() if latch.stored_written_at else None,
            f"{rate * 100:.2f}%" if rate is not None else "not yet measured",
            latch.boot_time.isoformat() if latch.boot_time is not None else None,
            self._derived_boot(latch, seconds, now).replace(microsecond=0).isoformat(),
        )

    def _latch_boot_time(
        self,
        latch: _UptimeLatch,
        boot_time: datetime,
        seconds: int,
        now: datetime,
        entry_data_updates: dict[str, Any],
    ) -> None:
        """Re-anchor this latch and persist it immediately."""
        previous = latch.boot_time
        latch.boot_time = boot_time.replace(microsecond=0)
        _LOGGER.info(
            "%s: %s latched: %s",
            self.entry.title,
            latch.label,
            latch.boot_time.isoformat(),
        )
        if previous is not None and latch.last_counter is not None:
            dropped = seconds < latch.last_counter - UPTIME_REBOOT_MARGIN
            if not dropped:
                # The signature of this entire bug class. A timestamp that
                # moves without the counter having dropped is either a
                # genuine gap reset or a defect, and the two are worth
                # telling apart from the log alone.
                _LOGGER.warning(
                    "%s: %s moved from %s to %s without a counter drop "
                    "(live %s s, previous %s s)",
                    self.entry.title,
                    latch.label,
                    previous.isoformat(),
                    latch.boot_time.isoformat(),
                    seconds,
                    latch.last_counter,
                )
        entry_data_updates[latch.boot_key] = latch.boot_time.isoformat()
        self._write_counter(latch, seconds, now)

    def _maybe_persist_counter(
        self, latch: _UptimeLatch, seconds: int, now: datetime
    ) -> None:
        """Flush the counter and accumulators on a fixed interval.

        **This is the half of the fix that addresses the observed defect.**
        The counter used to reach disk only when a latch happened, so the
        stored value froze at whatever the counter read one poll after a
        boot - 61 s on the instance this was written against - and the
        restart comparison could never fire again. Writing on an interval
        bounds how stale the stored value can be, for every stop condition
        rather than only an orderly one.

        A clean shutdown needs no hook: `async_delay_save` registers a
        final-write listener that flushes a pending save when Home Assistant
        stops.
        """
        if (
            latch.last_counter_write is not None
            and now - latch.last_counter_write < UPTIME_WRITE_INTERVAL
        ):
            return
        self._write_counter(latch, seconds, now)

    def _write_counter(self, latch: _UptimeLatch, seconds: int, now: datetime) -> None:
        """Schedule a debounced write of every latch's counter and accumulators."""
        latch.stored_counter = seconds
        latch.stored_written_at = dt_util.as_utc(now)
        latch.last_counter_write = now
        if self._store is None:
            return
        record = self._store_record()
        self._store.async_delay_save(lambda: record, UPTIME_SAVE_DELAY)

    def _store_record(self) -> dict[str, Any]:
        """Return the persisted form of all three latches.

        One record rather than three files: the three are written on the same
        poll and read on the same setup, and a single debounced save is the
        cadence the write interval already assumes. The fields inside each
        block match the sibling projects, so one reader serves all of them.
        """
        record: dict[str, Any] = {}
        for latch in self._latches:
            block: dict[str, Any] = {
                "last_uptime": latch.stored_counter,
                "written_at": (
                    latch.stored_written_at.isoformat()
                    if latch.stored_written_at is not None
                    else None
                ),
                "sum_wall": round(latch.drift_sum_wall, 3),
                "sum_counter": round(latch.drift_sum_counter, 3),
                "interval_count": latch.drift_interval_count,
            }
            if latch.drift_rate_min is not None:
                block["rate_min"] = round(latch.drift_rate_min, 6)
            if latch.drift_rate_max is not None:
                block["rate_max"] = round(latch.drift_rate_max, 6)
            record[latch.counter_key] = block
        return record

    async def async_load_stored_uptime(self) -> None:
        """Load the persisted counters and accumulators. Never raises.

        Awaited in `async_setup_entry` so the record is in memory before the
        background initialization task runs the first poll. An absent,
        corrupt or unreadable record resolves to "nothing learned", which
        routes to the cold-start path - the store is a cross-check, never the
        anchor.
        """
        self._store = Store(
            self.hass,
            UPTIME_STORAGE_VERSION,
            f"{DOMAIN}_{self.entry.entry_id}_uptime",
        )
        stored: dict[str, Any] | None = None
        try:
            stored = await self._store.async_load()
        except Exception as err:  # noqa: BLE001 - see below
            # Deliberately broad. The contract is that **no** storage fault
            # can fail entry setup: the store is a cross-check and the
            # cold-start path works without it. Narrowing this to the
            # exceptions seen so far would let an unanticipated one abort a
            # setup with no need of the store at all.
            _LOGGER.debug(
                "%s: uptime store unreadable, continuing without it: %s",
                self.entry.title,
                err,
            )
            return
        if not isinstance(stored, dict):
            return
        for latch in self._latches:
            block = stored.get(latch.counter_key)
            if isinstance(block, dict):
                self._restore_latch(latch, block)

    def _restore_latch(self, latch: _UptimeLatch, block: dict[str, Any]) -> None:
        """Read one latch's block back, treating anything unusable as absent."""
        with contextlib.suppress(ValueError, TypeError):
            raw = block.get("last_uptime")
            if raw is not None:
                latch.stored_counter = int(raw)
        with contextlib.suppress(ValueError, TypeError):
            latch.drift_sum_wall = float(block.get("sum_wall", 0.0))
            latch.drift_sum_counter = float(block.get("sum_counter", 0.0))
            latch.drift_interval_count = int(block.get("interval_count", 0))
        for key, attr in (
            ("rate_min", "drift_rate_min"),
            ("rate_max", "drift_rate_max"),
        ):
            with contextlib.suppress(ValueError, TypeError):
                raw = block.get(key)
                if raw is not None:
                    setattr(latch, attr, float(raw))

        # `written_at` carries the same naive-versus-aware hazard as the
        # anchor: both are read back as strings and both are subtracted from
        # `now()`. A value that will not parse, or parses naive, is treated
        # as absent - which means the record cannot date the gap, and the
        # floor comparison applies instead.
        raw_written = block.get("written_at")
        if raw_written:
            with contextlib.suppress(Exception):
                parsed = dt_util.parse_datetime(raw_written)
                if parsed is not None and parsed.tzinfo is not None:
                    latch.stored_written_at = dt_util.as_utc(parsed)

    @property
    def uptime_diagnostics(self) -> dict[str, Any]:
        """Return the drift picture, for the health sensor and diagnostics.

        Published because every constant in the latch was set from one device
        over one week on a sibling project. Without this a field report
        carries no rate, and the only route to one is a recorder extraction.

        Reports the hardware counter alone. The connection counters keep
        their own accumulators, and neither is a property of the host clock,
        so listing all three here would invite exactly the comparison that is
        not meaningful.
        """
        latch = self._system_latch
        rate = self._drift_rate(latch)
        return {
            "drift_rate_pct": round(rate * 100, 3) if rate is not None else None,
            "drift_rate_min_pct": (
                round(latch.drift_rate_min * 100, 3)
                if latch.drift_rate_min is not None
                else None
            ),
            "drift_rate_max_pct": (
                round(latch.drift_rate_max * 100, 3)
                if latch.drift_rate_max is not None
                else None
            ),
            "drift_intervals": latch.drift_interval_count,
            "drift_measured_seconds": round(latch.drift_sum_wall),
            "drift_deficit_seconds": round(
                latch.drift_sum_wall - latch.drift_sum_counter
            ),
        }

    @property
    def uptime_state(self) -> dict[str, Any]:
        """Return every latch's full state, for the diagnostics download.

        Wider than `uptime_diagnostics`, which is the rate summary the health
        sensor publishes. Carries no device data and nothing to redact:
        counters, rates and timestamps.
        """
        return {
            **self.uptime_diagnostics,
            "latches": {
                latch.counter_key: {
                    "anchor": (
                        latch.boot_time.isoformat()
                        if latch.boot_time is not None
                        else None
                    ),
                    "live_counter": latch.last_counter,
                    "stored_counter": latch.stored_counter,
                    "stored_written_at": (
                        latch.stored_written_at.isoformat()
                        if latch.stored_written_at is not None
                        else None
                    ),
                    "startup_reconciled": latch.startup_reconciled,
                    "pauses": latch.pauses,
                    "drift_rate_pct": self._latch_rate_pct(latch),
                }
                for latch in self._latches
            },
        }

    def _latch_rate_pct(self, latch: _UptimeLatch) -> float | None:
        """Return one latch's measured rate as a percentage, or `None`."""
        rate = self._drift_rate(latch)
        return round(rate * 100, 3) if rate is not None else None

    def _log_sms_shape(self, block: Any) -> None:
        """Log the SMS payload's shape, never its contents.

        **This used to log `data["sms_list"]` verbatim.** That block carries
        `Phone` and `Content` for every message, so a debug log held the
        sender's number and the full text of every SMS — the same two fields
        `diagnostics.py` deliberately pseudonymizes. A log file has no
        redaction layer at all and is the thing users are asked to paste into
        an issue report.

        The line exists to diagnose payload-shape variance, which `parse_sms_list`
        has to tolerate. Keys and a count answer that; values never did.
        Same pattern as `api.set_guest_wifi`, which logs `payload keys` only.
        """
        messages = (block or {}).get("Messages") or {}
        entries = messages.get("Message") or []
        if isinstance(entries, dict):
            entries = [entries]
        _LOGGER.debug(
            "%s: SMS list: %d message(s); fields: %s",
            self.entry.title,
            len(entries),
            sorted(entries[0]) if entries else [],
        )

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
            # **No sender number.** This is `info`, so it reaches every log on
            # a default install with no debug enabled - the only personal datum
            # that did. The bus event below carries `phone` and `content` for
            # anything that needs them, which is where the README's own
            # automation example reads them from.
            _LOGGER.info("%s: New SMS received", self.entry.title)
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
