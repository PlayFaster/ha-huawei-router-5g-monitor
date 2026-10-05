"""Produce a real diagnostics download against the router, and check it.

Not part of CI, and not a unit test. It exists because the unit suite asserts
on what the API client *holds*, while the user receives what `diagnostics.py`
*publishes*, and a capture can be correct on one side of that seam and absent
from the other.

`zte_router_5g` paid for that lesson twice. `canary` was added to its API in
`[3.3.9-dev5]`, asserted by five green unit tests, and absent from every
download that release produced; it was found by a human reading three files by
hand two releases later. This project's seam is narrower — `diagnostics.py`
builds its document as a dict literal rather than copying through an allow-list,
so a field cannot silently fall out of a list — but "narrower" is not "absent",
and nothing before this script had ever compared a produced Huawei download
against what the code intends to publish.

Three jobs, mirroring `zte_router_5g/scripts/diag_check.py`:

  1. Build a real coordinator against the real router and call the real
     `async_get_config_entry_diagnostics`, producing the artefact rather than a
     model of it.
  2. Assert over the produced file: the required keys are present, the captures
     are internally consistent with the coordinator state beside them, and no
     unredacted identifier survives.
  3. Run the whole thing **twice** and diff the two. Radio measurements and
     counters drift between runs and are ignored; a structural difference is a
     failure.

`--sabotage` adds a fourth: invalidate the session partway through the poll, so
`_record_verdict` classifies a real expiry from real firmware and the resulting
`last_rejection` is checked in the produced file. The three expiry codes this
integration keys on — `125002`, `125003`, `100003` — are hardcoded on the
strength of documentation rather than measurement, and this is the only thing in
the project that puts them against the hardware.

Three more modes, added in 1.2.3-dev16 to check the refusal-or-expiry decision
of `api.py` against real firmware (dev16 plan I2):

  `--mid-poll`         log the session out after `monitoring.status` has answered,
                       so the later endpoints meet a dead session; the poll must
                       recover by one retry, as the coordinator's does, and end
                       with every endpoint answered that the clean pass answered.
  `--refusal`          make one endpoint raise a 100003 (the library method is
                       patched, so the **refusal is simulated and the router's own
                       is not observed**) on a live session; the premise check and
                       the re-read are real. The endpoint must be recorded
                       `refused`, the premise `refused 100003`, the rest answered.
  `--refusal-expired`  the same simulated refusal with the session logged out as
                       well, so the re-read is refused too and the poll must raise
                       `HuaweiAuthError` before the coordinator's retry recovers.

`--entry` names the configured entry to test (its entry id, part of its title, or
part of its host), because the script otherwise takes the first `huawei_router_5g` entry.
The redaction secrets come from the same entry. The script counts the logins it
makes and stops at the first `LoginErrorAlreadyLoginException`, or at
`LOGIN_BOUND` logins, to stay clear of the lockout recorded in
`docs/huawei_how_to_access.md`.

Usage, inside the devcontainer, **from anywhere** — paths are resolved from
`__file__`, not the working directory:

    /usr/local/bin/python scripts/diag_check.py             # two runs, diffed
    /usr/local/bin/python scripts/diag_check.py --once      # one run, no diff
    /usr/local/bin/python scripts/diag_check.py --sabotage  # expiry mid-poll
    /usr/local/bin/python scripts/diag_check.py --mid-poll --entry B315
    /usr/local/bin/python scripts/diag_check.py --refusal --entry H165
    /usr/local/bin/python scripts/diag_check.py --keep      # also save the files

**Use the container interpreter, not `uv run`.** This imports the integration,
which imports Home Assistant; only `/usr/local/bin/python` has those installed.

Reads credentials from the configured Home Assistant entry — nothing is passed
on the command line. It makes no writes: the diagnostics download is a read
path. It does log the router in and out, which is safe here because this
hardware permits concurrent sessions.

Saved files under `--keep` contain live sanitized diagnostics and are written to
`.notes/local_only/diag_dl/`, which is not tracked.
"""

# The console report is this script's entire output — there is no logger to
# route it through.
# ruff: noqa: T201

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import contextlib
from datetime import UTC, datetime
import json
import os
import pathlib
import re
import sys
from typing import TYPE_CHECKING, Any, cast

from huawei_lte_api.exceptions import (
    LoginErrorAlreadyLoginException,
    ResponseErrorLoginRequiredException,
)

# Installs probatio as `voluptuous` before the package imports it (C-036).
import homeassistant  # noqa: F401

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

try:
    from custom_components.huawei_router_5g.api import (
        HuaweiAuthError,
        HuaweiRouter5GAPI,
        library_supports,
    )
    from custom_components.huawei_router_5g.const import (
        ENDPOINT_NAMES,
        LIBRARY_ADDED_ENDPOINTS,
    )
    from custom_components.huawei_router_5g.coordinator import (
        HuaweiRouter5GDataUpdateCoordinator,
    )
    from custom_components.huawei_router_5g.diagnostics import (
        REDACTED,
        async_get_config_entry_diagnostics,
    )
except ModuleNotFoundError as err:  # pragma: no cover - operator error
    raise SystemExit(
        f"cannot import the integration ({err}). Run this with "
        "/usr/local/bin/python inside the devcontainer, not with `uv run`."
    ) from err

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

CONFIG_ENTRIES = pathlib.Path("/config/.storage/core.config_entries")
OUTPUT_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / ".notes" / "local_only" / "diag_dl"
)

# How many times to poll before giving up on a payload. A cold coordinator can
# defer its first cycle, so a harness that polled once could produce an empty
# `data` block and call it a download.
POLL_ATTEMPTS = 3

# The router response codes `api.py` treats as an expired session. They are
# hardcoded there on the strength of documentation rather than measurement, and
# `--sabotage` is the only thing in this project that puts them against real
# firmware. A device answering some other code would be classified `refused`
# and retried forever instead of re-logging in, which is a defect in `api.py`
# and not in this script — so the check names what it saw rather than only
# failing.
EXPIRY_CODES = ("125002", "125003", "100003")

