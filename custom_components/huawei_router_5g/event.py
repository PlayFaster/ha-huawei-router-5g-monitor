"""Event platform for Huawei Router 5G Monitor.

One entity per config entry, `incoming_sms`, triggered once for each new SMS
in the same loop and order as the `huawei_router_5g_sms_received` bus event,
which is kept unchanged. The entity makes incoming SMS selectable in the
automation editor and visible in the logbook and on the device page.
Cross-project item `.shared/issues/x_project/incoming_sms_event_entity.md`.
"""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import ABOUT_UNRECORDED, HuaweiAboutEntity, HuaweiDeviceEntity

# Section 22. `0` (unlimited): the entity is pushed by the coordinator and
# makes no request of its own.
PARALLEL_UPDATES = 0

EVENT_TYPE_RECEIVED = "received"


@dataclass(frozen=True, kw_only=True)
class HuaweiEventEntityDescription(EventEntityDescription):
    """Describes a Huawei Router 5G event entity."""

    group: str = "system"
    # dev_standards Section 14 - the human-facing `about` note.
    about: str | None = None


INCOMING_SMS_DESCRIPTION = HuaweiEventEntityDescription(
    key="incoming_sms",
    translation_key="incoming_sms",
    group="sms",
    event_types=[EVENT_TYPE_RECEIVED],
    about=(
        "Fires once for each new SMS the router receives, with the same data "
        "as the huawei_router_5g_sms_received event. The sender and the text "
        "are not written to the recorder."
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the event platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        [HuaweiIncomingSmsEvent(coordinator, entry, INCOMING_SMS_DESCRIPTION)]
    )


class HuaweiIncomingSmsEvent(
    HuaweiAboutEntity,
    HuaweiDeviceEntity,
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator],
    EventEntity,
):
    """Event entity triggered for each new SMS."""

    _attr_has_entity_name = True
    entity_description: HuaweiEventEntityDescription

    # dev_standards Section 14. Home Assistant writes event attributes to the
    # recorder by default, so without this every sender and message text
    # would be stored in the database. `_unrecorded_attributes` is not unioned
    # across bases, so it starts from `ABOUT_UNRECORDED`.
    _unrecorded_attributes = ABOUT_UNRECORDED | frozenset({"phone", "content"})

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry: ConfigEntry,
        description: HuaweiEventEntityDescription,
    ) -> None:
        """Initialize the event entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

    async def async_added_to_hass(self) -> None:
        """Register for new messages from the coordinator."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.add_sms_listener(self._on_sms))

    @callback
    def _on_sms(self, message: dict[str, Any]) -> None:
        """Trigger the event for one new message."""
        self._trigger_event(
            EVENT_TYPE_RECEIVED,
            {
                "phone": message["phone"],
                "content": message["content"],
                "date": message["date"],
                "index": message["index"],
            },
        )
        self.async_write_ha_state()
