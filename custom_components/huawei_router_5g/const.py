"""Constants for the Huawei Router 5G Monitor integration."""

DOMAIN = "huawei_router_5g"

DEFAULT_NAME = "Huawei 5G"
CONF_NAME = "name"

NAME = "Huawei Router 5G Monitor"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 180
CONF_STOP_POLLING = "stop_polling"
FETCH_TIMEOUT = 30

# Repair issues this integration can raise. The registry keys on
# `(domain, issue_id)`, so each id is suffixed with the entry id — otherwise
# two routers share one slot and the healthy one's next successful poll deletes
# the failing one's repair.
#
# These names are also the `translation_key`s, which stay bare. **Never rename
# one**: `ir.async_delete_issue` looks up by id, so renaming while a repair is
# live orphans it permanently with no UI path to clear it.
REPAIR_AUTH_FAILED = "auth_failed"
REPAIR_CONN_ERROR = "conn_error"
REPAIR_NAMES: tuple[str, ...] = (REPAIR_AUTH_FAILED, REPAIR_CONN_ERROR)
