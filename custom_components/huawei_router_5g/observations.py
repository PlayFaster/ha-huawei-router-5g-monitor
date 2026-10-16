"""What the integration learns from watching successive polls.

Ported from `zte_router_5g` (`observations.py` there, 1.2.4-dev4 I5), with the
same two records, the same store names and the same shapes.

**Transition history.** A text entity cannot carry a `state_class`, so it
produces no long-term statistics: when an operator pushes a firmware update or
reassigns a WAN address, the recorder holds what it changed from and when for
ten days and then forgets. Eight values are watched for changes and the last
twenty transitions of each are kept.

**The populated set.** Which entities have ever reported a value on this
device. The `reset_entities` action uses it so that disabling everything
currently unavailable does not turn off entities that were populated
yesterday, such as 5G sensors while attached to LTE. It is only ever added to,
so a degraded poll fails to record rather than wrongly forgetting.

Both stores are keyed by device, the entry's unique id, as in ZTE.

**Divergences from ZTE.** A tracked value is read through its sensor
description's `value_fn`, because the Huawei payload is nested by endpoint
where ZTE's is flat; ZTE reads router keys through aliases. ZTE's counter-reset
record and learned session lifetimes are not ported: both describe ZTE's
session counter and login model, which Huawei does not share.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING, Any, Final

from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .helpers import _safe_int

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HISTORY_STORAGE_VERSION: Final = 1
OBSERVED_STORAGE_VERSION: Final = 1

# Where the observed store keeps what belongs to the store rather than to a
# device. Every reader here addresses its record by device id, so a key that
# cannot be one is invisible to all of them and needs no version bump.
META_KEY: Final = "_meta"

# Transitions kept per tracked key, oldest discarded first. An event count
# rather than an age, so a slow-moving value keeps years of history and a
# fast-moving one, such as the cell, a short rolling window.
HISTORY_CAP: Final = 20

# The sensor keys whose changes are remembered. Each is rare and consequential
# and can change without the user doing anything. ZTE's sixth key, the bridge
# or gateway mode, has no Huawei sensor yet.
TRACKED: Final[tuple[str, ...]] = (
    "sw_version",
    "wan_ip",
    "apn",
    "cell_id",
    "operator",
    "carrier_build",
    "wan_ipv6",
    "primary_dns",
)


def _device_uptime(data: dict[str, Any]) -> int | None:
    """The router's own uptime in seconds, or None where it is not reported."""
    info = data.get("device_information")
    if not isinstance(info, dict):
        return None
    return _safe_int(info.get("uptime"))


def _sensor_value_fns() -> dict[str, Any]:
    """Map each sensor key to its description's `value_fn`.

    Imported inside the function because the platform modules import the
    coordinator, which imports this one.
    """
    from .sensor import SENSOR_TYPES

    return {d.key: d.value_fn for d in SENSOR_TYPES}


def entity_keys_with_values(data: dict[str, Any]) -> set[str]:
    """Return the keys of every entity that reports a value from this payload.

    Evaluated through each description's own `value_fn` rather than by
    inspecting router keys, so derived values are covered by the same rule.
    """
    from .binary_sensor import VALUE_BINARY_SENSORS
    from .sensor import SENSOR_TYPES

    found: set[str] = set()
    for descriptions in (SENSOR_TYPES, VALUE_BINARY_SENSORS):
        for description in descriptions:
            value_fn = getattr(description, "value_fn", None)
            if value_fn is None:
                continue
            try:
                value = value_fn(data)
            except Exception:  # noqa: BLE001, S112 - see below
                # Broad and silent, as in ZTE: this runs on every successful
                # poll purely to note which entities reported something, and a
                # description that raises is surfaced by its own entity.
                continue
            if value not in (None, ""):
                found.add(description.key)
    return found


