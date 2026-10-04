"""Section 14 runtime sweep — attributes, against a real `hass`.

`test_entity_hygiene.py` already sweeps `_unrecorded_attributes` **statically**,
by walking modules and inspecting classes that override
`extra_state_attributes`. That check is worth keeping and it is not enough.

`dev_standards` Section 14 requires the runtime form, and states the reason
directly: description-driven entities build their attributes from a function on
the entity description, so the keys never appear in any class body and no static
check can see them. This integration is exactly that shape — 158 descriptions,
most of them carrying a `value_fn`, plus an `about` note injected by a shared
base. The static sweep can confirm a class declares *something*; only a live
entity can say what it actually publishes.

The failure this guards is silent. A new attribute is simply written to the
recorder on every state change and nothing errors — the database grows, and the
only symptom is a bill or a slow purge months later. It is also a failure that
has already happened here twice: `_unrecorded_attributes` turned out not to be
unioned across base classes, so six subclasses silently dropped `about` from the
exclusion, and Projected Usage published `confidence` that no static reading of
the class would have revealed.
"""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from tests.conftest import _live_entities

# Attributes deliberately left recorded, with the justification Section 14
# demands. **Empty by design.** Attributes carry detail that does not merit its
# own entity; they are not history. Anything that needs history should be an
# entity or a user template sensor.
#
# Adding an entry here is a reviewable act. Forgetting to add a key to
# `_unrecorded_attributes` is not — which is the entire point of the sweep.
ALLOWED_RECORDED: frozenset[str] = frozenset()


@pytest.mark.asyncio
async def test_no_live_entity_publishes_a_recorded_attribute(
    hass: HomeAssistant, live_entry: MockConfigEntry
) -> None:
    """Every attribute every live entity publishes must be excluded.

    This is the check the static sweep cannot make. It reads
    `extra_state_attributes` off the constructed entity, which is the same
    property HA itself calls, so whatever the entity really emits is what gets
    compared — `value_fn` output, the injected `about` note, and anything a
    base class adds along the way.
    """
    async with _live_entities(hass, live_entry) as entities:
        checked = 0
        offenders: list[str] = []

        for entity in entities:
            published = set(entity.extra_state_attributes or {})
            if not published:
                continue
            checked += 1
            leaked = published - entity._unrecorded_attributes - ALLOWED_RECORDED
            if leaked:
                offenders.append(f"{entity.entity_id}: {sorted(leaked)}")

    assert not offenders, "attributes published but recorded:\n" + "\n".join(offenders)

    # Guard the guard. If the payload above stops producing attributes — a key
    # renamed, a platform reshaped — the sweep would pass over an empty set and
    # go on passing after a real regression. This is the assertion that makes
    # the test non-vacuous, and it is the one that has mattered elsewhere.
    # Measured at 161 on 2026-08-15. The floor sits just below that rather
    # than at a token value: set to 20 it would have passed with seven eighths
    # of the component silently dropping out of the sweep, which is the exact
    # failure this assertion exists to catch.
    assert checked >= 150, (
        f"sweep inspected only {checked} entities publishing attributes — "
        "SWEEP_DATA is stale, not the component"
    )


@pytest.mark.asyncio
async def test_every_live_entity_publishes_its_about_note(
    hass: HomeAssistant, live_entry: MockConfigEntry
) -> None:
    """The `about` note must survive to runtime, on every entity.

    Section 14's note requirement is only met if the note actually reaches the
    state machine. `_unrecorded_attributes` is **not** unioned across base
    classes — a subclass that sets its own replaces the parent's rather than
    extending it — and that silently dropped `about` from the recorder
    exclusion on six classes when the notes first shipped. A static check on
    the descriptions cannot see that; this can.
    """
    async with _live_entities(hass, live_entry) as entities:
        missing = [
            entity.entity_id
            for entity in entities
            if "about" not in (entity.extra_state_attributes or {})
        ]

    assert not missing, "live entities publishing no about note:\n" + "\n".join(
        sorted(missing)
    )


# ---------------------------------------------------------------------------
# Section 12 — translations and icons, resolved against LIVE entities
#
# `test_entity_hygiene.py` reconciles both against **source**, by regex over
# `translation_key="..."` and by reading the description tuples. That catches
# drift and is worth keeping, but it is not what §12's tag asks for: the tag
# specifies live entities, because source-reading cannot tell whether an
# entity was actually constructed, which platform it landed on, or whether a
# key reachable in a module is reachable at runtime. An entity built by a
# factory, skipped by a capability check, or filed under a different platform
# than its module suggests is invisible to a regex and obvious here.
# ---------------------------------------------------------------------------


def _translations(name: str) -> dict:
    import json
    import pathlib

    import custom_components.huawei_router_5g as component

    path = pathlib.Path(component.__path__[0]) / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_every_live_entity_resolves_its_name(
    hass: HomeAssistant, live_entry: MockConfigEntry
) -> None:
    """Every constructed entity's `translation_key` must resolve, per platform.

    Checked **per platform**, which is the part source-reading cannot do. A key
    filed under `sensor` in `strings.json` while its entity is built on
    `binary_sensor` resolves fine to any check that flattens the file, and
    shows the user a raw key.
    """
    missing: list[str] = []

    async with _live_entities(hass, live_entry) as entities:
        for name in ("strings.json", "translations/en.json"):
            entity_section = _translations(name).get("entity", {})
            for entity in entities:
                key = getattr(entity, "translation_key", None)
                if not key:
                    continue
                platform = entity.entity_id.split(".", 1)[0]
                if key not in entity_section.get(platform, {}):
                    missing.append(f"{name}: {platform}.{key} ({entity.entity_id})")

    assert not missing, "live entities with no translated name:\n" + "\n".join(
        sorted(set(missing))
    )


@pytest.mark.asyncio
async def test_every_live_entity_has_an_icon_or_derives_one(
    hass: HomeAssistant, live_entry: MockConfigEntry
) -> None:
    """A live entity must get its icon from `icons.json` or a `device_class`.

    Those two only — a hardcoded `_attr_icon` does not count.

    Without either, HA falls back to a generic dot. That is not an error and
    nothing logs — it just looks unfinished, which is why this needs a test
    rather than a glance.

    Also checked per platform, and against what was actually built rather than
    against the description tuples.
    """
    icons = _translations("icons.json").get("entity", {})
    bare: list[str] = []

    async with _live_entities(hass, live_entry) as entities:
        for entity in entities:
            key = getattr(entity, "translation_key", None)
            if not key:
                continue
            platform = entity.entity_id.split(".", 1)[0]
            if key in icons.get(platform, {}):
                continue
            if getattr(entity, "device_class", None) is not None:
                continue
            # `_attr_icon` is deliberately NOT accepted. Section 12 wants icons
            # in `icons.json`, where they are translatable and reviewable in
            # one place; a hardcoded `_attr_icon` satisfies the eye and defeats
            # the check. Allowing it here made the sweep pass for any entity
            # that set one, which is the hole rather than the exemption.
            bare.append(f"{platform}.{key} ({entity.entity_id})")

    assert not bare, (
        "live entities with neither an icon nor a device_class:\n"
        + "\n".join(sorted(bare))
    )
