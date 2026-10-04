# Test Guards: Huawei Router 5G Monitor

Rationale for the guard tests listed under _Tests that will stop you_ in [`AGENTS.md`](../AGENTS.md). `AGENTS.md` states what fails and what to do; this file records why each guard exists. When a guard test is added, its row goes in `AGENTS.md` and its rationale here.

---

## Guards Moved From `AGENTS.md` (2026-09-23)

Each entry is the rationale column of the former `AGENTS.md` table, copied verbatim.

### `test_no_sensor_uses_the_total_state_class`

**Guards:** `ALLOWED_TOTAL_STATE_CLASS` (empty)

Four resetting counters shipped as `SensorStateClass.TOTAL` with no `last_reset`, so every daily and billing-month rollover was recorded as a large negative delta and walked long-term statistics backwards. Nothing failed at runtime.

### `test_total_state_class_sweep_is_not_vacuous`

**Guards:** the sweep above

The sweep passes trivially if `SENSOR_TYPES` stops carrying state classes. Pins that it inspected ≥20 sensors and that the four corrected counters are still `TOTAL_INCREASING`.

### `test_allowed_total_state_class_has_no_dead_entries`

**Guards:** the allow-list

An exemption must not outlive its sensor, where it would silently pre-approve a future sensor reusing the key.

### `test_every_entity_publishing_attributes_declares_unrecorded`

**Guards:** Section 14

The component had **zero** `_unrecorded_attributes`, so every attribute of every entity hit the recorder on every state change — including each tracked client's SSID, once per client per poll. Discovers entity classes by inspection, so a new platform cannot slip past it.

### `test_unrecorded_attribute_sweep_is_not_vacuous`

**Guards:** the sweep above

Fails if discovery stops finding classes (e.g. a refactor moving `extra_state_attributes` onto a shared base).

### `test_every_entity_description_carries_an_about_note`

**Guards:** Section 14

The same `x_proj_checks` row asked for `_unrecorded_attributes` **and** `about` notes; only the first was delivered, which left the row reading as closed. Without this sweep the notes written once stay correct and every entity added after them has none. A minimum length is enforced because a restatement of the entity name reports full coverage while carrying no information.

### `test_the_device_tracker_carries_a_class_level_note`

**Guards:** the one platform with no description

A sweep over entity descriptions cannot see it, so it would be the single entity in the component with no note and nothing would fail.

### `test_every_entity_publishing_attributes_keeps_the_about_note_unrecorded`

**Guards:** Section 14

`_unrecorded_attributes` is resolved by ordinary attribute lookup and is **not** unioned across bases, so a subclass declaring its own set silently discards the mixin's `{"about"}` — and starts recording the note on that entity alone. Invisible in a diff of the subclass.

### `test_an_entity_with_its_own_attributes_still_emits_the_note`

**Guards:** the mechanism, not the declaration

The declaration sweep passes while an entity's own `extra_state_attributes` returns a dict that never went through `_with_about`: the key is declared unrecorded and simply never emitted.

### `Sensor: Check Manifest` (`--check`)

**Guards:** `docs/about_attribute_list.md`, `all_sensors.md`, `value_min_max.md`

**Not a pytest test — a `Validate All` task.** Regenerates each document from the code and fails on any difference, which covers a missing entity, a phantom one and a reworded note alike. It replaced `test_about_attribute_list_doc_matches_the_code`, removed 2026-08-23: that test read the shipped document with a regex of its own, so the generator's output format had two parsers and only one owner. Chore `C-013`.

### `test_every_registered_action_has_an_icon`

**Guards:** Section 12

There was no `services` block at all while four actions were registered. Reads the action list from **`services.yaml`**, not from `icons.json` — reading the thing under test to build the expectation is how a bidirectional check goes vacuous.

### `test_no_icon_entry_names_an_action_that_does_not_exist`

**Guards:** the other direction

A dead icon entry renders nothing and breaks nothing, so it accumulates unnoticed.

### A repair issue

**Guards:** `test_every_repair_issue_has_title_and_rendered_text`, `test_the_fixable_repair_is_the_one_with_a_fix_flow`, `test_no_orphan_issue_translations`

