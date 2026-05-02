"""The Huawei Router 5G Monitor integration."""

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .api import HuaweiRouter5GAPI
from .const import DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("target"): vol.All(str, vol.Length(min=1)),
        vol.Required("message"): vol.All(str, vol.Length(min=1, max=160)),
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Huawei Router 5G Monitor from a config entry with Background Safety."""
    conf = entry.options

    api = HuaweiRouter5GAPI(
        conf[CONF_HOST],
        conf.get(CONF_USERNAME),
        conf[CONF_PASSWORD],
    )

    coordinator = HuaweiRouter5GDataUpdateCoordinator(hass, entry, api)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Register the root System device early to prevent via_device warnings in platforms.
    device_registry = dr.async_get(hass)
    host = conf[CONF_HOST]
    mac = entry.data.get("mac")
    sub_id_prefix = mac if mac else f"host_{host}"

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

    # Register services
    async def async_send_sms(service_call) -> None:
        """Service to send an SMS."""
        target = service_call.data["target"]
        message = service_call.data["message"]
        if isinstance(target, str):
            target = [target]
        await api.send_sms(target, message)

    hass.services.async_register(
        DOMAIN, "send_sms", async_send_sms, schema=SERVICE_SCHEMA
    )

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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and release resources."""
    import contextlib

    coordinator = hass.data[DOMAIN][entry.entry_id]
    with contextlib.suppress(Exception):
        await coordinator.api.logout()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.services.async_remove(DOMAIN, "send_sms")
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok
