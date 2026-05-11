"""Config flow for Huawei Router 5G Monitor integration."""

import logging
from collections.abc import Callable
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import AbortFlow, FlowResult

from .api import HuaweiAuthError, HuaweiConnectionError, HuaweiRouter5GAPI
from .const import CONF_NAME, DEFAULT_NAME, DOMAIN
from .helpers import get_router_model

_LOGGER = logging.getLogger(__name__)


def _user_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Return the user/options form schema, pre-filled with defaults."""
    return vol.Schema(
        {
            vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(
                CONF_HOST, default=defaults.get(CONF_HOST, "http://192.168.8.1")
            ): str,
            vol.Optional(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
        }
    )


async def _validate_credentials(user_input: dict[str, Any]) -> dict[str, Any]:
    """Validate router credentials and return basic device info."""
    api = HuaweiRouter5GAPI(
        user_input[CONF_HOST],
        user_input.get(CONF_USERNAME),
        user_input[CONF_PASSWORD],
    )
    await api.login()
    try:
        data = await api.get_data()
        dev_info = data.get("device_information") or {}
        mac = (
            dev_info.get("MacAddress1")
            or dev_info.get("wan_mac_address")
            or dev_info.get("WanMacAddress")
        )
        if mac:
            mac = mac.lower().replace(":", "").replace("-", "")
        return {
            "model": get_router_model(dev_info),
            "sw_version": dev_info.get("SoftwareVersion"),
            "hw_version": dev_info.get("HardwareVersion"),
            "mac": mac,
        }
    finally:
        await api.logout()


class HuaweiRouter5GConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,  # type: ignore[call-arg]
):
    """Handle a config flow for Huawei Router 5G Monitor."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        errors = {}

        if user_input is not None:
            try:
                info = await _validate_credentials(user_input)

                await self.async_set_unique_id(info["mac"] or user_input[CONF_HOST])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data=info,
                    options=user_input,
                )

            except AbortFlow:
                raise
            except HuaweiAuthError:
                errors["base"] = "invalid_auth"
            except HuaweiConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow user step")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle reauthentication."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        if self._reauth_entry is None:
            return self.async_abort(reason="entry_not_found")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Dialog that informs the user that reauth is required."""
        errors = {}
        if user_input is not None:
            try:
                await _validate_credentials(user_input)

                updated_options = dict(self._reauth_entry.options)
                updated_options.update(user_input)

                self.hass.config_entries.async_update_entry(
                    self._reauth_entry, options=updated_options
                )
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

            except HuaweiAuthError:
                errors["base"] = "invalid_auth"
            except HuaweiConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during reauth")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_user_schema(self._reauth_entry.options),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration."""
        errors = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            try:
                await _validate_credentials(user_input)

                self.hass.config_entries.async_update_entry(entry, options=user_input)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

            except HuaweiAuthError:
                errors["base"] = "invalid_auth"
            except HuaweiConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during reconfiguration")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(entry.options),
            errors=errors,
        )

    _ha_callback: Callable[[Callable[..., Any]], Callable[..., Any]] = (
        config_entries.callback
    )

    @staticmethod
    @_ha_callback
    def async_get_options_flow(
        entry: config_entries.ConfigEntry,
    ) -> HuaweiRouter5GOptionsFlow:
        """Return the options flow handler."""
        return HuaweiRouter5GOptionsFlow(entry)


class HuaweiRouter5GOptionsFlow(config_entries.OptionsFlow):
    """Handle reconfiguration of an existing Huawei Router entry."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options — reconfigure host, username, password."""
        errors = {}

        if user_input is not None:
            try:
                await _validate_credentials(user_input)

                new_name = user_input.get(CONF_NAME, DEFAULT_NAME)
                if new_name != self._entry.title:
                    self.hass.config_entries.async_update_entry(
                        self._entry, title=new_name
                    )

                updated_options = dict(self._entry.options)
                updated_options.update(user_input)

                return self.async_create_entry(title="", data=updated_options)

            except HuaweiAuthError:
                errors["base"] = "invalid_auth"
            except HuaweiConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow options step")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="init",
            data_schema=_user_schema(self._entry.options),
            errors=errors,
        )
