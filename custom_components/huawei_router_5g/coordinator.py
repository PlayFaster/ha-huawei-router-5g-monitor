"""DataUpdateCoordinator for Huawei Router 5G."""

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import HuaweiAuthError, HuaweiRouter5GAPI
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_STOP_POLLING,
    DEFAULT_SCAN_INTERVAL,
    FETCH_TIMEOUT,
)
from .helpers import get_router_model, parse_sms_list

_LOGGER = logging.getLogger(__name__)

# Minimum drop in a router uptime counter (seconds) treated as a genuine reset.
# A real reboot/reconnect resets the counter to ~0, so this margin only rejects
# small downward blips from counter quantisation or stale cached readings.
UPTIME_REBOOT_MARGIN = 30


class HuaweiRouter5GDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Huawei Router data with resilience and pausing."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: HuaweiRouter5GAPI,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.entry = entry
        self.consecutive_failures = 0
        self.last_update_success_time: datetime | None = None
        self.last_sms_timestamp: str | None = None
        self.fired_sms_hashes: set[str] = set()

        # Reboot-detection latches — frozen timestamps for uptime-derived sensors.
        # Each is recomputed exactly once per genuine counter reset and then held.
        self._system_boot_time: datetime | None = None
        self._last_system_uptime: int | None = None
        self._conn_start_time: datetime | None = None
        self._last_conn_uptime: int | None = None
        self._total_conn_start_time: datetime | None = None
        self._last_total_conn_time: int | None = None

        with contextlib.suppress(Exception):
            if v := entry.data.get("system_boot_time"):
                self._system_boot_time = dt_util.parse_datetime(v)
        with contextlib.suppress(ValueError, TypeError):
            if (v := entry.data.get("last_system_uptime")) is not None:
                self._last_system_uptime = int(v)
        with contextlib.suppress(Exception):
            if v := entry.data.get("conn_start_time"):
                self._conn_start_time = dt_util.parse_datetime(v)
        with contextlib.suppress(ValueError, TypeError):
            if (v := entry.data.get("last_conn_uptime")) is not None:
                self._last_conn_uptime = int(v)
        with contextlib.suppress(Exception):
            if v := entry.data.get("total_conn_start_time"):
                self._total_conn_start_time = dt_util.parse_datetime(v)
        with contextlib.suppress(ValueError, TypeError):
            if (v := entry.data.get("last_total_conn_time")) is not None:
                self._last_total_conn_time = int(v)

        # Load hardware identity from persistent ConfigEntry data.
        self.model = entry.data.get("model", "Huawei Router")
        self.sw_version = entry.data.get("sw_version")
        self.hw_version = entry.data.get("hw_version")
        self.mac = entry.data.get("mac")

        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{entry.title} Data",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the API with resilience and pause support."""
        is_paused = self.entry.options.get(CONF_STOP_POLLING, False)
        is_first_run = self.data is None

        if is_paused and not is_first_run:
            _LOGGER.debug(
                "%s: Polling is paused; returning cached data.", self.entry.title
            )
            return self.data

        try:
            async with asyncio.timeout(FETCH_TIMEOUT):
                try:
                    data = await self.api.get_data()
                except HuaweiAuthError:
                    _LOGGER.debug(
                        "%s: Session expired mid-fetch, retrying once.",
                        self.entry.title,
                    )
                    data = await self.api.get_data()

                # Critical Data Guard: If essential keys are missing, treat as a
                # fetch failure rather than a partial success that would
                # clear sensors.
                if not data or "device_information" not in data:
                    raise UpdateFailed(
                        "Critical data missing from fetch (e.g. device_info)"
                    )

                dev_info = data.get("device_information") or {}
                new_model = get_router_model(dev_info)
                new_sw = dev_info.get("SoftwareVersion")
                new_hw = dev_info.get("HardwareVersion")

                if (
                    new_model != self.model
                    or new_sw != self.sw_version
                    or new_hw != self.hw_version
                ):
                    _LOGGER.info(
                        "%s: Hardware metadata updated: %s sw=%s hw=%s",
                        self.entry.title,
                        new_model,
                        new_sw,
                        new_hw,
                    )
                    self.model = new_model
                    self.sw_version = new_sw
                    self.hw_version = new_hw

                    new_entry_data = dict(self.entry.data)
                    new_entry_data.update(
                        {
                            "model": new_model,
                            "sw_version": new_sw,
                            "hw_version": new_hw,
                        }
                    )
                    self.hass.config_entries.async_update_entry(
                        self.entry, data=new_entry_data
                    )

                if self.consecutive_failures > 0:
                    _LOGGER.info(
                        "%s: Communication restored after %d failures.",
                        self.entry.title,
                        self.consecutive_failures,
                    )
                    ir.async_delete_issue(
                        self.hass,
                        "huawei_router_5g",
                        f"conn_error_{self.entry.entry_id}",
                    )

                self.last_update_success_time = dt_util.now()
                self.consecutive_failures = 0

                # SMS Event Logic
                if "sms_list" in data:
                    _LOGGER.debug(
                        "%s: Raw SMS list: %s", self.entry.title, data["sms_list"]
                    )
                self._check_new_sms(data)

                # --- Uptime reboot-detection latches ---
                # Each counter is compared against its last-seen value. A drop of
                # more than UPTIME_REBOOT_MARGIN seconds is treated as a genuine
                # reset; the frozen timestamp is recomputed once and then held.
                # Bad or missing readings are ignored; the cached value is kept.
                entry_data_updates: dict[str, Any] = {}

                dev_info = data.get("device_information") or {}
                traffic = data.get("traffic_statistics") or {}

                # 1. System uptime → system boot timestamp
                sys_sec: int | None = None
                with contextlib.suppress(ValueError, TypeError):
                    if (raw := dev_info.get("uptime")) is not None:
                        sys_sec = int(float(raw))
                if sys_sec is None or sys_sec < 0:
                    data["system_boot_time"] = self._system_boot_time
                else:
                    if self._system_boot_time is None or (
                        self._last_system_uptime is not None
                        and sys_sec < self._last_system_uptime - UPTIME_REBOOT_MARGIN
                    ):
                        t = dt_util.now() - timedelta(seconds=sys_sec)
                        self._system_boot_time = t.replace(microsecond=0)
                        entry_data_updates["system_boot_time"] = (
                            self._system_boot_time.isoformat()
                        )
                        entry_data_updates["last_system_uptime"] = sys_sec
                        _LOGGER.debug(
                            "%s: System boot time latched: %s",
                            self.entry.title,
                            self._system_boot_time,
                        )
                    self._last_system_uptime = sys_sec
                    data["system_boot_time"] = self._system_boot_time

                # 2. Current connection time → connection start timestamp
                conn_sec: int | None = None
                with contextlib.suppress(ValueError, TypeError):
                    if (raw := traffic.get("CurrentConnectTime")) is not None:
                        conn_sec = int(float(raw))
                if conn_sec is None or conn_sec < 0:
                    data["conn_start_time"] = self._conn_start_time
                else:
                    if self._conn_start_time is None or (
                        self._last_conn_uptime is not None
                        and conn_sec < self._last_conn_uptime - UPTIME_REBOOT_MARGIN
                    ):
                        t = dt_util.now() - timedelta(seconds=conn_sec)
                        self._conn_start_time = t.replace(microsecond=0)
                        entry_data_updates["conn_start_time"] = (
                            self._conn_start_time.isoformat()
                        )
                        entry_data_updates["last_conn_uptime"] = conn_sec
                        _LOGGER.debug(
                            "%s: Connection start time latched: %s",
                            self.entry.title,
                            self._conn_start_time,
                        )
                    self._last_conn_uptime = conn_sec
                    data["conn_start_time"] = self._conn_start_time

                # 3. Total connection time → total connection origin timestamp
                total_sec: int | None = None
                with contextlib.suppress(ValueError, TypeError):
                    if (raw := traffic.get("TotalConnectTime")) is not None:
                        total_sec = int(float(raw))
                if total_sec is None or total_sec < 0:
                    data["total_conn_start_time"] = self._total_conn_start_time
                else:
                    if self._total_conn_start_time is None or (
                        self._last_total_conn_time is not None
                        and total_sec
                        < self._last_total_conn_time - UPTIME_REBOOT_MARGIN
                    ):
                        t = dt_util.now() - timedelta(seconds=total_sec)
                        self._total_conn_start_time = t.replace(microsecond=0)
                        entry_data_updates["total_conn_start_time"] = (
                            self._total_conn_start_time.isoformat()
                        )
                        entry_data_updates["last_total_conn_time"] = total_sec
                        _LOGGER.debug(
                            "%s: Total connection start time latched: %s",
                            self.entry.title,
                            self._total_conn_start_time,
                        )
                    self._last_total_conn_time = total_sec
                    data["total_conn_start_time"] = self._total_conn_start_time

                if entry_data_updates:
                    self.hass.config_entries.async_update_entry(
                        self.entry, data={**self.entry.data, **entry_data_updates}
                    )

                return data

        except (TimeoutError, HuaweiAuthError) as err:
            self.consecutive_failures += 1
            if self.data is not None and self.consecutive_failures <= 3:
                _LOGGER.warning(
                    "%s: Fetch failed due to %s (failure %d/3), "
                    "holding last known values.",
                    self.entry.title,
                    "session timeout"
                    if isinstance(err, HuaweiAuthError)
                    else "timeout",
                    self.consecutive_failures,
                )
                return self.data

            if isinstance(err, HuaweiAuthError):
                ir.async_create_issue(
                    self.hass,
                    "huawei_router_5g",
                    f"auth_failed_{self.entry.entry_id}",
                    is_fixable=True,
                    is_persistent=True,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="auth_failed",
                    translation_placeholders={"entry_title": self.entry.title},
                    data={"entry_id": self.entry.entry_id},
                )
                raise ConfigEntryAuthFailed("Authentication failed") from err

            error_msg = "API request timed out"
            _LOGGER.exception("%s: %s", self.entry.title, error_msg)
            ir.async_create_issue(
                self.hass,
                "huawei_router_5g",
                f"conn_error_{self.entry.entry_id}",
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="conn_error",
                translation_placeholders={"entry_title": self.entry.title},
            )
            raise UpdateFailed(error_msg) from err

        except Exception as err:
            self.consecutive_failures += 1
            if self.data is not None and self.consecutive_failures <= 3:
                _LOGGER.warning(
                    "%s: Fetch failed (failure %d/3), holding last known values: %s",
                    self.entry.title,
                    self.consecutive_failures,
                    err,
                )
                return self.data

            if is_paused:
                _LOGGER.warning(
                    "%s: Initial fetch failed while paused. Starting with empty data.",
                    self.entry.title,
                )
                return {}

            _LOGGER.exception(
                "%s: Connection lost. Marking entities unavailable.", self.entry.title
            )
            raise UpdateFailed(f"Communication error: {err}") from err

    def _check_new_sms(self, data: dict[str, Any]) -> None:
        """Check for new SMS messages and fire events."""
        sms_list = parse_sms_list(data.get("sms_list"))
        if not sms_list:
            return

        # Sort by date ascending (oldest first) to ensure events fire in order
        sms_list.sort(key=lambda x: x["date"])

        # On first run, just set the baseline timestamp and hashes
        if self.last_sms_timestamp is None:
            self.last_sms_timestamp = sms_list[-1]["date"]
            self.fired_sms_hashes = {
                f"{msg['index']}_{msg['date']}"
                for msg in sms_list
                if msg["date"] == self.last_sms_timestamp
            }
            _LOGGER.debug(
                "%s: SMS tracking baseline established at %s",
                self.entry.title,
                self.last_sms_timestamp,
            )
            return

        new_messages = []
        for msg in sms_list:
            msg_hash = f"{msg['index']}_{msg['date']}"
            if msg["date"] > self.last_sms_timestamp or (
                msg["date"] == self.last_sms_timestamp
                and msg_hash not in self.fired_sms_hashes
            ):
                new_messages.append(msg)

        for msg in new_messages:
            _LOGGER.info("%s: New SMS from %s", self.entry.title, msg["phone"])
            self.hass.bus.async_fire(
                "huawei_router_5g_sms_received",
                {
                    "entry_id": self.entry.entry_id,
                    "phone": msg["phone"],
                    "content": msg["content"],
                    "date": msg["date"],
                    "index": msg["index"],
                },
            )

            # Update tracking state
            msg_hash = f"{msg['index']}_{msg['date']}"
            if msg["date"] > self.last_sms_timestamp:
                self.last_sms_timestamp = msg["date"]
                self.fired_sms_hashes = {msg_hash}
            else:
                self.fired_sms_hashes.add(msg_hash)
