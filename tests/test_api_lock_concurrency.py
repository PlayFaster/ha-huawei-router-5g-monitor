"""The API lock serves concurrent calls one at a time.

ZTE technique rows 9 (logins serialized) and 10 (writes and polls take turns)
are answered on Huawei by `_locked`, and until this file no test started two
calls together. Plan `v124_dev1_plan.md` item I5.

Each case starts two tasks at once against the fake router and records the most
library calls running at one time. **The count is taken at the worker-thread
boundary, not inside the fake transport.** `requests_mock` sends every request
under one process-wide lock (`requests_mock/mocker.py`, `_send_lock`), so a
counter inside the transport reads 1 whether or not the API lock holds; measured
2026-10-09 with two separate API objects logging in together. Every library call
`api.py` makes goes through `asyncio.to_thread`, so the count wraps that call:
it holds each one with a blocking sleep in the worker thread and counts with a
thread lock, and two calls running together show as 2.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import threading
import time
from typing import Any
from unittest.mock import patch

import pytest
import requests_mock as requests_mock_module

from custom_components.huawei_router_5g import api as api_module
from custom_components.huawei_router_5g.api import HuaweiRouter5GAPI

from .transport import RouterTransport

ROUTER_URL = "http://192.168.8.1"
HOLD = 0.02


class _Overlap:
    """Counts the library calls running in worker threads at one time."""

    def __init__(self) -> None:
        self.running = 0
        self.most = 0
        self._lock = threading.Lock()
        self._to_thread = asyncio.to_thread

    async def to_thread(self, func: Callable[..., Any], /, *args: Any) -> Any:
        def counted() -> Any:
            with self._lock:
                self.running += 1
                self.most = max(self.most, self.running)
            try:
                time.sleep(HOLD)
                return func(*args)
            finally:
                with self._lock:
                    self.running -= 1

        return await self._to_thread(counted)


@pytest.fixture(name="transport")
def transport_fixture():
    """Serve a working router, with the delete command answered."""
    with requests_mock_module.Mocker() as mocker:
        transport = RouterTransport(mocker)
        transport.payloads["sms/delete-sms"] = "OK"
        yield transport


async def _logged_in() -> HuaweiRouter5GAPI:
    api = HuaweiRouter5GAPI(ROUTER_URL, "admin", "password")
    await api.login()
    return api


async def _most_at_once(*calls: Callable[[], Any]) -> int:
    """Run the calls together and return the most library calls at one time."""
    overlap = _Overlap()
    with patch.object(api_module.asyncio, "to_thread", overlap.to_thread):
        await asyncio.gather(*(call() for call in calls))
    return overlap.most


@pytest.mark.asyncio
@pytest.mark.usefixtures("transport")
async def test_a_poll_and_a_write_take_turns() -> None:
    """A delete started during a poll waits for the poll to finish."""
    api = await _logged_in()
    assert await _most_at_once(api.get_data, lambda: api.delete_sms(1)) == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("transport")
async def test_two_writes_take_turns() -> None:
    """Two deletes started together reach the router one after the other."""
    api = await _logged_in()
    assert (
        await _most_at_once(lambda: api.delete_sms(1), lambda: api.delete_sms(2)) == 1
    )


@pytest.mark.asyncio
async def test_two_logins_take_turns(transport) -> None:
    """Two logins started together after a reset are serialized.

    On ZTE two logins 30 ms apart had one refused, which is what row 9 records.
    """
    api = await _logged_in()
    api._reset_client()
    logins_before = transport.logins
    assert await _most_at_once(api.login, api.login) == 1
    assert transport.logins == logins_before + 2


@pytest.mark.asyncio
async def test_the_count_sees_two_calls_without_the_lock() -> None:
    """The positive control: two unlocked calls do show as 2."""

    async def unlocked() -> None:
        await api_module.asyncio.to_thread(lambda: None)

    assert await _most_at_once(unlocked, unlocked) == 2
