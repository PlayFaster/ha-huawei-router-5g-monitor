"""Tests for the `auth_failed` repair flow.

The sharp edge here is not that the flow works, but that it exists at all.
Home Assistant substitutes `ConfirmRepairFlow` for a fixable issue whose
integration ships no `repairs` platform, and that flow's Fix button shows an
empty confirm box and deletes the card — dismissing the problem while leaving
the credentials wrong. `test_the_fix_flow_is_ours_not_the_confirm_fallback` is
the test that fails if `repairs.py` is deleted or renamed.

"""

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.huawei_router_5g.const import DOMAIN, REPAIR_LIBRARY_RESTART
from custom_components.huawei_router_5g.repairs import (
    AuthFailedRepairFlow,
    LibraryRestartRepairFlow,
    async_create_fix_flow,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


async def test_the_fix_flow_is_ours_not_the_confirm_fallback(
    hass: HomeAssistant,
) -> None:
    """Without `repairs.py` HA substitutes a flow that dismisses the card.

    `ConfirmRepairFlow` deletes the issue on submit and touches nothing else,
    so the Fix button would resolve the symptom and leave the credentials
    rejected. Asserting the concrete type is what makes deleting this module a
    test failure rather than a silent downgrade.
    """
    flow = await async_create_fix_flow(hass, "auth_failed_abc", {"entry_id": "abc"})

    assert isinstance(flow, AuthFailedRepairFlow)


async def test_confirming_the_fix_starts_the_reauth_flow(hass: HomeAssistant) -> None:
    """The card promises re-entering credentials; the flow must deliver it."""
    entry = MockConfigEntry(domain=DOMAIN, title="Huawei 5G", data={})
    entry.add_to_hass(hass)

    flow = AuthFailedRepairFlow(entry.entry_id)
    flow.hass = hass

    form = await flow.async_step_init()
    assert form["type"] == "form"
    assert form["step_id"] == "confirm"

    with patch.object(entry, "async_start_reauth") as start_reauth:
        result = await flow.async_step_confirm({})

    start_reauth.assert_called_once_with(hass)
    assert result["type"] == "create_entry"


async def test_the_flow_survives_an_entry_deleted_under_it(
    hass: HomeAssistant,
) -> None:
    """Deleting the integration while the card is open must not raise.

    The repair is `is_persistent`, so it outlives a restart and can still be
    sitting there after the entry it describes is gone.
    """
    flow = AuthFailedRepairFlow("an-entry-that-no-longer-exists")
    flow.hass = hass

    result = await flow.async_step_confirm({})

    assert result["type"] == "create_entry"


async def test_the_factory_returns_the_restart_flow_for_the_library_issue(
    hass: HomeAssistant,
) -> None:
    """The domain-level issue gets its own flow, and every other id keeps the auth one."""
    library = await async_create_fix_flow(hass, REPAIR_LIBRARY_RESTART, None)
    auth = await async_create_fix_flow(hass, "auth_failed_abc", {"entry_id": "abc"})

    assert isinstance(library, LibraryRestartRepairFlow)
    assert isinstance(auth, AuthFailedRepairFlow)


async def test_the_restart_flow_shows_a_confirm_form_first(hass: HomeAssistant) -> None:
    """Nothing restarts until the user submits the form."""
    calls = async_mock_service(hass, "homeassistant", "restart")
    flow = LibraryRestartRepairFlow()
    flow.hass = hass

    result = await flow.async_step_init()

    assert result["type"] == "form"
    assert result["step_id"] == "confirm"
    assert calls == []


async def test_submitting_the_restart_flow_restarts_home_assistant_once(
    hass: HomeAssistant,
) -> None:
    """The Submit button is the restart."""
    calls = async_mock_service(hass, "homeassistant", "restart")
    flow = LibraryRestartRepairFlow()
    flow.hass = hass

    result = await flow.async_step_confirm({})

    assert result["type"] == "create_entry"
    assert len(calls) == 1


async def test_a_failed_restart_aborts_the_flow_with_a_reason(
    hass: HomeAssistant,
) -> None:
    """The restart service raises when the configuration check fails.

    The flow must abort and say so, not finish as though Home Assistant had
    restarted: the user would otherwise see the card disappear and nothing happen.
    """

    async def _refuse(call) -> None:
        raise HomeAssistantError("configuration check failed")

    hass.services.async_register("homeassistant", "restart", _refuse)
    flow = LibraryRestartRepairFlow()
    flow.hass = hass

    result = await flow.async_step_confirm({})

    assert result["type"] == "abort"
    assert result["reason"] == "restart_failed"
