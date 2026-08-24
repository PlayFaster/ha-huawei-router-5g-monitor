"""A refused write raises. It never reports success having done nothing.

Cross-project chore `C-026`, whose property is one line:

    **a method either does the thing, or raises — never a success-shaped
    result having done nothing.**

**Only half of the originating sweep applies here.** `zte_router_5g` raised
this from `tests/test_dead_session_sweep.py`, where the router answers
`200 OK` with every value blank on a dead session, so an unguarded call reads
that as "no data" and reports success. That is how its `send_sms` once
reported success while sending nothing. This router does not have that failure
mode: `huawei-lte-api` maps an `<error><code>` body onto an exception, so a
refusal arrives as a raise rather than as a hollow success, and there is no
dead-session detector here to test. What ports across is the refusal half and
its registry guard.

**So this file does not re-prove that the library raises.** It pins two things
the library cannot: that every write is shaped so it *has* no success value to
return, and that no write swallows a refusal on the way out. The next write
someone adds in six months is covered the moment it exists —
`test_every_write_is_in_the_refusal_sweep` fails if one is added without an
entry in `_CALLS`.

**The carve-outs are real and are asserted rather than assumed.** Three paths
deliberately do not raise, each for a reason written into the source, and §4
names them and holds the list closed. A fourth appearing without a decision is
the thing this file is meant to catch.

The fake router and the faults it serves are in [`transport.py`](transport.py).
"""

from __future__ import annotations

import ast
import logging
import pathlib
from typing import Any

import pytest
import requests_mock as requests_mock_module

from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI

from .transport import RouterTransport

_LOGGER = logging.getLogger(__name__)

ROUTER_URL = "http://192.168.8.1"

_API_PATH = pathlib.Path("custom_components/huawei_router_5g/api.py")

# Kept identical to `test_write_classification.py`, deliberately. Two detectors
# disagreeing about what counts as a write is how one of them silently stops
# covering something.
_WRITE_PREFIXES = ("set_", "send_", "delete_")
_WRITE_NAMES = frozenset({"reboot", "logout", "clear_traffic_statistics", "reconnect"})
_NOT_A_USER_FACING_WRITE = frozenset({"login"})

# Every write, with arguments good enough to reach the router. The values are
# never applied — the transport refuses before anything is written — so they
# only have to satisfy each signature.
_CALLS: dict[str, tuple[Any, ...]] = {
    "reboot": (),
    "reconnect": (),
    "clear_traffic_statistics": (),
    "set_mobile_data": (True,),
    "set_net_mode": ("00",),
    "set_wifi": (True,),
    "set_guest_wifi": (True,),
    "send_sms": (["+15551234567"], "a message"),
    "delete_sms": (1,),
}

# `logout` is a write by the detector's reckoning and is deliberately not in
# `_CALLS`. See §4 — it is one of the three carve-outs, not an omission.
_CARVE_OUTS = frozenset({"logout"})


@pytest.fixture(name="transport")
def transport_fixture():
    """Serve a router that answers normally until it is armed."""
    with requests_mock_module.Mocker() as mocker:
        yield RouterTransport(mocker)


def _api() -> HuaweiRouter5GAPI:
    """Build an API object against the faked transport."""
    return HuaweiRouter5GAPI(ROUTER_URL, "admin", "password")


def _public_writes() -> set[str]:
    """Return every public API method that commands the router."""
    tree = ast.parse(_API_PATH.read_text(encoding="utf-8"))
    api = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HuaweiRouter5GAPI"
    )
    found = {
        node.name
        for node in api.body
        if isinstance(node, ast.AsyncFunctionDef)
        and not node.name.startswith("_")
        and (node.name.startswith(_WRITE_PREFIXES) or node.name in _WRITE_NAMES)
    }
    return found - _NOT_A_USER_FACING_WRITE


# --- 1. The refusal itself ---------------------------------------------------


@pytest.mark.parametrize("method_name", sorted(_CALLS))
async def test_a_refused_write_raises(method_name: str, transport) -> None:
    """A write the router refuses must raise, not return.

    `endpoint_error` is `100002`, deliberately, and the choice is load-bearing.
    `_execute_with_retry` treats `125002`, `125003` and `100003` as session
    expiry and re-logs in, so a refusal served with any of those exercises the
    retry rather than the refusal. `100002` is not in that set, so it reaches
    the caller as the router declining the command — which is the case this
    property is about.

    The fault is not scoped to an endpoint, so it also covers the writes that
    read before they write: `set_wifi` reads the radio block, `set_net_mode`
    reads the current mode for its band arguments, and `reconnect` issues two
    calls. Each must still surface the refusal rather than proceeding on a
    value it never got.

    Written as try/except rather than `pytest.raises` so the failure message
    can say what the caller would actually have seen — a method that completed
    and handed back `None` is indistinguishable from success, and that is the
    defect, not the absence of an exception type. Any exception satisfies it
    deliberately: naming a type would test the library's error mapping, and
    would go green the day a write started raising the wrong thing.
    """
    transport.arm("endpoint_error")
    api = _api()

    returned: str | None = None
    try:
        result = await getattr(api, method_name)(*_CALLS[method_name])
    except Exception as err:  # noqa: BLE001
        # Raised, which is the property holding. Bound and logged rather than
        # passed over, so a run that goes green still shows *what* refused —
        # a write raising for the wrong reason is not the same as one raising
        # because the router declined it.
        _LOGGER.debug("%s refused with %s", method_name, err.__class__.__name__)
    else:
        returned = repr(result)

    assert returned is None, (
        f"{method_name} swallowed a refusal and returned {returned} — a "
        "success-shaped result having done nothing"
    )


