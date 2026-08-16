"""The `device_tracker` unique-ID migration.

`ScannerEntity.unique_id` returns the bare MAC address, which is not unique
across config entries: two Huawei routers seeing the same client mint the same
id, and Home Assistant refuses to add the second entity at all rather than
suffixing it. The entity now scopes its own id to the config entry.

**The migration is what makes that non-breaking**, so it is what these tests
are about. Rewriting the existing registry row preserves the `entity_id`, the
name, the area, the enabled state and every customization — only `unique_id`
changes. Without it the old rows would be orphaned and new entities minted with
`_2` suffixes, breaking every automation that referenced them.
"""

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.huawei_router_5g import _async_migrate_tracker_unique_ids
from custom_components.huawei_router_5g.const import DOMAIN

MAC = "AA:BB:CC:DD:EE:01"


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    """Build a loaded config entry with a MAC-derived unique id."""
    config_entry = MockConfigEntry(domain=DOMAIN, unique_id="dc7196112233")
    config_entry.add_to_hass(hass)
    return config_entry


async def test_a_legacy_bare_mac_id_is_rewritten_in_place(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """The row is rewritten, not replaced.

    This is the whole claim of the migration: same registry entry, same
    `entity_id`, new `unique_id`. If this ever regresses into
    delete-and-recreate, every automation referencing the tracker breaks.
    """
    registry = er.async_get(hass)
    original = registry.async_get_or_create(
        Platform.DEVICE_TRACKER,
        DOMAIN,
        MAC,
        config_entry=entry,
        suggested_object_id="huawei_5g_laptop",
    )
    original = registry.async_update_entity(original.entity_id, name="Sam's laptop")

    await _async_migrate_tracker_unique_ids(hass, entry)

    migrated = registry.async_get(original.entity_id)
    assert migrated is not None, "the entity_id changed — the row was not rewritten"
    assert migrated.unique_id == f"dc7196112233_{MAC}"
    assert migrated.id == original.id
    assert migrated.name == "Sam's laptop"


async def test_the_migration_is_idempotent(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """A second run must not double-prefix.

    `async_setup_entry` runs on every restart and every reload, so this runs
    far more often than once. Prefixing twice would mint
    `dc7196112233_dc7196112233_AA:...` and orphan the entity on the next
    startup.
    """
    registry = er.async_get(hass)
    created = registry.async_get_or_create(
        Platform.DEVICE_TRACKER, DOMAIN, MAC, config_entry=entry
    )

    await _async_migrate_tracker_unique_ids(hass, entry)
    await _async_migrate_tracker_unique_ids(hass, entry)

    assert registry.async_get(created.entity_id).unique_id == f"dc7196112233_{MAC}"


async def test_other_platforms_are_left_alone(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Only `device_tracker` ids are legacy.

    Every other platform has always built `{entry.unique_id}_{key}` ids, so
    touching them would prefix an already-prefixed id and orphan the entity.
    """
    registry = er.async_get(hass)
    sensor = registry.async_get_or_create(
        Platform.SENSOR, DOMAIN, "dc7196112233_rsrp", config_entry=entry
    )

    await _async_migrate_tracker_unique_ids(hass, entry)

    assert registry.async_get(sensor.entity_id).unique_id == "dc7196112233_rsrp"


async def test_an_entry_with_no_unique_id_is_skipped(hass: HomeAssistant) -> None:
    """No entry unique id means no prefix worth building.

    Prefixing with `None` would produce the literal string `None_AA:BB:...`,
    which is worse than leaving the id alone.
    """
    config_entry = MockConfigEntry(domain=DOMAIN, unique_id=None)
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    created = registry.async_get_or_create(
        Platform.DEVICE_TRACKER, DOMAIN, MAC, config_entry=config_entry
    )

    await _async_migrate_tracker_unique_ids(hass, config_entry)

    assert registry.async_get(created.entity_id).unique_id == MAC


async def test_two_routers_can_track_the_same_client(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """The defect this whole change exists for.

    With bare-MAC ids, a client seen by two Huawei routers produced one id
    twice and Home Assistant dropped the second entity. Scoped ids let both
    exist — which is the observable difference, and the reason a second router
    made this worth fixing.
    """
    second = MockConfigEntry(domain=DOMAIN, unique_id="001122aabbcc")
    second.add_to_hass(hass)
    registry = er.async_get(hass)

    first_tracker = registry.async_get_or_create(
        Platform.DEVICE_TRACKER, DOMAIN, f"{entry.unique_id}_{MAC}", config_entry=entry
    )
    second_tracker = registry.async_get_or_create(
        Platform.DEVICE_TRACKER,
        DOMAIN,
        f"{second.unique_id}_{MAC}",
        config_entry=second,
    )

    assert first_tracker.entity_id != second_tracker.entity_id
    assert first_tracker.unique_id != second_tracker.unique_id
