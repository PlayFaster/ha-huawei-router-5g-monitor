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


# ---------------------------------------------------------------------------
# Section 12 — icon coverage, in both directions
# ---------------------------------------------------------------------------


def _load_json(name: str) -> dict:
    """Load a JSON file from the component directory."""
    import json
    import pathlib

    import custom_components.huawei_router_5g as component

    path = pathlib.Path(component.__path__[0]) / name
    return json.loads(path.read_text(encoding="utf-8"))


def _registered_action_names() -> set[str]:
    """Read the registered actions from `services.yaml`, the source of truth.

    Not from a list in this file, and not from `icons.json` — reading the
    thing under test to build the expectation is how a bidirectional check
    becomes vacuous.
    """
    import pathlib

    import yaml

    import custom_components.huawei_router_5g as component

    path = pathlib.Path(component.__path__[0]) / "services.yaml"
    return set(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def test_every_registered_action_has_an_icon() -> None:
    """Section 12: `icons.json` must cover every action this integration registers.

    Action icons appear in the automation and script editors and in the
    Tools → Actions picker. An integration with no `services` block shows every
    one of its actions with the generic default while a sibling's carry theirs
    — which is how this went unnoticed: nothing is broken, it just looks
    unfinished next to the other three projects.

    This component had **no `services` block at all** while registering four
    actions.
    """
    icons = _load_json("icons.json").get("services", {})
    missing = sorted(_registered_action_names() - set(icons))

    assert not missing, "registered actions with no icon in icons.json: " + ", ".join(
        missing
    )


def test_no_icon_entry_names_an_action_that_does_not_exist() -> None:
    """The other direction: an icon must not outlive its action.

    A dead entry is invisible — it renders nothing and breaks nothing — so it
    accumulates. Checking only one direction is what let the family ship a
    hand-maintained `icons.json` that agreed with itself.
    """
    icons = _load_json("icons.json").get("services", {})
    dead = sorted(set(icons) - _registered_action_names())

    assert not dead, "icons.json names actions that are not registered: " + ", ".join(
        dead
    )


def test_action_icons_use_the_current_nested_form() -> None:
    """Home Assistant's current docs show only the nested form.

    The flat form (`"send_sms": "mdi:…"`) still renders, so this is
    modernization rather than a defect — but only the nested object has
    anywhere to put per-`section` icons, and a family split across two formats
    is the divergence this check exists to prevent. UniFi is the project still
    on the legacy shape.
    """
    icons = _load_json("icons.json").get("services", {})
    assert icons, "no services block at all"

    flat = sorted(name for name, value in icons.items() if not isinstance(value, dict))
    assert not flat, (
        "action icons declared in the legacy flat form — use "
        '{"service": "mdi:…"}: ' + ", ".join(flat)
    )
    for name, value in icons.items():
        assert value.get("service", "").startswith("mdi:"), (
            f"{name} has no `service` icon"
        )


def test_every_entity_description_has_an_icon_or_a_device_class() -> None:
    """Section 12: every entity must be identifiable in the UI.

    Read from **module source** rather than by comparing `icons.json` against
    `strings.json`: two hand-maintained files can agree perfectly and both
    describe an entity that no longer exists. Descriptions here live in a mix
    of one big tuple and module-level singletons, so both shapes are collected.

    A `device_class` is an acceptable substitute — Home Assistant supplies the
    icon from it, and adding a redundant one to `icons.json` would create an
    entry with nothing keeping it honest.
    """
    import importlib
    import inspect
    import pkgutil

    from homeassistant.helpers.entity import EntityDescription

    import custom_components.huawei_router_5g as component

    icons = _load_json("icons.json")["entity"]

    missing: list[str] = []
    checked = 0
    for mod_info in pkgutil.iter_modules(component.__path__):
        platform = mod_info.name
        if platform not in icons:
            continue
        module = importlib.import_module(f"{component.__name__}.{platform}")

        descriptions: list[EntityDescription] = []
        for _, obj in inspect.getmembers(module):
            if isinstance(obj, EntityDescription):
                descriptions.append(obj)
            elif isinstance(obj, tuple):
                descriptions.extend(d for d in obj if isinstance(d, EntityDescription))

        for desc in descriptions:
            checked += 1
            if getattr(desc, "device_class", None) is not None:
                continue
            if desc.key not in icons[platform]:
                missing.append(f"{platform}.{desc.key}")

    assert not missing, (
        "entities with neither an icon nor a device_class:\n"
        + "\n".join(sorted(set(missing)))
    )
    # Guard the guard: this sweep is worthless if it inspected nothing.
    assert checked >= 50, (
        f"sweep only inspected {checked} entity descriptions — discovery is stale"
    )


# ---------------------------------------------------------------------------
# Section 22 — PARALLEL_UPDATES is a decision, and it is recorded here
# ---------------------------------------------------------------------------

# The value follows **the write path**, not the platform's name.
#
# `1` where an entity service call issues a command with a real-world effect on
# the router. `api.py` serializes every call behind an `asyncio.Lock` because
# concurrent calls answer with "Busy" / `110001`; that lock is the actual
# safety mechanism, and `1` states the same intent at the platform boundary.
#
# `0` (unlimited) on read-only platforms, which are coordinator-driven with
# nothing to serialize — and on `number`, which is the interesting one:
# `zte_router_5g` sets `1` on every writable platform, but Huawei's only number
# entity writes to `ConfigEntry.options`, which Home Assistant owns. There is no
# session to tear down and no command to duplicate, so `1` would buy nothing.
EXPECTED_PARALLEL_UPDATES = {
    "button": 1,  # reboot, clear traffic statistics — commands the router
    "switch": 1,  # mobile data, guest WiFi — commands the router
    "select": 1,  # network mode — commands the router
    "number": 0,  # polling interval — writes ConfigEntry.options only
    "sensor": 0,  # read-only
    "binary_sensor": 0,  # read-only
    "device_tracker": 0,  # read-only
}


def test_parallel_updates_matches_the_recorded_decision() -> None:
    """Section 22: every platform declares `PARALLEL_UPDATES`, deliberately.

    The rule is that the constant is set **on purpose**, which is not something
    a reader of the source can verify — `0` from a considered decision and `0`
    from a copy-paste look identical. Pinning the values here is what makes the
    decision reviewable: changing one means changing this table, and changing
    this table means reading the comment above it.
    """
    import importlib

    import custom_components.huawei_router_5g as component

    for platform, expected in EXPECTED_PARALLEL_UPDATES.items():
        module = importlib.import_module(f"{component.__name__}.{platform}")
        actual = getattr(module, "PARALLEL_UPDATES", None)
        assert actual == expected, (
            f"{platform}.PARALLEL_UPDATES is {actual}, expected {expected} — "
            "if this is intended, update EXPECTED_PARALLEL_UPDATES and its "
            "reasoning rather than only the module"
        )


def test_every_entity_platform_is_covered_by_the_decision() -> None:
    """A new platform must not slip in without a `PARALLEL_UPDATES` decision.

    Checking only the platforms already listed would let platform number eight
    ship with whatever it happened to be given.
    """
    import importlib
    import pkgutil

    from homeassistant.const import Platform

    import custom_components.huawei_router_5g as component

    known = {p.value for p in Platform}
    platforms = {
        m.name for m in pkgutil.iter_modules(component.__path__) if m.name in known
    }

    assert platforms == set(EXPECTED_PARALLEL_UPDATES), (
        "platform modules and the recorded decision disagree: "
        f"{platforms ^ set(EXPECTED_PARALLEL_UPDATES)}"
    )
    for platform in platforms:
        module = importlib.import_module(f"{component.__name__}.{platform}")
        assert hasattr(module, "PARALLEL_UPDATES"), (
            f"{platform} does not declare PARALLEL_UPDATES at all"
        )


# ---------------------------------------------------------------------------
# Section 2.1 — guard bands, and a document that cannot drift again
# ---------------------------------------------------------------------------

# Sensors that carry a unit or a state class but deliberately ship without
# bounds. Empty: there are none today. An entry here is a reviewable act.
#
# The rule is narrower than "every numeric sensor needs bounds" on purpose. A
# first-draft version of this sweep on a sibling project demanded an upper
# bound on every numeric sensor and flagged forty — counts, byte totals,
# uptimes — where the sensors were right and the rule was wrong. An invented
# ceiling on an unbounded quantity suppresses real data.
UNGUARDED_ALLOWLIST: frozenset[str] = frozenset()


def test_every_numeric_sensor_has_a_guard_band() -> None:
    """A sensor Home Assistant treats as a measurement must declare bounds.

    "Treated as a measurement" means it carries a unit or a state class. Those
    are the values that reach long-term statistics, so an implausible reading
    is permanent once recorded.

    **If this fails, the new sensor needs a band, not an allow-list entry.**
    Add one to `UNGUARDED_ALLOWLIST` only where a bound genuinely cannot be
    stated — and note that a *minimum alone* is a band. Most counters have a
    floor of zero and no meaningful ceiling.
    """
    offenders = [
        d.key
        for d in SENSOR_TYPES
        if (d.native_unit_of_measurement is not None or d.state_class is not None)
        and d.min_limit is None
        and d.max_limit is None
        and d.key not in UNGUARDED_ALLOWLIST
    ]

    assert not offenders, (
        "sensors carrying a unit or state class with no guard band:\n"
        + "\n".join(sorted(offenders))
    )


def test_unguarded_allowlist_has_no_dead_entries() -> None:
    """An exemption must not outlive the sensor it exempts."""
    keys = {d.key for d in SENSOR_TYPES}
    stale = sorted(UNGUARDED_ALLOWLIST - keys)
    assert not stale, (
        "UNGUARDED_ALLOWLIST names sensors that no longer exist: " + ", ".join(stale)
    )


def _shipped_root():
    """Return the project root of the **shipped** tree, not a working copy.

    `mutmut` runs the suite from a `mutants/` directory holding a rewritten
    copy of `custom_components/`, `tests/` and `also_copy` — and **nothing
    else**. Two static checks in this file are about the shipped tree rather
    than about behavior, and both broke the mutation run before a single
    mutant was tested:

    - the document reconciliations, because `docs/` is simply absent there;
    - the suppression sweep, because every mutated copy of a function carries
      its `# type: ignore` comment again, turning two reviewed suppressions
      into several hundred unreviewed ones.

    Neither was a fault in the tests or in the code. Resolving from the first
    ancestor that actually carries a `docs/` directory steps out of the mutant
    tree and reads what ships. It never falls back to a copy and never skips:
    a genuinely missing tree still raises.
    """
    import pathlib

    import custom_components.huawei_router_5g as component

    start = pathlib.Path(component.__path__[0]).parent.parent
    for base in (start, *start.parents):
        if (base / "docs").is_dir():
            return base
    raise FileNotFoundError(f"no docs/ directory found above {start}")


def _shipped_doc(name: str):
    """Locate a document under `docs/`, from the source tree or a mutant copy.

    `mutmut` copies only `source_paths`, `tests/` and `also_copy` into
    `mutants/`, so `docs/` is **absent** in the mutant tree and a naive
    `component/../../docs` resolves to a path that does not exist. That failed
    the baseline collection and stopped the whole mutation run before a single
    mutant was tested — the tests were fine, the tree was not.

    Walking up to the first ancestor that actually has the document keeps both
    trees working while still reading the **real, shipped** file. It never
    falls back to a copy and never skips: a genuinely missing document still
    raises, which is the behavior these checks depend on.
    """

    return _shipped_root() / "docs" / name


def _documented_bands() -> dict[str, tuple[float | None, float | None]]:
    """Parse the band table out of `docs/value_min_max.md`.

    Reads the shipped document rather than a copy in this file — a second copy
    would agree with itself forever while the real document rotted.
    """
    import re

    path = _shipped_doc("value_min_max.md")
    row = re.compile(
        r"^\|[^|]+\|\s*`([^`]+)`\s*\|\s*(—|`[^`]+`)\s*\|\s*(—|`[^`]+`)\s*\|"
    )

    bands: dict[str, tuple[float | None, float | None]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = row.match(line)
        if not match:
            continue
        key, lo, hi = match.groups()
        bands[key] = (
            None if lo == "—" else float(lo.strip("`")),
            None if hi == "—" else float(hi.strip("`")),
        )
    return bands


def test_value_min_max_doc_matches_the_code() -> None:
    """`docs/value_min_max.md` and `sensor.py` must agree, in both directions.

    This is the check that was structurally impossible before: a guard band is
    never published as a state or an attribute, so **no live query can observe
    one**. Only a static comparison can, and until this test existed the
    document had never been reconciled since it was written.

    What it had drifted into: two documented bands (`transmit_power`,
    `5g_transmit_power`) that **did not exist in the code**, and roughly twenty
    implemented bands that were undocumented.
    """
    documented = _documented_bands()
    actual = {
        d.key: (d.min_limit, d.max_limit)
        for d in SENSOR_TYPES
        if d.min_limit is not None or d.max_limit is not None
    }

    assert documented, "no band table found in docs/value_min_max.md — parser broken"

    undocumented = sorted(set(actual) - set(documented))
    assert not undocumented, (
        "sensors with a guard band that docs/value_min_max.md does not list:\n"
        + "\n".join(undocumented)
    )

    phantom = sorted(set(documented) - set(actual))
    assert not phantom, (
        "docs/value_min_max.md documents bands that do not exist in the code:\n"
        + "\n".join(phantom)
    )

    mismatched = [
        f"{key}: doc {documented[key]} vs code {actual[key]}"
        for key in sorted(actual)
        if documented[key] != actual[key]
    ]
    assert not mismatched, "guard bands disagree with the document:\n" + "\n".join(
        mismatched
    )


# ---------------------------------------------------------------------------
# Section 19 — the Integration Health attribute contract is published
# ---------------------------------------------------------------------------

# Normative spellings. Users write templates against these, so a project that
# spells one differently is not a style variation — every automation example,
# dashboard card and support answer written for a sibling project is silently
# wrong against it. `checks_failed`, `degraded` and `last_good_scan` are prior
# spellings found in the field and are NOT valid.
SECTION_19_ATTRIBUTES = frozenset(
    {"severity", "issues", "degraded_capabilities", "drift", "last_good_update"}
)


def test_integration_health_publishes_the_normative_attribute_names() -> None:
    """Section 19's attribute names are a published contract, not an internal one.

    Asserted against the entity's own output rather than against the
    coordinator's snapshot dict, because the entity is what users read — a
    rename in the property layer would not be caught otherwise.
    """
    from unittest.mock import MagicMock

    from custom_components.huawei_router_5g.binary_sensor import (
        INTEGRATION_HEALTH_DESCRIPTION,
        HuaweiIntegrationHealthSensor,
    )

    coordinator = MagicMock()
    coordinator.health_snapshot = {
        "severity": None,
        "issues": [],
        "degraded_capabilities": [],
        "drift": [],
        "last_good_update": None,
    }
    sensor = HuaweiIntegrationHealthSensor(
        coordinator, MagicMock(), INTEGRATION_HEALTH_DESCRIPTION
    )

    assert set(sensor.extra_state_attributes) == SECTION_19_ATTRIBUTES | {"about"}


def test_integration_health_attributes_are_all_unrecorded() -> None:
    """None of the health detail is a time series.

    A list of *current* issues has no meaning as history, and recording it
    writes a row per poll for the life of the integration.
    """
    from custom_components.huawei_router_5g.binary_sensor import (
        HuaweiIntegrationHealthSensor,
    )

    assert HuaweiIntegrationHealthSensor._unrecorded_attributes >= SECTION_19_ATTRIBUTES


# ---------------------------------------------------------------------------
# Suppressed static-analysis directives — every one is a reviewed decision
# ---------------------------------------------------------------------------
#
# `masked_errors_check` Class D. An audit on 2026-08-14 found five suppressions
# here, of which **three were wrong and two were hiding live defects**:
# `Connection.logout` and `Monitoring.clear_traffic` did not exist in the
# pinned library, so Logout and Clear Traffic Statistics had never worked, and
# a third carried a justification that was factually false.
#
# A prompt run is a point-in-time audit. This is the mechanism that keeps it
# true afterwards: the set cannot grow without someone editing the table below
# and writing a reason.
#
# **Why ruff and mypy do not already cover this.** `RUF100` and mypy's
# `warn_unused_ignores` report a suppression that is *unnecessary* — one where
# no error would have fired. They are silent on the dangerous case: a
# suppression that IS doing work, because the error is real. Both were clean
# while two calls to non-existent methods sat behind `type: ignore`.
#
# Keyed on (file, code) rather than line number, so ordinary edits do not
# churn it.
ALLOWED_SUPPRESSIONS: dict[tuple[str, str], str] = {
    ("api.py", "noqa: SLF001"): (
        "Reaches wlan._session.post_set directly for wlan/multi-basic-settings. "
        "A public set_multi_basic_settings() exists, but it posts only "
        "{'Ssids': ..., 'WifiRestart': 1} and drops every other top-level key. "
        "Probed against a live B535 on 2026-08-14: the GET returns Ssids, "
        "DbhoEnable and modify_guest_ssid, so the public setter would silently "
        "discard band-steering and guest-SSID state on each toggle. "
        "Round-tripping the full GET response is the correct behavior here. "
        "Second use, added 2026-08-15: reconnect posts dialup/dial Action 0. "
        "net/reconnect is refused by this hardware with -1: Unknown despite "
        "the library exposing it, and DialUp.dial() hardcodes Action 1, so "
        "there is no public wrapper for the disconnect half."
    ),
    ("device_tracker.py", "type: ignore[attr-defined]"): (
        "ScannerEntity is re-exported from homeassistant.components.device_tracker "
        "but is absent from its __all__, so mypy reports an implicit re-export. "
        "The component root is the conventional import path for HA platforms."
    ),
    ("device_tracker.py", "type: ignore[misc]"): (
        "ScannerEntity.device_info is decorated @final and returns None. This "
        "integration overrides it deliberately so every tracked client attaches "
        "to the Clients sub-device — and, more importantly, because "
        "entity_registry_enabled_default is True only when device_info is set: "
        "without it every client tracker would be disabled by default unless "
        "its MAC were already known to another integration. @final is a "
        "typing-only constraint and there is no deprecation or removal date. "
        "Recorded in docs/ha_compatibility.md."
    ),
    ("hardware_check.py", "ruff: noqa: T201"): (
        "The console report is this script's entire output. There is no logger "
        "to route it through, and a caller reading the transcript is the point. "
        "File-level rather than per-line because every print in the file is the "
        "same deliberate choice."
    ),
    ("hardware_check.py", "noqa: BLE001"): (
        "Each of these wraps one hardware interaction whose failure IS the "
        "result being reported. A narrower except would let an unanticipated "
        "library error abort the run and discard the checks already recorded, "
        "which is the opposite of what a diagnostic script should do. The "
        "exception type is always printed, never swallowed silently."
    ),
    ("hardware_check.py", "noqa: SLF001"): (
        "Reads api._client to confirm logout actually released it. There is no "
        "public accessor, and adding one would put shipped API surface into the "
        "integration for the sake of a script HACS never ships. Read-only: the "
        "script observes the state, it never assigns it."
    ),
}


def _real_comments() -> list[tuple[str, int, str]]:
    """Return every genuine comment in the component and tests.

    Uses `tokenize` rather than a regex over raw text: several docstrings in
    this project quote directives such as `# type: ignore[attr-defined]` while
    explaining why a past one was wrong, and a text search cannot tell those
    apart from a live suppression.
    """
    import tokenize

    # `scripts/` is swept too. It is not shipped, but it is the one place that
    # talks to real hardware, so a suppression hiding a wrong belief about the
    # library does more damage there than anywhere else — that is exactly what
    # `type: ignore[attr-defined]` did to `clear_traffic` and `logout`.
    #
    # Resolved from the shipped tree rather than from `__file__` or the
    # imported package, so a `mutants/` copy is never swept — see
    # `_shipped_root`.
    root = _shipped_root()
    roots = [
        root / "custom_components" / "huawei_router_5g",
        root / "tests",
        root / "scripts",
    ]

    found: list[tuple[str, int, str]] = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            with path.open("rb") as handle:
                found.extend(
                    (path.name, token.start[0], token.string)
                    for token in tokenize.tokenize(handle.readline)
                    if token.type == tokenize.COMMENT
                )
    return found


def _live_suppressions() -> dict[tuple[str, str], list[int]]:
    """Map (file, directive) to the lines carrying it."""
    import re

    # The optional `ruff: ` prefix is the **file-level** form, and it must be
    # caught: that directive at the top of a module suppresses its rule for
    # every line in the file, which is broader than any per-line directive
    # here. It was invisible to this sweep until the dead-entry check below
    # flagged an allow-list entry that matched nothing — the guard-the-guard
    # earning its place.
    #
    # The literal form is deliberately not written out in this comment: ruff
    # scans comments for it and would read the example as a real directive.
    #
    # The prefix is kept in the captured code rather than normalized away, so
    # a file-level suppression can never be reviewed as if it were one line.
    pattern = re.compile(
        r"#\s*((?:ruff:\s*)?(?:type:\s*ignore(?:\[[^\]]*\])?"
        r"|noqa(?::\s*[A-Z0-9, ]+)?|pragma:\s*no cover))"
    )

    live: dict[tuple[str, str], list[int]] = {}
    for filename, line, comment in _real_comments():
        for raw in pattern.findall(comment):
            code = " ".join(raw.split())
            live.setdefault((filename, code), []).append(line)
    return live


def test_every_suppression_is_on_the_reviewed_allow_list() -> None:
    """No `type: ignore`, `noqa` or `pragma: no cover` without a written reason.

    **If this fails, the new suppression needs a reason, not an entry.** Ask
    what the tool would have said and whether that thing is actually true —
    an `attr-defined` ignore on a library call is a *claim about that library*,
    and this project has twice made that claim falsely.
    """
    unlisted = sorted(
        f"{filename}:{','.join(str(n) for n in lines)}  {code}"
        for (filename, code), lines in _live_suppressions().items()
        if (filename, code) not in ALLOWED_SUPPRESSIONS
    )

    assert not unlisted, (
        "suppressions with no reviewed justification:\n"
        + "\n".join(unlisted)
        + "\n\nAdd to ALLOWED_SUPPRESSIONS with a reason, or fix the underlying "
        "problem. Removing the suppression alone is not a fix."
    )


def test_allowed_suppressions_has_no_dead_entries() -> None:
    """An allow-list entry must not outlive the suppression it covers.

    A dead entry silently pre-approves the next occurrence of the same
    directive in the same file, which is how a reviewed exception becomes an
    unreviewed habit.
    """
    live = set(_live_suppressions())
    stale = sorted(f"{f}  {c}" for (f, c) in ALLOWED_SUPPRESSIONS if (f, c) not in live)

    assert not stale, (
        "ALLOWED_SUPPRESSIONS entries that no longer match anything:\n"
        + "\n".join(stale)
    )


def test_every_allowed_suppression_states_a_reason() -> None:
    """The reason is the entire value of the allow-list.

    An entry with an empty or token justification is indistinguishable from
    one added to make a check pass, which is the thing being guarded against.
    """
    thin = sorted(
        f"{f}  {c}"
        for (f, c), reason in ALLOWED_SUPPRESSIONS.items()
        if len(reason.strip()) < 40
    )
    assert not thin, "allow-list entries with no real justification:\n" + "\n".join(
        thin
    )


# ---------------------------------------------------------------------------
# Long-term statistics exclusions (status_plan §T-4f)
# ---------------------------------------------------------------------------
#
# **The mechanism is `state_class`, not `device_class`.** A sensor with no
# `state_class` is never recorded into long-term statistics whatever its device
# class, and setting `device_class=None` on its own does not prevent it. So
# every assertion here is about the absence of `state_class`.
#
# This stops long-term statistics only. Short-term recorder history cannot be
# suppressed from an integration at all — that is a `recorder:` exclude in the
# user's own configuration, and their decision rather than ours.
#
# Written as a sweep over the descriptions rather than a comment per entity,
# because a comment cannot fail. This is the §6 lesson: a correct check over
# descriptions that declare nothing is a no-op and is indistinguishable in
# source from one doing real work.

# Identifiers: digits that are not quantities. These need FOUR declarations
# absent, not one — a unit or a device class makes Home Assistant treat the
# state as numeric, which is where `01` becomes `1` and a 15-digit IMEI becomes
# `8.60123456789012e+14`.
#
# `secondary_cell_pci` is the one to watch: it reads `361`, a plain integer that
# passes unnoticed through any check looking at the value rather than at the
# declaration.
LTS_EXCLUDED_IDENTIFIERS: frozenset[str] = frozenset(
    {
        "imei",
        "imsi",
        "iccid",
        "sim_number",
        "serial_number",
        "mcc_mnc",
        "secondary_cell_pci",
    }
)

# Numeric, but not measurements. Settings change only when the owner edits the
# router's data plan, so a statistics series is a flat line with occasional
# steps — and `mean`/`min`/`max` over an allowance mean nothing. The projection
# is an estimate whose underlying usage is already in LTS via the month total.
LTS_EXCLUDED_NUMERICS: frozenset[str] = frozenset(
    {
        "data_allowance",
        "billing_cycle_day",
        "alert_threshold",
        "projected_usage",
        # Disabled by default, but the exclusion must hold IF a user enables
        # them — which is the whole reason this is a test and not a comment.
        "month_connected_time",
        "day_connected_time",
    }
)


def test_no_lts_excluded_sensor_declares_a_state_class() -> None:
    """`state_class` is the only thing that puts a sensor into statistics."""
    excluded = LTS_EXCLUDED_IDENTIFIERS | LTS_EXCLUDED_NUMERICS
    offenders = sorted(
        f"{d.key} -> {d.state_class}"
        for d in SENSOR_TYPES
        if d.key in excluded and d.state_class is not None
    )
    assert not offenders, (
        "sensors that must stay out of long-term statistics but declare a "
        "state_class:\n" + "\n".join(offenders)
    )


def test_identifier_sensors_are_declared_as_text() -> None:
    """There is no explicit text flag — it is the absence of four declarations.

    Set any one and Home Assistant starts treating the state as a number.
    """
    numeric_declarations = (
        "state_class",
        "device_class",
        "native_unit_of_measurement",
        "suggested_display_precision",
    )
    offenders = [
        f"{d.key}.{attr} = {getattr(d, attr)!r}"
        for d in SENSOR_TYPES
        if d.key in LTS_EXCLUDED_IDENTIFIERS
        for attr in numeric_declarations
        if getattr(d, attr, None) is not None
    ]
    assert not offenders, (
        "identifier sensors carrying a numeric declaration:\n" + "\n".join(offenders)
    )


def test_the_lts_exclusion_lists_have_no_dead_entries() -> None:
    """An exemption must not outlive the sensor it covers.

    A stale entry is worse than a missing one: it reads as coverage.
    """
    keys = {d.key for d in SENSOR_TYPES}
    stale = sorted((LTS_EXCLUDED_IDENTIFIERS | LTS_EXCLUDED_NUMERICS) - keys)
    assert not stale, f"listed for LTS exclusion but no longer a sensor: {stale}"


# ---------------------------------------------------------------------------
# Section 14 — every entity carries an `about` note, and it is never recorded
# ---------------------------------------------------------------------------

# The platforms whose entities are description-driven. `device_tracker` is
# deliberately absent: it creates one entity per discovered client and has no
# description at all, so its note is a class-level `_attr_about` and is checked
# separately below.
DESCRIPTION_PLATFORMS = (
    "sensor",
    "binary_sensor",
    "button",
    "switch",
    "select",
    "number",
)

# The shortest a note may be. Not an arbitrary number: it is long enough that
# "Signal strength." cannot pass as a note for LTE RSRP. The value of the
# mechanism is entirely in the entities whose meaning is *not* obvious from
# the name, and a one-word restatement of the name is how this set decays
# while still reporting full coverage.
MINIMUM_ABOUT_LENGTH = 60


def _descriptions_by_platform() -> dict[str, dict[str, object]]:
    """Collect every entity description in the component, keyed by platform.

    Read from **module source** by inspection rather than from a list here.
    Descriptions live in a mix of one large tuple and module-level singletons,
    so both shapes are collected; a hand-maintained list is the failure mode
    this file is written against.
    """
    import importlib
    import inspect
    import pkgutil

    from homeassistant.helpers.entity import EntityDescription

    import custom_components.huawei_router_5g as component

    found: dict[str, dict[str, object]] = {}
    for mod_info in pkgutil.iter_modules(component.__path__):
        platform = mod_info.name
        if platform not in DESCRIPTION_PLATFORMS:
            continue
        module = importlib.import_module(f"{component.__name__}.{platform}")
        seen: dict[str, object] = {}
        for _, obj in inspect.getmembers(module):
            if isinstance(obj, EntityDescription):
                seen[obj.key] = obj
            elif isinstance(obj, tuple):
                for item in obj:
                    if isinstance(item, EntityDescription):
                        seen[item.key] = item
        found[platform] = seen
    return found


def test_every_entity_description_carries_an_about_note() -> None:
    """Section 14: a new entity may not ship without a note.

    This is the point of the exercise. `x_proj_checks_20260802.md` section 1.3
    asked for two things — `_unrecorded_attributes` **and** `about` notes — and
    only the first was delivered, which left the row reading as closed. Without
    a sweep the set decays exactly that way: the notes written today stay
    correct and every entity added after them has none.

    **Satisfy this by writing a note, never by amending the sweep.**
    """
    missing: list[str] = []
    thin: list[str] = []
    checked = 0
    for platform, descriptions in _descriptions_by_platform().items():
        for key, desc in descriptions.items():
            checked += 1
            note = getattr(desc, "about", None)
            if not note:
                missing.append(f"{platform}.{key}")
            elif len(note) < MINIMUM_ABOUT_LENGTH:
                thin.append(f"{platform}.{key} ({len(note)} chars)")

    assert not missing, (
        "entity descriptions with no `about` note — every one of these ships "
        "an entity a user cannot interpret from its name alone:\n"
        + "\n".join(sorted(missing))
    )
    assert not thin, (
        f"`about` notes shorter than {MINIMUM_ABOUT_LENGTH} characters, which "
        "is a restatement of the entity name rather than a note:\n"
        + "\n".join(sorted(thin))
    )
    # Guard the guard: a discovery that finds nothing passes trivially.
    assert checked >= 150, (
        f"sweep only inspected {checked} entity descriptions — discovery is stale"
    )


def test_the_device_tracker_carries_a_class_level_note() -> None:
    """The one platform with no entity description still needs a note.

    A sweep over descriptions cannot see this entity, so without this it would
    be the one entity in the component with no note and nothing would fail.
    """
    from custom_components.huawei_router_5g.device_tracker import (
        HuaweiRouterDeviceTracker,
    )

    note = HuaweiRouterDeviceTracker._attr_about
    assert note is not None
    assert len(note) >= MINIMUM_ABOUT_LENGTH


def test_every_entity_publishing_attributes_keeps_the_about_note_unrecorded() -> None:
    """Section 14: `about` must be excluded from the recorder, everywhere.

    Home Assistant resolves `_unrecorded_attributes` by ordinary attribute
    lookup and does **not** union it across base classes, so a subclass that
    declares its own set silently discards the mixin's `{"about"}` — and the
    note, identical on every state change, starts being written to history on
    that entity alone. Nothing about that is visible in a diff of the subclass.
    """
    offenders = [
        cls.__name__
        for cls in _entity_classes_declaring_attributes()
        if "about" not in getattr(cls, "_unrecorded_attributes", frozenset())
    ]
    assert not offenders, (
        "entity classes whose `_unrecorded_attributes` shadows the mixin's and "
        "drops `about`, so the note is written to the recorder:\n"
        + "\n".join(sorted(offenders))
    )


def test_an_entity_with_its_own_attributes_still_emits_the_note() -> None:
    """Mechanism, not coverage — and the two are different here.

    The declaration test above passes while an entity's own
    `extra_state_attributes` returns a bare dict that never went through
    `_with_about`: the key is *declared* unrecorded and simply never emitted.
    This asserts the note actually reaches the attribute dict on an entity
    that overrides the property, which is the case that breaks.
    """
    from unittest.mock import MagicMock

    from custom_components.huawei_router_5g.switch import (
        GUEST_WIFI_DESCRIPTION,
        HuaweiGuestWifiSwitch,
    )

    coordinator = MagicMock()
    coordinator.data = {}
    switch = HuaweiGuestWifiSwitch(coordinator, MagicMock(), GUEST_WIFI_DESCRIPTION)

    assert switch.extra_state_attributes["about"] == GUEST_WIFI_DESCRIPTION.about


def _documented_about_notes() -> dict[str, str]:
    """Read every key-to-note pair out of `docs/about_attribute_list.md`.

    Reads the shipped document rather than a copy in this file — a second copy
    would agree with itself forever while the real document rotted.
    """
    import re

    path = _shipped_doc("about_attribute_list.md")
    row = re.compile(r"^\|[^|]+\|[^|]+\|\s*`([^`]+)`\s*\|(.*)\|\s*$")

    notes: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = row.match(line)
        if match:
            notes[match.group(1)] = match.group(2).strip()
    return notes


def test_about_attribute_list_doc_matches_the_code() -> None:
    """`docs/about_attribute_list.md` and the descriptions must agree, both ways.

    `dev_std_review` treats this file as a **descriptive document**, which
    means an entry for an entity that does not exist fails as readily as a
    missing one. The text is compared verbatim rather than only the key set: a
    note reworded in the source while the document keeps the old wording is
    the same defect as an absent one, and it is the more likely of the two.
    """
    from custom_components.huawei_router_5g.device_tracker import (
        HuaweiRouterDeviceTracker,
    )

    documented = _documented_about_notes()
    actual = {
        key: getattr(desc, "about", None) or ""
        for descriptions in _descriptions_by_platform().values()
        for key, desc in descriptions.items()
    }
    actual["_attr_about"] = HuaweiRouterDeviceTracker._attr_about or ""

    assert documented, (
        "no note table found in docs/about_attribute_list.md — parser broken"
    )

    undocumented = sorted(set(actual) - set(documented))
    assert not undocumented, "entities the document does not list:\n" + "\n".join(
        undocumented
    )

    phantom = sorted(set(documented) - set(actual))
    assert not phantom, (
        "docs/about_attribute_list.md lists entities that do not exist:\n"
        + "\n".join(phantom)
    )

    mismatched = [key for key in sorted(actual) if documented[key] != actual[key]]
    assert not mismatched, (
        "note text differs between the code and the document:\n" + "\n".join(mismatched)
    )


# ---------------------------------------------------------------------------
# Section 12 — every translation_key used in code resolves in both files
# ---------------------------------------------------------------------------


def _component_root():
    """Return the shipped component directory.

    Resolved from the imported package rather than from a literal path, for
    the same reason `_shipped_root` walks upward: under `mutmut` the tests run
    from a rewritten copy, and a hardcoded `custom_components/...` string
    reads whichever tree the process happens to be sitting in.
    """
    import pathlib

    import custom_components.huawei_router_5g as component

    return pathlib.Path(component.__path__[0])


def _translation_file(name: str) -> dict:
    import json

    return json.loads((_component_root() / name).read_text(encoding="utf-8"))


def test_translation_keys_resolve_in_both_files() -> None:
    """Every `translation_key` in source must resolve in both translation files.

    **Compared against the code, not file-to-file.** A count that matches
    between `strings.json` and `en.json` says nothing: both can carry the same
    stale entry, and both can be missing the same live entity. Only the code
    knows which keys are actually reachable.

    This is Section 12's check (a), and it did not exist until now. The only
    thing that had ever compared these was `iqs_next_steps` Check B — an
    analysis pass run by hand — and when it ran on 2026-08-14 it found two
    dead entity strings that had been orphaned since 2026-05-02. A test would
    have caught them the moment they were orphaned. That is the whole argument
    for this being a test rather than a review step.

    `en.json` is checked separately rather than assumed to mirror
    `strings.json`: HA ships `strings.json` to translators and serves
    `translations/en.json` to the user, so a key present in one and absent
    from the other shows the raw key in the UI for English users while every
    static check on the other file passes.
    """
    import re

    source = "".join(
        p.read_text(encoding="utf-8") for p in sorted(_component_root().glob("*.py"))
    )
    keys = set(re.findall(r'translation_key="([^"]+)"', source))
    assert keys, "no translation_key found in source — the pattern has drifted"

    for name in ("strings.json", "translations/en.json"):
        data = _translation_file(name)
        resolved = {
            key for platform in data.get("entity", {}).values() for key in platform
        }
        resolved |= set(data.get("issues", {}))
        resolved |= set(data.get("exceptions", {}))
        resolved |= set(data.get("services", {}))
        missing = sorted(keys - resolved)
        assert not missing, f"{name} does not resolve: {missing}"


def test_no_translation_entry_is_dead() -> None:
    """The reverse direction: no entity string without a key that produces it.

    Two dead entity strings — `sensor.hw_version` and `sensor.imei` — sat in
    `strings.json` for three months after the sensors were deleted. They were
    invisible to every count-based check, because a file with more entries
    than the code has keys reads as healthy right up until the sets are
    actually diffed.

    Scoped to `entity`, which is the section that drifts. `services`,
    `issues`, `exceptions` and `config` carry entries that are legitimately
    not produced by a `translation_key=` literal.
    """
    import re

    source = "".join(
        p.read_text(encoding="utf-8") for p in sorted(_component_root().glob("*.py"))
    )
    keys = set(re.findall(r'translation_key="([^"]+)"', source))

    for name in ("strings.json", "translations/en.json"):
        entity = _translation_file(name).get("entity", {})
        declared = {key for platform in entity.values() for key in platform}
        dead = sorted(declared - keys)
        assert not dead, f"{name} defines entity strings nothing produces: {dead}"
