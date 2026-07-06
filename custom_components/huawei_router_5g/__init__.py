"""The Huawei Router 5G Monitor integration."""

import logging
from typing import Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from huawei_lte_api.enums.sms import BoxTypeEnum

from .api import HuaweiRouter5GAPI
from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import parse_sms_list

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SEND_SMS_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("target"): vol.All(cv.ensure_list, [str]),
        vol.Required("message"): vol.All(str, vol.Length(min=1, max=160)),
    }
)

SERVICE_DELETE_SMS_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("index"): vol.Coerce(int),
    }
)

SERVICE_DELETE_ALL_SMS_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("keep_last", default=0): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=50)
        ),
    }
)

SERVICE_GET_SMS_LIST_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("page", default=1): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional("count", default=20): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=50)
        ),
        vol.Optional("box_type", default=1): vol.All(
            vol.Coerce(int), vol.In([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        ),
    }
)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.DEVICE_TRACKER,
    Platform.NUMBER,
]


def _get_coordinator(
    hass: HomeAssistant, call_data: dict[str, Any]
) -> HuaweiRouter5GDataUpdateCoordinator:
    """Get coordinator from service call data."""
    entry_id = call_data.get("entry_id")
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == DOMAIN:
            if hasattr(entry, "runtime_data") and entry.runtime_data:
                return cast(HuaweiRouter5GDataUpdateCoordinator, entry.runtime_data)
            raise HomeAssistantError(f"Router {entry.title} is not ready")

    # No entry_id given: auto-select only when exactly one router is loaded.
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if getattr(entry, "runtime_data", None)
    ]
    if len(entries) == 1:
        return cast(HuaweiRouter5GDataUpdateCoordinator, entries[0].runtime_data)
    if not entries:
        raise HomeAssistantError("No active Huawei Router 5G entries found")
    raise HomeAssistantError(
        "Multiple Huawei Router 5G routers are configured — specify entry_id"
    )


async def async_send_sms(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to send an SMS."""
    coordinator = _get_coordinator(hass, call.data)
    target = call.data["target"]
    message = call.data["message"]

    try:
        await coordinator.api.send_sms(target, message)
    except Exception as err:
        raise HomeAssistantError(f"Failed to send SMS: {err}") from err


async def async_delete_sms(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to delete an SMS."""
    coordinator = _get_coordinator(hass, call.data)
    index = call.data["index"]

    try:
        await coordinator.api.delete_sms(index)
        await coordinator.async_request_refresh()
    except Exception as err:
        raise HomeAssistantError(f"Failed to delete SMS: {err}") from err


async def async_delete_all_sms(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to delete all SMS messages."""
    coordinator = _get_coordinator(hass, call.data)
    keep_last = call.data.get("keep_last", 0)

    try:
        # Fetch current list to identify messages to delete
        response = await coordinator.api.get_sms_list(
            page=1, box_type=BoxTypeEnum.LOCAL_INBOX, read_count=50
        )
        messages = parse_sms_list(response)

        # Skip the most recent 'keep_last' messages
        to_delete = messages[keep_last:] if keep_last > 0 else messages

        for msg in to_delete:
            await coordinator.api.delete_sms(msg["index"])

        await coordinator.async_request_refresh()
    except Exception as err:
        raise HomeAssistantError(f"Failed to delete all SMS: {err}") from err


async def async_get_sms_list(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Service to get SMS list with response."""
    coordinator = _get_coordinator(hass, call.data)
    page = call.data["page"]
    count = call.data["count"]

    try:
        box_type = BoxTypeEnum(call.data["box_type"])
        response = await coordinator.api.get_sms_list(
            page=page, box_type=box_type, read_count=count
        )
        return {"messages": parse_sms_list(response)}
    except Exception as err:
        raise HomeAssistantError(f"Failed to fetch SMS list: {err}") from err


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Huawei Router 5G Monitor component."""

    async def _handle_send_sms(call: ServiceCall) -> None:
        await async_send_sms(hass, call)

    async def _handle_delete_sms(call: ServiceCall) -> None:
        await async_delete_sms(hass, call)

    async def _handle_delete_all_sms(call: ServiceCall) -> None:
        await async_delete_all_sms(hass, call)

    async def _handle_get_sms_list(call: ServiceCall) -> dict[str, Any]:
        return await async_get_sms_list(hass, call)

    hass.services.async_register(
        DOMAIN,
        "send_sms",
        _handle_send_sms,
        schema=SERVICE_SEND_SMS_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        "delete_sms",
        _handle_delete_sms,
        schema=SERVICE_DELETE_SMS_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        "delete_all_sms",
        _handle_delete_all_sms,
        schema=SERVICE_DELETE_ALL_SMS_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        "get_sms_list",
        _handle_get_sms_list,
        schema=SERVICE_GET_SMS_LIST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[HuaweiRouter5GDataUpdateCoordinator]
) -> bool:
    """Set up Huawei Router 5G Monitor from a config entry with Background Safety."""
    conf = entry.options

    api = HuaweiRouter5GAPI(
        conf[CONF_HOST],
        conf.get(CONF_USERNAME),
        conf[CONF_PASSWORD],
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(hass, entry, api)
    entry.runtime_data = coordinator

    # Register the root System device early to prevent via_device warnings in platforms.
    device_registry = dr.async_get(hass)
    host = conf[CONF_HOST]
    mac = entry.data.get("mac")
    sub_id_prefix = mac or f"host_{host}"

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{sub_id_prefix}_system")},
        name=f"{entry.title} System",
        manufacturer="Huawei",
        model=entry.data.get("model", "Huawei Router"),
        sw_version=entry.data.get("sw_version"),
        hw_version=entry.data.get("hw_version"),
        configuration_url=f"http://{host}",
    )

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{sub_id_prefix}_clients")},
        name=f"{entry.title} Clients",
        manufacturer="Huawei",
        model=entry.data.get("model", "Huawei Router"),
        via_device=(DOMAIN, f"{sub_id_prefix}_system"),
    )

    # Forward platforms immediately so entities appear in HA at startup.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # BACKGROUND INITIALIZATION TASK
    # Offloads the initial connection to keep HA startup instant.
    async def _async_background_setup() -> None:
        try:
            await api.login()
            await coordinator.async_refresh()
            _LOGGER.info("%s: Background initialization complete.", entry.title)
        except Exception as err:
            _LOGGER.warning(
                "%s: Background initialization failed (will retry): %s",
                entry.title,
                err,
            )

    entry.async_create_background_task(
        hass, _async_background_setup(), "huawei-router-setup"
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry[HuaweiRouter5GDataUpdateCoordinator]
) -> bool:
    """Unload a config entry and release resources."""
    import contextlib

    coordinator = entry.runtime_data
    with contextlib.suppress(Exception):
        await coordinator.api.logout()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    return bool(unload_ok)
