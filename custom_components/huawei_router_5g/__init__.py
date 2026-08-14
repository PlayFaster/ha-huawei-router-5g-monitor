"""The Huawei Router 5G Monitor integration."""

import logging
from typing import Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType
from huawei_lte_api.enums.sms import BoxTypeEnum

from ._compat import via_device_link
from .api import HuaweiRouter5GAPI
from .const import DOMAIN, REPAIR_NAMES, SERVICE_CLEANUP
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

SERVICE_CLEANUP_SCHEMA = vol.Schema(
    {
        vol.Optional("dry_run", default=True): cv.boolean,
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
        await coordinator.async_force_refresh()
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

        await coordinator.async_force_refresh()
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


def _tracked_macs(coordinator: HuaweiRouter5GDataUpdateCoordinator) -> set[str]:
    """Return every MAC the router currently reports, from both host lists."""
    data = coordinator.data or {}
    macs: set[str] = set()
    for key in ("lan_host_info", "wlan_host_list"):
        block = data.get(key)
        if not isinstance(block, dict):
            continue
        for host in block.get("Hosts", {}).get("Host", []) or []:
            if isinstance(host, dict) and (mac := host.get("MacAddress")):
                macs.add(mac)
    return macs


def _stale_tracker_entities(
    hass: HomeAssistant, entry: ConfigEntry
) -> list[er.RegistryEntry]:
    """Return device_tracker entities for clients the router no longer lists.

    A tracker is created for every client ever seen and nothing removes it, so
    a guest's phone seen once leaves a permanent entity. With two routers
    configured that accumulation stops being cosmetic.

    **Nothing is removed while the coordinator has no data.** An empty payload
    during an outage would otherwise make every client look stale and delete
    the lot — the failure mode this guard exists for.
    """
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None or not coordinator.data:
        return []

    live = _tracked_macs(coordinator)
    if not live:
        return []

    prefix = f"{entry.unique_id}_"
    registry = er.async_get(hass)
    return [
        item
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        if item.domain == Platform.DEVICE_TRACKER
        and item.unique_id.startswith(prefix)
        and item.unique_id[len(prefix) :] not in live
    ]


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

    async def _handle_cleanup(call: ServiceCall) -> dict[str, Any]:
        """Report or remove client trackers the router no longer lists."""
        dry_run: bool = call.data["dry_run"]
        report: dict[str, Any] = {}

        for entry in hass.config_entries.async_entries(DOMAIN):
            stale = _stale_tracker_entities(hass, entry)
            report[entry.title] = [item.entity_id for item in stale]
            if dry_run:
                continue
            registry = er.async_get(hass)
            for item in stale:
                _LOGGER.info(
                    "%s: Removing tracker for a client the router no longer "
                    "reports: %s",
                    entry.title,
                    item.entity_id,
                )
                registry.async_remove(item.entity_id)

        return {
            "dry_run": dry_run,
            "removed" if not dry_run else "would_remove": report,
        }

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

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEANUP,
        _handle_cleanup,
        schema=SERVICE_CLEANUP_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    return True


async def _async_migrate_tracker_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Scope `device_tracker` unique IDs to this config entry.

    `ScannerEntity.unique_id` returns the bare MAC address, so two Huawei
    routers tracking the same client would mint the same id and Home Assistant
    would refuse to add the second entity at all. The entity now scopes its own
    id; this rewrites the ids already in the registry to match.

    **Rewriting the registry row is what makes the change non-breaking.** The
    `entity_id`, name, area, enabled state and every customisation live on that
    row and are preserved — only `unique_id` changes. Skipping this would
    orphan the old rows and mint new entities with `_2` suffixes, breaking
    every automation and dashboard that referenced them.

    Idempotent: rows already carrying the prefix are left alone, so a second
    run is a no-op. Scoped to `device_tracker`, because every other platform
    has always built entry-scoped ids.

    Must run **before** platforms are forwarded, or the platform adds entities
    with new ids while the old rows still hold them and the collision this
    exists to prevent happens during the migration itself.
    """
    if not entry.unique_id:
        return

    prefix = f"{entry.unique_id}_"

    @callback
    def _migrate(registry_entry: er.RegistryEntry) -> dict[str, Any] | None:
        if registry_entry.domain != Platform.DEVICE_TRACKER:
            return None
        if registry_entry.unique_id.startswith(prefix):
            return None
        return {"new_unique_id": f"{prefix}{registry_entry.unique_id}"}

    await er.async_migrate_entries(hass, entry.entry_id, _migrate)


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

    # The `via_device` tuple is deprecated in HA 2026.8 and removed in 2027.8.
    # `via_device_link` feature-detects and emits `via_device_id` where
    # available. The System device is created immediately above, so the parent
    # always resolves.
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{sub_id_prefix}_clients")},
        name=f"{entry.title} Clients",
        manufacturer="Huawei",
        model=entry.data.get("model", "Huawei Router"),
        **via_device_link(hass, DOMAIN, f"{sub_id_prefix}_system", entry.entry_id),
    )

    # Before any platform is forwarded — see the docstring for why the order
    # is not incidental.
    await _async_migrate_tracker_unique_ids(hass, entry)

    # Forward platforms immediately so entities appear in HA at startup.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # BACKGROUND INITIALIZATION TASK
    # Offloads the initial connection to keep HA startup instant.
    async def _async_background_setup() -> None:
        try:
            await api.login()
            await coordinator.async_refresh()
            _LOGGER.info("%s: Background initialization complete.", entry.title)
        except Exception:
            _LOGGER.exception(
                "%s: Background initialization failed (will retry)",
                entry.title,
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

    # A repair raised by this entry must not outlive it. Cleared here as well
    # as in async_remove_entry because a disabled or reloaded entry leaves the
    # repair pointing at an integration that is not running.
    coordinator.clear_repairs()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    return bool(unload_ok)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up after the integration is deleted.

    Home Assistant calls this after `async_unload_entry`, when the entry is
    being removed for good. Without it, a repair raised at deletion time stays
    in the Repairs panel permanently — there is no coordinator left that could
    ever clear it, and `auth_failed` is `is_fixable=True`, so it would offer a
    repair flow for an integration that no longer exists.

    Deliberately does not go through `runtime_data`: it has already been torn
    down by the time this runs.
    """
    for name in REPAIR_NAMES:
        ir.async_delete_issue(hass, DOMAIN, f"{name}_{entry.entry_id}")
