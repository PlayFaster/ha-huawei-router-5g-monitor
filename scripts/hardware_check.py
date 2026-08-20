"""Exercise the write path against a real router, and record what it answers.

Not part of CI, and not a unit test. This exists because the unit suite cannot
falsify a wrong belief about the device or its library: a mock is written from
the model, so a test built on a wrong model passes while the code is broken.

**This project supplied the textbook case on 2026-08-14.** Clear Traffic
Statistics called `Monitoring.clear_traffic()` and Logout called
`Connection.logout()`. Neither method has ever existed in `huawei-lte-api`.
Both calls sat under a `# type: ignore[attr-defined]`, so mypy was silent; the
Clear Traffic test asserted the wrong method name against a bare `MagicMock`,
so pytest was silent too. Every layer of static and unit checking agreed the
code was correct, because every layer was consulting the same wrong model.
**Only a real router can say otherwise.** That is what this script is for.

Two tiers, and the separation is the whole safety story:

  1. **Unattended** — only writes classified `SAFE` in
     `scripts/write_classification.py`. Today that is `logout` alone, because
     Huawei's write surface is otherwise radio and network state, where a
     script dying mid-way leaves the household without internet. The check
     round-trips a login, a read, a logout and a read-back, which is the only
     way to see a logout that silently does nothing: failure there is swallowed
     by design, since a failed logout must never block an unload.

  2. **Attended, under `--attended`** — the writes that cannot be made quiet.
     Each is offered one at a time, behind its own confirmation, with the cost
     stated *before* the prompt. Nothing in this tier runs without a human
     answering `y`, and the default answer is always no.

`send_sms` and `delete_sms` are offered as **one paired check**, added
2026-08-16. They were previously excluded on the grounds that both need a target
typed at a prompt, where a mistyped number sends a real message to a stranger
and a mistyped index destroys the wrong message. That objection was about
*typing a target*, not about the writes, and it is answered by never asking for
one: the message goes to the SIM's own `Msisdn`, read from the router, and the
delete only ever targets the index that check just created. Neither is offered
alone — a send with no delete leaves litter, and a delete with no send has
nothing safe to remove.

The send may still cost money with your operator, which is why it is the one
check that names its cost in the prompt.

Usage, inside the devcontainer, **from anywhere** — paths are resolved from
`__file__`, not the working directory:

    /usr/local/bin/python scripts/hardware_check.py             # safe tier only
    /usr/local/bin/python scripts/hardware_check.py --attended  # + prompted tier

**Use the container interpreter, not `uv run`.** This imports the integration,
which imports Home Assistant; only `/usr/local/bin/python` has those installed.

Reads credentials from the configured Home Assistant entry — nothing is passed
on the command line, and nothing is printed. The router's own identifiers are
never echoed: this script's output is meant to be pasteable.
"""

# The console report is this script's entire output — there is no logger to
# route it through, and a caller reading the transcript is the point.
# ruff: noqa: T201

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import pathlib
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI
from custom_components.huawei_router_5g.switch import _guest_enable_flag
from scripts.write_classification import ATTENDED, OFFERED_WHEN_ATTENDED, SAFE

CONFIG_ENTRIES = pathlib.Path("/config/.storage/core.config_entries")
DOMAIN = "huawei_router_5g"

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Where the run is written. **Both are gitignored**, and the split is about
# what may be read casually, not about secrecy.
#
# The summary carries verdicts and non-identifying detail. The detail report
# carries the same rows with values that could identify a person or a device —
# the SIM's own number, an SMS sender, message text — and is written only when
# a check actually captured one. A run that never touches PII leaves no file in
# `local_only`, rather than an empty one nobody knows is empty.
REPORT_DIR = PROJECT_ROOT / ".reports"
DETAIL_DIR = PROJECT_ROOT / ".notes" / "local_only"

# Long-lived access token for driving the running Home Assistant instance.
# Read from the file the owner maintains; never taken from `.storage/auth`,
# and never written to either report.
HA_URL = "http://localhost:8123"
HA_TOKEN_FILE = PROJECT_ROOT / ".notes" / "ha_restart" / "token.txt"

# Seconds to let the radio re-register before reading a value back. Only the
# attended tier waits: nothing in the safe tier disturbs the connection.
RECONNECT_SETTLE = 15.0

# An SMS to your own number is not instant and delivery is the network's, not
# the router's. Six polls at five seconds gives it thirty seconds before the
# check gives up and tells the operator to delete it by hand.
SMS_DELIVERY_POLL = 5.0
SMS_DELIVERY_ATTEMPTS = 6

# A reboot on the reference B535 takes well under three minutes; the budget is
# generous because a slow return is a wait, not a failure.
REBOOT_TIMEOUT = 300.0

# Longest any single check may run before it is recorded as stalled.
#
# The script had no per-check timeout, so a deadlocked write hung the whole run
# with no report written — which is exactly what the 2026-08-17 network-mode
# deadlock would have done had the script been re-run. An operator watching it
# would have seen the run stop and learned nothing. A timeout turns that into a
# named failure in the report.
#
# Generous on purpose: `set_net_mode` settles for `NET_MODE_SETTLE` and reads
# back, and a toggle-and-restore does two writes plus two reads. Reboot is the
# one check that legitimately exceeds this and passes its own budget.
CHECK_TIMEOUT = 180.0
REBOOT_POLL = 15.0

# How long the Home Assistant contention check waits for the select to settle.
# A mode change re-registers the radio and the coordinator then has to poll, so
# this is deliberately longer than the write itself takes.
HA_SETTLE_POLL = 5.0
HA_SETTLE_ATTEMPTS = 12

# Colour is emitted unconditionally, the way `pytest --color=yes` is used by the
# sibling tasks: stdout here is usually a pipe into `tee`, so auto-detection
# would strip it exactly when it is wanted. `NO_COLOR` turns it off.
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


def _yellow(text: str) -> str:
    """Return text in bold yellow."""
    return _c("1;33", text)


def _cyan(text: str) -> str:
    """Return text in bold cyan."""
    return _c("1;36", text)


