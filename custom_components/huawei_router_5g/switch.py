"""Switch platform for Huawei Router 5G Monitor."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STOP_POLLING, DOMAIN
from .coordinator import HuaweiRouter5GDataUpdateCoordinator
from .helpers import (
    ABOUT_UNRECORDED,
    HuaweiAboutEntity,
    build_device_info,
    confirm_write,
)

_LOGGER = logging.getLogger(__name__)

# Section 22. `1`, not `0`.
#
# `0` means *unlimited*. This platform issues commands with a real-world effect
# on the router, and `api.py` serializes every call behind an `asyncio.Lock`
# precisely because concurrent calls answer with "Busy" / `110001`. That lock is
# the actual safety mechanism; `PARALLEL_UPDATES = 1` states the same intent at
# the platform boundary and stops N concurrent service calls each occupying a
# Home Assistant task while they queue on it.
#
# Decided per write path rather than copied from `zte_router_5g` — see
# `number.py`, which reaches the opposite answer for the opposite reason.
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class HuaweiSwitchEntityDescription(SwitchEntityDescription):
    """Describes a Huawei Router 5G switch entity."""

    group: str = "system"
    # dev_standards Section 14 - the human-facing `about` note. Mandatory; a
    # sweep in `tests/test_entity_hygiene.py` fails when one is missing.
    about: str | None = None


PAUSE_POLLING_DESCRIPTION = HuaweiSwitchEntityDescription(
    key="pause_polling",
    about=(
        "Stops the scheduled polling without removing the integration. "
        "Entities hold their last values rather than going unavailable. "
        "Explicit actions - Refresh Now, and the refresh after a control "
        "change - still reach the router while this is on."
    ),
    translation_key="pause_polling",
    entity_category=EntityCategory.CONFIG,
    group="system",
)

MOBILE_DATA_DESCRIPTION = HuaweiSwitchEntityDescription(
    key="mobile_data",
    about=(
        "Turns the mobile data connection on or off. The LAN and WiFi are "
        "unaffected, so this does not disconnect local devices from each "
        "other - only from the internet. A refusal by the router raises an "
        "error rather than reporting an unearned success."
    ),
    translation_key="mobile_data",
    entity_category=EntityCategory.CONFIG,
    group="system",
)

WIFI_DESCRIPTION = HuaweiSwitchEntityDescription(
    key="wifi",
    about=(
        "Turns the router's WiFi radios on or off. It writes the **radio** "
        "switch rather than the per-SSID flags, because those flags are gated "
        "by the radio and writing them while it is off changes nothing - an "
        "earlier implementation that did so appeared to work and did not."
    ),
    translation_key="wifi",
    entity_category=EntityCategory.CONFIG,
    group="wifi",
)

GUEST_WIFI_DESCRIPTION = HuaweiSwitchEntityDescription(
    key="wifi_guest_network",
    about=(
        "Turns the guest network on or off. The `ssid` attribute names the "
        "network being controlled. Worth knowing before leaving it on: on "
        "this hardware the guest SSID is configured open, so an unattended "
        "`on` is an unauthenticated network on air."
    ),
    translation_key="wifi_guest_network",
    entity_category=EntityCategory.CONFIG,
    group="wifi",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinator: HuaweiRouter5GDataUpdateCoordinator = entry.runtime_data

    initial_pause_state = entry.options.get(CONF_STOP_POLLING, False)

    async_add_entities(
        [
            HuaweiPausePollingSwitch(
                coordinator, entry, PAUSE_POLLING_DESCRIPTION, initial_pause_state
            ),
            HuaweiMobileDataSwitch(coordinator, entry, MOBILE_DATA_DESCRIPTION),
            HuaweiWifiSwitch(coordinator, entry, WIFI_DESCRIPTION),
            HuaweiGuestWifiSwitch(coordinator, entry, GUEST_WIFI_DESCRIPTION),
        ]
    )


class HuaweiSwitch(
    HuaweiAboutEntity,
    CoordinatorEntity[HuaweiRouter5GDataUpdateCoordinator],
    SwitchEntity,
):
    """Base class for Huawei Router 5G switches."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description: HuaweiSwitchEntityDescription

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry: ConfigEntry,
        description: HuaweiSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._group = description.group

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information with sub-device support."""
        return build_device_info(self.coordinator, self._group)

    async def _async_confirm(
        self,
        endpoint: str,
        extract: Callable[[dict[str, Any]], Any],
        expected: str,
        label: str,
    ) -> None:
        """Confirm a completed write by re-reading the one key it changed.

        Section 22. Replaces a debounced full refresh — 26 endpoints and up to
        ten seconds to learn a single flag, during which the frontend's
        optimistic toggle springs back and then corrects itself.

        **Three outcomes, and only one of them is an error.** A read that
        disagrees twice means the router declined the command and the user
        must be told. A read that fails or omits the key means *unverified*:
        the write may well have taken effect, so it is logged and left to the
        next poll rather than reported as a failure the user would act on.

        Called after the write has already succeeded, so it never re-raises
        the write's own exception.
        """
        confirmed = await confirm_write(
            self.coordinator.api,
            endpoint,
            extract,
            expected,
            label=f"{self._entry.title}: {label}",
        )

        if confirmed is False:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_not_confirmed",
                translation_placeholders={"action": label},
            )

        if confirmed is True:
            # The device agrees. Publish now rather than waiting for a poll.
            self.async_write_ha_state()
            return

        # Unverified. Nothing to publish and nothing to raise; the next
        # scheduled poll settles it.
        await self.coordinator.async_force_refresh()


def _guest_enable_flag(block: dict[str, Any]) -> Any:
    """Pull the guest SSID's enable flag out of the WiFi settings block.

    The flag is not a top-level key: the block carries every SSID and the
    guest network is the one whose `wifiisguestnetwork` is set. Matching on
    that rather than on list position, because the router does not guarantee
    an order — the same lesson the APN profile lookup learned when it came
    back 1, 3, 2.
    """
    ssids = (block.get("Ssids") or {}).get("Ssid", [])
    if isinstance(ssids, dict):
        ssids = [ssids]
    for ssid in ssids:
        if str(ssid.get("wifiisguestnetwork")) == "1":
            return ssid.get("WifiEnable")
    return None


class HuaweiPausePollingSwitch(HuaweiSwitch):
    """Switch to pause/resume data polling with persistence across restarts."""

    def __init__(
        self,
        coordinator: HuaweiRouter5GDataUpdateCoordinator,
        entry: ConfigEntry,
        description: HuaweiSwitchEntityDescription,
        initial_state: bool,
    ) -> None:
        """Initialize the pause polling switch."""
        super().__init__(coordinator, entry, description)
        self._attr_is_on = initial_state

    @property
    def is_on(self) -> bool:
        """Return True if polling is paused."""
        return bool(self._entry.options.get(CONF_STOP_POLLING, False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Pause polling."""
        _LOGGER.debug("Pausing Huawei Router polling")
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Resume polling."""
        _LOGGER.debug("Resuming Huawei Router polling")
        await self._async_set_state(False)

    async def _async_set_state(self, state: bool) -> None:
        """Persist pause state to ConfigEntry options and notify HA."""
        new_options = dict(self._entry.options)
        new_options[CONF_STOP_POLLING] = state
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        self.async_write_ha_state()

        if not state:
            await self.coordinator.async_force_refresh()


class HuaweiMobileDataSwitch(HuaweiSwitch):
    """Switch to enable or disable the mobile data connection."""

    @property
    def is_on(self) -> bool | None:
        """Return True if mobile data is enabled."""
        data = self.coordinator.data
        if not data:
            return None
        mobile_sw = data.get("mobile_dataswitch") or {}
        val = mobile_sw.get("dataswitch")
        if val is None:
            return None
        return str(val) == "1"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable mobile data."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable mobile data."""
        await self._async_set(False)

    async def _async_set(self, enable: bool) -> None:
        """Write the mobile-data state, raising if the router refused.

        A write path may never return a success-shaped result having done
        nothing. This previously logged the exception and returned, so a failed
        toggle looked identical to a successful one: the service call
        succeeded, the switch sprang back on the next poll, and the only
        evidence was a log line. `button.py` already had this right.
        """
        action = "Enable" if enable else "Disable"
        try:
            await self.coordinator.api.set_mobile_data(enable)
        except Exception as err:
            _LOGGER.exception("%s: %s mobile data failed", self._entry.title, action)
            raise HomeAssistantError(f"{action} mobile data failed: {err}") from err

        # Outside the error boundary on purpose. The write has already
        # succeeded; a blip while re-reading must not report the write as
        # failed and invite a retry of a command with a real-world effect.
        await self._async_confirm(
            "mobile_dataswitch",
            lambda block: block.get("dataswitch"),
            "1" if enable else "0",
            f"{action} mobile data",
        )