# The most logins a run may make against one router. A run makes about two per
# download and three in the modes that retry, so 12 is the ceiling for one
# invocation with room to spare; it exists because `docs/huawei_how_to_access.md`
# records a lockout after repeated logins and its threshold is unmeasured.
LOGIN_BOUND = 12

# Endpoints `--refusal` can be pointed at, by the fetch key that `api.py` records
# them under: the library group and method that the poll calls for each. Chosen
# because every one is read on a poll and answers on the routers held.
REFUSABLE: dict[str, tuple[str, str]] = {
    "traffic_statistics": ("monitoring", "traffic_statistics"),
    "month_statistics": ("monitoring", "month_statistics"),
    "net_mode": ("net", "net_mode"),
    "sms_count": ("sms", "sms_count"),
    "mobile_dataswitch": ("dial_up", "mobile_dataswitch"),
}
DEFAULT_REFUSED = "traffic_statistics"

# The endpoint after which `--mid-poll` ends the session: the third of the poll,
# so the first endpoints answer and the later ones meet the dead session.
MID_POLL_AFTER = ("monitoring", "status")

# Payload keys the coordinator writes itself, after `api.get_data()` returns.
#
# They are not endpoints and never appear in the endpoint map: they are the
# three uptime latches, reconciled in `coordinator.py` from the router's
# counters and the values persisted on the entry. Measured against a real
# download on 2026-09-07, where treating them as unexplained blocks failed a
# run in which nothing was wrong.
#
# Named rather than tolerated by pattern: a fourth derived key appearing here
# should fail this check until someone decides it belongs, which is the same
# reasoning `zte_router_5g` applies to its published-field partition.
COORDINATOR_DERIVED = frozenset(
    {"system_boot_time", "conn_start_time", "total_conn_start_time"}
)

# The keys `diagnostics.py` publishes at the top of its document. Asserted
# present in the produced file, which is the guarantee `zte_router_5g` gets
# from partitioning its allow-list and this project gets from here.
REQUIRED_KEYS = (
    "entry",
    "coordinator",
    "data",
    "last_rejection",
    "login",
    "endpoints",
    "entity_resolution",
    "probes",
    "premise",
    "probe_sessions_lost",
)

# The verdicts a probe entry may carry. `not_run` and `session_lost` are the two
# the sweep records when it is cut short (deadline, a failed login, a third
# lost session) or when a session ended under a probe and could not be
# repeated; they are known verdicts, and their count is in the check's detail.
PROBE_OUTCOMES = frozenset(
    {"answered", "refused", "unavailable", "not_run", "session_lost"}
)

# Fields the coordinator block must carry, whatever their values.
REQUIRED_COORDINATOR_FIELDS = (
    "consecutive_failures",
    "last_update_success",
    "last_update_success_time",
    "data_available",
    "update_interval_seconds",
)

# Values that legitimately differ between two runs minutes apart: radio
# measurements, counters and anything clocked. A difference here is the device
# living its life, not the download changing shape.
#
# **Two blocks are tolerated wholesale, by path.** `traffic_statistics` and
# `month_statistics` are counters end to end — bytes, seconds and the rates
# derived from them — and naming their fields individually would be a list to
# maintain against firmware that adds to it. `showtraffic` is the exception
# inside one of them: it is a display setting, not a counter, and is excluded
# from the tolerance so a change to it is still reported.
#
# **Everything else is matched by field name, and the names are Huawei's.**
# The first version of this pattern was adapted from `zte_router_5g`, whose API
# is snake_case, so `_time` and `_temp` carried a leading underscore that never
# matches `CurrentConnectTime` or `MonthDuration`. Measured against a real
# download on 2026-09-07: five clocked fields were being compared that cannot
# hold still, of which `MonthDuration` was simply the first to be reported.
_VOLATILE = re.compile(
    r"(?i)("
    # Whole blocks of counters, by path.
    r"^/data/month_statistics/"
    r"|^/data/traffic_statistics/(?!showtraffic$)"
    # Radio measurements and the cell the device happens to be camped on.
    r"|rsrp|rsrq|rssi|snr|sinr|cqi|mcs|bler|ecio|rscp|txpower|rank"
    r"|cell_id|enodeb_id|nei_cellid|lac|tac|pci|arfcn|freq|band|bandwidth|bsic"
    r"|signalicon|signalbar|maxsignal|bars?$"
    # Anything clocked or counted, in either naming convention.
    r"|time$|_time|uptime|timestamp|duration|boot"
    # The health snapshot's clock reading of the last successful poll.
    r"|^/_health/last_good_update$"
    r"|wifiuser|temperature|_temp"
    r"|batterylevel|batterypercent|batterystatus"
    # Which SMS the router holds, and how many, changes on its own.
    r"|^/data/sms_|^/data/monitoring_check_notifications/"
    # Client lists come and go as devices join and leave the network.
    r"|^/data/lan_host_info/|^/data/wlan_host_list/"
    # Per-endpoint timing, which is the point of recording it: it moves every
    # run. The endpoint's outcome, key counts and type beside it do not, and
    # those are what the comparison is watching.
    r"|elapsed_ms$"
    # A populated count moves with the device — a radio field that blanks
    # between two runs changes it — while the outcome, the type, the key count
    # and the key names do not, and those are what the comparison is watching.
    r"|^/probes/[a-z_0-9]+/populated$"
    r"|^/endpoints/[a-z_0-9]+/populated$"
    # This script's own bookkeeping.
    r"|^/_elapsed$"
    r")"
)

# A pseudonym assigned by `diagnostics._Tokenizer`. Tokens are allocated in
# first-seen order and are stable only within one download, so `ip-5` in one
# file and `ip-5` in the next are unrelated. Comparing them across files
# compares allocation order, and a pass that read its keys in a different order
# would report a permutation as a difference. Only the kind survives, so only
# the kind is compared.
_TOKEN = re.compile(r"^(ip|mac|cell|phone|ssid|name|imei|serial)-\d+$")

_COLOUR = os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    """Wrap text in an ANSI code, or return it unchanged when colour is off."""
    return f"\033[{code}m{text}\033[0m" if _COLOUR else text


