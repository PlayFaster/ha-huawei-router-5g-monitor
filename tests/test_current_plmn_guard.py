"""The operator sensors when `net.current_plmn` is not a mapping.

A B315s-22 with no SIM answers `net.current_plmn` with the string `FAILED`
(measured 2026-10-05), and the three operator value functions called `.get` on
it, raising six listener errors per start. Plan `v124_dev1_plan.md` item I4:
anything that is not a mapping reads as no value.
"""

from __future__ import annotations

import pytest

from custom_components.huawei_router_5g.diagnostics import _entity_resolution
from custom_components.huawei_router_5g.sensor import SENSOR_TYPES

OPERATOR_KEYS = ("operator", "plmn", "operator_search_mode")

# The shape the H165-383 returns, with the operator's values replaced.
PLMN = {"FullName": "Test Carrier", "Numeric": "00101", "State": "0"}


def _value_fn(key: str):
    return next(d for d in SENSOR_TYPES if d.key == key).value_fn


@pytest.mark.parametrize("key", OPERATOR_KEYS)
@pytest.mark.parametrize("answer", ["FAILED", "", 0, ["FAILED"], None])
def test_an_answer_that_is_not_a_mapping_reads_as_no_value(key, answer) -> None:
    """The string `FAILED`, and any other non-mapping, gives None and no exception."""
    assert _value_fn(key)({"current_plmn": answer}) is None


def test_the_download_lists_the_operator_sensors_as_no_value_not_raised() -> None:
    """`entity_resolution` reports a missing value, not a defect in the sensor."""
    sensors = _entity_resolution({"current_plmn": "FAILED"})["sensor"]
    assert set(OPERATOR_KEYS) <= set(sensors["no_value"])
    assert sensors["raised"] == {}


def test_the_mapping_the_router_returns_still_resolves() -> None:
    """The guard changes nothing for a router that answers normally."""
    data = {"current_plmn": PLMN}
    assert _value_fn("operator")(data) == "Test Carrier"
    assert _value_fn("plmn")(data) == "00101"
    assert _value_fn("operator_search_mode")(data) == "Auto"
    assert _value_fn("operator_search_mode")({"current_plmn": {"State": "1"}}) == (
        "Manual"
    )
