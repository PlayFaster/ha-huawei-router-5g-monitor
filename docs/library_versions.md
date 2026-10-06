# Library Versions: `huawei-lte-api` 1.11.0 And 2.0.1

**Written:** 2026-10-05 · **Applies to:** 1.2.3-dev15 onward · **Status:** Reference

This integration runs on either of two versions of the `huawei-lte-api` library, 1.11.0 or 2.0.1. As of 2026-10-05, Home Assistant core `huawei_lte` integration pins `huawei-lte-api` to 1.11.0, and both integrations share one Python environment. This document records what each version does, how the manifest range, the startup guard and the version gate fit together, what was measured, and what to do when core or the library moves. It exists so that a change in either does not become a research task.

---

## Background: why the exact pin became a range

From 1.2.0-dev12 (2026-08-15) until 1.2.3-dev14 the integration pinned `huawei-lte-api==2.0.1`. Home Assistant core ships its own `huawei_lte` integration, which pins `huawei-lte-api==1.11.0`, and every integration runs in the same Python environment. Two problems followed from the two exact pins.

1. **Hassfest began to reject the pin.** Core pull request 181913, merged on 2026-09-14, added a hassfest check that the requirements of a custom integration do not conflict with the versions Home Assistant itself depends on. An exact pin of 2.0.1 cannot hold beside core's exact pin of 1.11.0, and the validation failed with `Requirement huawei-lte-api==2.0.1 is incompatible with huawei-lte-api==1.11.0, which Home Assistant depends on.` The pin had passed hassfest before because the check did not exist. The failure appeared in the GitHub validation and was reproduced by the local hassfest task.
2. **The same conflict was already a runtime problem on systems with both integrations installed.** Home Assistant installs an integration's requirement when it sets the integration up. With two exact pins that cannot both hold, the library on disk changes from one version to the other during start-up, and the version in use is the one on disk when the process started. On the development instance, with both integrations configured, the library alternated between 1.11.0 and 2.0.1 across restarts, and one start failed core's import with `No module named 'huawei_lte_api.api.Led'` while pip was replacing files (section 4.1). That is a measurement on the development instance. The same alternation is expected on any system that has had both integrations installed since the move to library 2.0.1, whether or not its owner noticed, because the two pins conflict there regardless of hassfest.

The change addresses both:

- **The exact pin became the range `>=1.11.0,<2.0.2`.** Hassfest's own guidance for a package that Home Assistant depends on is a minimum version and not an exact pin, and a range that overlaps core's pin at 1.11.0 passes the check. With a range this integration is satisfied by either version and never forces a reinstall, so the alternation stops: when core is configured, core's install decides the version.
- **A version gate keeps the integration healthy on 1.11.0**, where two endpoints do not exist.
- **A startup guard and a restart repair move a system without a core entry to 2.0.1.** The range alone would leave such a system on 1.11.0 indefinitely.

The hassfest failure is what prompted the work. The range, and the behavior in sections 1 to 3, also repairs the behavior of systems running both integrations.

---

## 1. The rule

| Piece | What it is | Where |
| :-- | :-- | :-- |
| Requirement range | `huawei-lte-api>=1.11.0,<2.0.2` | `manifest.json`, `.validate/requirements_custom.txt`, and `.validate/requirements_test.txt` through the sync |
| Startup guard | Installs 2.0.1 when no core `huawei_lte` entry exists and the installed version is older | `custom_components/huawei_router_5g/library_guard.py` |
| Restart repair | One fixable repair that restarts Home Assistant after a verified install | `repairs.py`, issue `library_restart_required` |
| Version gate | Skips two endpoints that 1.11.0 lacks, by the loaded library's version | `api.py`, `LIBRARY_ADDED_ENDPOINTS` in `const.py` |

The range admits 1.11.0 and 2.0.1 in practice because 2.0.0 was tagged and never published to PyPI. A release of 2.0.2 or above is outside the range and needs full testing before the range moves (section 6).

---

## 2. What each version does

