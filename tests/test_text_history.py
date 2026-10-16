"""Long-term history for eight text sensors (1.2.4-dev4 I5).

Ported from `zte_router_5g` with its verification: a change appends a
transition, the list keeps the latest twenty, both stores survive a reload and
are deleted with the entry, and the populated set only grows.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.huawei_router_5g import async_remove_entry
from custom_components.huawei_router_5g.const import DOMAIN
from custom_components.huawei_router_5g.observations import (
    HISTORY_CAP,
    TRACKED,
    ObservationRecorder,
)
from custom_components.huawei_router_5g.sensor import SENSOR_TYPES, HuaweiRouterSensor
from homeassistant.core import HomeAssistant


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="00:11:22:33:44:55", data={})
    entry.add_to_hass(hass)
    return entry


def _payload(version: str, *, signal: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "device_information": {"SoftwareVersion": version, "uptime": "1234"},
    }
    if signal:
        data["device_signal"] = {"rsrp": "-90dBm"}
    return data


@pytest.mark.asyncio
async def test_a_change_appends_a_transition(hass: HomeAssistant) -> None:
    """The first reading starts the series; a change is a counted transition."""
    recorder = ObservationRecorder(hass, _entry(hass))
    assert recorder.observe(_payload("1.0"))
    assert recorder.change_count("sw_version") == 0
    assert recorder.observe(_payload("1.1"))
    assert not recorder.observe(_payload("1.1"))

    entries = recorder.history("sw_version")
    assert [(e["from"], e["to"]) for e in entries] == [(None, "1.0"), ("1.0", "1.1")]
    assert entries[-1]["uptime_at_change"] == 1234
    assert recorder.change_count("sw_version") == 1


@pytest.mark.asyncio
async def test_the_history_keeps_the_latest_twenty(hass: HomeAssistant) -> None:
    """25 changes keep 20 entries, and the counter keeps all of them."""
    recorder = ObservationRecorder(hass, _entry(hass))
    for n in range(26):
        recorder.observe(_payload(f"v{n}"))
    entries = recorder.history("sw_version")
    assert len(entries) == HISTORY_CAP == 20
    assert entries[-1]["to"] == "v25"
    assert recorder.change_count("sw_version") == 25


@pytest.mark.asyncio
async def test_both_records_survive_a_reload(hass: HomeAssistant) -> None:
    """A second recorder on the same entry reads what the first saved."""
    entry = _entry(hass)
    first = ObservationRecorder(hass, entry)
    first.observe(_payload("1.0"))
    first.observe(_payload("1.1"))
    await first.async_save()

    second = ObservationRecorder(hass, entry)
    await second.async_load()
    assert second.history("sw_version") == first.history("sw_version")
    assert second.change_count("sw_version") == 1
    assert "sw_version" in second.ever_populated()


@pytest.mark.asyncio
async def test_removing_the_entry_deletes_both_stores(hass: HomeAssistant) -> None:
    """`async_remove_entry` deletes the history and the observed store."""
    entry = _entry(hass)
    first = ObservationRecorder(hass, entry)
    first.observe(_payload("1.0"))
    await first.async_save()

    await async_remove_entry(hass, entry)

    second = ObservationRecorder(hass, entry)
    await second.async_load()
    assert second.history("sw_version") == []
    assert second.ever_populated() == frozenset()


@pytest.mark.asyncio
async def test_the_populated_set_only_grows(hass: HomeAssistant) -> None:
    """A degraded poll that drops a block removes nothing from the set."""
    recorder = ObservationRecorder(hass, _entry(hass))
    recorder.observe(_payload("1.0"))
    before = recorder.ever_populated()
    assert "rsrp" in before

    recorder.observe(_payload("1.0", signal=False))
    assert recorder.ever_populated() == before
    assert recorder.populated_history()["entities_known_populated"] == len(before)


@pytest.mark.asyncio
async def test_an_install_with_no_store_starts_empty_and_records(
    hass: HomeAssistant,
) -> None:
    """Upgrade sequence: no store before 1.2.4-dev4, then one written and read back."""
    entry = _entry(hass)
    recorder = ObservationRecorder(hass, entry)
    await recorder.async_load()
    assert recorder.history("sw_version") == []
    assert recorder.change_count("sw_version") == 0

    recorder.observe(_payload("1.0"))
    await recorder.async_save()
    restarted = ObservationRecorder(hass, entry)
    await restarted.async_load()
    assert restarted.history("sw_version")[0]["to"] == "1.0"
    assert restarted.change_count("sw_version") == 0


def test_eight_counters_exist_and_only_software_version_is_enabled() -> None:
    """One counter per tracked key; only Software Version's is enabled."""
    counters = {d.counts_changes_of: d for d in SENSOR_TYPES if d.counts_changes_of}
    assert set(counters) == set(TRACKED)
    assert len(TRACKED) == 8
    enabled = {key for key, d in counters.items() if d.entity_registry_enabled_default}
    assert enabled == {"sw_version"}
    assert all(d.state_class == "total_increasing" for d in counters.values())