def _dim(text: str) -> str:
    """Return text dimmed, for supporting detail."""
    return _c("2", text)


WITHHELD = "[withheld - see the detail report]"


class Report:
    """Collects results so one failure does not hide the rest, and files them.

    **The filing is the point.** Until 2026-08-18 this class printed to stdout
    and kept a list; nothing was written anywhere, in either mode, so there was
    no way to examine a run afterwards and a skipped check left no trace at all
    — `skip()` printed and returned without recording. A hardware check whose
    results cannot be reviewed is a claim, not evidence.
    """

    def __init__(self, mode: str) -> None:
        """Start an empty report for one run."""
        self.mode = mode
        self.started = datetime.now(UTC)
        # status, name, public detail, sensitive detail (None when there is
        # nothing that could identify a person or a device).
        self.rows: list[tuple[str, str, str, str | None]] = []

    def record(
        self,
        ok: bool,
        name: str,
        detail: str = "",
        *,
        sensitive: str | None = None,
    ) -> None:
        """Print one result and remember it.

        `sensitive` carries the identifying form of the evidence — a phone
        number, message text. When present, `detail` must already be the
        redacted form: this class does not sanitise, it files what it is given
        on each side of the line.
        """
        self.rows.append(("PASS" if ok else "FAIL", name, detail, sensitive))
        badge = _green("✔  PASS") if ok else _red("✖  FAIL")
        suffix = _dim(f"  — {detail}") if detail else ""
        print(f"  {badge}  {name}{suffix}")

    def skip(self, name: str, why: str) -> None:
        """Note something deliberately not run. Not counted as a failure.

        **Recorded, not merely printed.** A skip that leaves no row is
        indistinguishable afterwards from a check that was never written, which
        is the difference between "we chose not to run it" and "nobody noticed
        it was missing".
        """
        self.rows.append(("SKIP", name, why, None))
        print(f"  {_yellow('○  SKIP')}  {name}{_dim(f'  — {why}')}")

    @property
    def checks(self) -> list[tuple[str, str, str, str | None]]:
        """Return the rows that ran, excluding skips."""
        return [row for row in self.rows if row[0] != "SKIP"]

    @property
    def failed(self) -> int:
        """Return how many checks failed, for the exit code."""
        return sum(1 for status, _, _, _ in self.rows if status == "FAIL")

    @property
    def skipped(self) -> int:
        """Return how many checks were deliberately not run."""
        return sum(1 for status, _, _, _ in self.rows if status == "SKIP")

    def _table(self, *, identifying: bool) -> str:
        """Render the rows, with or without the identifying evidence."""
        lines = ["| Result | Check | Evidence |", "| :-- | :-- | :-- |"]
        for status, name, detail, sensitive in self.rows:
            if sensitive is not None:
                evidence = sensitive if identifying else WITHHELD
            else:
                evidence = detail
            lines.append(f"| {status} | `{name}` | {evidence or '-'} |")
        return "\n".join(lines)

    def _header(self, title: str) -> str:
        """Render the run's identity and totals."""
        passed = sum(1 for status, _, _, _ in self.rows if status == "PASS")
        stamp = self.started.strftime("%Y-%m-%d %H:%M:%SZ")
        return (
            f"# {title}\n\n"
            f"**Project** `{DOMAIN}` · **Mode** {self.mode} · "
            f"**Started** {stamp}\n\n"
            f"**{passed} passed · {self.failed} failed · {self.skipped} skipped "
            f"· {len(self.rows)} rows.** Every check offered appears below; a "
            "check with no row was never reached, which is itself a finding.\n"
        )

    def write(self, coverage: str = "") -> list[pathlib.Path]:
        """Write the summary, and the identifying detail when there is any.

        Called from a `finally`, so an aborted run still files what it has.
        """
        stamp = self.started.strftime("%Y%m%d_%H%M%S")
        written: list[pathlib.Path] = []

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        summary = REPORT_DIR / f"hardware_check_{stamp}.md"
        body = self._header("Hardware check") + "\n" + self._table(identifying=False)
        if coverage:
            body += "\n\n" + coverage
        summary.write_text(body + "\n", encoding="utf-8")
        written.append(summary)

        if any(row[3] is not None for row in self.rows):
            DETAIL_DIR.mkdir(parents=True, exist_ok=True)
            detail = DETAIL_DIR / f"hardware_check_detail_{stamp}.md"
            detail.write_text(
                self._header("Hardware check - identifying detail")
                + "\n> This file holds values that identify a person or a "
                "device - the SIM's own number, an SMS sender, message text. "
                "It is gitignored and must not be pasted into a shared "
                "document.\n\n" + self._table(identifying=True) + "\n",
                encoding="utf-8",
            )
            written.append(detail)

        return written


