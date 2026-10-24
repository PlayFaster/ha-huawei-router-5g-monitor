"""An SMS received while Home Assistant was stopped (1.2.4-dev8 plan I7).

Cross-project item
`.shared/issues/x_project/sms_received_while_home_assistant_was_stopped.md`;
the first three case names are the ones that item requires in every project.
Each "restart" builds a second coordinator on the same entry, which loads the
observed store the first one saved, as `async_setup_entry` does.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.huawei_router_5g.const import DOMAIN, SMS_SEEN_CAP
from custom_components.huawei_router_5g.coordinator import (
    HuaweiRouter5GDataUpdateCoordinator,
)
from homeassistant.core import HomeAssistant


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="001122334455", data={})
    entry.add_to_hass(hass)
    return entry


def _inbox(*indexes: int) -> dict[str, Any]:
    """An `sms_list` block holding one message per index."""
    return {
        "sms_list": {
            "Messages": {
                "Message": [
                    {
                        "Index": str(index),
                        "Phone": "+15555550123",
                        "Content": f"message {index}",
                        "Date": f"2026-10-24 09:{index % 60:02d}:00",
                    }
                    for index in indexes
                ]
            }
        }
    }


async def _start(
    hass: HomeAssistant, entry: MockConfigEntry
) -> tuple[HuaweiRouter5GDataUpdateCoordinator, list[dict[str, Any]], list[int]]:
    """Build a coordinator as setup does, recording bus events and listener calls."""
    api = MagicMock()
    # A real value: the coordinator persists it in the same store.
    api.information_answered = True
    coordinator = HuaweiRouter5GDataUpdateCoordinator(hass, entry, api)
    await coordinator.observations.async_load()
    coordinator.restore_sms_record()
    fired: list[dict[str, Any]] = []
    hass.bus.async_listen(
        "huawei_router_5g_sms_received",
        lambda event: (
            fired.append(event.data)
            if event.data["entry_id"] == entry.entry_id
            else None
        ),
    )
    triggered: list[int] = []
    coordinator.add_sms_listener(lambda msg: triggered.append(msg["index"]))
    return coordinator, fired, triggered


async def _poll(
    hass: HomeAssistant, coordinator: HuaweiRouter5GDataUpdateCoordinator, data
) -> None:
    """The SMS step of a successful poll, then its save."""
    coordinator._check_new_sms(data)
    await coordinator._async_observe(data)
    await hass.async_block_till_done()


async def test_a_message_received_while_stopped_fires_once(
    hass: HomeAssistant,
) -> None:
    """A message that arrived during a stop is announced once after the start.

    Once on the bus and once to the event entity's listener; a second poll of
    the same inbox announces nothing.
    """
    entry = _entry(hass)
    first, _, _ = await _start(hass, entry)
    await _poll(hass, first, _inbox(1, 2))

    second, fired, triggered = await _start(hass, entry)
    await _poll(hass, second, _inbox(1, 2, 3))
    await _poll(hass, second, _inbox(1, 2, 3))

    assert [event["index"] for event in fired] == [3]
    assert triggered == [3]


async def test_a_first_install_takes_a_silent_baseline(hass: HomeAssistant) -> None:
    """With no record, the first poll fires nothing for messages already held.

    The same holds for a store written by 1.2.4-dev7, which has no `sms` key:
    the upgrade-sequence check of `code_first_dev_cycle.md` §6.1.
    """
    entry = _entry(hass)
    coordinator, fired, triggered = await _start(hass, entry)

    await _poll(hass, coordinator, _inbox(1, 2))

    assert fired == []
    assert triggered == []
    assert coordinator.observations.sms_record() is not None


async def test_the_record_is_not_in_the_diagnostics(hass: HomeAssistant) -> None:
    """The download carries a count, never the secret or an identity."""
    entry = _entry(hass)
    coordinator, _, _ = await _start(hass, entry)
    await _poll(hass, coordinator, _inbox(1, 2))
    secret, seen = coordinator.observations.sms_record() or ("", [])

    report = json.dumps(coordinator.observations.report())

    assert json.loads(report)["sms_seen"] == 2
    assert secret not in report
    assert all(identity not in report for identity in seen)


async def test_a_message_fired_on_an_unchanged_poll_is_saved(
    hass: HomeAssistant,
) -> None:
    """A fire is saved on its own poll, even when nothing else changed."""
    entry = _entry(hass)
    first, _, _ = await _start(hass, entry)
    await _poll(hass, first, _inbox(1))
    with patch.object(first.observations, "observe", return_value=False):
        await _poll(hass, first, _inbox(1, 2))

    second, fired, _ = await _start(hass, entry)
    await _poll(hass, second, _inbox(1, 2))

    assert fired == []


async def test_the_cap_drops_the_oldest_and_keeps_what_is_still_read(
    hass: HomeAssistant,
) -> None:
    """Past `SMS_SEEN_CAP`, the oldest identity no longer read is dropped."""
    entry = _entry(hass)
    coordinator, _, _ = await _start(hass, entry)
    await _poll(hass, coordinator, _inbox(0))
    for index in range(1, SMS_SEEN_CAP + 1):
        await _poll(hass, coordinator, _inbox(0, index))

    order = coordinator._sms_seen_order
    oldest_read = coordinator._sms_identity(
        {"index": 0, "phone": "+15555550123", "content": "message 0"}
    )
    dropped = coordinator._sms_identity(
        {"index": 1, "phone": "+15555550123", "content": "message 1"}
    )
    assert len(order) == SMS_SEEN_CAP
    assert oldest_read in order
    assert dropped not in order


async def test_a_record_without_its_secret_takes_a_silent_baseline(
    hass: HomeAssistant,
) -> None:
    """Identities that cannot be recomputed are discarded, not replayed."""
    entry = _entry(hass)
    first, _, _ = await _start(hass, entry)
    await _poll(hass, first, _inbox(1, 2))
    first.observations._observed[first.observations.device_id]["sms"].pop("secret")
    await first.observations.async_save()

    second, fired, triggered = await _start(hass, entry)
    await _poll(hass, second, _inbox(1, 2))

    assert fired == []
    assert triggered == []