# --- 2. The shape that makes a success-shaped result impossible --------------


def test_every_write_is_annotated_to_return_none() -> None:
    """A write with no return value cannot report a false success.

    The structural half of the property, and the half a behavioral test cannot
    reach: a method annotated `-> bool` invites a caller to branch on it, and
    the first `return False` added to one is the defect this chore exists to
    stop. Checked on the annotation rather than at runtime, because the point
    is the contract offered to callers.
    """
    tree = ast.parse(_API_PATH.read_text(encoding="utf-8"))
    api = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HuaweiRouter5GAPI"
    )

    writes = [
        node
        for node in api.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in _CALLS
    ]
    wrong = [
        f"{node.name} -> {ast.unparse(node.returns) if node.returns else 'nothing'}"
        for node in writes
        if not (isinstance(node.returns, ast.Constant) and node.returns.value is None)
    ]

    assert not wrong, f"writes must be annotated `-> None`: {wrong}"


def test_no_write_contains_a_bare_return_of_a_value() -> None:
    """`-> None` is only a promise if nothing returns a value under it."""
    tree = ast.parse(_API_PATH.read_text(encoding="utf-8"))
    api = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HuaweiRouter5GAPI"
    )

    offenders = [
        f"{node.name}: return {ast.unparse(inner.value)}"
        for node in api.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in _CALLS
        for inner in ast.walk(node)
        if isinstance(inner, ast.Return) and inner.value is not None
    ]

    assert not offenders, f"a write returned a value: {offenders}"


# --- 3. The registry guard ---------------------------------------------------


def test_every_write_is_in_the_refusal_sweep() -> None:
    """A write added without an entry in `_CALLS` goes unchecked.

    This is the test that makes the file hold its value. Without it the sweep
    covers whatever was true the day it was written, and a command added later
    is simply absent — which is the shape of every gap this project's write
    tests were added to close.
    """
    covered = set(_CALLS) | _CARVE_OUTS
    missing = sorted(_public_writes() - covered)
    stale = sorted(covered - _public_writes())

    assert not missing, (
        f"writes missing from the refusal sweep: {missing}. Add each to "
        "`_CALLS` with arguments, or to `_CARVE_OUTS` with its reason in §4."
    )
    assert not stale, (
        f"`_CALLS`/`_CARVE_OUTS` name writes that no longer exist: {stale}"
    )


# --- 4. The carve-outs, and holding the list closed --------------------------


def test_the_carve_out_list_stays_closed() -> None:
    """Three paths deliberately do not raise. A fourth needs a decision.

    Each is documented where it lives, and each is the same judgement: the
    command reached the router and may have applied, so reporting failure
    would invite the user to repeat something that already took effect. That
    is Section 22's third outcome — unverified, not failed — and it is a
    different thing from swallowing a refusal.

    | Path | Why it does not raise |
    | :-- | :-- |
    | `logout` | Teardown. A failed logout is not worth propagating and the connection is discarded either way. The wrong-method-name defect it once hid is caught by `test_library_contract.py`, not by a narrower catch. |
    | `_write_deadline` expiry | The write was sent and the waiting stopped, not the command. Raising would report a successful write as broken. |
    | `set_net_mode` answering `-1` | The router applies the change and answers abnormally while the radio re-registers. A read-back decides it; only a confirmed disagreement raises. |

    This test does not re-verify the reasons. It asserts the list has not
    grown, so a fourth swallow has to be argued for rather than added.
    """
    assert sorted(_CARVE_OUTS) == ["logout"], (
        "the set of writes exempt from the refusal sweep changed; add the "
        "reason to the table above before changing this assertion"
    )


def test_the_sweep_is_not_vacuous() -> None:
    """A sweep over an empty set passes and proves nothing."""
    assert len(_CALLS) >= 9, (
        f"only {len(_CALLS)} writes in the sweep; api.py has "
        f"{len(_public_writes())} public writes"
    )
