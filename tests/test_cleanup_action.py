"""The `cleanup_unused_entities` action.

A `device_tracker` entity is created for every client the router has ever
reported and nothing removes it, so a guest's phone seen once leaves a
permanent entity. With two routers configured that accumulation stops being
cosmetic.

**The dangerous case is not failing to delete — it is deleting too much.** An
empty coordinator payload during an outage would make every client look stale,
so the guard against that is the most important thing here and is tested first.
"""

from unittest.mock import MagicMock

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.huawei_router_5g import _stale_tracker_entities, _tracked_macs
from custom_components.huawei_router_5g.const import DOMAIN

PRESENT = "AA:BB:CC:DD:EE:01"
GONE = "AA:BB:CC:DD:EE:99"


def _payload(*macs: str) -> dict:
    return {
        "lan_host_info": {
            "Hosts": {"Host": [{"MacAddress": macs[0]}]} if macs else {"Host": []}
        },
        "wlan_host_list": {"Hosts": {"Host": [{"MacAddress": m} for m in macs[1:]]}},
    }


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    """Build a config entry with two client trackers registered."""
    config_entry = MockConfigEntry(domain=DOMAIN, unique_id="dc7196112233")
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for mac in (PRESENT, GONE):
        registry.async_get_or_create(
            Platform.DEVICE_TRACKER,
            DOMAIN,
            f"dc7196112233_{mac}",
            config_entry=config_entry,
        )
    return config_entry