class _Collector(logging.Handler):
    """Holds the integration's own log records for the duration of one check."""

    def __init__(self) -> None:
        """Collect at DEBUG, since the confirmation trail is logged there."""
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Keep the record rather than formatting it anywhere."""
        self.records.append(record)


@contextlib.contextmanager
def _capture_integration_log() -> Iterator[_Collector]:
    """Capture `custom_components.huawei_router_5g` records, then restore.

    **This is what makes the write-confirmation path checkable.** The script
    verifies from the device, so it passes whether `confirm_write` returned
    `True` or `None` — correct for testing the router, and it leaves the
    confirmation logic with no hardware verification at all. Reading the
    records turns "which of the three outcomes fired" into a reported check
    instead of something an operator has to notice in a log.

    It raises the logger's own level for the duration, so no flag is needed
    and the ordinary run is the complete one.
    """
    logger = logging.getLogger("custom_components.huawei_router_5g")
    collector = _Collector()
    previous = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(collector)
    try:
        yield collector
    finally:
        logger.removeHandler(collector)
        logger.setLevel(previous)


def _confirmation_outcome(records: list[logging.LogRecord]) -> tuple[bool, str]:
    """Say which Section 22 outcome the net-mode write took, and whether it is ok.

    Matched on the log text rather than on internals, which is deliberately
    looser coupling — but it is coupling: reword these messages in `api.py` and
    this check goes quiet rather than failing. The fragments chosen are the
    ones that carry the meaning, not incidental wording.
    """
    messages = [record.getMessage() for record in records]

    if any("refused by the router" in message for message in messages):
        return False, "refused - the read-back disagreed twice"
    if any("could not be confirmed" in message for message in messages):
        return (
            False,
            "unverified - the router did not answer the read-back, so the "
            "confirmation decided nothing",
        )
    if any("answered -1 while re-registering" in message for message in messages):
        return True, "confirmed by read-back after the -1 answer"
    return True, "accepted outright - the router did not answer -1"


def _credentials() -> dict[str, Any]:
    """Read the router credentials from the configured Home Assistant entry."""
    if not CONFIG_ENTRIES.exists():
        raise SystemExit(
            f"{CONFIG_ENTRIES} not found. Run this inside the devcontainer, "
            "with the integration configured against a real router."
        )
    with CONFIG_ENTRIES.open(encoding="utf-8") as handle:
        data = json.load(handle)
    for entry in data["data"]["entries"]:
        if entry["domain"] == DOMAIN:
            return dict(entry["options"])
    raise SystemExit(f"no {DOMAIN} entry in {CONFIG_ENTRIES}")


def _api() -> HuaweiRouter5GAPI:
    """Build an API client from the configured entry."""
    options = _credentials()
    return HuaweiRouter5GAPI(
        options["host"],
        options.get("username") or None,
        options["password"],
    )


# ---------------------------------------------------------------------------
# Unattended tier
# ---------------------------------------------------------------------------


async def check_login_and_read(api: HuaweiRouter5GAPI, report: Report) -> None:
    """Log in and take one full read, as the precondition for everything else.

    Recorded as a result even though it is not a write: when it fails, every
    later FAIL is noise, and a reader needs to see which one to believe.
    """
    try:
        await api.login()
        data = await api.get_data()
    except Exception as err:  # noqa: BLE001 - the report is the error channel
        report.record(False, "login and first read", type(err).__name__)
        return

    blocks = sorted(k for k, v in data.items() if v)
    report.record(
        bool(blocks),
        "login and first read",
        f"{len(blocks)} populated blocks",
    )


async def check_read_back_endpoints(api: HuaweiRouter5GAPI, report: Report) -> None:
    """Every Section 22 read-back must return the key its caller compares.

    **This is the check that mocks cannot make.** `confirm_write` compares one
    key out of one endpoint, and every unit test around it supplies the block
    itself — so the tests prove the comparison logic and prove nothing about
    whether the router answers in that shape. If a key is absent or spelled
    differently, `confirm_write` returns `None` for ever: each write reports
    *unverified*, never confirmed and never refused, and nothing errors. The
    mechanism degrades to doing nothing, silently.

    A read only. Nothing here changes router state.
    """
    expected = {
        "mobile_dataswitch": "dataswitch",
        "monitoring_status": "WifiStatus",
        # Added 2026-08-19. Its absence was the one real gap the lockup review
        # found: nothing had ever confirmed the router returns `NetworkMode` in
        # the shape `confirm_write` compares. A renamed or missing key would
        # make every network-mode write report *unverified* for ever, with
        # nothing erroring and no check noticing — the silent degradation this
        # whole check exists to catch.
        "net_mode": "NetworkMode",
    }

    for endpoint, key in expected.items():
        try:
            block = await api.read_back(endpoint)
        except Exception as err:  # noqa: BLE001 - the report is the error channel
            report.record(False, f"read-back {endpoint}", type(err).__name__)
            continue

        if block is None:
            report.record(False, f"read-back {endpoint}", "returned None")
            continue

        report.record(
            key in block,
            f"read-back {endpoint}.{key}",
            f"{key}={block.get(key)!r}"
            if key in block
            else f"keys: {sorted(block)[:6]}",
        )

    # The guest flag is nested inside the SSID list rather than being a flat
    # key, so the extractor is exercised rather than a `.get()`.
    try:
        block = await api.read_back("wlan_multi_basic_settings")
    except Exception as err:  # noqa: BLE001 - the report is the error channel
        report.record(False, "read-back wlan_multi_basic_settings", type(err).__name__)
        return

    if block is None:
        report.record(False, "read-back wlan_multi_basic_settings", "returned None")
        return

    flag = _guest_enable_flag(block)
    report.record(
        flag is not None,
        "read-back guest WiFi flag",
        f"WifiEnable={flag!r}" if flag is not None else "no guest SSID found",
    )


async def check_logout_ends_the_session(api: HuaweiRouter5GAPI, report: Report) -> None:
    """`logout` must actually end the session, not merely return.

    **This is the check that would have caught the real defect.** `logout`
    called `Connection.logout()`, which does not exist; the `AttributeError`
    was swallowed, because a failed logout must not block a Home Assistant
    unload. The method therefore returned cleanly while leaking a session on
    every reload, and no unit test could see it — a mock has whatever method
    the test asks for.

    Read back, not asserted from the return value. The only evidence that
    counts is the router's own view of the session.
    """
    held_before = api._client is not None  # noqa: SLF001 - reading state
    try:
        await api.logout()
    except Exception as err:  # noqa: BLE001 - the report is the error channel
        report.record(False, "logout returns cleanly", type(err).__name__)
        return

    report.record(
        True,
        "logout returns cleanly",
        f"session was {'open' if held_before else 'already closed'} before the call",
    )

    # The client is reset on the way out, so a subsequent read has to build a
    # new connection. That it succeeds proves the credentials still work; that
    # it had to reconnect is what `_client is None` records.
    ended = api._client is None  # noqa: SLF001 - reading state, not driving it
    report.record(
        ended,
        "logout released the client",
        "reconnect required for the next read" if ended else "client still held",
    )

    try:
        await api.login()
        data = await api.get_data()
    except Exception as err:  # noqa: BLE001 - the report is the error channel
        report.record(False, "session re-establishes after logout", type(err).__name__)
        return
    report.record(
        True,
        "session re-establishes after logout",
        f"{sum(1 for value in data.values() if value)} populated blocks on the "
        "new session",
    )


# ---------------------------------------------------------------------------
# Attended tier
# ---------------------------------------------------------------------------


def _confirm(prompt: str) -> bool:
    """Ask, defaulting to no. A closed stdin is a no, never a yes."""
    try:
        return input(f"  {prompt} [y/N] ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


async def _offer(
    report: Report,
    name: str,
    cost: str,
    run: Any,
    timeout: float = CHECK_TIMEOUT,
) -> None:
    """Offer one attended write, stating its cost before the prompt.

    The timeout is the point of this wrapper as much as the prompt is. A check
    that hangs — a deadlocked write is the case that prompted it — would
    otherwise stall the run with no report written at all.
    """
    print()
    print(f"  {_cyan(name)}")
    for line in cost.splitlines():
        print(f"    {_dim(line)}")
    if not _confirm(f"run {name}?"):
        report.skip(name, "declined")
        return
    try:
        async with asyncio.timeout(timeout):
            await run()
    except TimeoutError:
        # Before the broad handler: TimeoutError is an OSError, so the order
        # here is what keeps a stall distinguishable from a device error.
        report.record(False, name, f"stalled - no result within {timeout:.0f}s")
    except Exception as err:  # noqa: BLE001 - the report is the error channel
        report.record(False, name, f"{type(err).__name__}: {err}")


async def _timed(report: Report, name: str, run: Any) -> None:
    """Run one unattended check under the same stall guard as `_offer`."""
    try:
        async with asyncio.timeout(CHECK_TIMEOUT):
            await run()
    except TimeoutError:
        report.record(False, name, f"stalled - no result within {CHECK_TIMEOUT:.0f}s")
    except Exception as err:  # noqa: BLE001 - the report is the error channel
        report.record(False, name, f"{type(err).__name__}: {err}")


async def _toggle_and_restore(
    api: HuaweiRouter5GAPI,
    report: Report,
    name: str,
    read: Any,
    write: Any,
    headers: dict[str, str] | None = None,
    key: str | None = None,
) -> None:
    """Flip a boolean write, read it back, and put it back as it was.

    Restores on the failure path too. A script that leaves guest WiFi on, or
    mobile data off, has done more harm than the check was worth.
    """
    before = await read()
    if before is None:
        report.record(False, name, "could not read the current value")
        return
    try:
        await write(not before)
        await asyncio.sleep(RECONNECT_SETTLE)
        after = await read()
        report.record(
            after is not None and after != before,
            name,
            f"{before} -> {after}",
        )

        # Second row, second question. The one above says the router changed;
        # this says Home Assistant told the user so.
        if key is not None:
            await _check_published_state(report, headers, name, key, not before)
    finally:
        try:
            await write(before)
        except Exception as err:  # noqa: BLE001 - restoration must be reported
            report.record(False, f"{name} restore", f"{type(err).__name__}: {err}")
        else:
            # Recorded, not merely printed. "Was the house put back?" is the
            # question an attended run most needs to answer afterwards, and
            # until 2026-08-18 only a *failed* restore left a row — so a report
            # showing nothing meant either a clean restore or a check that
            # never got that far.
            report.record(True, f"{name} restore", f"put back to {before}")
            print(f"    {_dim(f'restored to {before}')}")


async def _mobile_data_state(api: HuaweiRouter5GAPI) -> bool | None:
    """Read the current mobile-data switch position."""
    data = await api.get_data()
    raw = (data.get("mobile_dataswitch") or {}).get("dataswitch")
    return None if raw is None else raw == "1"


async def _wifi_state(api: HuaweiRouter5GAPI) -> bool | None:
    """Read whether the WiFi radios are on."""
    data = await api.get_data()
    raw = (data.get("monitoring_status") or {}).get("WifiStatus")
    return None if raw in (None, "") else str(raw) == "1"


async def _guest_wifi_state(api: HuaweiRouter5GAPI) -> bool | None:
    """Read whether any SSID flagged as a guest network is enabled."""
    data = await api.get_data()
    ssids = (data.get("wlan_multi_basic_settings") or {}).get("Ssids", {})
    entries = ssids.get("Ssid", [])
    if isinstance(entries, dict):
        entries = [entries]
    guests = [s for s in entries if s.get("wifiisguestnetwork") == "1"]
    if not guests:
        return None
    return any(s.get("WifiEnable") == "1" for s in guests)


async def check_attended_writes(api: HuaweiRouter5GAPI, report: Report) -> None:
    """Offer every ATTENDED write this script is willing to drive.

    The set offered here is asserted against the register by
    `tests/test_write_classification.py`, in both directions: nothing offered
    may be outside the ATTENDED tier, and nothing the register claims is
    offered may be missing from this file.
    """
    # Read once, at the top: every write check now verifies what Home
    # Assistant published as well as what the router holds.
    headers = _ha_headers()
    print()
    print(_yellow("  Attended tier - each write is confirmed separately."))
    print(_dim("  Answering anything but 'y' skips. Ctrl-C also skips."))

    # The guest SSID is gated by the radio: with WiFi off, writing the per-SSID
    # flag changes nothing observable and the check would pass or fail on
    # nothing. **The radio is normally off on the reference unit**, so this is
    # the usual case and not an edge one. Skipping loudly beats reporting a
    # result that means nothing.
    radio_on = await _wifi_state(api)
    if radio_on is None:
        print()
        print(
            f"    {_yellow('WifiStatus unreadable - guest result may not be meaningful')}"
        )
    await _offer(
        report,
        "set_guest_wifi",
        "Toggles the guest network and puts it back.\n"
        "On the reference B535 the guest SSID is OPEN - unauthenticated - so a\n"
        "crash between the toggle and the restore leaves it broadcasting.\n"
        "If the WiFi radio is off it is turned ON for this check and put back,\n"
        "because the guest SSID is gated by the radio and cannot be observed\n"
        "without it.",
        lambda: _check_guest_wifi(api, report, radio_on, headers),
    )

    await _offer(
        report,
        "set_wifi",
        "Toggles the WiFi radios and puts them back.\n"
        "Every wireless client in the house drops while they are off, and a\n"
        "crash between the toggle and the restore leaves them down.",
        lambda: _toggle_and_restore(
            api,
            report,
            "set_wifi",
            lambda: _wifi_state(api),
            api.set_wifi,
            headers=headers,
            key="wifi",
        ),
    )

    await _offer(
        report,
        "set_mobile_data",
        "Turns the mobile data connection off, reads it back, turns it on.\n"
        "The household has no internet for roughly "
        f"{RECONNECT_SETTLE:.0f} seconds, and longer if\n"
        "this script dies in between.",
        lambda: _toggle_and_restore(
            api,
            report,
            "set_mobile_data",
            lambda: _mobile_data_state(api),
            api.set_mobile_data,
            headers=headers,
            key="mobile_data",
        ),
    )

    if headers is None:
        report.skip(
            "ha_contention",
            f"no token at {HA_TOKEN_FILE.name} - the Home Assistant checks "
            "need one to drive the running instance",
        )
    else:
        await _offer(
            report,
            "ha_contention",
            "Changes Preferred Network Mode THROUGH Home Assistant and presses\n"
            "Refresh immediately - the exact sequence that deadlocked the\n"
            "integration on 2026-08-17. Re-registers the radio; the mode is put\n"
            "back afterwards.",
            lambda: _check_ha_contention(report, headers),
        )

    await _offer(
        report,
        "set_net_mode",
        "Re-registers the radio twice - once to the test mode, once back.\n"
        "Mobile data drops for roughly "
        f"{RECONNECT_SETTLE * 2:.0f} seconds. The original mode is\n"
        "restored and the restore is verified against the router.",
        lambda: _check_net_mode(api, report),
    )

    await _offer(
        report,
        "send_sms / delete_sms",
        "Sends one message to the SIM's own number, then deletes it.\n"
        "YOUR OPERATOR MAY CHARGE FOR THIS. Nothing else in this suite costs\n"
        "money. The delete only ever targets the message this check sent.",
        lambda: _check_send_and_delete_sms(api, report),
    )

    await _offer(
        report,
        "clear_traffic_statistics",
        "IRREVERSIBLE. Zeroes the router's byte counters, and puts a step\n"
        "change into Home Assistant's long-term statistics for every total\n"
        "sensor. Nothing can put either back.",
        lambda: _check_clear_traffic(api, report),
    )

    await _offer(
        report,
        "reconnect",
        "Drops the data session and re-establishes it. Seconds of downtime,\n"
        "nothing left in a changed state. The router answers with blank values\n"
        "while it re-registers, so a populated read is the only proof it came back.",
        lambda: _check_reconnect(api, report),
    )

    await _offer(
        report,
        "reboot",
        f"Minutes of downtime. Waits up to {REBOOT_TIMEOUT:.0f}s for the router\n"
        "to answer again. Nothing is left in a changed state.",
        lambda: _check_reboot(api, report),
        timeout=REBOOT_TIMEOUT + 60,
    )


async def _check_guest_wifi(
    api: HuaweiRouter5GAPI,
    report: Report,
    radio_on: bool | None,
    headers: dict[str, str] | None,
) -> None:
    """Exercise the guest SSID, turning the radio on first when it is off.

    **This used to skip itself and it should not have.** The guest SSID is
    gated by the radio, and the radio is normally off on the reference unit, so
    the auto-skip fired in the ordinary case — leaving the one write that
    touches an open, unauthenticated network as the least-exercised of the set.
    "Cannot be observed with the radio off" is a reason to turn the radio on,
    not a reason to give up: `set_wifi` in this same run already toggles it and
    puts it back, so the exposure was accepted one check earlier.
    """
    enabled_here = False
    try:
        if radio_on is False:
            await api.set_wifi(enable=True)
            await asyncio.sleep(RECONNECT_SETTLE)
            enabled_here = True
            report.record(
                True,
                "set_guest_wifi radio enabled",
                "radio was off; turned on so the guest SSID can be observed",
            )

        await _toggle_and_restore(
            api,
            report,
            "set_guest_wifi",
            lambda: _guest_wifi_state(api),
            api.set_guest_wifi,
            headers=headers,
            key="guest_wifi",
        )
    finally:
        if enabled_here:
            try:
                await api.set_wifi(enable=False)
            except Exception as err:  # noqa: BLE001 - restoration must be reported
                report.record(
                    False,
                    "set_guest_wifi radio restore",
                    f"{type(err).__name__}: {err} - the radio is still ON",
                )
            else:
                report.record(
                    True, "set_guest_wifi radio restore", "radio put back off"
                )


async def _check_net_mode(api: HuaweiRouter5GAPI, report: Report) -> None:
    """Set the network mode to auto and confirm the router accepted it."""
    data = await api.get_data()
    current = (data.get("net_mode") or {}).get("NetworkMode")
    print(f"    {_dim(f'current NetworkMode is {current!r}')}")

    # The target must differ from the current mode, or the write proves nothing
    # either way. `00` (Auto) is the least disruptive target; when the router is
    # already on Auto, `03` (4G Only) is the fallback — still a mode this
    # hardware holds, and the check restores nothing, so the operator is told.
    target = "03" if current == "00" else "00"
    print(f"    {_dim(f'setting {target!r}')}")

    try:
        with _capture_integration_log() as captured:
            await api.set_net_mode(target)
        await asyncio.sleep(RECONNECT_SETTLE)

        after = (await api.get_data()).get("net_mode", {}).get("NetworkMode")
        report.record(
            after == target,
            "set_net_mode",
            f"before {current!r}, target {target!r}, after {after!r}",
        )

        # A separate row, because it answers a separate question. The row above
        # says the router holds the new mode; this one says whether the
        # integration's own confirmation reached a verdict or quietly did
        # nothing.
        ok, outcome = _confirmation_outcome(captured.records)
        report.record(ok, "set_net_mode confirmation", outcome)
    finally:
        # **Restored, like every other write here.** This check used to print
        # "set it back yourself" and leave the radio on whatever it had chosen,
        # on the reasoning that a mode the serving cell handles poorly might not
        # come back on its own. That reasoning does not survive inspection: the
        # router is reached over the LAN, and the LAN is not carried by the
        # cellular mode — the write back is the same local call that got us
        # here, and it works whether or not the data session came up.
        if current:
            try:
                await api.set_net_mode(current)
                await asyncio.sleep(RECONNECT_SETTLE)
                restored = (await api.get_data()).get("net_mode", {}).get("NetworkMode")
            except Exception as err:  # noqa: BLE001 - restoration must be reported
                report.record(
                    False, "set_net_mode restore", f"{type(err).__name__}: {err}"
                )
            else:
                report.record(
                    restored == current,
                    "set_net_mode restore",
                    f"put back to {current!r}, router reports {restored!r}",
                )


def _ha_headers() -> dict[str, str] | None:
    """Return the auth header for the running Home Assistant, or None.

    The token is read from the file the owner maintains. It is never taken from
    `.storage/auth`, and it is never written to either report.
    """
    if not HA_TOKEN_FILE.exists():
        return None
    token = HA_TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _ha_get(path: str, headers: dict[str, str]) -> Any:
    """GET one Home Assistant REST path."""
    response = requests.get(f"{HA_URL}{path}", headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()


def _ha_post(path: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
    """POST one Home Assistant service call."""
    response = requests.post(
        f"{HA_URL}{path}", headers=headers, json=payload, timeout=30
    )
    response.raise_for_status()


def _ha_log_length(headers: dict[str, str]) -> int:
    """Return the current length of Home Assistant's error log, in characters."""
    response = requests.get(f"{HA_URL}/api/error_log", headers=headers, timeout=15)
    response.raise_for_status()
    return len(response.text)


def _ha_log_since(headers: dict[str, str], offset: int) -> list[str]:
    """Return this integration's WARNING and ERROR lines added since `offset`.

    **The one blind spot in the one check that runs inside Home Assistant.**
    Everything else here verifies against the router; `ha_contention` verifies
    against entity state, and an error Home Assistant logged that did not move
    an entity was invisible to the report.

    Only matching lines are returned, and they go to the identifying report:
    the log carries SSIDs, addresses and client names that are not this
    script's to publish.

    Deliberately does not need HA debug logging. The two outcomes that matter
    are logged at WARNING and ERROR, which the default level already captures;
    only the healthy "answered -1" line is DEBUG.
    """
    response = requests.get(f"{HA_URL}/api/error_log", headers=headers, timeout=15)
    response.raise_for_status()
    added = response.text[offset:]
    return [
        line
        for line in added.splitlines()
        if DOMAIN in line and ("ERROR" in line or "WARNING" in line)
    ]


def _find_entity(states: list[dict[str, Any]], domain: str, *words: str) -> str | None:
    """Return the first entity in `domain` whose friendly name carries `words`."""
    for state in states:
        entity_id = str(state.get("entity_id", ""))
        if not entity_id.startswith(f"{domain}."):
            continue
        name = str(state.get("attributes", {}).get("friendly_name", "")).lower()
        if all(word in name for word in words):
            return entity_id
    return None