Add the key to `REPAIR_NAMES` and give it a `title` in **both** `strings.json` and `translations/en.json`, then **exactly one** of `description` or `fix_flow` — `hassfest` declares them `vol.Exclusive`, because a fixable issue renders its prose in the flow's step. **A fixable repair needs `repairs.py`**: without that platform Home Assistant substitutes `ConfirmRepairFlow`, whose Fix button deletes the card and does nothing else.

### `test_action_icons_use_the_current_nested_form`

**Guards:** format drift

The flat form works, so nothing would ever fail; only the nested object can carry per-`section` icons.

### `test_every_live_entity_belongs_to_a_device`

**Guards:** the cross-project item

An entity without `device_info` registers against the config entry and no device: it is in the entity list, counted in the integration's total, and on none of the six device cards. Home Assistant does not reject it and no other test looks at where an entity lives. Swept over **live** entities — a description cannot carry the fault. Asserts the `device_tracker` platform is present, because a tracker that loses its device is never registered and so vanishes rather than reporting as homeless.

### `test_device_info_is_declared_once`

**Guards:** the code half of the same item

The sweep above catches the omission; this stops it being available. Seven platform bases each declared the property, and every copy was a place the next one could be left out — which is how `ZTEOperatorProvisionedSensor` shipped with none.

### `test_every_entity_description_has_an_icon_or_a_device_class`

**Guards:** Section 12

Found `button.refresh` shipping with neither. Reads keys from **module source** across all seven platforms — two hand-maintained files can agree perfectly and both describe an entity that no longer exists.

### `test_parallel_updates_matches_the_recorded_decision`

**Guards:** Section 22

The rule is that the constant is set _deliberately_, which source cannot show: a considered `0` and a copy-pasted `0` are identical. Changing a value means changing the table and reading its reasoning.

### `test_every_entity_platform_is_covered_by_the_decision`

**Guards:** the table above

Stops platform number eight shipping with whatever value it happened to get.

### `test_every_numeric_sensor_has_a_guard_band`

**Guards:** `UNGUARDED_ALLOWLIST` (empty)

A sensor carrying a unit or a state class reaches long-term statistics, where an implausible reading is permanent. **Note the rule is narrow on purpose** — a wider draft on a sibling flagged 40 sensors that were right.

### `test_value_min_max_doc_matches_the_code`

**Guards:** `docs/value_min_max.md`

The document had **never** been reconciled: it documented two bands that did not exist and omitted about twenty that did. A guard band is never published as a state or attribute, so **no live query can see one** — only this static check can.

### `test_integration_health_publishes_the_normative_attribute_names`

**Guards:** Section 19

`severity` / `issues` / `degraded_capabilities` / `drift` / `last_good_update` are a **published contract**. Users write templates against them, so a rename silently breaks every example written for a sibling project.

### `test_translation_keys_resolve_in_both_files`

**Guards:** Section 12 check (a)

Nothing had ever compared `translation_key=` in source against the translation files. The only thing that ever had was an analysis pass run by hand, and when it ran it found two dead entity strings orphaned three months earlier. Compared against the **code**, not file-to-file: both files can carry the same stale entry and both can miss the same live entity.

### `test_no_translation_entry_is_dead`

**Guards:** the other direction

`sensor.hw_version` and `sensor.imei` sat in `strings.json` for three months after the sensors were deleted, invisible to every count-based check — a file with more entries than the code has keys reads as healthy until the sets are diffed.

### `test_no_live_entity_publishes_a_recorded_attribute`

**Guards:** Section 14, **at runtime**

The static sweep above can see a class declares _something_; it cannot see what a description-driven entity actually emits, because the keys come from a function on the description. Proven non-vacuous by adding an attribute inside the projection's `extra_state_attributes`: the static sweep passed, this one failed. Forces disabled-by-default entities on — the identity sensors ship disabled and are the most likely to publish something unreviewed.

### `test_every_live_entity_publishes_its_about_note`

**Guards:** the note reaching runtime

A note that never reaches the state machine satisfies every static check and shows the user nothing.