def test_the_history_attributes_are_unrecorded() -> None:
    """The history and its two summary fields never reach the recorder."""
    assert {"history", "previous_version", "last_changed"} <= (
        HuaweiRouterSensor._unrecorded_attributes
    )


@pytest.mark.asyncio
async def test_an_unreadable_store_is_counted_and_reported(hass: HomeAssistant) -> None:
    """A read fault leaves an empty record, a count, and a warning."""
    from unittest.mock import AsyncMock, patch

    recorder = ObservationRecorder(hass, _entry(hass))
    with patch.object(
        recorder._history_store, "async_load", AsyncMock(side_effect=OSError("bad"))
    ):
        await recorder.async_load()
    recorder.observe(_payload("1.0"))
    report = recorder.report()
    assert report["load_faults"] == 1
    assert report["series"]["sw_version"]["entries"] == 1
    assert report["entities_known_populated"] > 0


@pytest.mark.asyncio
async def test_a_write_fault_is_swallowed(hass: HomeAssistant) -> None:
    """A store that cannot be written never raises into the poll."""
    from unittest.mock import AsyncMock, patch

    recorder = ObservationRecorder(hass, _entry(hass))
    recorder.observe(_payload("1.0"))
    with (
        patch.object(
            recorder._history_store,
            "async_save",
            AsyncMock(side_effect=OSError("full")),
        ) as history_save,
        patch.object(recorder._observed_store, "async_save", AsyncMock()) as observed,
    ):
        await recorder.async_save()
    history_save.assert_awaited_once()
    # The fault on one store does not stop the other being written.
    observed.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_snapshot_is_saved_and_read_back(hass: HomeAssistant) -> None:
    """The reset action's baseline lives in the observed store."""
    entry = _entry(hass)
    recorder = ObservationRecorder(hass, entry)
    assert recorder.snapshot() == {}
    await recorder.async_save_snapshot({"rsrp": True})
    again = ObservationRecorder(hass, entry)
    await again.async_load()
    assert again.snapshot() == {"rsrp": True}


@pytest.mark.asyncio
async def test_a_recorder_that_does_not_persist_writes_nothing(
    hass: HomeAssistant,
) -> None:
    """The Diag Check's recorder shares the live entry's id and must not write."""
    entry = _entry(hass)
    recorder = ObservationRecorder(hass, entry, persist=False)
    recorder.observe(_payload("1.0"))
    await recorder.async_save()
    reader = ObservationRecorder(hass, entry)
    await reader.async_load()
    assert reader.history("sw_version") == []


@pytest.mark.asyncio
async def test_removal_survives_a_store_fault(hass: HomeAssistant) -> None:
    """`async_remove` swallows a fault, so removal always completes."""
    from unittest.mock import AsyncMock, patch

    recorder = ObservationRecorder(hass, _entry(hass))
    with (
        patch.object(
            recorder._history_store,
            "async_remove",
            AsyncMock(side_effect=OSError("x")),
        ) as history_remove,
        patch.object(recorder._observed_store, "async_remove", AsyncMock()) as observed,
    ):
        await recorder.async_remove()
    history_remove.assert_awaited_once()
    observed.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_payload_without_device_information_has_no_uptime(
    hass: HomeAssistant,
) -> None:
    """No uptime is recorded when the block is missing, and nothing raises."""
    from custom_components.huawei_router_5g.observations import _device_uptime

    assert _device_uptime({}) is None
    recorder = ObservationRecorder(hass, _entry(hass))
    assert recorder.observe({"device_signal": {"rsrp": "-90dBm"}})


@pytest.mark.asyncio
async def test_a_value_function_that_raises_is_skipped(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A description that raises is neither recorded nor fatal."""
    from custom_components.huawei_router_5g import observations

    def boom(_data: Any) -> Any:
        raise ValueError("odd payload")

    monkeypatch.setattr(
        observations, "_sensor_value_fns", lambda: dict.fromkeys(TRACKED, boom)
    )
    recorder = ObservationRecorder(hass, _entry(hass))
    recorder.observe(_payload("1.0"))
    assert recorder.history("sw_version") == []


def test_a_description_without_a_value_function_is_not_populated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A binary description with no `value_fn` never enters the populated set."""
    from custom_components.huawei_router_5g import binary_sensor
    from custom_components.huawei_router_5g.observations import entity_keys_with_values

    blank = binary_sensor.HuaweiBinarySensorEntityDescription(key="blank")
    monkeypatch.setattr(
        binary_sensor,
        "VALUE_BINARY_SENSORS",
        (*binary_sensor.VALUE_BINARY_SENSORS, blank),
    )
    assert "blank" not in entity_keys_with_values(_payload("1.0"))