| Behaviour | 1.11.0 | 2.0.1 | Basis |
| :-- | :-- | :-- | :-- |
| `Voice.volte` and `Monitoring.onekey_diag` | Absent | Present | Measured: absent from the 1.11.0 package in the dev container, present on 2.0.1 |
| The VoLTE and Router Diagnostics entities | Unknown; their endpoints are recorded `unsupported` | Populated | Measured: diagnostics download on 2026-10-05 |
| Integration Health | `ok`; skipped endpoints are not counted as lost capabilities | `ok` | Measured |
| Supplementary-plane characters in SMS (emoji) | Corrupted in both directions | Encoded as the router expects (CESU-8) | Owner test on 2026-10-04 on 1.11.0: of five emoji sent, three arrived correctly, one as a placeholder block and one as another character; of five sent to the router, only the first was received. The 2.0.0 release notes describe the CESU-8 change. The 2.0.1 behavior is inferred and has not been tested on this router |
| `AuthorizedConnection`, `login_on_demand`, `device.reboot()`, `device.control()`, integer SMS sort types | Present | Removed | 2.0.0 release notes; this integration uses none of them |
| Other differences | None of consequence | None of consequence | Compare of the two tags: formatting, typing and docstrings; no change to CSRF handling, retry or error mapping |
| Mypy strict | No issues | No issues | Measured on 2026-10-05 |

---

## 3. How the pieces interact

The gate reads `huawei_lte_api.__version__`, the version of the modules in memory. The guard reads the version on disk through `importlib.metadata`. They differ for the interval between an install and the next restart, and that interval is why they are separate.

| Core `huawei_lte` entry | Library on disk at start | What happens |
| :-- | :-- | :-- |
| Present, enabled or not | Any | The guard does nothing and clears any restart repair. Core's own install leaves 1.11.0 on disk |
| Absent | 2.0.1 or later | The guard does nothing and clears any restart repair |
| Absent | Older than 2.0.1 | The guard installs `huawei-lte-api>=2.0.1,<2.0.2` as a background task, re-reads the version, and raises the restart repair only when the re-read version is 2.0.1 or later |
| Any | Any, with `skip_pip` set or the package in `skip_pip_packages` | The guard logs one warning and does not install |

A system without a core entry reaches the third row in practice when the core integration was installed earlier and later removed, because the 1.11.0 that core installed remains on disk. A system updated from release 1.2.0 or later already has 2.0.1, because those releases pinned it.

A timeout or a cancellation of the install is an unknown outcome: no repair is raised, and the next start decides from the version on disk. The installer call is shielded, so the guard's timeout of 180 seconds only stops it waiting.

---

## 4. Measured behavior

### 4.1 Core and the integration in one environment (2026-10-04)

| Start | Core entry | Library on disk after start | Endpoints `voice_volte` and `onekey_diag` |
| :-- | :-- | :-- | :-- |
| 21:41 | Added | 1.11.0 | Not read. Core failed to import with `No module named 'huawei_lte_api.api.Led'` |
| 21:43 | Present | 1.11.0, installed 29 s after the process started | `answered`, because the process had imported 2.0.1 before core's install replaced it |
| 22:03 | Present | 2.0.1, installed 10 s after the process started | `unavailable`, on the 1.11.0 already on disk at start |
| 23:00 and 23:02 | Removed | 1.11.0, unchanged | `unavailable` |

With both integrations configured the library on disk changed at each start, and the version in use was the one on disk when the process started. With the core entry removed nothing installed 2.0.1, which is the gap the guard closes.

### 4.2 The guard and the repair (2026-10-05)

| Step | Observation |
| :-- | :-- |
| Restart on 1.11.0 with no core entry | 2.0.1 installed at start; the repair `library_restart_required` was raised (`is_fixable`, warning); the running process stayed on 1.11.0, both endpoints read `unsupported`, health read `ok`, and the log held no errors |
| Repair opened and submitted | The flow showed its confirm form; submitting it restarted Home Assistant |
| After that restart | 2.0.1 loaded; both endpoints `answered`; 26 of 26 endpoints answered; no repair; health `ok`; no log errors |
| Diag Check on 1.11.0 with the version gate | 34 of 34 passed |
| Hassfest with `huawei-lte-api==2.0.1` in the manifest | `Invalid integrations: 1`, requirement conflict with core's pin |
| Hassfest with the range | `Invalid integrations: 0` |

### 4.3 Coexistence with the core entry re-added (2026-10-05)

| Point | Library on disk | `voice_volte` and `onekey_diag` | Repair | Health | Log errors |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Core entry added, no restart | 1.11.0, installed by core at the moment the entry was added | `answered`, the running process still holds 2.0.1 | None | `ok` | 0 from the library |
| Restart 1 with core present | 1.11.0, unchanged | `unsupported` | None | `ok` | 0 |
| Restart 2 with core present | 1.11.0, unchanged | `unsupported` | None | `ok` | 0 |

