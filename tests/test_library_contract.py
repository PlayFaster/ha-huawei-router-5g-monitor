"""The `huawei-lte-api` surface this integration depends on actually exists.

**This file exists because two calls did not.** `Connection.logout` and
`Monitoring.clear_traffic` were called for months and neither has ever existed
in the library. Both were suppressed with `# type: ignore[attr-defined]`, and
`clear_traffic` was additionally asserted by a test against a bare `MagicMock`,
which creates any attribute on demand. The result was a Logout that logged out
of nothing and a Clear Traffic Statistics button that could not work.

The check is deliberately **derived from source rather than from a list**. A
hand-maintained inventory of library calls is one more thing to forget to
update — and forgetting is exactly the failure being guarded against. The names
are extracted from `api.py` itself, so a new call is covered the moment it is
written.

`Client.__init__` only constructs its endpoint groups; it performs no IO, so a
`MagicMock` connection is enough to introspect the real classes.
"""

import inspect
import re
from unittest.mock import MagicMock

import pytest
from huawei_lte_api.Client import Client

from custom_components.huawei_router_5g import api as api_module

# `client.<group>.<attribute>` — with or without a call, because a method
# passed to `asyncio.to_thread` is referenced without parentheses.
_CALL = re.compile(r"\bclient\.([a-z_][a-z_0-9]*)\.([a-z_][a-z_0-9]*)")


def _referenced_library_calls() -> set[tuple[str, str]]:
    """Return every `(group, attribute)` pair `api.py` reaches for.

    Private attributes are skipped: reaching into a library's internals is a
    separate finding with its own justification, and is covered by the
    suppression sweep rather than here.
    """
    source = inspect.getsource(api_module)
    return {
        (group, attr)
        for group, attr in _CALL.findall(source)
        if not group.startswith("_") and not attr.startswith("_")
    }


def test_every_library_call_exists_on_the_installed_package() -> None:
    """Every `client.<group>.<method>` in `api.py` must really exist.

    **If this fails, the call is wrong — the library is not.** Check the method
    name against the installed package before changing anything here. A
    suppression comment is never the fix.
    """
    client = Client(MagicMock())
    missing = []

    for group, attr in sorted(_referenced_library_calls()):
        endpoint = getattr(client, group, None)
        if endpoint is None:
            missing.append(f"client.{group} — no such endpoint group")
        elif not hasattr(endpoint, attr):
            missing.append(
                f"client.{group}.{attr} — {type(endpoint).__name__} has no such method"
            )

    assert not missing, (
        "api.py calls library methods that do not exist on the installed "
        "huawei-lte-api:\n" + "\n".join(missing)
    )


def test_the_contract_sweep_is_not_vacuous() -> None:
    """Guard the guard.

    The extraction above is a regex over source. If `api.py` is refactored so
    the calls no longer read `client.<group>.<method>` — wrapped in a helper,
    say — this file would pass while checking nothing at all, and would keep
    passing through exactly the defect it was written for.
    """
    found = _referenced_library_calls()
    assert len(found) >= 15, (
        f"only {len(found)} library calls extracted from api.py — the pattern "
        "has stopped matching and this sweep is no longer checking anything"
    )
    # Two that must always be present, and are the two that were broken.
    assert ("user", "logout") in found
    assert ("monitoring", "set_clear_traffic") in found


@pytest.mark.parametrize(
    "group,attr",
    [
        ("device", "set_control"),
        ("monitoring", "set_clear_traffic"),
        ("user", "logout"),
        ("wlan", "set_multi_basic_settings"),
    ],
)
def test_named_methods_that_have_previously_been_got_wrong(group, attr) -> None:
    """Pin the specific names this project has already got wrong once.

    The sweep above covers whatever `api.py` currently calls. This pins the
    correct spellings independently, so a regression that removes a call
    entirely — and therefore removes it from the sweep — still fails here.

    - `device.set_control` replaced `device.reboot`, removed in library 2.0.0.
    - `monitoring.set_clear_traffic` was called as `clear_traffic`.
    - `user.logout` was called as `connection.logout`.
    - `wlan.set_multi_basic_settings` was bypassed for `_session.post_set`
      under a comment claiming no public setter existed.
    """
    client = Client(MagicMock())
    assert hasattr(getattr(client, group), attr), (
        f"client.{group}.{attr} is missing from the installed huawei-lte-api"
    )