class HuaweiWifiSwitch(HuaweiSwitch):
    """Master WiFi switch - the radios, not the individual networks.

    **A different level from the guest switch**, and that distinction is why an
    earlier attempt at this control could not be made to work. The router keeps
    radio state in `wlan/status-switch-settings` and per-SSID state in
    `wlan/multi-basic-settings`; the SSID flags are gated by the radio, so
    writing them while the radio is off changes nothing.

    Reads `monitoring_status.WifiStatus`, which is already polled - the radio
    block would be a second round trip for the same fact. Confirmed to track
    the radios in both directions on a live B535.
    """

    @property
    def is_on(self) -> bool | None:
        """Return True if the WiFi radios are on."""
        data = self.coordinator.data
        if not data:
            return None
        raw = (data.get("monitoring_status") or {}).get("WifiStatus")
        return None if raw in (None, "") else str(raw) == "1"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the WiFi radios on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the WiFi radios off."""
        await self._async_set(False)

    async def _async_set(self, enable: bool) -> None:
        """Write the radio state, raising if the router refused."""
        action = "Enable" if enable else "Disable"
        try:
            await self.coordinator.api.set_wifi(enable)
        except Exception as err:
            _LOGGER.exception("%s: %s WiFi failed", self._entry.title, action)
            raise HomeAssistantError(f"{action} WiFi failed: {err}") from err

        # Outside the error boundary - see HuaweiMobileDataSwitch._async_set.
        await self._async_confirm(
            "monitoring_status",
            lambda block: block.get("WifiStatus"),
            "1" if enable else "0",
            f"{action} WiFi",
        )


class HuaweiGuestWifiSwitch(HuaweiSwitch):
    """Switch to enable or disable the guest WiFi network."""

    # dev_standards Section 14. The guest SSID is a static string republished
    # on every poll; recording it adds a row per poll and puts the network name
    # into long-term history.
    _unrecorded_attributes = ABOUT_UNRECORDED | frozenset({"ssid"})

    @property
    def is_on(self) -> bool | None:
        """Return True if guest WiFi is enabled."""
        data = self.coordinator.data
        if not data:
            return None
        multi_settings = data.get("wlan_multi_basic_settings") or {}
        ssids = multi_settings.get("Ssids", {}).get("Ssid", [])
        if isinstance(ssids, dict):
            ssids = [ssids]

        for ssid in ssids:
            if str(ssid.get("wifiisguestnetwork")) == "1":
                return str(ssid.get("WifiEnable")) == "1"
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable guest WiFi."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable guest WiFi."""
        await self._async_set(False)

    async def _async_set(self, enable: bool) -> None:
        """Write the guest-WiFi state, raising if the router refused.

        The previous form logged the failure and then refreshed in a `finally`,
        which masked it twice over: the service call reported success, and the
        refresh made the switch look as though it had simply been re-read.
        """
        action = "Enable" if enable else "Disable"
        try:
            await self.coordinator.api.set_guest_wifi(enable)
        except Exception as err:
            _LOGGER.exception("%s: %s guest WiFi failed", self._entry.title, action)
            raise HomeAssistantError(f"{action} guest WiFi failed: {err}") from err

        # Outside the error boundary — see HuaweiMobileDataSwitch._async_set.
        # The guest flag is nested inside the SSID list rather than being a
        # flat key, which is why the read-back takes an extractor.
        await self._async_confirm(
            "wlan_multi_basic_settings",
            _guest_enable_flag,
            "1" if enable else "0",
            f"{action} guest WiFi",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        data = self.coordinator.data
        if not data:
            return self._with_about(None) or {}
        multi_settings = data.get("wlan_multi_basic_settings") or {}
        ssids = multi_settings.get("Ssids", {}).get("Ssid", [])
        if isinstance(ssids, dict):
            ssids = [ssids]

        for ssid in ssids:
            if str(ssid.get("wifiisguestnetwork")) == "1":
                return self._with_about({"ssid": ssid.get("WifiSsid")}) or {}
        return self._with_about(None) or {}