def _green(text: str) -> str:
    """Return text in bold green."""
    return _c("1;32", text)


def _red(text: str) -> str:
    """Return text in bold red."""
    return _c("1;31", text)


def _cyan(text: str) -> str:
    """Return text in bold cyan."""
    return _c("1;36", text)


def _dim(text: str) -> str:
    """Return text dimmed, for supporting detail."""
    return _c("2", text)


class Report:
    """Collects results so one failure does not hide the rest."""

    def __init__(self) -> None:
        """Start an empty report."""
        self.checks: list[tuple[bool, str, str]] = []

    def record(self, ok: bool, name: str, detail: str = "") -> None:
        """Print one result and remember it for the summary."""
        self.checks.append((ok, name, detail))
        badge = _green("✔  PASS") if ok else _red("✖  FAIL")
        suffix = _dim(f"  — {detail}") if detail else ""
        print(f"  {badge}  {name}{suffix}")

    @property
    def failed(self) -> int:
        """Return how many checks failed, for the exit code."""
        return sum(1 for ok, _, _ in self.checks if not ok)


class _StubEntry:
    """The parts of a `ConfigEntry` the diagnostics path actually reads.

    `async_get_config_entry_diagnostics` takes `hass` but never touches it, and
    reads only `title`, `data`, `options` and `runtime_data` from the entry.
    `async_on_unload` is here for `DataUpdateCoordinator.__init__`, which
    registers its shutdown against the entry.

    A stub rather than the live entry on purpose: this builds its own
    coordinator so a run cannot disturb the one serving the user's entities.
    """

    def __init__(
        self, options: dict[str, Any], data: dict[str, Any], entry_id: str, title: str
    ) -> None:
        """Hold the entry fields the diagnostics path reads."""
        self.options = options
        self.data = data
        self.entry_id = entry_id
        self.title = title
        self.runtime_data: Any = None

    def async_on_unload(self, func: Any) -> Any:
        """Accept and return the shutdown callback, registering nothing."""
        return func


def _select_entry(
    entries: list[dict[str, Any]], selector: str | None
) -> dict[str, Any]:
    """Return the configured router entry named by `selector`.

    With no selector the first `huawei_router_5g` entry is returned, as before.
    A selector matches an entry id exactly, any part of a title ignoring case, or
    any part of the host the entry is set up with; the first entry that matches is
    taken, and no match lists what is configured instead of guessing.
    """
    ours = [entry for entry in entries if entry.get("domain") == "huawei_router_5g"]
    if not ours:
        raise SystemExit(f"no huawei_router_5g entry in {CONFIG_ENTRIES}")
    if selector is None:
        return ours[0]
    wanted = selector.lower()
    for entry in ours:
        host = str((entry.get("options") or {}).get("host", "")).lower()
        if (
            str(entry.get("entry_id")) == selector
            or wanted in str(entry.get("title", "")).lower()
            or wanted in host
        ):
            return entry
    configured = ", ".join(
        f"{entry.get('title')} ({(entry.get('options') or {}).get('host')})"
        for entry in ours
    )
    raise SystemExit(f"no entry matches {selector!r}; configured: {configured}")


