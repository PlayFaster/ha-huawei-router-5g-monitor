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

Usage, inside the devcontainer, **from anywhere** — paths are resolved from
`__file__`, not the working directory:

    /usr/local/bin/python scripts/diag_check.py             # two runs, diffed
    /usr/local/bin/python scripts/diag_check.py --once      # one run, no diff
    /usr/local/bin/python scripts/diag_check.py --sabotage  # expiry mid-poll
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

# Installs probatio as `voluptuous` before the package imports it (C-036).
import homeassistant  # noqa: F401

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

try:
    from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI
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


def _credentials() -> tuple[dict[str, Any], dict[str, Any], str, str]:
    """Read the router entry from the configured Home Assistant instance."""
    with CONFIG_ENTRIES.open() as handle:
        stored = json.load(handle)
    for entry in stored["data"]["entries"]:
        if entry["domain"] == "huawei_router_5g":
            return (
                dict(entry["options"]),
                dict(entry["data"]),
                str(entry["entry_id"]),
                str(entry.get("title") or "Huawei Router"),
            )
    raise SystemExit(f"no huawei_router_5g entry in {CONFIG_ENTRIES}")


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


async def produce(
    label: str, report: Report, *, sabotage: bool = False
) -> dict[str, Any]:
    """Build a coordinator against the live router and return one download."""
    from homeassistant.core import HomeAssistant

    options, data, entry_id, title = _credentials()
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
    if sabotage:
        HuaweiRouter5GAPI._ensure_client = _sabotaging_ensure(  # type: ignore[method-assign]  # noqa: SLF001
            original
        )
    try:
        # A cold coordinator does not always produce a payload on its first
        # poll: startup reconciliation can defer a cycle, and a paused entry
        # takes the safe startup bypass. Polled to a payload rather than a
        # fixed count, because how many deferrals happen is the coordinator's
        # business and not this script's to encode.
        for _ in range(1 if sabotage else POLL_ATTEMPTS):
            coordinator._force_refresh_once = True  # noqa: SLF001 - nothing to debounce on
            try:
                coordinator.data = await coordinator._async_update_data()  # noqa: SLF001
            except Exception as err:  # noqa: BLE001 - a failed poll is the subject
                print(_dim(f"           [poll raised {type(err).__name__}: {err}]"))
            if coordinator.data:
                break

        result = await async_get_config_entry_diagnostics(hass, entry_as_config)
    finally:
        HuaweiRouter5GAPI._ensure_client = original  # type: ignore[method-assign]  # noqa: SLF001
        await api.logout()

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
    report.record(
        all(
            o in {"answered", "refused", "expired", "unavailable", "skipped"}
            for o in outcomes
        ),
        f"[{label}] every outcome is one of the known verdicts",
        f"outcomes: {outcomes}",
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
        if isinstance(value, dict) and value.get("outcome") != "answered"
    }
    report.record(
        bool(disturbed),
        f"[{label}] the endpoint map names what the lost session cost",
        f"{len(disturbed)} not answered: {sorted(disturbed)[:5]}"
        if disturbed
        else "every endpoint answered — the sabotage did not land",
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
        all(o in {"answered", "refused", "unavailable"} for o in outcomes),
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
    parser.add_argument(
        "--keep", action="store_true", help="save the produced downloads"
    )
    args = parser.parse_args()

    report = Report()
    options, data, _, _ = _credentials()
    secrets = _secrets(options, data)

    first = await produce("1", report, sabotage=args.sabotage)
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
    if args.sabotage:
        check_sabotage(first, report, "1")
    check_redaction(first, secrets, report, "1")
    if args.keep:
        print(_dim(f"           saved: {_save(first, 'run1')}"))

    # A sabotaged run loses endpoints on purpose, so diffing it against a clean
    # one reports the sabotage as instability. The second run is skipped rather
    # than compared and tolerated.
    if not args.once and not args.sabotage:
        second = await produce("2", report)
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
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
