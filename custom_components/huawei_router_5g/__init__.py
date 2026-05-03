"""The Huawei Router 5G Monitor integration."""

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Huawei Router 5G Monitor component."""

    async def async_send_sms(service_call) -> None:
        """Service to send an SMS."""
        entries: list[ConfigEntry[HuaweiRouter5GDataUpdateCoordinator]] = (
            hass.config_entries.async_entries(DOMAIN)
        )
        if not entries:
            raise HomeAssistantError("No Huawei Router 5G entries found")

        # Use the first available entry's coordinator
        entry = entries[0]
        if not hasattr(entry, "runtime_data"):
            raise HomeAssistantError(f"Integration entry {entry.title} not ready")

        coordinator = entry.runtime_data
        target = service_call.data["target"]
        message = service_call.data["message"]
        if isinstance(target, str):
            target = [target]

        try:
            await coordinator.api.send_sms(target, message)
        except Exception as err:
            raise HomeAssistantError(f"Failed to send SMS: {err}") from err

    if not hass.services.has_service(DOMAIN, "send_sms"):
        hass.services.async_register(
            DOMAIN, "send_sms", async_send_sms, schema=SERVICE_SCHEMA
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

    return unload_ok
