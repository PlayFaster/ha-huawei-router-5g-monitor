"""Tests for the `auth_failed` repair flow.

The sharp edge here is not that the flow works, but that it exists at all.
Home Assistant substitutes `ConfirmRepairFlow` for a fixable issue whose
integration ships no `repairs` platform, and that flow's Fix button shows an
empty confirm box and deletes the card — dismissing the problem while leaving
the credentials wrong. `test_the_fix_flow_is_ours_not_the_confirm_fallback` is
the test that fails if `repairs.py` is deleted or renamed.

Raised by `x_project/repair_set_alignment.md` §3.1.
"""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.huawei_router_5g.const import DOMAIN
from custom_components.huawei_router_5g.repairs import (
    AuthFailedRepairFlow,
    async_create_fix_flow,
)


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
