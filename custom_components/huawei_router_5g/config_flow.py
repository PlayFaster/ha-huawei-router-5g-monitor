"""Config flow for Huawei Router 5G integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.data_entry_flow import AbortFlow

from .api import HuaweiRouter5GAPI
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Huawei Router"


def _user_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(
                CONF_HOST, default=defaults.get(CONF_HOST, "http://192.168.8.1")
            ): str,
            vol.Required(
                CONF_USERNAME, default=defaults.get(CONF_USERNAME, "admin")
            ): str,
            vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=7200)),
            vol.Required(
                CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, False)
            ): bool,
        }
    )


async def _validate_credentials(user_input: dict[str, Any]) -> dict[str, Any]:
    """Validate router credentials and return hardware info."""
    api = HuaweiRouter5GAPI(
        user_input[CONF_HOST],
        user_input.get(CONF_USERNAME),
        user_input[CONF_PASSWORD],
        user_input.get(CONF_VERIFY_SSL, False),
    )
    await api.login()
    try:
        data = await api.get_data()
        dev_info = data.get("device_information", {})
        return {
            "model": dev_info.get("DeviceName", "Huawei Router"),
            "sw_version": dev_info.get("SoftwareVersion"),
            "hw_version": dev_info.get("HardwareVersion"),
            "mac": dev_info.get("WanMacAddress"),  # Might need adjustment
        }
    finally:
        await api.logout()


class HuaweiRouter5GConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step."""
        errors = {}
        if user_input is not None:
            try:
                info = await _validate_credentials(user_input)
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=info,
                    options=user_input,
                )
            except AbortFlow:
                raise
            except Exception as e:
                _LOGGER.error("Setup failed: %s", e)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(entry):
        """Return the options flow."""
        return HuaweiRouter5GOptionsFlow(entry)


class HuaweiRouter5GOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, entry):
        """Initialize options flow."""
        self._entry = entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        if user_input is not None:
            try:
                await _validate_credentials(user_input)
                updated_options = dict(self._entry.options)
                updated_options.update(user_input)
                self.hass.config_entries.async_update_entry(
                    self._entry, title=user_input[CONF_NAME]
                )
                return self.async_create_entry(title="", data=updated_options)
            except Exception as e:
                _LOGGER.error("Update failed: %s", e)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="init",
            data_schema=_user_schema(self._entry.options),
            errors=errors,
        )