def _find_switch(states: list[dict[str, Any]], key: str) -> str | None:
    """Return the switch entity for one description key.

    Matched on `entity_id` rather than friendly name, because names are
    translated and keys are not. `guest_wifi` also ends with `wifi`, so the
    master WiFi switch excludes it explicitly - matching the longest key
    instead would silently pick the wrong entity when a key is added.
    """
    for state in states:
        entity_id = str(state.get("entity_id", ""))
        if not entity_id.startswith("switch."):
            continue
        if not entity_id.endswith(f"_{key}"):
            continue
        if key == "wifi" and entity_id.endswith("_guest_wifi"):
            continue
        return entity_id
    return None


async def _check_published_state(
    report: Report,
    headers: dict[str, str] | None,
    name: str,
    key: str,
    expected: bool,
) -> None:
    """Assert Home Assistant publishes what the router was just told.

    **The gap this closes.** Every other write check verifies the *router*, by
    reading the value back through the API. The router was never the problem in
    the 2026-08-19 switch defect: the write landed, the read-back confirmed it,
    and Home Assistant published the pre-write value anyway. Four clean runs of
    this script reported PASS on write paths that showed users the wrong state,
    because nothing here had ever asked what the integration published.

    **Additive, never a replacement.** The device row still runs and still
    means what it meant; this is a second row answering a second question.

    **The refresh is not optional.** Entity state is whatever the last poll
    produced, and polling may be paused or on a long interval, so without
    forcing a fetch this would read a stale entity and pass or fail on timing
    rather than on behaviour. Refresh Now reaches the router even while Pause
    Polling is on, by the Section 13 contract.
    """
    if headers is None:
        report.skip(f"{name} published", "no Home Assistant token")
        return

    states = await asyncio.to_thread(_ha_get, "/api/states", headers)
    entity_id = _find_switch(states, key)
    button_id = _find_entity(states, "button", "refresh")
    if entity_id is None or button_id is None:
        report.skip(f"{name} published", "entity or Refresh button not found")
        return

    await asyncio.to_thread(
        _ha_post, "/api/services/button/press", headers, {"entity_id": button_id}
    )

    want = "on" if expected else "off"
    state = ""
    for _ in range(HA_SETTLE_ATTEMPTS):
        await asyncio.sleep(HA_SETTLE_POLL)
        fresh = await asyncio.to_thread(_ha_get, f"/api/states/{entity_id}", headers)
        state = str(fresh.get("state"))
        if state == want:
            break

    report.record(
        state == want,
        f"{name} published",
        f"{entity_id} reads {state!r} after a refresh; the router was set to {want!r}",
    )


