"""Capability flag values in the diagnostics download.

Plan `v124_dev1_plan.md` item I8 and decision D18. The probe record keeps the
values of the capability probes, and the download publishes a value after the
sanitizer: a number as it is, text only under a known text key, and any other
text as a marker naming its type. Every other probe stays key names only.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI
from custom_components.huawei_router_5g.const import (
    CAPABILITY_BASIC_INFO_KEYS,
    CAPABILITY_PROBES,
)
from custom_components.huawei_router_5g.diagnostics import (
    _capability_value,
    _publish_probes,
    _Tokenizer,
    async_get_config_entry_diagnostics,
)
from homeassistant.core import HomeAssistant


def _api() -> HuaweiRouter5GAPI:
    return HuaweiRouter5GAPI("http://192.168.8.1", "admin", "password")


def _probes(answers: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple((key, lambda _c, v=value: v) for key, value in answers.items())


async def _sweep(answers: dict[str, Any]) -> dict[str, Any]:
    """Run the real probe sweep over probes that answer `answers`."""
    api = _api()
    with (
        patch.object(api, "_ensure_client", return_value=MagicMock()),
        patch.object(type(api), "DIAGNOSTIC_PROBES", _probes(answers)),
    ):
        return await api.probe_diagnostic_endpoints()


async def _download(probes: dict[str, Any]) -> dict[str, Any]:
    """Build the diagnostics document around a probe sweep result."""
    entry = MagicMock()
    entry.data = {}
    entry.options = {}
    coordinator = MagicMock()
    coordinator.data = {"device_information": {"DeviceName": "H165-383"}}
    coordinator.api.probe_diagnostic_endpoints.return_value = probes
    coordinator.api.last_rejection = None
    coordinator.api.login_metadata = {}
    coordinator.api.premise_result = None
    coordinator.api.sweep_sessions_lost = 0
    coordinator.api.endpoint_outcomes = {}
    coordinator.health_snapshot = {}
    entry.runtime_data = coordinator

    async def probe() -> dict[str, Any]:
        return probes

    coordinator.api.probe_diagnostic_endpoints = probe
    return await async_get_config_entry_diagnostics(
        MagicMock(spec=HomeAssistant), entry
    )


def test_the_probe_list_holds_47_entries_including_the_dial_up_switch() -> None:
    """46 probes before 1.2.4-dev1, plus `dial_up.dialup_feature_switch`."""
    keys = [key for key, _ in _api().DIAGNOSTIC_PROBES]
    assert len(keys) == 47
    assert "dial_up_feature_switch" in keys
    assert set(keys) >= CAPABILITY_PROBES


@pytest.mark.asyncio
async def test_every_allow_listed_key_keeps_its_value() -> None:
    """The sweep keeps the values of every capability probe."""
    answers = {key: {"flag_enabled": "1"} for key in CAPABILITY_PROBES}
    result = await _sweep(answers)
    for key in CAPABILITY_PROBES:
        assert result[key]["values"] == {"flag_enabled": "1"}


@pytest.mark.asyncio
async def test_a_probe_outside_the_list_keeps_key_names_only() -> None:
    """`sms_config` holds the service-centre number and stays names only."""
    result = await _sweep(
        {
            "sms_config": {"Sca": "+447911123456"},
            "device_basic_information": {
                "classify": "cpe",
                "multimode": "0",
                "devicename": "H165-383",
            },
        }
    )
    assert "values" not in result["sms_config"]
    assert result["sms_config"]["keys"] == ["Sca"]
    assert result["device_basic_information"]["values"] == {
        k: v
        for k, v in {"classify": "cpe", "multimode": "0"}.items()
        if k in CAPABILITY_BASIC_INFO_KEYS
    }


@pytest.mark.asyncio
async def test_the_download_publishes_numbers_and_masks_other_text() -> None:
    """Numbers stay, `classify` stays, other text becomes a type marker."""
    probes = await _sweep(
        {
            "global_module_switch": {
                "coulometer_enabled": "0",
                "nrProductEnable": "1",
                "a_future_name": "Living Room",
                "a_negative": "-3",
                "an_empty": "",
            },
            "device_basic_information": {"classify": "cpe", "multimode": "0"},
        }
    )
    document = await _download(probes)
    values = document["probes"]["global_module_switch"]["values"]
    assert values == {
        "coulometer_enabled": "0",
        "nrProductEnable": "1",
        "a_future_name": "<str>",
        "a_negative": "-3",
        "an_empty": "",
    }
    assert document["probes"]["device_basic_information"]["values"] == {
        "classify": "cpe",
        "multimode": "0",
    }
    assert "Living Room" not in json.dumps(document, default=str)


@pytest.mark.asyncio
async def test_an_identifier_under_a_known_text_key_is_tokenized() -> None:
    """The sanitizer runs first, so a MAC or a phone number under `classify` is a token."""
    for seeded, prefix in (("AA:BB:CC:DD:EE:01", "mac-"), ("+447911123456", "phone-")):
        probes = await _sweep({"device_basic_information": {"classify": seeded}})
        document = await _download(probes)
        published = document["probes"]["device_basic_information"]["values"]["classify"]
        assert published.startswith(prefix)
        assert seeded not in json.dumps(document, default=str)


def test_a_numeric_value_of_a_number_type_is_published_as_it_is() -> None:
    """A value already parsed to a number stays a number; a boolean is masked."""
    tokenizer = _Tokenizer()
    assert _capability_value("flag", 3, tokenizer) == 3
    assert _capability_value("ratio", 0.5, tokenizer) == 0.5
    assert _capability_value("flag", True, tokenizer) == "<bool>"
    assert _capability_value("nested", {"a": "1"}, tokenizer) == "<dict>"


def test_a_sweep_result_that_is_not_a_mapping_is_passed_through() -> None:
    """The sweep's own failure record is left as it is."""
    assert _publish_probes(None, _Tokenizer()) is None
    assert _publish_probes({"error": "TimeoutError"}, _Tokenizer()) == {
        "error": "TimeoutError"
    }
