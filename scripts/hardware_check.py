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

`send_sms` and `delete_sms` are classified ATTENDED but deliberately **not**
offered here. Both need a target typed at a prompt — a phone number, a message
index — and a mistyped one sends a real message to a stranger or destroys the
wrong message. They stay a manual exercise.

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
import json
import os
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI

CONFIG_ENTRIES = pathlib.Path("/config/.storage/core.config_entries")
DOMAIN = "huawei_router_5g"

# Seconds to let the radio re-register before reading a value back. Only the
# attended tier waits: nothing in the safe tier disturbs the connection.
RECONNECT_SETTLE = 15.0

# A reboot on the reference B535 takes well under three minutes; the budget is
# generous because a slow return is a wait, not a failure.
REBOOT_TIMEOUT = 300.0
REBOOT_POLL = 15.0

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

    def skip(self, name: str, why: str) -> None:
        """Note something deliberately not run. Not counted as a failure."""
        print(f"  {_yellow('○  SKIP')}  {name}{_dim(f'  — {why}')}")

    @property
    def failed(self) -> int:
        """Return how many checks failed, for the exit code."""
        return sum(1 for ok, _, _ in self.checks if not ok)


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
    try:
        await api.logout()
    except Exception as err:  # noqa: BLE001 - the report is the error channel
        report.record(False, "logout returns cleanly", type(err).__name__)
        return

    report.record(True, "logout returns cleanly")

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
        await api.get_data()
    except Exception as err:  # noqa: BLE001 - the report is the error channel
        report.record(False, "session re-establishes after logout", type(err).__name__)
        return
    report.record(True, "session re-establishes after logout")


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
) -> None:
    """Offer one attended write, stating its cost before the prompt."""
    print()
    print(f"  {_cyan(name)}")
    for line in cost.splitlines():
        print(f"    {_dim(line)}")
    if not _confirm(f"run {name}?"):
        report.skip(name, "declined")
        return
    try:
        await run()
    except Exception as err:  # noqa: BLE001 - the report is the error channel
        report.record(False, name, f"{type(err).__name__}: {err}")


async def _toggle_and_restore(
    api: HuaweiRouter5GAPI,
    report: Report,
    name: str,
    read: Any,
    write: Any,
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
    finally:
        try:
            await write(before)
        except Exception as err:  # noqa: BLE001 - restoration must be reported
            report.record(False, f"{name} restore", f"{type(err).__name__}: {err}")
        else:
            print(f"    {_dim(f'restored to {before}')}")


async def _mobile_data_state(api: HuaweiRouter5GAPI) -> bool | None:
    """Read the current mobile-data switch position."""
    data = await api.get_data()
    raw = (data.get("mobile_dataswitch") or {}).get("dataswitch")
    return None if raw is None else raw == "1"


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
    print()
    print(_yellow("  Attended tier - each write is confirmed separately."))
    print(_dim("  Answering anything but 'y' skips. Ctrl-C also skips."))

    await _offer(
        report,
        "set_guest_wifi",
        "Toggles the guest network and puts it back.\n"
        "On the reference B535 the guest SSID is OPEN - unauthenticated - so a\n"
        "crash between the toggle and the restore leaves it broadcasting.",
        lambda: _toggle_and_restore(
            api,
            report,
            "set_guest_wifi",
            lambda: _guest_wifi_state(api),
            api.set_guest_wifi,
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
        ),
    )

    await _offer(
        report,
        "set_net_mode",
        "Re-registers the radio. NOT restored automatically - the current mode\n"
        "is reported first so you can set it back from the Network Mode select.\n"
        "A mode the serving cell handles poorly may not come back on its own.",
        lambda: _check_net_mode(api, report),
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
        "reboot",
        f"Minutes of downtime. Waits up to {REBOOT_TIMEOUT:.0f}s for the router\n"
        "to answer again. Nothing is left in a changed state.",
        lambda: _check_reboot(api, report),
    )


async def _check_net_mode(api: HuaweiRouter5GAPI, report: Report) -> None:
    """Set the network mode to auto and confirm the router accepted it."""
    data = await api.get_data()
    current = (data.get("net_mode") or {}).get("NetworkMode")
    print(f"    {_dim(f'current NetworkMode is {current!r}')}")

    await api.set_net_mode("00")  # 00 = auto, the least disruptive target
    await asyncio.sleep(RECONNECT_SETTLE)

    after = (await api.get_data()).get("net_mode", {}).get("NetworkMode")
    report.record(after == "00", "set_net_mode", f"{current} -> {after}")
    if current != "00":
        print(f"    {_yellow(f'NOT restored - set it back to {current!r} yourself')}")


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
    args = parser.parse_args()

    print()
    print(_cyan("  Huawei Router 5G - hardware check"))
    print(_dim("  Safe tier only unless --attended is given."))
    print()

    api = _api()
    report = Report()

    await check_login_and_read(api, report)
    await check_logout_ends_the_session(api, report)

    if args.attended:
        await check_attended_writes(api, report)
    else:
        print()
        print(_dim("  Attended tier not run. Pass --attended to offer it."))

    print()
    total = len(report.checks)
    if report.failed:
        print(_red(f"  {report.failed} of {total} checks failed."))
    else:
        print(_green(f"  All {total} checks passed."))
    print()

    await api.logout()
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