async def _check_ha_contention(report: Report, headers: dict[str, str]) -> None:
    """Change the mode through Home Assistant, then press Refresh immediately.

    **This is the reported failure, reproduced.** Every other check in this
    file calls the API object directly: one caller, no coordinator, no
    contention. The 2026-08-17 lockup needed a write and a poll competing for
    the same lock, which only happens inside a running Home Assistant — so it
    was outside this script's reach until the script learned to drive HA.

    Against the pre-fix code the select would have hung and every entity would
    have gone unavailable and stayed there, so this is a real regression check
    and not a smoke test.
    """
    states = await asyncio.to_thread(_ha_get, "/api/states", headers)

    select_id = _find_entity(states, "select", "network mode")
    button_id = _find_entity(states, "button", "refresh")
    if select_id is None or button_id is None:
        report.skip(
            "ha_contention",
            "the Network Mode select or the Refresh button is not present in "
            "this Home Assistant instance",
        )
        return

    current = next(s for s in states if s["entity_id"] == select_id)
    options = list(current.get("attributes", {}).get("options", []))
    before = str(current.get("state"))
    target = next((o for o in options if o != before), None)
    if target is None:
        report.skip("ha_contention", f"{select_id} offers no alternative option")
        return

    print(f"    {_dim(f'{select_id}: {before!r} -> {target!r}, then Refresh')}")

    # Where Home Assistant's own log stands before the write, so the diff
    # afterwards is this check's output and not the session's history.
    try:
        log_offset: int | None = await asyncio.to_thread(_ha_log_length, headers)
    except Exception as err:  # noqa: BLE001 - the report is the error channel
        log_offset = None
        report.record(
            False, "ha_contention log readable", f"{type(err).__name__}: {err}"
        )

    try:
        await asyncio.to_thread(
            _ha_post,
            "/api/services/select/select_option",
            headers,
            {"entity_id": select_id, "option": target},
        )
        # Immediately, with no settle: pressing Refresh straight after the
        # write is what the owner did, and it is the contention being tested.
        await asyncio.to_thread(
            _ha_post,
            "/api/services/button/press",
            headers,
            {"entity_id": button_id},
        )

        # The integration must still be answering. `unavailable` here is the
        # lockup signature: the write wedged the lock and every poll behind it
        # died at the coordinator's timeout.
        state = ""
        for _ in range(HA_SETTLE_ATTEMPTS):
            await asyncio.sleep(HA_SETTLE_POLL)
            fresh = await asyncio.to_thread(
                _ha_get, f"/api/states/{select_id}", headers
            )
            state = str(fresh.get("state"))
            if state == target:
                break

        report.record(
            state not in ("unavailable", "unknown"),
            "ha_contention entity survives",
            f"{select_id} reads {state!r} after the write and an immediate "
            "Refresh press",
        )
        report.record(
            state == target,
            "ha_contention write applied",
            f"expected {target!r}, got {state!r}",
        )

        if log_offset is not None:
            complaints = await asyncio.to_thread(_ha_log_since, headers, log_offset)
            report.record(
                not complaints,
                "ha_contention no complaints in the HA log",
                f"{len(complaints)} warning/error line(s) from {DOMAIN}"
                if complaints
                else "no warnings or errors logged during the write and refresh",
                sensitive="\n".join(complaints) if complaints else None,
            )
    finally:
        # Put the mode back. The router keeps whatever it was last told, so a
        # crash between the write and here leaves the radio where the check
        # moved it.
        with contextlib.suppress(Exception):
            await asyncio.to_thread(
                _ha_post,
                "/api/services/select/select_option",
                headers,
                {"entity_id": select_id, "option": before},
            )


