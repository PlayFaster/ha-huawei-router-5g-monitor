"""The incoming SMS event entity (1.2.4-dev8 plan I6).

Cross-project item `.shared/issues/x_project/incoming_sms_event_entity.md`;
the three case names are the ones that item requires in every project.
"""

from __future__ import annotations

import json
from typing import Any

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.recorder.const import SupportedDialect
from homeassistant.components.recorder.db_schema import StateAttributes
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er
from tests.conftest import _live_entities


def _inbox(*messages: tuple[str, str]) -> dict[str, Any]:
    """An `sms_list` block holding `(index, date)` messages."""
    return {
        "sms_list": {
            "Messages": {
                "Message": [
                    {
                        "Index": index,
                        "Phone": "+15555550123",
                        "Content": f"message {index}",
                        "Date": date,
                    }
                    for index, date in messages
                ]
            }
        }
    }


def _event_entity_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "event", "huawei_router_5g", f"{entry.unique_id}_incoming_sms"
    )
    assert entity_id is not None
    return entity_id


async def test_a_new_sms_triggers_the_event_entity(
    hass: HomeAssistant, live_entry: MockConfigEntry
) -> None:
    """A new message triggers the entity once, with the bus event's data."""
    async with _live_entities(hass, live_entry):
        coordinator = live_entry.runtime_data
        entity_id = _event_entity_id(hass, live_entry)

        # Setup's first poll took the silent baseline, so this message is new.
        assert hass.states.get(entity_id).state == "unknown"
        coordinator._check_new_sms(_inbox(("2", "2026-10-24 09:05:00")))
        await hass.async_block_till_done()

        state = hass.states.get(entity_id)
        assert state.state != "unknown"
        assert state.attributes["event_type"] == "received"
        assert state.attributes["phone"] == "+15555550123"
        assert state.attributes["content"] == "message 2"
        assert state.attributes["index"] == 2


async def test_the_bus_event_still_fires(
    hass: HomeAssistant, live_entry: MockConfigEntry
) -> None:
    """The bus event fires as before, once per new message."""
    fired: list[dict[str, Any]] = []
    hass.bus.async_listen(
        "huawei_router_5g_sms_received", lambda event: fired.append(event.data)
    )
    async with _live_entities(hass, live_entry):
        coordinator = live_entry.runtime_data
        coordinator._check_new_sms(_inbox(("2", "2026-10-24 09:05:00")))
        coordinator._check_new_sms(_inbox(("2", "2026-10-24 09:05:00")))
        await hass.async_block_till_done()

    assert [data["index"] for data in fired] == [2]
    assert fired[0]["content"] == "message 2"


async def test_the_sender_and_text_are_not_recorded(
    hass: HomeAssistant, live_entry: MockConfigEntry
) -> None:
    """The attributes the recorder stores hold the event type, not sender or text.

    The entity's `state_changed` event is passed through the recorder's own
    serializer, `StateAttributes.shared_attrs_bytes_from_event`, which builds
    the stored attributes row. A running recorder cannot be set up here: an
    autouse fixture creates `hass` before the recorder fixture can.
    """
    changes: list[Event] = []
    async with _live_entities(hass, live_entry):
        coordinator = live_entry.runtime_data
        entity_id = _event_entity_id(hass, live_entry)
        hass.bus.async_listen(
            EVENT_STATE_CHANGED,
            lambda event: (
                changes.append(event) if event.data["entity_id"] == entity_id else None
            ),
        )

        coordinator._check_new_sms(_inbox(("2", "2026-10-24 09:05:00")))
        await hass.async_block_till_done()

    assert changes
    stored = json.loads(
        StateAttributes.shared_attrs_bytes_from_event(
            changes[-1], SupportedDialect.SQLITE
        )
    )
    assert stored["event_type"] == "received"
    assert "phone" not in stored
    assert "content" not in stored
