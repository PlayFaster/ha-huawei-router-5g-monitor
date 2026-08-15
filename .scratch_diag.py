"""Owner-authorised: read onekey_diag with the data session up, then down.

Settles what `connection_status` means. Restores the connection either way.
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, "/workspaces/ha-huawei-router-5g-monitor")
from custom_components.huawei_router_5g.api import _normalize_router_url
from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection

o = next(
    e["options"]
    for e in json.loads(
        pathlib.Path("/config/.storage/core.config_entries").read_text()
    )["data"]["entries"]
    if e["domain"] == "huawei_router_5g"
)
c = Client(
    Connection(
        _normalize_router_url(o["host"]),
        username=(o.get("username") or None),
        password=o["password"],
        timeout=25,
    )
)


def snapshot(label: str) -> None:
    diag = c.monitoring.onekey_diag()
    conn = c.monitoring.status().get("ConnectionStatus")
    print(f"\n--- {label} ---")
    print(f"  monitoring_status.ConnectionStatus = {conn!r}")
    for k, v in diag.items():
        print(f"    {k:22} = {v!r}")


try:
    snapshot("connection UP")

    print("\n>>> disconnecting (dialup/dial Action 0)")
    c.wlan._session.post_set("dialup/dial", {"Action": 0})
    time.sleep(4)
    snapshot("connection DOWN")

finally:
    print("\n>>> reconnecting (dialup/dial Action 1)")
    try:
        c.dial_up.dial()
    except Exception as err:
        print(f"    dial() failed: {err}; trying mobile data switch")
        c.dial_up.set_mobile_dataswitch(1)
    time.sleep(12)
    snapshot("connection RESTORED")