def _coverage_section(report: Report) -> str:
    """Render what the register expects against what this run actually did.

    Answers "what was not checked" from the report itself, rather than from
    reading this file. A write that is classified and never exercised is the
    exact failure the register exists to prevent, and it was invisible here
    until 2026-08-18.
    """
    ran = {name.split()[0] for _, name, _, _ in report.rows}
    lines = [
        "## Write coverage this run",
        "",
        "From `scripts/write_classification.py`. `not offered` means the check "
        "was never reached — a declined prompt is recorded as `SKIP` in the "
        "table above, which is a different thing.",
        "",
        "| Write | Tier | This run |",
        "| :-- | :-- | :-- |",
    ]
    for name in sorted(SAFE):
        state = "exercised" if name in ran else "not offered"
        lines.append(f"| `{name}` | SAFE | {state} |")
    for name in sorted(ATTENDED):
        if name in ran:
            state = next(
                status for status, row, _, _ in report.rows if row.split()[0] == name
            )
        elif name in OFFERED_WHEN_ATTENDED:
            state = "not offered"
        else:
            state = "not scripted"
        lines.append(f"| `{name}` | ATTENDED | {state} |")
    return "\n".join(lines)


async def _check_send_and_delete_sms(api: HuaweiRouter5GAPI, report: Report) -> None:
    """Send a message to the router's own SIM, then delete it.

    **These two are paired on purpose.** `send_sms` alone leaves a message in
    the store; `delete_sms` alone has nothing safe to delete — deleting an
    arbitrary index would destroy a real message. Sending to the SIM's own
    number produces something this script owns and may remove.

    The send may cost money. That is why the prompt states it and why this is
    the only check that asks the operator to confirm a number.
    """
    data = await api.get_data()
    own = (data.get("device_information") or {}).get("Msisdn")
    if not own:
        report.skip(
            "send_sms", "the SIM reports no number, so there is nowhere safe to send"
        )
        report.skip("delete_sms", "no message was sent, so there is nothing to delete")
        return

    print(f"    {_dim(f'sending to the SIM own number {own!r}')}")
    if not _confirm(f"send an SMS to {own}? (your operator may charge)"):
        report.skip("send_sms", "declined")
        report.skip("delete_sms", "no message was sent")
        return

    marker = f"hardware_check {datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}"
    before = await _sms_indexes(api)
    await api.send_sms([own], marker)
    report.record(
        True,
        "send_sms",
        f"sent {marker!r} to the SIM's own number",
        sensitive=f"sent {marker!r} to {own!r}",
    )

    # Delivery is not instant and is not this integration's to guarantee, so
    # poll rather than assume. A message that never arrives is a delivery
    # question, not a defect in the write.
    arrived: int | None = None
    for _ in range(SMS_DELIVERY_ATTEMPTS):
        await asyncio.sleep(SMS_DELIVERY_POLL)
        new = await _sms_indexes(api) - before
        if new:
            arrived = max(new)
            break

    if arrived is None:
        report.skip(
            "delete_sms",
            f"the message did not arrive within "
            f"{SMS_DELIVERY_ATTEMPTS * SMS_DELIVERY_POLL:.0f}s - "
            f"delete it by hand if it lands later",
        )
        return

    await api.delete_sms(arrived)
    remaining = await _sms_indexes(api)
    report.record(arrived not in remaining, "delete_sms", f"index {arrived} removed")


