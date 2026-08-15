"""Every command this integration can send, and whether a script may send it.

Ported from `zte_router_5g`, where the register exists because the Data Limit
Switch had never worked in any release and nobody noticed for weeks — not
because testing was hard, but because **nobody used that entity**. A control the
owner does not personally use is exercised only by accident.

**Huawei restated that failure before this register was written.** Clear Traffic
Statistics called `Monitoring.clear_traffic()`, a method that has never existed
in `huawei-lte-api`. The call raised `AttributeError` underneath a
`# type: ignore[attr-defined]`, and its test passed because it asserted the
wrong name against a bare `MagicMock`. The button could not have worked in any
release. Two independent guards were needed to catch it — a library contract
test and a suppression sweep — and neither is this file's job. This file's job
is the third thing that was missing: **nobody had decided, in writing, whether
that button was ever going to be exercised against real hardware.**

So the guarantee here is not "these are tested". It is *"no write can be added
without someone deciding, in writing, whether it can be tested"*.
`tests/test_write_classification.py` fails on an unclassified write, and fails
again if something classified SAFE is not actually exercised by
`scripts/hardware_check.py`.

The three tiers:

``SAFE``
    Automatable unattended. Must be reversible **in-process**, must not
    interrupt service, cost money, or touch anyone else's property — and,
    because a crash can strand it, **either resting state must be harmless**.
    That last clause does most of the work here, and it is why this tier holds
    exactly one entry: Huawei's write surface is almost entirely radio and
    network state, where a stranded resting state means the household has no
    internet.

``ATTENDED``
    Exercised only with a human confirming each step individually, and never in
    an unattended run. Everything that re-establishes the connection lives here:
    it is recoverable, but a script cannot judge whether it recovered.

``NEVER_AUTOMATED``
    Must never be issued by a script under any flag, because no amount of human
    confirmation makes it recoverable or acceptable.

    **Currently empty, and that is deliberate** — the same conclusion ZTE
    reached. The tier began as a catch-all for "costs money, reaches a third
    party, or destroys data", which conflated *cannot be automated* with
    *cannot be scripted at all*. With a person typing a confirmation and
    supplying the target, sending an SMS and deleting one are ordinary tests;
    they simply cannot run unattended. Keeping the tier defined but empty
    preserves the decision point for a future command that warrants it.
"""

from __future__ import annotations

# --- Automatable unattended -------------------------------------------------
SAFE: dict[str, str] = {
    "logout": (
        "Ends a session the script immediately re-establishes, so both resting "
        "states are harmless. Worth covering for a reason specific to this "
        "integration: `logout` called a `Connection.logout` that has never "
        "existed in the library, so every unload and every reload leaked a "
        "session. It was invisible because failure is silent by design — the "
        "call is wrapped to swallow, since a failed logout must not block an "
        "unload. A read-back check is the only thing that can see it."
    ),
}

# --- Human present, one step at a time --------------------------------------
ATTENDED: dict[str, str] = {
    "reboot": (
        "Minutes of downtime. Verification is only a retry loop until the "
        "device answers again, so the cost is time rather than risk — nothing "
        "is left in a changed state. Confirmed working against the live router "
        "on 2026-08-14."
    ),
    "clear_traffic_statistics": (
        "Irreversibly zeroes the router's byte counters, and nothing can put "
        "them back. It also puts a step change into the Home Assistant "
        "long-term statistics for every total sensor, so the damage outlives "
        "the router's own state. Acceptable attended because the operator is "
        "resetting counters they own and chose the moment; never unattended, "
        "because there is no moment a script can choose."
    ),
    "set_mobile_data": (
        "Turning mobile data off takes the household's internet away. It is "
        "one call to put back, but a script that dies between the two leaves "
        "the connection down with nothing watching — the exact case the "
        "'either resting state must be harmless' clause excludes."
    ),
    "set_net_mode": (
        "Radio re-registration. Forcing a mode the current cell serves poorly "
        "may not come back on its own, and the router answers with blank "
        "values while re-registering, which a script cannot tell from a dead "
        "session."
    ),
    "reconnect": (
        "Drops and re-establishes the mobile data session. Recoverable in "
        "seconds and nothing is left in a changed state, but the router "
        "answers with blank values while re-registering, which a script "
        "cannot tell apart from a dead session - the same reason set_net_mode "
        "is here. Not exercised unattended; the owner verifies it by hand."
    ),
    "set_guest_wifi": (
        "Looks cosmetic and is not. On the live B535 the guest SSID carries "
        "`WifiAuthmode: OPEN` — a stranded ON leaves an unauthenticated "
        "wireless network broadcasting from the user's home. Reversible in one "
        "call, but the ON resting state is not harmless, so it fails SAFE. "
        "This write also takes the non-obvious path through `post_set` rather "
        "than the library's public setter; see docs/DEVELOPMENT.md."
    ),
    "send_sms": (
        "Costs money and delivers to a third party, so it can never run "
        "unattended. With a person supplying the destination and confirming, "
        "it is an ordinary test: one message, to a number they chose."
    ),
    "delete_sms": (
        "Irreversibly destroys a message — nothing can put one back. "
        "Acceptable attended because the target is a single, named message the "
        "operator sees identified before confirming, not an arbitrary one."
    ),
}

# --- Not scriptable under any flag ------------------------------------------
NEVER_AUTOMATED: dict[str, str] = {}

# Writes the hardware script is expected to exercise. Kept separate from `SAFE`
# so the test can tell "classified safe" from "actually covered" — the gap that
# let ZTE's Data Limit Switch and this project's Clear Traffic button both ship
# broken. Adding a SAFE write without covering it fails the test.
EXERCISED_BY_HARDWARE_CHECK: frozenset[str] = frozenset({"logout"})

# ATTENDED writes the script offers under `--attended`.
#
# `send_sms` and `delete_sms` are classified but deliberately unscripted. Both
# need a target the operator supplies — a phone number, a message index — and a
# menu that prompts for one invites a mistyped number sending a real message to
# a stranger, or deleting the wrong message. They stay a manual exercise.
OFFERED_WHEN_ATTENDED: frozenset[str] = frozenset(
    {
        "reboot",
        "reconnect",
        "clear_traffic_statistics",
        "set_mobile_data",
        "set_net_mode",
        "set_guest_wifi",
    }
)


def classification(name: str) -> str | None:
    """Return the tier a write belongs to, or None when unclassified."""
    tiers = (
        ("SAFE", SAFE),
        ("ATTENDED", ATTENDED),
        ("NEVER_AUTOMATED", NEVER_AUTOMATED),
    )
    for tier, register in tiers:
        if name in register:
            return tier
    return None