With a core entry present the guard does nothing and nothing else installs, so the library stays on 1.11.0 across restarts and the alternation of section 4.1 does not occur. The import failure seen on 2026-10-04 did not recur when the entry was added. The record is kept in `shared/ProjNotes/Notes-ha-huawei-router-5g-monitor/local_only/library_coexistence_live_check.md`.

---

## 5. Accepted limits

- **A config flow opened with no entries runs the guard.** An abandoned flow can leave the restart repair until the next restart. The issue is not persistent, and the guard decides again at every start.
- **The first start after a core entry is added can fail core's import once.** pip replaces library files under a running process, as at 21:41 in section 4.1. The next restart clears it.
- **An installation whose core entry is disabled stays on 1.11.0.** Enabling the entry later would otherwise reinstall 1.11.0.
- **2.0.1 on this router is not tested for emoji.** The SMS effect is inferred from the release notes (section 2).

---

## 6. When core or the library moves

### 6.1 Core moves to 2.0.1

1. Read core's `homeassistant/components/huawei_lte/manifest.json` and confirm the pin reads `huawei-lte-api==2.0.1`.
2. The range already admits it. Run the `HA: Hassfest Validation` task; it must report `Invalid integrations: 0`.
3. The guard's skip for a core entry becomes unnecessary because both integrations then want the same version. Leave it in place unless a release removes it deliberately, and record the decision in the changelog.
4. Run the coexistence live check (section 7) with core configured and confirm both endpoints read `answered`.
5. Update section 4 and `docs/ha_compatibility.md`.

### 6.2 Core moves to 2.0.2 or above

1. Hassfest rejects the range as incompatible with core's pin. The range passes today only because it overlaps core's pin at 1.11.0 and at 2.0.1, and `<2.0.2` stops overlapping any later pin.
2. Do not widen the bound without testing. Read the release notes and the tag compare for the new version and run the procedure in section 6.3 against it.
3. Change the upper bound in `manifest.json` and the two requirement files, `LIBRARY_REQUIREMENT` in `const.py`, and the first versions in `LIBRARY_ADDED_ENDPOINTS` where they differ.
4. Run Mypy strict under 1.11.0 where it is still supported and under the new version, the contract test, and the Diag Check against the live router.
5. Update this document and `docs/ha_compatibility.md`.

### 6.3 The library releases 2.0.2 or above

1. Read the release notes and compare the tags (`compare/2.0.1...<new>` on GitHub). List removed methods, changed signatures and encoding changes.
2. Check every library call in `api.py` against the new package with `tests/test_library_contract.py`, with the new version installed.
3. Run Mypy strict, the full test suite, the Diag Check and the hardware check against the live router, and an SMS round trip with an emoji in both directions.
4. Only then move the bound in `manifest.json`, the two requirement files, `LIBRARY_REQUIREMENT` and `LIBRARY_PREFERRED_VERSION`.
5. Run the coexistence live check and update sections 2 and 4.

---

## 7. Development environment

Normal validation runs with the core `huawei_lte` entry absent and 2.0.1 installed, so that the library version does not depend on start order. The coexistence check is the one exception:

1. Reset the dev container to 1.11.0 with `pip install huawei-lte-api==1.11.0` inside it, with no core entry, and restart. The guard must install 2.0.1 and raise the repair.
2. Submit the repair. Home Assistant restarts and loads 2.0.1; both endpoints must read `answered` and the repair must be gone.
3. Add the core `huawei_lte` entry with the router credentials (an owner action), restart twice, and read the library on disk and the two endpoints after each restart. The expected state is 1.11.0 and `unsupported`.
4. Remove the core entry, restore 2.0.1, and restart.

Read the library on disk with `pip list` inside the container, the endpoint outcomes from the diagnostics download, and the repair with the repairs websocket command. The Diag Check on 1.11.0 passes only before the guard installs 2.0.1, so a repeat needs step 1 first.

---

## Version Control

| Version | Date | Change |
| :-- | :-- | :-- |
| 1.2.0 | 2026-10-05 | Section 3 states how a system without a core entry usually reaches the upgrade row |
| 1.1.0 | 2026-10-05 | Added the Background section: the hassfest check that rejected the exact pin, the alternation on systems with both integrations, and the change |
| 1.0.0 | 2026-10-05 | First issue, from the plan `v123_dev15_plan.md` |