async def _sms_indexes(api: HuaweiRouter5GAPI) -> set[int]:
    """Return the set of inbox message indexes, empty if the box is unreadable."""
    listing = await api.get_sms_list()
    messages = (listing or {}).get("Messages") or {}
    entries = messages.get("Message") or []
    if isinstance(entries, dict):
        entries = [entries]
    out: set[int] = set()
    for entry in entries:
        try:
            out.add(int(entry.get("Index")))
        except (TypeError, ValueError):
            continue
    return out


async def _check_clear_traffic(api: HuaweiRouter5GAPI, report: Report) -> None:
    """Clear the counters and confirm they actually went to zero.

    Read back rather than trusted. This write spent every release calling a
    method that does not exist, returning cleanly the whole time — the return
    value has already been proven worthless here.
    """
    before = (await api.get_data()).get("traffic_statistics", {})
    was = before.get("CurrentUpload")
    print(f"    {_dim(f'CurrentUpload before: {was!r}')}")

    await api.clear_traffic_statistics()
    await asyncio.sleep(5.0)

    after = (await api.get_data()).get("traffic_statistics", {})
    cleared = after.get("CurrentUpload") == "0" and after.get("CurrentDownload") == "0"
    report.record(
        cleared,
        "clear_traffic_statistics",
        f"CurrentUpload {was} -> {after.get('CurrentUpload')}",
    )


async def _check_reconnect(api: HuaweiRouter5GAPI, report: Report) -> None:
    """Reconnect and confirm a populated read comes back.

    Read back rather than trusted, for the reason the whole script exists: a
    write that returns cleanly has already been proven worthless here twice.
    """
    await api.reconnect()
    await asyncio.sleep(RECONNECT_SETTLE)

    for attempt in range(4):
        try:
            await api.login()
            data = await api.get_data()
        except Exception:  # noqa: BLE001 - an absent session is the expected case
            print(f"    {_dim(f'attempt {attempt + 1} - no answer yet')}")
            await asyncio.sleep(RECONNECT_SETTLE)
            continue
        if (data.get("device_signal") or {}).get("rsrp"):
            report.record(True, "reconnect", f"populated read on attempt {attempt + 1}")
            return
        print(f"    {_dim('answering, but the payload is blank')}")
        await asyncio.sleep(RECONNECT_SETTLE)

    report.record(False, "reconnect", "no populated read after four attempts")


async def _check_reboot(api: HuaweiRouter5GAPI, report: Report) -> None:
    """Reboot and wait for the router to serve a real payload again.

    Waiting for the device to *answer* is not enough. A router part-way back
    answers with authenticated keys blanked, which an integration can score as
    a clean success while every entity publishes `unknown`. The check is that a
    signal block comes back populated, not that a request completes.
    """
    await api.reboot()
    print(f"    {_dim('rebooting - polling until a populated read comes back')}")

    waited = 0.0
    while waited < REBOOT_TIMEOUT:
        await asyncio.sleep(REBOOT_POLL)
        waited += REBOOT_POLL
        try:
            await api.login()
            data = await api.get_data()
        except Exception:  # noqa: BLE001 - an absent router is the expected case
            print(f"    {_dim(f'{waited:.0f}s - no answer yet')}")
            continue
        if (data.get("device_signal") or {}).get("rsrp"):
            report.record(True, "reboot", f"populated read after {waited:.0f}s")
            return
        print(f"    {_dim(f'{waited:.0f}s - answering, but the payload is blank')}")

    report.record(False, "reboot", f"no populated read within {REBOOT_TIMEOUT:.0f}s")


# ---------------------------------------------------------------------------


async def main() -> int:
    """Run the safe tier, then the attended tier if it was asked for."""
    parser = argparse.ArgumentParser(description="Exercise Huawei router writes.")
    parser.add_argument(
        "--attended",
        action="store_true",
        help="also offer the writes that need a human confirming each step",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "stream the integration's DEBUG output to the console for "
            "troubleshooting; the write-confirmation outcome is checked and "
            "reported either way"
        ),
    )
    args = parser.parse_args()

    if args.debug:
        # Troubleshooting only. The confirmation path is captured and reported
        # by `_check_net_mode` whether or not this is set, so a default run is
        # the complete one -- an opt-in flag that changed what got *verified*
        # would make the default run the weaker one.
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        )
        logging.getLogger("custom_components.huawei_router_5g").setLevel(logging.DEBUG)

    print()
    print(_cyan("  Huawei Router 5G - hardware check"))
    print(_dim("  Safe tier only unless --attended is given."))
    if args.debug:
        print(_dim("  Debug logging on - console output only."))
    print()

    api = _api()
    report = Report("attended" if args.attended else "unattended")

    await _timed(
        report, "login and first read", lambda: check_login_and_read(api, report)
    )
    await _timed(
        report, "read-back endpoints", lambda: check_read_back_endpoints(api, report)
    )
    await _timed(
        report,
        "logout ends the session",
        lambda: check_logout_ends_the_session(api, report),
    )

    try:
        if args.attended:
            await check_attended_writes(api, report)
        else:
            print()
            print(_dim("  Attended tier not run. Pass --attended to offer it."))
    finally:
        # In a `finally` on purpose. A run that aborts half way is exactly when
        # the report matters most, and until 2026-08-18 nothing was written at
        # all — in either mode, aborted or not.
        written = report.write(_coverage_section(report))

        print()
        total = len(report.checks)
        if report.failed:
            print(_red(f"  {report.failed} of {total} checks failed."))
        else:
            print(_green(f"  All {total} checks passed."))
        if report.skipped:
            print(_yellow(f"  {report.skipped} skipped."))
        for path in written:
            print(_dim(f"  report: {path}"))
        print()

    await api.logout()
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
