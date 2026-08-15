"""Section 9 — an Options change must reach the running integration.

The defect this closes was found twice, independently, from opposite
directions: `dev_std_review` reading the standard, and `code_review` reading
the code. Nothing reloaded. `async_setup_entry` handed the host, username and
password to `HuaweiRouter5GAPI` once, and the Options flow wrote new values to
the entry that the running object never saw — so a user who changed the
router's password watched the form validate (it really does log in) and then
saw nothing change until a restart.

The inconsistency was the sharp part: Reauth reloads and Reconfigure reloads.
Options edits the same three fields and did not.

**Both halves are tested here, and the second is the one that decays.** That a
connection change reloads is the fix. That a tuning change does *not* reload is
what stops the fix turning every nudge of the polling slider into a session
teardown — and it is the half a later "simplification" would quietly remove.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from custom_components.huawei_router_5g import (
    LIVE_OPTION_KEYS,
    _async_options_updated,
    _reload_signature,
)
from custom_components.huawei_router_5g.const import (
    CONF_SCAN_INTERVAL,
    CONF_STOP_POLLING,
)

BASE_OPTIONS = {
    CONF_HOST: "192.168.8.1",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "password",
    CONF_SCAN_INTERVAL: 60,
    CONF_STOP_POLLING: False,
}


def _entry(options: dict):
    entry = MagicMock()
    entry.entry_id = "test"
    entry.options = options
    entry.runtime_data = MagicMock()
    entry.runtime_data.reload_signature = _reload_signature(BASE_OPTIONS)
    return entry


def test_the_live_keys_are_exactly_the_two_read_every_cycle() -> None:
    """`LIVE_OPTION_KEYS` may only hold options applied without a rebuild.

    Both of these are consulted fresh on each cycle — the coordinator reads
    the interval when it schedules and the pause flag when it decides whether
    to fetch — so a change takes effect on the next tick with no reload.

    Adding a key here is what makes a setting silently stop working: it would
    be written to the entry, skipped by the reload, and never read by anything
    holding the old value. Pinned so that becomes a deliberate act.
    """
    assert frozenset({CONF_SCAN_INTERVAL, CONF_STOP_POLLING}) == LIVE_OPTION_KEYS


def test_the_signature_ignores_the_live_keys() -> None:
    """Tuning options must not appear in the reload signature."""
    signature = _reload_signature(BASE_OPTIONS)

    assert CONF_SCAN_INTERVAL not in signature
    assert CONF_STOP_POLLING not in signature
    assert signature[CONF_HOST] == "192.168.8.1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "value"),
    [
        (CONF_HOST, "192.168.8.99"),
        (CONF_USERNAME, "someone_else"),
        (CONF_PASSWORD, "a new password"),
    ],
)
async def test_a_connection_change_reloads(key: str, value: str) -> None:
    """Changing any of the three connection fields must rebuild the entry.

    Parametrized over all three rather than testing the host alone, because
    the API captures all three at construction and any of them going stale is
    the same defect.
    """
    hass = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    entry = _entry({**BASE_OPTIONS, key: value})

    await _async_options_updated(hass, entry)

    hass.config_entries.async_reload.assert_awaited_once_with("test")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "value"),
    [(CONF_SCAN_INTERVAL, 300), (CONF_STOP_POLLING, True)],
)
async def test_a_tuning_change_does_not_reload(key: str, value: object) -> None:
    """The polling controls apply live and must not tear down the session.

    Without the allow-list, every nudge of the interval slider would drop the
    router session and rebuild every entity — which is why "reload on any
    change" is not the simpler correct answer it looks like.
    """
    hass = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    entry = _entry({**BASE_OPTIONS, key: value})

    await _async_options_updated(hass, entry)

    hass.config_entries.async_reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unchanged_signature_does_not_reload() -> None:
    """A listener firing with nothing relevant changed must do nothing.

    HA fires the update listener on every write to the entry, including ones
    this integration did not cause. Reloading unconditionally would rebuild
    the entry for no reason and, worse, could loop.
    """
    hass = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    entry = _entry(dict(BASE_OPTIONS))

    await _async_options_updated(hass, entry)

    hass.config_entries.async_reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_signature_is_updated_before_the_reload() -> None:
    """The stored signature must move with the change.

    If it did not, the entry would reload once and then reload again on the
    next unrelated listener firing, because the comparison would keep seeing
    a difference that had already been applied.
    """
    hass = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    entry = _entry({**BASE_OPTIONS, CONF_HOST: "192.168.8.99"})

    await _async_options_updated(hass, entry)

    assert entry.runtime_data.reload_signature[CONF_HOST] == "192.168.8.99"


@pytest.mark.asyncio
async def test_setup_registers_the_listener() -> None:
    """The mechanism is worthless unless it is actually wired up.

    This is the assertion that would have failed before the fix: the listener
    did not exist, so every test of its behavior would have been testing
    something nothing ever called.
    """
    from custom_components.huawei_router_5g import async_setup_entry

    hass = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    entry = _entry(dict(BASE_OPTIONS))
    entry.data = {"mac": "dc7196112233"}
    entry.title = "Router"
    # Close the coroutine rather than leaving it un-awaited: the background
    # setup is not what this test is about, and an abandoned coroutine emits a
    # RuntimeWarning that would be noise in every future run.
    entry.async_create_background_task = MagicMock(
        side_effect=lambda _hass, coro, _name: coro.close()
    )
    entry.add_update_listener = MagicMock(return_value="unsub")
    entry.async_on_unload = MagicMock()

    with (
        patch("custom_components.huawei_router_5g.HuaweiRouter5GAPI"),
        patch("custom_components.huawei_router_5g.HuaweiRouter5GDataUpdateCoordinator"),
        patch("custom_components.huawei_router_5g.dr.async_get"),
        patch(
            "custom_components.huawei_router_5g._async_migrate_tracker_unique_ids",
            AsyncMock(),
        ),
        patch("custom_components.huawei_router_5g.via_device_link", return_value={}),
    ):
        assert await async_setup_entry(hass, entry) is True

    entry.add_update_listener.assert_called_once_with(_async_options_updated)
    # Registered through `async_on_unload`, so the listener is torn down with
    # the entry rather than outliving it.
    entry.async_on_unload.assert_called_once_with("unsub")


@pytest.mark.asyncio
async def test_a_reload_is_scoped_to_the_entry_that_changed(
    hass: HomeAssistant,
) -> None:
    """Two routers: changing one must not rebuild the other."""
    hass_mock = MagicMock()
    hass_mock.config_entries.async_reload = AsyncMock()
    entry = _entry({**BASE_OPTIONS, CONF_HOST: "192.168.8.99"})
    entry.entry_id = "router_a"

    await _async_options_updated(hass_mock, entry)

    hass_mock.config_entries.async_reload.assert_awaited_once_with("router_a")
