"""Owner-authorised: hold the data session down long enough to read onekey_diag.

The reconnect window was under four seconds because the router auto-redials, so
this uses the mobile-data switch, which stays where it is put. Restored in a
`finally`, and again via a second path if the first restore fails.
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

BASE = None


def snapshot(label: str) -> dict:
    diag = c.monitoring.onekey_diag()
    st = c.monitoring.status()
    print(f"\n--- {label} ---")
    print(
        f"  ConnectionStatus={st.get('ConnectionStatus')!r}  "
        f"dataswitch={c.dial_up.mobile_dataswitch().get('dataswitch')!r}"
    )
    changed = (
        {k: v for k, v in diag.items() if BASE and BASE.get(k) != v} if BASE else {}
    )
    for k, v in diag.items():
        mark = "  <== CHANGED" if k in changed else ""
        print(f"    {k:22} = {v!r}{mark}")
    return diag


try:
    BASE = snapshot("mobile data ON")
    print("\n>>> mobile data OFF")
    c.dial_up.set_mobile_dataswitch(0)
    time.sleep(12)
    snapshot("mobile data OFF")
finally:
    print("\n>>> restoring mobile data ON")
    try:
        c.dial_up.set_mobile_dataswitch(1)
    except Exception as err:
        print(f"    FIRST RESTORE FAILED: {err}")
        c.dial_up.set_mobile_dataswitch(1)
    time.sleep(15)
    snapshot("restored")