def _credentials(
    selector: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    """Read the router entry from the configured Home Assistant instance."""
    with CONFIG_ENTRIES.open() as handle:
        stored = json.load(handle)
    entry = _select_entry(stored["data"]["entries"], selector)
    return (
        dict(entry["options"]),
        dict(entry["data"]),
        str(entry["entry_id"]),
        str(entry.get("title") or "Huawei Router"),
    )


def _secrets(options: dict[str, Any], data: dict[str, Any]) -> list[str]:
    """Return the live values that must not survive into the download.

    Drawn from the entry itself rather than from a fixture, so this asserts
    against the actual credentials and identifiers of the device in front of
    it. Short values are excluded: a two-character username would match half
    the document by coincidence and prove nothing.
    """
    candidates = [
        options.get("password"),
        options.get("username"),
        options.get("host"),
        data.get("mac"),
    ]
    return [str(v) for v in candidates if v and len(str(v)) >= 6]


def _serialize(artefact: dict[str, Any], *, indent: int | None = None) -> str:
    """Render a download as JSON the way Home Assistant does.

    **`default=str` is not cosmetic.** The entry's stored data carries real
    `datetime` objects — `system_boot_time`, `conn_start_time` and
    `total_conn_start_time` are written back by the coordinator — and Home
    Assistant serializes the download with its own encoder, so the user's file
    is valid JSON while `json.dumps` on the same object raises. Every site in
    this script that serializes goes through here, because the first version
    did not and the first hardware run died on it before printing a verdict.
    """
    return json.dumps(artefact, indent=indent, default=str)


def _walk(node: Any, path: str = "") -> dict[str, Any]:
    """Flatten a document to leaf path → value, for comparison."""
    flat: dict[str, Any] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            flat.update(_walk(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            flat.update(_walk(value, f"{path}/{index}"))
    else:
        flat[path] = node
    return flat


def _comparable(value: Any) -> Any:
    """Return a value with any cross-file-unstable pseudonym reduced to its kind."""
    if isinstance(value, str):
        match = _TOKEN.match(value)
        if match:
            return f"{match.group(1)}-*"
    return value


def _sabotaging_ensure(original: Any) -> Any:
    """Wrap `_ensure_client` so the poll runs on a session the router has ended.

    **Invalidating before the poll does nothing**, which the first hardware run
    of this script proved: `get_data` opens with `_ensure_client`, which finds
    no client and logs in cleanly, so the pass that followed was a healthy one
    and every endpoint answered. Measured 2026-09-07.

    What lands is establishing the session and then logging it out, leaving the
    poll to use a credential the router has already discarded. The endpoint
    calls go to the real device and it answers with whatever it really says to
    a client whose session is gone — which is the point, since the three codes
    `api.py` classifies on have never been confirmed against this firmware.

    Every call is sabotaged, not just the first: `get_data` resets its rejection
    record at the start of each poll, so a later healthy attempt would clear the
    evidence this run exists to collect.
    """

    async def ensure_client(self: Any) -> Any:
        client = await original(self)
        with contextlib.suppress(Exception):
            await asyncio.to_thread(client.user.logout)
        print(_dim("           [session established, then logged out]"))
        return client

    return ensure_client


class RunStoppedError(BaseException):
    """Raised to end the whole run: the login bound or an already-logged-in refusal.

    A `BaseException` so that the `except Exception` handlers around the login in
    `api.py` do not turn it into a connection error and let the run go on.
    """


class LoginBudget:
    """Counts the real logins of a run and ends it before a lockout.

    Counted at `_create_connection_sync`, which every login goes through
    (`login`, `_login_internal` and the liveness probe). The anonymous premise
    connection is not one, because it never sends credentials.

    The run stops at the first `LoginErrorAlreadyLoginException`, which is the
    router saying it holds a session already and the first sign of the lockout
    this exists to avoid, and at `bound` logins whatever happens.
    """

    def __init__(self, bound: int = LOGIN_BOUND) -> None:
        """Start counting at zero."""
        self.bound = bound
        self.count = 0
        self.stopped: str | None = None

    def wrap(self, original: Any) -> Any:
        """Return `_create_connection_sync` wrapped to count and to stop."""

        def create(api: Any) -> Any:
            if self.stopped is not None:
                raise RunStoppedError(self.stopped)
            if self.count >= self.bound:
                self.stopped = f"login bound of {self.bound} reached"
                raise RunStoppedError(self.stopped)
            self.count += 1
            try:
                return original(api)
            except LoginErrorAlreadyLoginException:
                self.stopped = "the router answered LoginErrorAlreadyLoginException"
                raise

        return create


def _midpoll_ensure(original: Any, state: dict[str, bool]) -> Any:
    """Wrap `_ensure_client` so the first session ends after `monitoring.status`.

    The method that ends the session is patched onto the first client only, so
    the coordinator's retry, which logs in again, runs on a healthy session and
    the poll recovers. The logout is the real one, so the router answers the
    later endpoints with whatever it really says to a client whose session is
    gone.
    """

    async def ensure_client(self: Any) -> Any:
        client = await original(self)
        if not state.get("done"):
            state["done"] = True
            group = getattr(client, MID_POLL_AFTER[0])
            real = getattr(group, MID_POLL_AFTER[1])

            def answer_then_log_out(*args: Any, **kwargs: Any) -> Any:
                try:
                    return real(*args, **kwargs)
                finally:
                    with contextlib.suppress(Exception):
                        client.user.logout()
                    print(_dim("           [session logged out mid-poll]"))

            setattr(group, MID_POLL_AFTER[1], answer_then_log_out)
        return client

    return ensure_client


def _refusal_ensure(
    original: Any, state: dict[str, bool], key: str, *, expire: bool
) -> Any:
    """Wrap `_ensure_client` so one endpoint raises 100003 on the first session.

    **The refusal is simulated.** The library method for `key` is patched to
    raise `ResponseErrorLoginRequiredException`, which is what the library
    raises for a 100003; the router never refuses a polled endpoint itself on
    any router held. Everything `api.py` does next is real: the premise check
    is an anonymous read against the router, and the re-read is a real read on
    the session. With `expire` the session is also logged out, so the re-read is
    refused too and the decision is an expiry. The patch is on the first client
    only, so the coordinator's retry recovers.
    """
    group_name, method_name = REFUSABLE[key]

    async def ensure_client(self: Any) -> Any:
        client = await original(self)
        if not state.get("done"):
            state["done"] = True
            group = getattr(client, group_name)

            def refuse(*args: Any, **kwargs: Any) -> Any:
                if expire:
                    with contextlib.suppress(Exception):
                        client.user.logout()
                    print(_dim("           [session logged out with the refusal]"))
                raise ResponseErrorLoginRequiredException("login required", 100003)

            setattr(group, method_name, refuse)
        return client

    return ensure_client


def _recording_get_data(original: Any, seen: list[str]) -> Any:
    """Wrap `get_data` to remember the `HuaweiAuthError` the coordinator retries.

    The retry's own poll clears the rejection record, so the exception is the
    only evidence that the first poll ended in an expiry.
    """

    async def get_data(self: Any) -> Any:
        try:
            return await original(self)
        except HuaweiAuthError:
            seen.append("HuaweiAuthError")
            raise

    return get_data


async def produce(
    label: str,
    report: Report,
    *,
    sabotage: bool = False,
    entry: str | None = None,
    mode: str | None = None,
    refused: str = DEFAULT_REFUSED,
    budget: LoginBudget | None = None,
    polls: int = 1,
) -> dict[str, Any]:
    """Build a coordinator against the live router and return one download.

    `entry` names the configured entry to use, so the credentials, and the
    redaction secrets `main` draws from the same selector, are that entry's.
    `mode` is `mid-poll`, `refusal` or `refusal-expired`, or `None`. `polls` is
    the least number of polls made before the download, on the one session, so
    that the Integration Health verdict is read after the strike budget has run.
    """
    from homeassistant.core import HomeAssistant

    options, data, entry_id, title = _credentials(entry)
    entry = _StubEntry(options, data, entry_id, title)
    hass = HomeAssistant("/config")

    print(_cyan(f"\n[{label}] producing a download"))

    api = HuaweiRouter5GAPI(
        options["host"], options.get("username"), options["password"]
    )
    # `_StubEntry` carries the four attributes the diagnostics path reads plus
    # the one hook the coordinator registers; it is not a ConfigEntry and
    # cannot be, since building a real one needs a running Home Assistant. The
    # cast states that deliberately rather than widening either signature for a
    # script's benefit.
    entry_as_config = cast("ConfigEntry[Any]", entry)
    coordinator = HuaweiRouter5GDataUpdateCoordinator(hass, entry_as_config, api)
    entry.runtime_data = coordinator

    start = datetime.now(UTC)
    original = HuaweiRouter5GAPI._ensure_client  # noqa: SLF001
    original_get_data = HuaweiRouter5GAPI.get_data
    original_create = HuaweiRouter5GAPI._create_connection_sync  # noqa: SLF001
    auth_errors: list[str] = []
    patched = original
    if sabotage:
        patched = _sabotaging_ensure(original)
    elif mode == "mid-poll":
        patched = _midpoll_ensure(original, {})
    elif mode in ("refusal", "refusal-expired"):
        patched = _refusal_ensure(
            original, {}, refused, expire=mode == "refusal-expired"
        )
    if patched is not original:
        HuaweiRouter5GAPI._ensure_client = patched  # type: ignore[method-assign]  # noqa: SLF001
    if mode is not None:
        HuaweiRouter5GAPI.get_data = _recording_get_data(  # type: ignore[method-assign]
            original_get_data, auth_errors
        )
    if budget is not None:
        HuaweiRouter5GAPI._create_connection_sync = budget.wrap(  # type: ignore[method-assign]  # noqa: SLF001
            original_create
        )
    try:
        # A cold coordinator does not always produce a payload on its first
        # poll: startup reconciliation can defer a cycle, and a paused entry
        # takes the safe startup bypass. Polled to a payload rather than a
        # fixed count, because how many deferrals happen is the coordinator's
        # business and not this script's to encode.
        attempts = 1 if sabotage or mode is not None else POLL_ATTEMPTS
        for made in range(1, max(attempts, polls) + 1):
            coordinator._force_refresh_once = True  # noqa: SLF001 - nothing to debounce on
            try:
                coordinator.data = await coordinator._async_update_data()  # noqa: SLF001
            except Exception as err:  # noqa: BLE001 - a failed poll is the subject
                print(_dim(f"           [poll raised {type(err).__name__}: {err}]"))
            if coordinator.data and made >= polls:
                break

        result = await async_get_config_entry_diagnostics(hass, entry_as_config)
    finally:
        HuaweiRouter5GAPI._ensure_client = original  # type: ignore[method-assign]  # noqa: SLF001
        HuaweiRouter5GAPI.get_data = original_get_data  # type: ignore[method-assign]
        HuaweiRouter5GAPI._create_connection_sync = original_create  # type: ignore[method-assign]  # noqa: SLF001
        await api.logout()

    result["_auth_errors"] = list(auth_errors)
    result["_health"] = dict(coordinator.health_snapshot)
    result["_elapsed"] = (datetime.now(UTC) - start).total_seconds()
    report.record(
        True,
        f"[{label}] a download was produced",
        f"{len(_serialize(result))} bytes in {result['_elapsed']:.1f}s",
    )
    return result


def check_shape(
    artefact: dict[str, Any], report: Report, label: str, *, expect_payload: bool = True
) -> None:
    """Assert the produced file carries what `diagnostics.py` intends to publish."""
    missing = [key for key in REQUIRED_KEYS if key not in artefact]
    report.record(
        not missing,
        f"[{label}] every published key reached the file",
        f"missing: {sorted(missing)}" if missing else f"{len(REQUIRED_KEYS)} keys",
    )

    coordinator = artefact.get("coordinator")
    if isinstance(coordinator, dict):
        absent = [f for f in REQUIRED_COORDINATOR_FIELDS if f not in coordinator]
        report.record(
            not absent,
            f"[{label}] the coordinator block is complete",
            f"missing: {sorted(absent)}" if absent else "",
        )
    else:
        report.record(False, f"[{label}] the coordinator block is complete", "absent")

    payload = artefact.get("data")
    if expect_payload:
        report.record(
            isinstance(payload, dict) and bool(payload),
            f"[{label}] the payload block is populated",
            f"{len(payload)} endpoints"
            if isinstance(payload, dict)
            else "not a mapping",
        )


def check_captures(artefact: dict[str, Any], report: Report, label: str) -> None:
    """Assert the two captures agree with the coordinator state beside them.

    The value of a capture is that it explains a state the rest of the file
    reports, so a rejection recorded against a healthy poll — or a healthy poll
    with a stale rejection still attached — is a defect in the clearing rule
    however well-formed both halves look on their own.
    """
    login = artefact.get("login")
    report.record(
        isinstance(login, dict) and login.get("result") == "ok",
        f"[{label}] the login record says the session was established",
        f"result: {login.get('result') if isinstance(login, dict) else login}",
    )

    coordinator = artefact.get("coordinator") or {}
    succeeded = bool(coordinator.get("last_update_success"))
    rejection = artefact.get("last_rejection")

    if succeeded:
        report.record(
            rejection is None,
            f"[{label}] a successful poll left no rejection behind",
            "" if rejection is None else f"stale: {rejection}",
        )
    else:
        report.record(
            isinstance(rejection, dict) and "verdict" in rejection,
            f"[{label}] a failed poll left its verdict behind",
            f"verdict: {rejection.get('verdict')}"
            if isinstance(rejection, dict)
            else "nothing recorded",
        )


def check_endpoints(artefact: dict[str, Any], report: Report, label: str) -> None:
    """Assert the endpoint map accounts for the payload beside it.

    The map exists so an absence from `data` can be read. That only works if
    the two agree: every endpoint that answered must have left a block, and
    every block must have come from an endpoint that answered. A map that
    drifts from the payload is worse than no map, because it is believed.
    """
    endpoints = artefact.get("endpoints")
    if not isinstance(endpoints, dict) or not endpoints:
        report.record(False, f"[{label}] the endpoint map is populated", "empty")
        return

    payload = artefact.get("data") or {}
    answered = {k for k, v in endpoints.items() if v.get("outcome") == "answered"}
    unexplained = sorted(set(payload) - answered - COORDINATOR_DERIVED)
    missing = sorted(answered - set(payload))

    report.record(
        not unexplained and not missing,
        f"[{label}] the endpoint map accounts for the payload",
        f"unexplained blocks: {unexplained}; answered but absent: {missing}"
        if (unexplained or missing)
        else f"{len(answered)} answered, {len(COORDINATOR_DERIVED)} derived",
    )

    outcomes = sorted({v.get("outcome") for v in endpoints.values()})

    def outcome_is_known(key: str, outcome: Any) -> bool:
        # `unsupported` is a known verdict only for an endpoint the loaded
        # library predates, so it cannot pass for any other endpoint or on a
        # library that has the method.
        if outcome in {"answered", "refused", "expired", "unavailable", "skipped"}:
            return True
        added = LIBRARY_ADDED_ENDPOINTS.get(key)
        return (
            outcome == "unsupported"
            and added is not None
            and not library_supports(added[2])
        )

    report.record(
        all(outcome_is_known(k, v.get("outcome")) for k, v in endpoints.items()),
        f"[{label}] every outcome is one of the known verdicts",
        f"outcomes: {outcomes}",
    )

    for key, (_, _, first) in LIBRARY_ADDED_ENDPOINTS.items():
        if library_supports(first):
            outcome = endpoints.get(key, {}).get("outcome")
            report.record(
                outcome == "answered",
                f"[{label}] {key} answered on a library that has it",
                f"outcome {outcome!r}",
            )


def check_sabotage(artefact: dict[str, Any], report: Report, label: str) -> None:
    """Assert a real session loss was classified the way `api.py` believes.

    Only meaningful after a `--sabotage` run: the session was taken away
    mid-poll, so the router answered a live request with whatever it says when
    a session is gone, and the integration classified it.
    """
    rejection = artefact.get("last_rejection") or {}
    endpoints = artefact.get("endpoints") or {}

    verdict = rejection.get("verdict") if isinstance(rejection, dict) else None
    report.record(
        verdict in {"expired", "refused", "unavailable"},
        f"[{label}] the lost session was recorded as a rejection",
        f"verdict: {verdict}",
    )

    code = rejection.get("code") if isinstance(rejection, dict) else None
    report.record(
        verdict == "expired",
        f"[{label}] the router's answer classified as an expiry",
        f"verdict {verdict!r} on code {code!r} — if this is `refused`, the code "
        f"is outside {EXPIRY_CODES} and `api.py` retries instead of re-logging in",
    )

    if code is not None:
        report.record(
            str(code) in EXPIRY_CODES,
            f"[{label}] the code is one api.py classifies on",
            f"code {code!r}, known {EXPIRY_CODES}",
        )

    disturbed = {
        key: value.get("outcome")
        for key, value in endpoints.items()
        if isinstance(value, dict)
        and value.get("outcome") not in ("answered", "unsupported")
    }
    report.record(
        bool(disturbed),
        f"[{label}] the endpoint map names what the lost session cost",
        f"{len(disturbed)} not answered: {sorted(disturbed)[:5]}"
        if disturbed
        else "every endpoint answered — the sabotage did not land",
    )


def _answered(artefact: dict[str, Any]) -> set[str]:
    """Return the endpoints the download records as answered."""
    return {
        key
        for key, value in (artefact.get("endpoints") or {}).items()
        if isinstance(value, dict) and value.get("outcome") == "answered"
    }


def check_mid_poll(
    artefact: dict[str, Any], baseline: dict[str, Any], report: Report, label: str
) -> None:
    """Assert a session lost mid-poll was recovered with nothing lost.

    Every endpoint the clean pass answered must be answered after the poll's
    retry, and the poll must really have met the dead session first: the
    expiry shows as a `HuaweiAuthError` the coordinator retried.
    """
    report.record(
        "HuaweiAuthError" in (artefact.get("_auth_errors") or []),
        f"[{label}] the dead session was met and raised an expiry",
        f"{artefact.get('_auth_errors')}",
    )
    lost = sorted(_answered(baseline) - _answered(artefact))
    report.record(
        not lost,
        f"[{label}] every endpoint the clean pass answered was answered after the retry",
        f"lost: {lost}" if lost else f"{len(_answered(artefact))} answered",
    )


def check_refusal(
    artefact: dict[str, Any],
    baseline: dict[str, Any],
    report: Report,
    label: str,
    refused: str = DEFAULT_REFUSED,
) -> None:
    """Assert a simulated refusal on a live session was judged a refusal.

    The router's own refusal is **not observed** here: the library method was
    patched. What is checked is everything `api.py` did with it.
    """
    endpoints = artefact.get("endpoints") or {}
    record = endpoints.get(refused) or {}
    report.record(
        record.get("outcome") == "refused" and record.get("code") == "100003",
        f"[{label}] {refused} was recorded refused with 100003",
        f"{record}",
    )
    report.record(
        record.get("judged") == "live_session",
        f"[{label}] the refusal was judged against a live session",
        f"judged {record.get('judged')!r}",
    )
    premise = artefact.get("premise") or {}
    report.record(
        premise == {"outcome": "refused", "code": "100003"},
        f"[{label}] the premise check read device.information anonymously and got 100003",
        f"{premise}",
    )
    others = sorted((_answered(baseline) - {refused}) - _answered(artefact))
    report.record(
        not others,
        f"[{label}] the rest of the poll answered",
        f"lost: {others}" if others else f"{len(_answered(artefact))} answered",
    )
    report.record(
        not artefact.get("_auth_errors"),
        f"[{label}] no expiry was raised",
        f"{artefact.get('_auth_errors')}",
    )


def check_refusal_expired(
    artefact: dict[str, Any], baseline: dict[str, Any], report: Report, label: str
) -> None:
    """Assert the same refusal with the session ended raised `HuaweiAuthError`."""
    report.record(
        "HuaweiAuthError" in (artefact.get("_auth_errors") or []),
        f"[{label}] the refusal on an ended session raised HuaweiAuthError",
        f"{artefact.get('_auth_errors')}",
    )
    premise = artefact.get("premise") or {}
    report.record(
        premise == {"outcome": "refused", "code": "100003"},
        f"[{label}] the premise check read device.information anonymously and got 100003",
        f"{premise}",
    )
    lost = sorted(_answered(baseline) - _answered(artefact))
    report.record(
        not lost,
        f"[{label}] the coordinator's retry recovered every endpoint",
        f"lost: {lost}" if lost else f"{len(_answered(artefact))} answered",
    )


def check_health(
    artefact: dict[str, Any],
    report: Report,
    label: str,
    expect_not_served: int | None = None,
) -> None:
    """Assert the Integration Health verdict separates standing refusals.

    Read after the polls the run made (`--polls`). Every endpoint the router
    refused with its own code and that never answered must be listed under
    `not_served` and absent from `degraded_capabilities`; `expect_not_served`
    states how many that is on the router in front of it (0 on a router that
    refuses nothing).
    """
    health = artefact.get("_health") or {}
    endpoints = artefact.get("endpoints") or {}
    refused = {
        ENDPOINT_NAMES[key]
        for key, value in endpoints.items()
        if isinstance(value, dict)
        and value.get("outcome") == "refused"
        and key in ENDPOINT_NAMES
    }
    not_served = set(health.get("not_served") or [])
    degraded = set(health.get("degraded_capabilities") or [])
    report.record(
        not_served == refused,
        f"[{label}] not_served lists the endpoints the router refuses",
        f"not_served {sorted(not_served)}, refused {sorted(refused)}",
    )
    report.record(
        not (not_served & degraded),
        f"[{label}] no refused endpoint is also degraded",
        f"degraded {sorted(degraded)}",
    )
    if expect_not_served is not None:
        report.record(
            len(not_served) == expect_not_served,
            f"[{label}] not_served holds {expect_not_served} endpoint(s)",
            f"{len(not_served)}: severity {health.get('severity')!r}",
        )


def check_entity_resolution(
    artefact: dict[str, Any], report: Report, label: str
) -> None:
    """Assert the entity map is present, complete and free of raising descriptions.

    A description whose `value_fn` throws against a live payload is a defect in
    the integration rather than in the firmware, and it is invisible in normal
    operation — the entity simply shows nothing. This is the only place it
    surfaces.
    """
    resolution = artefact.get("entity_resolution")
    if not isinstance(resolution, dict) or not resolution:
        report.record(
            False, f"[{label}] the entity resolution map is present", "absent"
        )
        return

    counted = all(
        block.get("total")
        == block.get("resolved")
        + len(block.get("no_value", []))
        + len(block.get("raised", {}))
        for block in resolution.values()
    )
    totals = {name: block.get("total") for name, block in resolution.items()}
    report.record(counted, f"[{label}] every description is accounted for", f"{totals}")

    raised = {
        f"{name}.{key}": err
        for name, block in resolution.items()
        for key, err in (block.get("raised") or {}).items()
    }
    report.record(
        not raised,
        f"[{label}] no description raised against the live payload",
        f"{len(raised)} raised: {sorted(raised)[:5]}" if raised else "",
    )

    summary = {
        name: f"{block.get('resolved')}/{block.get('total')}"
        for name, block in resolution.items()
    }
    report.record(
        any(block.get("resolved") for block in resolution.values()),
        f"[{label}] the payload populates entities",
        f"{summary}",
    )


def check_probes(artefact: dict[str, Any], report: Report, label: str) -> None:
    """Assert the unpolled endpoints were all attempted and all accounted for.

    The value of this block is that a silence is reported rather than absent:
    an endpoint this router does not serve must appear with `refused` and the
    router's code, not be missing. A probe map shorter than the probe list
    means the sweep stopped early and the gaps are unexplained.
    """
    probes = artefact.get("probes")
    if not isinstance(probes, dict) or not probes:
        report.record(False, f"[{label}] the probe map is populated", "empty")
        return
    if "error" in probes and len(probes) == 1:
        report.record(
            False, f"[{label}] the probe sweep completed", f"{probes['error']}"
        )
        return

    outcomes = Counter(v.get("outcome") for v in probes.values() if isinstance(v, dict))
    report.record(
        sum(outcomes.values()) == len(probes),
        f"[{label}] every probe recorded an outcome",
        f"{len(probes)} probed: {dict(outcomes)}",
    )
    report.record(
        all(o in PROBE_OUTCOMES for o in outcomes),
        f"[{label}] every probe outcome is a known verdict",
        f"{sorted(outcomes)}",
    )
    report.record(
        outcomes.get("unavailable", 0) == 0,
        f"[{label}] no probe failed outside the router's own answer",
        f"{outcomes.get('unavailable', 0)} unavailable"
        if outcomes.get("unavailable")
        else "",
    )


def check_redaction(
    artefact: dict[str, Any], secrets: list[str], report: Report, label: str
) -> None:
    """Assert no live identifier survives anywhere in the serialized document.

    Asserted over the whole document rather than key by key: a key-by-key
    assertion only finds the leaks somebody already thought of, which is the
    reasoning `test_diagnostics.py` records for the unit suite.
    """
    serialized = _serialize(artefact)
    leaked = [value for value in secrets if value in serialized]
    report.record(
        not leaked,
        f"[{label}] no live identifier survived into the file",
        f"leaked: {leaked}" if leaked else f"{len(secrets)} values checked",
    )
    report.record(
        REDACTED in serialized,
        f"[{label}] the credential is present as a redaction marker",
        "" if REDACTED in serialized else "no marker found — is anything redacted?",
    )


def check_stability(
    first: dict[str, Any], second: dict[str, Any], report: Report
) -> None:
    """Diff two downloads, ignoring what the device changes on its own."""
    flat_a = _walk(first)
    flat_b = _walk(second)

    only_a = sorted(set(flat_a) - set(flat_b))
    only_b = sorted(set(flat_b) - set(flat_a))
    structural = [p for p in only_a + only_b if not _VOLATILE.search(p)]
    report.record(
        not structural,
        "the two downloads carry the same fields",
        f"{len(structural)} differ: {structural[:5]}" if structural else "",
    )

    changed = [
        path
        for path in set(flat_a) & set(flat_b)
        if _comparable(flat_a[path]) != _comparable(flat_b[path])
        and not _VOLATILE.search(path)
    ]
    report.record(
        not changed,
        "no stable value changed between the two runs",
        f"{len(changed)} changed: {changed[:5]}" if changed else "",
    )


def _save(artefact: dict[str, Any], label: str) -> pathlib.Path:
    """Write one download to the untracked local folder."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"diag_check_{stamp}_{label}.json"
    path.write_text(_serialize(artefact, indent=2), encoding="utf-8")
    return path


async def main() -> int:
    """Produce the downloads, check them, and report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="one run only, skipping the diff"
    )
    parser.add_argument(
        "--sabotage",
        action="store_true",
        help="invalidate the session mid-poll and check the recorded verdict",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--mid-poll",
        action="store_const",
        dest="mode",
        const="mid-poll",
        help="log the session out after monitoring.status and check the recovery",
    )
    modes.add_argument(
        "--refusal",
        action="store_const",
        dest="mode",
        const="refusal",
        help="simulate a 100003 from one endpoint on a live session",
    )
    modes.add_argument(
        "--refusal-expired",
        action="store_const",
        dest="mode",
        const="refusal-expired",
        help="the same refusal with the session logged out, which must raise",
    )
    parser.add_argument(
        "--refuse",
        default=DEFAULT_REFUSED,
        choices=sorted(REFUSABLE),
        help="the endpoint the refusal modes refuse",
    )
    parser.add_argument(
        "--entry",
        default=None,
        help="the entry to test: its entry id, its title, or part of its host",
    )
    parser.add_argument(
        "--polls",
        type=int,
        default=1,
        help="polls to make on one session before the download (3 reads health)",
    )
    parser.add_argument(
        "--expect-not-served",
        type=int,
        default=None,
        help="how many endpoints the Integration Health sensor must list as not served",
    )
    parser.add_argument(
        "--keep", action="store_true", help="save the produced downloads"
    )
    args = parser.parse_args()

    report = Report()
    options, data, _, title = _credentials(args.entry)
    secrets = _secrets(options, data)
    budget = LoginBudget()
    print(_dim(f"entry: {title}"))

    try:
        status = await _run(args, report, secrets, budget)
    except RunStoppedError as stop:
        report.record(False, "the run stopped to protect the router", str(stop))
        status = 1
    # The router's own count of what this run asked of it, against the bound.
    report.record(
        budget.count <= budget.bound and budget.stopped is None,
        "the logins made stayed inside the bound",
        f"{budget.count} of {budget.bound}"
        + (f"; stopped: {budget.stopped}" if budget.stopped else ""),
    )

    total = len(report.checks)
    passed = total - report.failed
    # The banner lives here rather than in the VS Code task because `tee >(...)`
    # reports the exit status of `tee`, not of this script. The wording is
    # `zte_router_5g`'s verbatim: the shared `Show: Results Summary` task greps
    # every project's `diag_check.txt` for this exact string.
    if report.failed:
        print(_red(f"\n✖  Diagnostics check: FAILED  ({passed}/{total} passed)"))
    else:
        print(_green(f"\n✔  Diagnostics check: PASSED  ({passed}/{total})"))
    return 1 if report.failed or status else 0


async def _run(
    args: argparse.Namespace,
    report: Report,
    secrets: list[str],
    budget: LoginBudget,
) -> int:
    """Run the selected checks. Split from `main` so a stopped run still reports."""
    if args.mode is not None:
        return await _run_mode(args, report, secrets, budget)

    first = await produce(
        "1",
        report,
        sabotage=args.sabotage,
        entry=args.entry,
        budget=budget,
        polls=args.polls,
    )
    check_shape(first, report, "1", expect_payload=not args.sabotage)
    # `check_captures` asks whether the captures agree with a *healthy* poll.
    # A sabotaged run has no healthy poll to agree with, and a freshly built
    # coordinator reports `last_update_success` as True before it has ever
    # succeeded, so the pairing check would misread the run. `check_sabotage`
    # asks the questions that apply instead.
    if not args.sabotage:
        check_captures(first, report, "1")
    if not args.sabotage:
        check_endpoints(first, report, "1")
        check_entity_resolution(first, report, "1")
        check_probes(first, report, "1")
        if args.polls > 1 or args.expect_not_served is not None:
            check_health(first, report, "1", args.expect_not_served)
    if args.sabotage:
        check_sabotage(first, report, "1")
    check_redaction(first, secrets, report, "1")
    if args.keep:
        print(_dim(f"           saved: {_save(first, 'run1')}"))

    # A sabotaged run loses endpoints on purpose, so diffing it against a clean
    # one reports the sabotage as instability. The second run is skipped rather
    # than compared and tolerated.
    if not args.once and not args.sabotage:
        second = await produce("2", report, entry=args.entry, budget=budget)
        check_shape(second, report, "2")
        check_captures(second, report, "2")
        check_endpoints(second, report, "2")
        check_entity_resolution(second, report, "2")
        check_probes(second, report, "2")
        check_redaction(second, secrets, report, "2")
        if args.keep:
            print(_dim(f"           saved: {_save(second, 'run2')}"))

        print(_cyan("\n[diff] comparing the two downloads"))
        check_stability(first, second, report)
    return 0


async def _run_mode(
    args: argparse.Namespace,
    report: Report,
    secrets: list[str],
    budget: LoginBudget,
) -> int:
    """Run a clean pass, then the same poll under one of the three modes.

    The clean pass is the baseline: the modes ask that no endpoint it answered
    is lost, and an endpoint that a router never answers cannot be lost.
    """
    baseline = await produce(
        "clean", report, entry=args.entry, budget=budget, polls=args.polls
    )
    check_shape(baseline, report, "clean")
    check_endpoints(baseline, report, "clean")
    check_probes(baseline, report, "clean")
    if args.polls > 1 or args.expect_not_served is not None:
        check_health(baseline, report, "clean", args.expect_not_served)
    check_redaction(baseline, secrets, report, "clean")
    if args.keep:
        print(_dim(f"           saved: {_save(baseline, 'clean')}"))

    run = await produce(
        args.mode,
        report,
        entry=args.entry,
        mode=args.mode,
        refused=args.refuse,
        budget=budget,
    )
    check_shape(run, report, args.mode)
    check_redaction(run, secrets, report, args.mode)
    if args.mode == "mid-poll":
        check_mid_poll(run, baseline, report, args.mode)
    elif args.mode == "refusal":
        check_refusal(run, baseline, report, args.mode, args.refuse)
    else:
        check_refusal_expired(run, baseline, report, args.mode)
    if args.keep:
        print(_dim(f"           saved: {_save(run, args.mode)}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
