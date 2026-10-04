"""Tests that assert on the produced diagnostics file, not on the producer.

**This is the seam `zte_router_5g` was caught by.** In `[3.3.9-dev5]` a field
was recorded by the producer, asserted by five passing unit tests, and dropped
on the way out by a sanitizer that was never extended to name it. Three
downloads taken from hardware carried none of it, and a human reading the files
found the omission two releases later. Branch coverage cannot close that gap.

Every test here therefore calls `async_get_config_entry_diagnostics` and asserts
on its return value, never on the API attribute the capture is stored in. The
tests for the captures themselves are in `test_diagnostic_capture.py`.

**`zte_router_5g`'s field-partition test has no counterpart here, and that is a
property of the code rather than an omission.** That project's sanitizer copies
named fields through `DISCOVERY_METADATA_PUBLISHED` and
`DISCOVERY_METADATA_GATED`, so a field missing from the list disappears
silently and the two sets must be asserted to partition the producer's output.
This project's `diagnostics.py` has no copy-list: the returned document is a
dict literal and `_sanitize` is a deny-by-pattern walker over values, so there
is no allow-list for a field to fall out of. The guarantee is provided instead
by the tests below, which require each published key to be present in the file.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from custom_components.huawei_router_5g.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

SECRET = "sekrit_hunter2"

# A rejected payload carries the same router values an accepted one does, so it
# must be swept by the same walker. These are the values that must not survive.
IDENTIFIERS = [
    "860123456789012",  # IMEI
    "DC:71:96:11:22:33",  # router WAN MAC
    "10.1.2.3",  # WAN IP
]


def _rejected_payload() -> dict:
    """Return a partial payload of the kind a failed poll leaves behind."""
    return {
        "device_information": {
            "DeviceName": "B535s-232",
            "Imei": "860123456789012",
            "MacAddress1": "DC:71:96:11:22:33",
            "WanIPAddress": "10.1.2.3",
        }
    }


@pytest.fixture(name="diagnostics_entry")
def diagnostics_entry_fixture():
    """A config entry whose coordinator has never completed a poll.

    `data` is `None`, which is the state a download is usually requested in and
    the reason these two captures exist.
    """
    entry = MagicMock(spec=ConfigEntry)
    entry.title = "Huawei Router"
    entry.data = {CONF_USERNAME: "admin", CONF_PASSWORD: SECRET}
    entry.options = {}

    coordinator = MagicMock()
    coordinator.data = None
    coordinator.consecutive_failures = 3
    coordinator.last_update_success = False
    coordinator.last_update_success_time = None
    coordinator.update_interval = None
    coordinator.api.last_rejection = None
    coordinator.api.login_metadata = {}
    coordinator.api.endpoint_outcomes = {}
    entry.runtime_data = coordinator
    return entry


async def _dump(entry: ConfigEntry) -> tuple[dict, str]:
    """Return the diagnostics document and its serialized form."""
    result = await async_get_config_entry_diagnostics(
        MagicMock(spec=HomeAssistant), entry
    )
    return result, json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# The captures reach the file
# ---------------------------------------------------------------------------


async def test_both_captures_are_published_beside_data(diagnostics_entry) -> None:
    """The three keys exist in the document, whatever they hold."""
    result, _ = await _dump(diagnostics_entry)

    assert "last_rejection" in result
    assert "login" in result
    assert "endpoints" in result


async def test_the_download_carries_the_endpoint_outcomes(diagnostics_entry) -> None:
    """An endpoint absent from `data` is explained by its outcome here.

    This is what a reader of a stranger's download needs: `security_sip` is
    missing from the payload, and the map says the router refused it with a
    code rather than leaving the absence to be guessed at.
    """
    diagnostics_entry.runtime_data.api.endpoint_outcomes = {
        "device_signal": {"outcome": "answered"},
        "security_sip": {"outcome": "refused", "code": "100002"},
        "start_date": {"outcome": "skipped"},
    }

    result, _ = await _dump(diagnostics_entry)

    assert result["endpoints"]["security_sip"] == {
        "outcome": "refused",
        "code": "100002",
    }
    assert result["endpoints"]["start_date"]["outcome"] == "skipped"


async def test_the_endpoint_map_is_copied_not_referenced(diagnostics_entry) -> None:
    """The download is a snapshot; a later poll must not rewrite it."""
    live = {"device_signal": {"outcome": "answered"}}
    diagnostics_entry.runtime_data.api.endpoint_outcomes = live

    result, _ = await _dump(diagnostics_entry)
    live["device_signal"]["outcome"] = "refused"

    assert result["endpoints"]["device_signal"]["outcome"] == "answered"


async def test_an_untouched_client_publishes_an_empty_capture(
    diagnostics_entry,
) -> None:
    """Nothing rejected and nothing logged in reads as absent, not as missing."""
    result, _ = await _dump(diagnostics_entry)

    assert result["last_rejection"] is None
    assert result["login"] == {}


async def test_the_download_carries_the_rejection(diagnostics_entry) -> None:
    """The verdict, the router's code and the endpoint all reach the file."""
    diagnostics_entry.runtime_data.api.last_rejection = {
        "verdict": "refused",
        "code": "100002",
        "key": "device_signal",
    }

    result, _ = await _dump(diagnostics_entry)

    assert result["last_rejection"]["verdict"] == "refused"
    assert result["last_rejection"]["code"] == "100002"
    assert result["last_rejection"]["key"] == "device_signal"