class ObservationRecorder:
    """Holds both per-device records and writes them after a poll."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, *, persist: bool = True
    ) -> None:
        """Create the two stores. Neither is read until `async_load`.

        `persist` false keeps both records in memory only, for
        `scripts/diag_check.py`, whose coordinator shares the live entry's id
        and must not overwrite its stores.
        """
        self._entry = entry
        self._persist = persist
        self._history_store: Store[dict[str, Any]] = Store(
            hass, HISTORY_STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_history"
        )
        self._observed_store: Store[dict[str, Any]] = Store(
            hass, OBSERVED_STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_observed"
        )
        self._history: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self._observed: dict[str, dict[str, Any]] = {}
        self.device_id: str = (
            getattr(entry, "unique_id", None) or f"entry_{entry.entry_id}"
        )
        self._load_faults: int = 0

    async def _load_one(
        self, store: Store[dict[str, Any]], label: str
    ) -> dict[str, Any]:
        """Read one store, resolving any fault to an empty record.

        Deliberately broad: no storage fault may fail entry setup, because
        everything here is advisory. Counted and logged at warning, because the
        two are the only trace a fault leaves.
        """
        try:
            stored = await store.async_load()
        except Exception as err:  # noqa: BLE001 - see docstring
            self._load_faults += 1
            _LOGGER.warning(
                "%s: %s store unreadable, continuing without it: %s",
                self._entry.title,
                label,
                err,
            )
            return {}
        return stored if isinstance(stored, dict) else {}

    async def async_load(self) -> None:
        """Read both records into memory. Never raises."""
        self._history = await self._load_one(self._history_store, "history")
        self._observed = await self._load_one(self._observed_store, "observed")
        meta = self._observed.get(META_KEY)
        if isinstance(meta, dict):
            self._load_faults += int(meta.get("load_faults", 0))

    async def async_remove(self) -> None:
        """Delete both files."""
        for store in (self._history_store, self._observed_store):
            with contextlib.suppress(Exception):
                await store.async_remove()

    # -- reading ---------------------------------------------------------

    def history(self, key: str) -> list[dict[str, Any]]:
        """Return the recorded transitions for one tracked key, newest last."""
        return list(self._history.get(self.device_id, {}).get(key, []))

    def change_count(self, key: str) -> int:
        """Return how many transitions have been recorded for one key.

        Counted rather than derived from the capped list, so the counter keeps
        rising after the twenty-first change pushes the first one out.
        """
        record = self._observed.get(self.device_id, {})
        counts = record.get("change_counts", {})
        return int(counts.get(key, 0))

    def ever_populated(self) -> frozenset[str]:
        """Return the entity keys this device has ever reported a value for."""
        record = self._observed.get(self.device_id, {})
        return frozenset(record.get("populated", []))

    def populated_history(self) -> dict[str, Any]:
        """Describe how much the populated record knows, for the reset action."""
        record = self._observed.get(self.device_id, {})
        return {
            "entities_known_populated": len(record.get("populated", [])),
            "recording_since": record.get("since"),
        }

    def report(self) -> dict[str, Any]:
        """Describe both records, for the diagnostics download.

        Shape and dates only, never a recorded value: the tracked values are
        addresses and identifiers.
        """
        record = self._observed.get(self.device_id, {})
        series = self._history.get(self.device_id, {})
        return {
            "recording_since": record.get("since"),
            "load_faults": self._load_faults,
            "entities_known_populated": len(record.get("populated", [])),
            "change_counts": dict(record.get("change_counts", {})),
            "series": {
                key: {
                    "entries": len(entries),
                    "oldest": entries[0].get("timestamp") if entries else None,
                    "newest": entries[-1].get("timestamp") if entries else None,
                }
                for key, entries in series.items()
            },
        }

    def snapshot(self) -> dict[str, bool]:
        """Return the user's saved baseline for this device, or an empty map."""
        record = self._observed.get(self.device_id, {})
        saved = record.get("snapshot")
        return dict(saved) if isinstance(saved, dict) else {}

    async def async_save_snapshot(self, enabled: dict[str, bool]) -> None:
        """Record the enabled state of every entity as this device's baseline."""
        self._observed.setdefault(self.device_id, {})["snapshot"] = dict(enabled)
        await self.async_save()

    # -- writing ---------------------------------------------------------

    def observe(self, data: dict[str, Any]) -> bool:
        """Fold one successful poll into both records.

        Returns whether anything changed, so a caller can skip the write on
        the overwhelming majority of polls where nothing did.
        """
        now = datetime.now(UTC).isoformat()
        dirty = self._observe_transitions(data, now)
        return self._observe_populated(data, now) or dirty

    def _observe_transitions(self, data: dict[str, Any], now: str) -> bool:
        """Append a transition for any tracked value that has changed."""
        record = self._history.setdefault(self.device_id, {})
        counts = self._observed.setdefault(self.device_id, {}).setdefault(
            "change_counts", {}
        )
        value_fns = _sensor_value_fns()
        dirty = False

        for key in TRACKED:
            try:
                value = value_fns[key](data)
            except Exception:  # noqa: BLE001, S112 - as in `entity_keys_with_values`
                continue
            if value in (None, ""):
                continue
            current = str(value)
            entries = record.setdefault(key, [])
            previous = entries[-1]["to"] if entries else None

            # The first reading is not a change. Recorded with `from: None` so
            # the series has a start, but it does not count as a transition.
            if entries and previous == current:
                continue

            entries.append(
                {
                    "timestamp": now,
                    "from": previous,
                    "to": current,
                    "uptime_at_change": _device_uptime(data),
                }
            )
            del entries[:-HISTORY_CAP]
            if previous is not None:
                counts[key] = int(counts.get(key, 0)) + 1
            dirty = True

        return dirty

    def _observe_populated(self, data: dict[str, Any], now: str) -> bool:
        """Add any entity reporting a value to the populated set. Monotonic."""
        record = self._observed.setdefault(self.device_id, {})
        known = set(record.get("populated", []))
        found = entity_keys_with_values(data)
        if found <= known:
            return False

        record["populated"] = sorted(known | found)
        record.setdefault("since", now)
        return True

    async def async_save(self) -> None:
        """Persist both records. Never raises."""
        if not self._persist:
            return
        self._observed[META_KEY] = {"load_faults": self._load_faults}
        for store, payload, label in (
            (self._history_store, self._history, "history"),
            (self._observed_store, self._observed, "observed"),
        ):
            try:
                await store.async_save(payload)
            except Exception as err:  # noqa: BLE001 - advisory, never fatal
                _LOGGER.debug(
                    "%s: %s store unwritable: %s", self._entry.title, label, err
                )
