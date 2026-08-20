"""The Huawei Router 5G Monitor integration."""

import logging
from collections.abc import Mapping
from typing import Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType
from huawei_lte_api.enums.sms import BoxTypeEnum

from ._compat import via_device_link
from .api import HuaweiRouter5GAPI
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_STOP_POLLING,
    DOMAIN,
    REPAIR_NAMES,
    SERVICE_CLEANUP,
    SMS_MAX_CHARS_GSM7,
    SMS_MAX_CHARS_UNICODE,
    SMS_SEGMENTS_MAX,
)
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import _stale_tracker_entities, is_gsm7, parse_sms_list

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SEND_SMS_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("target"): vol.All(cv.ensure_list, [str]),
        vol.Required("message"): vol.All(
            str, vol.Length(min=1, max=SMS_MAX_CHARS_GSM7)
        ),
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


def _validate_sms_length(message: str) -> None:
    """Reject a message longer than the router will carry, before sending it.

    Which ceiling applies depends on the content: a message drawn entirely
    from the GSM 03.38 alphabet is packed as septets and fits far more than one
    containing a single emoji or curly quote, which forces UCS-2 for the whole
    message. The flat `max=160` this replaced was wrong in both directions —
    too small for plain text on a router that carries 612, and silent about the
    fact that the limit halves the moment one special character appears.

    `ServiceValidationError` rather than `HomeAssistantError`: the caller got
    the call wrong and can fix it (dev_standards Section 9).
    """
    gsm7 = is_gsm7(message)
    limit = SMS_MAX_CHARS_GSM7 if gsm7 else SMS_MAX_CHARS_UNICODE
    if len(message) <= limit:
        return
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="sms_too_long",
        translation_placeholders={
            "length": str(len(message)),
            "limit": str(limit),
            "encoding": "GSM-7" if gsm7 else "Unicode",
            "segments": str(SMS_SEGMENTS_MAX),
        },
    )


async def async_send_sms(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to send an SMS."""
    coordinator = _get_coordinator(hass, call.data)
    target = call.data["target"]
    message = call.data["message"]
    _validate_sms_length(message)

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
    `entity_id`, name, area, enabled state and every customization live on that
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


LIVE_OPTION_KEYS = frozenset({CONF_SCAN_INTERVAL, CONF_STOP_POLLING})
"""Options that may be applied to a running entry without rebuilding it.

Both are read fresh on every cycle — `coordinator.py` consults the scan
interval when it schedules and the pause flag when it decides whether to
fetch — so changing either takes effect on the next tick with no reload.
Everything outside this set is connection-affecting or structural.
"""


def _reload_signature(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return the options whose change requires a reload.

    Reload-by-default (Section 9): anything not named live is assumed to
    change how the integration connects or what it builds, so it rebuilds the
    entry rather than being applied to the running one. The allow-list exists
    only so the two frequently-tuned controls do not tear down the session
    every time they are nudged.
    """
    return {k: v for k, v in options.items() if k not in LIVE_OPTION_KEYS}


async def _async_options_updated(
    hass: HomeAssistant, entry: ConfigEntry[HuaweiRouter5GDataUpdateCoordinator]
) -> None:
    """Reload the entry when a non-live option changes.

    Without this the Options flow validates a new host or credential, writes
    it to the entry, and nothing else happens: `async_setup_entry` passed the
    values to `HuaweiRouter5GAPI` once at setup, so the coordinator keeps
    polling on the session it already holds and the new value is used only
    after a restart. Reauth and Reconfigure both reload; Options edits the
    same three fields and must behave the same way.

    Comparing signatures rather than reloading unconditionally is what keeps
    the polling interval and the pause switch live — both fire this listener
    on every change, and neither should cost a reconnect.
    """
    coordinator = entry.runtime_data
    signature = _reload_signature(entry.options)
    if signature == coordinator.reload_signature:
        return
    coordinator.reload_signature = signature
    await hass.config_entries.async_reload(entry.entry_id)


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

    # Remember which non-live options this entry was built with, so the update
    # listener can tell a connection change (reload) from a tuning change
    # (apply live). Section 9.
    coordinator.reload_signature = _reload_signature(entry.options)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

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

            # **Before the refresh, and inside its own guard.** Both halves of
            # that matter and they pull in opposite directions.
            #
            # Before: platforms are forwarded above, before this task runs
            # (Section 1), so the select cannot read its options at setup —
            # there is no client yet. It reads them from the coordinator as a
            # property instead, and `async_refresh` below is what makes every
            # entity write its state. Setting this *after* that call leaves the
            # first state write carrying the fallback list, and nothing writes
            # again until the next scheduled poll — three minutes of wrong
            # options by default.
            #
            # Guarded: this is a cosmetic label next to the data fetch, and must
            # never be able to prevent one. An earlier revision let a failure
            # here abort the whole initialization.
            try:
                coordinator.supported_net_modes = await api.get_supported_net_modes()
            except Exception:
                _LOGGER.debug("Could not read the accepted mode list", exc_info=True)

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

    # Before the logout: a pending follow-up refresh would otherwise fire
    # against a coordinator whose session has just been closed.
    coordinator.async_cancel_scheduled_refresh()

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
