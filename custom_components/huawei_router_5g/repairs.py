"""Repair flows for Huawei Router 5G.

This module holds the fix flows for the two `is_fixable=True` issues the
integration raises: `auth_failed`, a per-entry issue, and
`library_restart_required`, a domain-level one. The `auth_failed` flow exists for
a narrow purpose that is worth stating, because the alternative looks like it
works.

Home Assistant resolves a fixable issue's Fix button through the integration's
`repairs` platform. When an integration has none, `RepairsFlowManager`
substitutes `ConfirmRepairFlow` — an empty confirm form that deletes the issue
on submit. The button therefore appears, is clickable, and *dismisses the card
without touching the credentials*. A user whose password the router rejected
would press Fix, watch the problem disappear, and still have a broken
integration until the next poll raised it again.

The flow below starts the reauth flow instead, which is what the repair's own
text promises.

`library_restart_required` is raised by the library guard after it has installed
`huawei-lte-api` 2.0.1, which takes effect only when Home Assistant restarts. Its
flow restarts Home Assistant when the user submits it.
"""

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import REPAIR_LIBRARY_RESTART


class AuthFailedRepairFlow(RepairsFlow):
    """Send the user to the reauth flow for the entry that failed."""

    def __init__(self, entry_id: str) -> None:
        """Store the entry this repair was raised for."""
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Handle the first step of the fix flow."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Confirm, then hand off to reauth.

        `async_start_reauth` is a no-op when a reauth flow for this entry is
        already in progress, which is the normal case: the coordinator raises
        `ConfigEntryAuthFailed` in the same breath as this repair, and Home
        Assistant starts one from that. Calling it here covers the case where
        that flow was dismissed and the card is the only way back.
        """
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry is not None:
                entry.async_start_reauth(self.hass)
            return self.async_create_entry(data={})

        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}))


class LibraryRestartRepairFlow(RepairsFlow):
    """Restart Home Assistant so an installed library upgrade takes effect."""

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Handle the first step of the fix flow."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Confirm, then restart Home Assistant.

        The service is called blocking so that a failed configuration check,
        which the service reports by raising, reaches this flow and aborts it
        instead of leaving a button that did nothing. A successful call returns
        once the stop has been scheduled.
        """
        if user_input is not None:
            try:
                await self.hass.services.async_call(
                    "homeassistant", "restart", blocking=True
                )
            except HomeAssistantError:
                return self.async_abort(reason="restart_failed")
            return self.async_create_entry(data={})

        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}))


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for a repair issue.

    The entry is read from `data` rather than parsed out of `issue_id`. The id
    format is an internal detail — it is `{name}_{entry_id}` here and
    `{entry_id}_{name}` on `zte_router_5g` — and an entry id containing an
    underscore would make either parse ambiguous.
    """
    if issue_id == REPAIR_LIBRARY_RESTART:
        return LibraryRestartRepairFlow()
    entry_id = str((data or {}).get("entry_id", ""))
    return AuthFailedRepairFlow(entry_id)


__all__ = [
    "AuthFailedRepairFlow",
    "LibraryRestartRepairFlow",
    "async_create_fix_flow",
]