def test_nothing_is_stale_while_the_coordinator_has_no_data(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """An outage must never look like "every client has left".

    `coordinator.data` is `None` before the first successful poll and can be
    empty during a failure. Treating that as authoritative would delete every
    tracker the integration has — the worst possible outcome for a cleanup
    action, and irreversible.
    """
    coordinator = MagicMock()
    coordinator.data = None
    entry.runtime_data = coordinator

    assert _stale_tracker_entities(hass, entry) == []

    coordinator.data = {}
    assert _stale_tracker_entities(hass, entry) == []


def test_a_payload_with_no_hosts_at_all_removes_nothing(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """A successful poll that lists zero clients is still not a mandate.

    The router returning an empty host list is indistinguishable from it
    failing to populate one, so this errs towards keeping entities. A user who
    genuinely has no clients has nothing to clean up anyway.
    """
    coordinator = MagicMock()
    coordinator.data = _payload()
    entry.runtime_data = coordinator

    assert _stale_tracker_entities(hass, entry) == []


def test_only_the_client_the_router_no_longer_lists_is_stale(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """The actual job: one present, one gone, exactly one reported."""
    coordinator = MagicMock()
    coordinator.data = _payload(PRESENT)
    entry.runtime_data = coordinator

    stale = _stale_tracker_entities(hass, entry)

    assert [item.unique_id for item in stale] == [f"dc7196112233_{GONE}"]


def test_entities_from_another_config_entry_are_untouched(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """A second router's trackers must never be cleaned up by the first.

    This is the whole reason the unique-id prefix exists; the cleanup filters
    on it, so a bug here would delete the other router's clients.
    """
    other = MockConfigEntry(domain=DOMAIN, unique_id="001122aabbcc")
    other.add_to_hass(hass)
    registry = er.async_get(hass)
    theirs = registry.async_get_or_create(
        Platform.DEVICE_TRACKER, DOMAIN, f"001122aabbcc_{GONE}", config_entry=other
    )

    coordinator = MagicMock()
    coordinator.data = _payload(PRESENT)
    entry.runtime_data = coordinator

    stale = _stale_tracker_entities(hass, entry)

    assert theirs.entity_id not in [item.entity_id for item in stale]


def test_non_tracker_entities_are_never_stale(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Only client trackers are dynamic; every other entity is fixed.

    A sensor whose key happens not to appear in the host list must not be
    swept up — the filter is on platform, not merely on the prefix.
    """
    registry = er.async_get(hass)
    sensor = registry.async_get_or_create(
        Platform.SENSOR, DOMAIN, "dc7196112233_rsrp", config_entry=entry
    )

    coordinator = MagicMock()
    coordinator.data = _payload(PRESENT)
    entry.runtime_data = coordinator

    assert sensor.entity_id not in [
        item.entity_id for item in _stale_tracker_entities(hass, entry)
    ]


def test_macs_are_collected_from_both_host_lists() -> None:
    """Wired and wireless clients live in different blocks.

    Reading only one would report every client on the other as stale, which is
    a deletion bug rather than a reporting one.
    """
    coordinator = MagicMock()
    coordinator.data = {
        "lan_host_info": {"Hosts": {"Host": [{"MacAddress": "WIRED"}]}},
        "wlan_host_list": {"Hosts": {"Host": [{"MacAddress": "WIFI"}]}},
    }

    assert _tracked_macs(coordinator) == {"WIRED", "WIFI"}


def test_a_malformed_host_block_does_not_lose_the_other_one() -> None:
    """A non-dict block is skipped, not fatal, and does not discard the rest.

    Same shape as the device_tracker discovery guard: the broken source is
    first, so "skipped and continued" is distinguishable from "skipped and
    stopped".
    """
    coordinator = MagicMock()
    coordinator.data = {
        "lan_host_info": "ERROR",
        "wlan_host_list": {"Hosts": {"Host": [{"MacAddress": "WIFI"}]}},
    }

    assert _tracked_macs(coordinator) == {"WIFI"}


def test_host_entries_without_a_mac_are_skipped() -> None:
    """A host row missing `MacAddress` must be ignored, not counted.

    Two rows with the unusable one first, so "skipped and continued" is
    distinguishable from "skipped and stopped" — a stop here would report every
    later client as stale and delete it.
    """
    coordinator = MagicMock()
    coordinator.data = {
        "lan_host_info": {
            "Hosts": {"Host": [{"HostName": "no-mac"}, {"MacAddress": "WIRED"}]}
        },
        "wlan_host_list": {"Hosts": {"Host": []}},
    }

    assert _tracked_macs(coordinator) == {"WIRED"}


async def test_the_action_previews_by_default_and_removes_nothing(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """`dry_run` defaults to true.

    Removal is irreversible and the stale signal is a judgement about a router
    that may simply have aged a client out of its table, so the default has to
    be the safe one.
    """
    from custom_components.huawei_router_5g import async_setup
    from custom_components.huawei_router_5g.const import SERVICE_CLEANUP

    coordinator = MagicMock()
    coordinator.data = _payload(PRESENT)
    entry.runtime_data = coordinator
    await async_setup(hass, {})

    response = await hass.services.async_call(
        DOMAIN, SERVICE_CLEANUP, {}, blocking=True, return_response=True
    )

    assert response["dry_run"] is True
    registry = er.async_get(hass)
    assert registry.async_get_entity_id(
        Platform.DEVICE_TRACKER, DOMAIN, f"dc7196112233_{GONE}"
    ), "a preview run removed an entity"


async def test_the_action_removes_when_dry_run_is_off(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """The distinction being asserted is *removed vs. reported*.

    A test that only checked the response payload would pass against an
    implementation that reports everything and deletes nothing.
    """
    from custom_components.huawei_router_5g import async_setup
    from custom_components.huawei_router_5g.const import SERVICE_CLEANUP

    coordinator = MagicMock()
    coordinator.data = _payload(PRESENT)
    entry.runtime_data = coordinator
    await async_setup(hass, {})

    registry = er.async_get(hass)
    assert registry.async_get_entity_id(
        Platform.DEVICE_TRACKER, DOMAIN, f"dc7196112233_{GONE}"
    )

    response = await hass.services.async_call(
        DOMAIN, SERVICE_CLEANUP, {"dry_run": False}, blocking=True, return_response=True
    )

    assert response["dry_run"] is False
    assert (
        registry.async_get_entity_id(
            Platform.DEVICE_TRACKER, DOMAIN, f"dc7196112233_{GONE}"
        )
        is None
    ), "the stale tracker was reported but not removed"
    # The live client must survive.
    assert registry.async_get_entity_id(
        Platform.DEVICE_TRACKER, DOMAIN, f"dc7196112233_{PRESENT}"
    ), "a client the router still reports was removed"
