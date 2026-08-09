"""Entity hygiene sweeps.

These are **coverage** tests, not mechanism tests. Each asserts that every
member of a set satisfies a property, so it fails the moment the set grows —
which is the shape that catches a new entity shipped without the thing every
other entity has. A mechanism test passes right up until the mechanism is
bypassed; a coverage test cannot.

**If one of these fails, it has found something. Do not reach for the
allow-list first.** The failure will look unrelated to whatever you just
changed, because the trigger is the set growing rather than the code path
running.
"""

from homeassistant.components.sensor import SensorStateClass

from custom_components.huawei_router_5g.sensor import SENSOR_TYPES

# ---------------------------------------------------------------------------
# Section 2.2 — SensorStateClass.TOTAL is banned
# ---------------------------------------------------------------------------

# Deliberately empty. Adding an entry is a reviewable act; typing `TOTAL` into
# a new description is not.
ALLOWED_TOTAL_STATE_CLASS: frozenset[str] = frozenset()


def test_no_sensor_uses_the_total_state_class() -> None:
    """No sensor may use `SensorStateClass.TOTAL`.

    `TOTAL` and `TOTAL_INCREASING` look interchangeable and are not. Under
    `TOTAL` the recorder recognizes a new cycle *only* from a changing
    `last_reset` attribute; a counter that simply drops to zero is not treated
    as having reset. `TOTAL_INCREASING` detects the drop itself and needs no
    attribute.

    This integration published four resetting counters under `TOTAL` without
    ever publishing `last_reset` — one daily and three monthly — so every
    billing rollover was recorded as a large negative delta and walked the
    long-term statistics sum backwards. Nothing failed at runtime, which is
    exactly why this is a test and not a code-review item.

    **If this test fails, the `TOTAL` must be justified, not silenced.** A
    genuine `TOTAL` sensor is one whose value can legitimately fall without
    that being a reset — net import/export, a draining tank — and it must
    publish `last_reset`. If the new sensor really is that, add its key to
    `ALLOWED_TOTAL_STATE_CLASS` with a comment saying why. If it is a counter
    that resets to zero, the sensor is wrong and the test is right.
    """
    offenders = [
        description.key
        for description in SENSOR_TYPES
        if description.state_class is SensorStateClass.TOTAL
        and description.key not in ALLOWED_TOTAL_STATE_CLASS
    ]

    assert not offenders, (
        "sensors using SensorStateClass.TOTAL — use TOTAL_INCREASING for a "
        "counter that resets to zero, or justify the TOTAL in "
        "ALLOWED_TOTAL_STATE_CLASS:\n" + "\n".join(sorted(offenders))
    )


def test_total_state_class_sweep_is_not_vacuous() -> None:
    """Guard the guard.

    The sweep above passes trivially if `SENSOR_TYPES` stops carrying state
    classes at all — a refactor that moved them onto the entity class would
    leave it green forever. Pin that the set it inspects is non-empty and that
    the counters it was written for are still the corrected class.
    """
    with_state_class = [d for d in SENSOR_TYPES if d.state_class is not None]
    assert len(with_state_class) >= 20, (
        f"sweep only inspected {len(with_state_class)} sensors — SENSOR_TYPES "
        "is stale or state classes have moved off the descriptions"
    )

    by_key = {d.key: d for d in SENSOR_TYPES}
    for key in ("current_day_used", "month_download", "month_upload", "month_total"):
        assert by_key[key].state_class is SensorStateClass.TOTAL_INCREASING, (
            f"{key} is a resetting counter and must be TOTAL_INCREASING"
        )


def test_allowed_total_state_class_has_no_dead_entries() -> None:
    """An exemption must not outlive the sensor it exempts.

    Without this, deleting an exempted sensor leaves its key in the allow-list,
    where it silently pre-approves any future sensor that happens to reuse the
    key.
    """
    keys = {d.key for d in SENSOR_TYPES}
    stale = sorted(ALLOWED_TOTAL_STATE_CLASS - keys)
    assert not stale, (
        "ALLOWED_TOTAL_STATE_CLASS names sensors that no longer exist: "
        + ", ".join(stale)
    )


# ---------------------------------------------------------------------------
# Section 14 — every published attribute must be an explicit recorder decision
# ---------------------------------------------------------------------------

# Attributes that are *deliberately* written to the recorder, because their
# history is worth keeping. Empty today: nothing this integration publishes as
# an attribute is a time series. An entry here is a reviewable act; forgetting
# `_unrecorded_attributes` on a new entity is not, which is what this sweep
# exists to catch.
ALLOWED_RECORDED: frozenset[str] = frozenset()


def _entity_classes_declaring_attributes() -> list[type]:
    """Every entity class in the component that overrides `extra_state_attributes`.

    Found by inspection rather than listed, so a new platform cannot be added
    without this sweep seeing it. A hand-maintained list is the failure mode
    this whole file is written against.
    """
    import importlib
    import inspect
    import pkgutil

    import custom_components.huawei_router_5g as component

    found: list[type] = []
    for mod_info in pkgutil.iter_modules(component.__path__):
        module = importlib.import_module(f"{component.__name__}.{mod_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            if "extra_state_attributes" in vars(obj):
                found.append(obj)
    return found


def test_every_entity_publishing_attributes_declares_unrecorded() -> None:
    """Section 14: an entity that publishes attributes must decide their fate.

    Without `_unrecorded_attributes`, every attribute of every entity is
    written to the recorder on every state change. This integration had **zero**
    across the whole component, so a device tracker republished each client's
    interface type and associated SSID once per client per poll, and the SMS
    sensor republished the sender's phone number.

    **If this fails, the new entity needs a decision, not an exemption.** Add
    `_unrecorded_attributes` naming its keys; only add to `ALLOWED_RECORDED` if
    the attribute is genuinely a time series worth keeping.
    """
    offenders = [
        cls.__name__
        for cls in _entity_classes_declaring_attributes()
        if not getattr(cls, "_unrecorded_attributes", frozenset())
        and cls.__name__ not in ALLOWED_RECORDED
    ]

    assert not offenders, (
        "entity classes publishing attributes with no _unrecorded_attributes "
        "declaration — every attribute they emit is being recorded:\n"
        + "\n".join(sorted(offenders))
    )


def test_unrecorded_attribute_sweep_is_not_vacuous() -> None:
    """Guard the guard.

    If the discovery above stops finding classes — a refactor moving
    `extra_state_attributes` onto a shared base, say — the sweep passes
    trivially and keeps passing through any regression.
    """
    found = _entity_classes_declaring_attributes()
    assert len(found) >= 3, (
        f"discovery found only {len(found)} entity classes publishing "
        "attributes — it has stopped seeing the component"
    )