async def test_the_download_carries_the_login_outcome(diagnostics_entry) -> None:
    """The login record reaches the file with its outcome intact."""
    diagnostics_entry.runtime_data.api.login_metadata = {
        "result": "auth_failed",
        "username_configured": True,
        "error": "LoginErrorPasswordWrongException",
    }

    result, _ = await _dump(diagnostics_entry)

    assert result["login"]["result"] == "auth_failed"
    assert result["login"]["error"] == "LoginErrorPasswordWrongException"


# ---------------------------------------------------------------------------
# The rejected payload is sanitized by the same walker as `data`
# ---------------------------------------------------------------------------


async def test_the_retained_payload_is_sanitized(diagnostics_entry) -> None:
    """A rejected payload is no more revealing than an accepted one."""
    diagnostics_entry.runtime_data.api.last_rejection = {
        "verdict": "expired",
        "code": "125002",
        "key": "device_signal",
        "payload": _rejected_payload(),
    }

    _, serialized = await _dump(diagnostics_entry)

    for identifier in IDENTIFIERS:
        assert identifier not in serialized, f"{identifier} survived sanitization"


async def test_the_payloads_model_name_is_kept(diagnostics_entry) -> None:
    """Sanitizing must not empty the record of everything useful."""
    diagnostics_entry.runtime_data.api.last_rejection = {
        "verdict": "expired",
        "payload": _rejected_payload(),
    }

    _, serialized = await _dump(diagnostics_entry)

    assert "B535s-232" in serialized


# ---------------------------------------------------------------------------
# The negative property, over the whole document
# ---------------------------------------------------------------------------


async def test_no_credential_appears_anywhere_in_the_document(
    diagnostics_entry,
) -> None:
    """Asserted structurally, not key by key.

    A key-by-key assertion only finds the leaks somebody already thought of,
    which is the reasoning `test_diagnostics.py` records for the main payload
    and the reason the login record is included in the same sweep here.
    """
    diagnostics_entry.runtime_data.api.login_metadata = {
        "result": "auth_failed",
        "username_configured": True,
        "error": "LoginErrorPasswordWrongException",
    }

    _, serialized = await _dump(diagnostics_entry)

    assert SECRET not in serialized


async def test_a_capture_that_is_not_a_mapping_is_not_published(
    diagnostics_entry,
) -> None:
    """Diagnostics must survive a coordinator whose api is a stand-in.

    A non-serializable object reaching the file would break the download the
    user is about to attach to an issue, so both captures are type-guarded
    rather than trusted.
    """
    diagnostics_entry.runtime_data.api.last_rejection = MagicMock()
    diagnostics_entry.runtime_data.api.login_metadata = MagicMock()
    diagnostics_entry.runtime_data.api.endpoint_outcomes = MagicMock()

    result, _ = await _dump(diagnostics_entry)

    assert result["last_rejection"] is None
    assert result["login"] == {}
    assert result["endpoints"] == {}


# ---------------------------------------------------------------------------
# A description that throws — a defect in this integration, not in the firmware
# ---------------------------------------------------------------------------


async def test_a_description_that_raises_is_named_with_its_exception(
    diagnostics_entry,
) -> None:
    """A `value_fn` that throws against a payload is recorded, not swallowed.

    This is the one outcome in `entity_resolution` that is a defect on **our**
    side. An entity whose description raises simply shows nothing, so without
    this the failure is invisible in operation and invisible in the download —
    and it is exactly the shape an unfamiliar firmware would provoke, by
    answering a block with a type or a nesting this integration never expected.
    """
    exploding = SensorEntityDescription(key="explodes")
    object.__setattr__(exploding, "value_fn", lambda _payload: 1 / 0)
    diagnostics_entry.runtime_data.coordinator = None
    diagnostics_entry.runtime_data.data = {"device_information": {"a": "1"}}

    with patch("custom_components.huawei_router_5g.sensor.SENSOR_TYPES", (exploding,)):
        result, _ = await _dump(diagnostics_entry)

    sensor = result["entity_resolution"]["sensor"]
    assert sensor["raised"] == {"explodes": "ZeroDivisionError"}
    assert sensor["total"] == 1
    assert sensor["resolved"] == 0


async def test_a_raising_description_does_not_stop_the_others(
    diagnostics_entry,
) -> None:
    """One bad description must not cost the whole resolution map."""
    exploding = SensorEntityDescription(key="explodes")
    object.__setattr__(exploding, "value_fn", lambda _payload: 1 / 0)
    working = SensorEntityDescription(key="works")
    object.__setattr__(working, "value_fn", lambda payload: payload.get("present"))

    diagnostics_entry.runtime_data.data = {"present": "yes"}

    with patch(
        "custom_components.huawei_router_5g.sensor.SENSOR_TYPES",
        (exploding, working),
    ):
        result, _ = await _dump(diagnostics_entry)

    sensor = result["entity_resolution"]["sensor"]
    assert sensor["raised"] == {"explodes": "ZeroDivisionError"}
    assert sensor["resolved"] == 1
    assert sensor["total"] == 2
