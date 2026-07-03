"""Config flow for Huawei Router 5G Monitor integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import HuaweiAuthError, HuaweiConnectionError, HuaweiRouter5GAPI
from .const import CONF_NAME, DEFAULT_NAME, DOMAIN
from .helpers import get_router_model

_LOGGER = logging.getLogger(__name__)


def _clean_host(host: str) -> str:
    """Strip protocol prefix and trailing slashes from a host entry.

    The API layer re-adds a scheme via ``_normalize_router_url``, so only the
    bare host is stored. This keeps the device ``configuration_url`` (built as
    ``http://{host}``) from doubling up (e.g. ``http://http://192.168.8.1``).
    """
    clean = host.strip()
    if "://" in clean:
        clean = clean.split("://", 1)[1]
    return clean.rstrip("/")


def _password_selector() -> TextSelector:
    """Return a masked password text selector."""
    return TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _user_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Return the initial setup schema. The password field is masked."""
    return vol.Schema(
        {
            vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(
                CONF_HOST, default=defaults.get(CONF_HOST, "http://192.168.8.1")
            ): str,
            vol.Optional(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD, default=""): _password_selector(),
        }
    )


def _edit_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Return the reconfigure/reauth/options schema.

    The password field is intentionally left blank so the stored value cannot
    be retrieved via the UI eye-icon. Leave it blank to keep the existing
    password, or enter a new value to change it. Non-sensitive fields (name,
    host, username) are pre-filled for convenience.
    """
    return vol.Schema(
        {
            vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Optional(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Optional(CONF_PASSWORD, default=""): _password_selector(),
        }
    )


def _merge_credentials(
    user_input: dict[str, Any], existing: Mapping[str, Any]
) -> dict[str, Any]:
    """Fill a blank password field from the existing stored value."""
    merged = dict(user_input)
    if not (merged.get(CONF_PASSWORD) or "").strip():
        merged[CONF_PASSWORD] = existing.get(CONF_PASSWORD) or ""
    return merged


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
    domain=DOMAIN,
):
    """Handle a config flow for Huawei Router 5G Monitor."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors = {}

        if user_input is not None:
            user_input[CONF_HOST] = _clean_host(user_input[CONF_HOST])
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

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        if self._reauth_entry is None:
            return self.async_abort(reason="entry_not_found")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        errors = {}
        assert self._reauth_entry is not None
        if user_input is not None:
            user_input[CONF_HOST] = _clean_host(user_input[CONF_HOST])
            merged = _merge_credentials(user_input, self._reauth_entry.options)
            try:
                await _validate_credentials(merged)

                updated_options = dict(self._reauth_entry.options)
                updated_options.update(merged)

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
            data_schema=_edit_schema(self._reauth_entry.options),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration."""
        errors = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        if user_input is not None:
            user_input[CONF_HOST] = _clean_host(user_input[CONF_HOST])
            merged = _merge_credentials(user_input, entry.options)
            try:
                await _validate_credentials(merged)

                self.hass.config_entries.async_update_entry(
                    entry, options={**entry.options, **merged}
                )
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
            data_schema=_edit_schema(entry.options),
            errors=errors,
        )

    _ha_callback: Callable[[Callable[..., Any]], Callable[..., Any]] = callback

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
    ) -> ConfigFlowResult:
        """Manage the options — reconfigure host, username, password."""
        errors = {}

        if user_input is not None:
            user_input[CONF_HOST] = _clean_host(user_input[CONF_HOST])
            merged = _merge_credentials(user_input, self._entry.options)
            try:
                await _validate_credentials(merged)

                new_name = merged.get(CONF_NAME, DEFAULT_NAME)
                if new_name != self._entry.title:
                    self.hass.config_entries.async_update_entry(
                        self._entry, title=new_name
                    )

                updated_options = dict(self._entry.options)
                updated_options.update(merged)

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
            data_schema=_edit_schema(self._entry.options),
            errors=errors,
        )