### `test_every_live_entity_resolves_its_name`

**Guards:** Section 12, **per platform**

A key filed under `sensor` while its entity is built on `binary_sensor` resolves fine to any check that flattens the file, and shows the user a raw key. Proven by filing a live key under the wrong platform: the source-reading check passed, this one failed.

### `test_every_live_entity_has_an_icon_or_derives_one`

**Guards:** Section 12, live

Only an `icons.json` entry or a `device_class` counts — **`_attr_icon` is deliberately not accepted**, because it satisfies the eye while defeating the check and puts the icon somewhere untranslatable.

### `test_every_write_is_classified`

**Guards:** `scripts/write_classification.py`

A write shipping with nobody having asked whether it could be exercised is how Clear Traffic reached users calling a method that does not exist. Every command must sit in exactly one tier with a written reason.

### `test_every_safe_write_is_exercised_by_the_hardware_check`

**Guards:** the tier boundary

A write classified SAFE and never actually run is a claim, not a check.

### `test_no_lts_excluded_sensor_declares_a_state_class`

**Guards:** long-term statistics

LTS is driven by `state_class`, not `device_class`. An identifier that acquires one starts accumulating statistics nobody wants and the recorder never gives that back.

### `test_every_read_back_endpoint_is_a_real_one`

**Guards:** Section 22

A typo in the read-back map surfaces only as a control that silently never confirms — no error, no failure, just a mechanism doing nothing.

### `test_the_live_keys_are_exactly_the_two_read_every_cycle`

**Guards:** Section 9

Adding a key to `LIVE_OPTION_KEYS` makes that setting silently stop working: written to the entry, skipped by the reload, never re-read by anything holding the old value.

### `test_compat.py` (all)

**Guards:** `_compat.py`

Forces **both** branches of each shim by patching the detection flag. The suite runs against one HA version, so the other branch would never execute — and this integration must be correct on ≤2026.7 and post-2027.8 alike.

### `assert_links_to_parent()` / `assert_is_root()`

**Guards:** device-registry link shape

**Never assert `info["via_device"]` directly.** Twelve tests did, and were green only because the installed HA took that branch. These assert the link's presence and exclusivity instead.

---

## Guards Added to the Table (2026-09-23)

Tests that fire on an ordinary change and were not previously listed. Each rationale is the test's docstring.

### `test_unguarded_allowlist_has_no_dead_entries`

An exemption must not outlive the sensor it exempts.

### `test_integration_health_attributes_are_all_unrecorded`

None of the health detail is a time series. A list of _current_ issues has no meaning as history, and recording it writes a row per poll for the life of the integration.

### `test_every_suppression_is_on_the_reviewed_allow_list`

No `type: ignore`, `noqa` or `pragma: no cover` without a written reason. **If this fails, the new suppression needs a reason, not an entry.** Ask what the tool would have said and whether that thing is actually true — an `attr-defined` ignore on a library call is a _claim about that library_, and this project has twice made that claim falsely.

### `test_allowed_suppressions_has_no_dead_entries`

An allow-list entry must not outlive the suppression it covers. A dead entry silently pre-approves the next occurrence of the same directive in the same file, which is how a reviewed exception becomes an unreviewed habit.

### `test_every_allowed_suppression_states_a_reason`

The reason is the entire value of the allow-list. An entry with an empty or token justification is indistinguishable from one added to make a check pass, which is the thing being guarded against.

### `test_identifier_sensors_are_declared_as_text`

There is no explicit text flag — it is the absence of four declarations. Set any one and Home Assistant starts treating the state as a number.

### `test_the_lts_exclusion_lists_have_no_dead_entries`

An exemption must not outlive the sensor it covers. A stale entry is worse than a missing one: it reads as coverage.

### `test_sensors_disabled_by_decision_are_still_disabled`

A recorded default must not be reverted without the register changing.

### `test_the_disabled_by_decision_register_has_no_dead_entries`

A register naming a sensor that no longer exists checks nothing.

### `test_every_disabled_by_decision_entry_carries_a_reason`

A register entry with no reason is indistinguishable from a guess.
