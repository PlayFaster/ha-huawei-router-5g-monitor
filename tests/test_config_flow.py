"""Tests for the Huawei Router 5G config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import AbortFlow, FlowResultType

from custom_components.huawei_router_5g.api import (
    HuaweiAuthError,
    HuaweiConnectionError,
)
from custom_components.huawei_router_5g.config_flow import (
    HuaweiRouter5GConfigFlow,
    HuaweiRouter5GOptionsFlow,
    _clean_host,
    _merge_credentials,
    _validate_credentials,
)

# ---------------------------------------------------------------------------
# _clean_host / _merge_credentials
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("192.168.8.1", "192.168.8.1"),
        ("  192.168.8.1  ", "192.168.8.1"),
        ("http://192.168.8.1", "192.168.8.1"),
        ("https://192.168.8.1/", "192.168.8.1"),
        ("http://192.168.8.1///", "192.168.8.1"),
    ],
)
def test_clean_host(raw, expected):
    """Test that host entries are normalised to a bare host."""
    assert _clean_host(raw) == expected


def test_merge_credentials_blank_password_uses_stored():
    """A blank password falls back to the stored value."""
    merged = _merge_credentials(
        {CONF_HOST: "192.168.8.1", CONF_PASSWORD: ""},
        {CONF_HOST: "192.168.8.1", CONF_PASSWORD: "stored"},
    )
    assert merged[CONF_PASSWORD] == "stored"


def test_merge_credentials_new_password_overrides_stored():
    """A supplied password replaces the stored value."""
    merged = _merge_credentials(
        {CONF_HOST: "192.168.8.1", CONF_PASSWORD: "new"},
        {CONF_HOST: "192.168.8.1", CONF_PASSWORD: "stored"},
    )
    assert merged[CONF_PASSWORD] == "new"


# ---------------------------------------------------------------------------
# _validate_credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_credentials_success():
    """Test that _validate_credentials returns device info on success."""
    with patch(
        "custom_components.huawei_router_5g.config_flow.HuaweiRouter5GAPI"
    ) as mock_api_class:
        mock_api = mock_api_class.return_value
        mock_api.login = AsyncMock()
        mock_api.get_data = AsyncMock(
            return_value={
                "device_information": {
                    "DeviceName": "B535s-232",
                    "SoftwareVersion": "11.0.1.1",
                    "HardwareVersion": "Ver.A",
                    "MacAddress1": "DC:71:96:11:22:33",
                }
            }
        )
        mock_api.logout = AsyncMock()

        user_input = {
            CONF_HOST: "http://192.168.8.1",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
        }
        result = await _validate_credentials(user_input)

    assert result["model"] == "B535s-232"
    assert result["sw_version"] == "11.0.1.1"
    assert result["hw_version"] == "Ver.A"
    # MAC is normalized to lowercase without colons
    assert result["mac"] == "dc7196112233"
    mock_api.login.assert_called_once()
    mock_api.logout.assert_called_once()


@pytest.mark.asyncio
async def test_validate_credentials_calls_logout_on_error():
    """Test that logout is called even when get_data raises."""
    with patch(
        "custom_components.huawei_router_5g.config_flow.HuaweiRouter5GAPI"
    ) as mock_api_class:
        mock_api = mock_api_class.return_value
        mock_api.login = AsyncMock()
        mock_api.get_data = AsyncMock(side_effect=HuaweiConnectionError("fail"))
        mock_api.logout = AsyncMock()

        with pytest.raises(HuaweiConnectionError):
            await _validate_credentials(
                {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}
            )

        mock_api.logout.assert_called_once()


# ---------------------------------------------------------------------------
# HuaweiRouter5GConfigFlow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_flow_user_step_success():
    """Test successful config flow user step creates an entry."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = None

    user_input = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "password",
    }
    fake_info = {
        "model": "B535s-232",
        "sw_version": "11.0.1.1",
        "hw_version": "Ver.A",
        "mac": "DC:71:96:11:22:33",
    }

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        return_value=fake_info,
    ):
        result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == fake_info
    assert result["options"] == user_input


@pytest.mark.asyncio
async def test_config_flow_user_step_shows_form_when_no_input():
    """Test that no user_input returns the form."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}

    result = await flow.async_step_user(None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_config_flow_user_step_invalid_auth():
    """Test that HuaweiAuthError maps to invalid_auth error."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=HuaweiAuthError,
    ):
        result = await flow.async_step_user(
            {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "wrong"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_config_flow_user_step_cannot_connect():
    """Test that HuaweiConnectionError maps to cannot_connect error."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=HuaweiConnectionError,
    ):
        result = await flow.async_step_user(
            {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}
        )

    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_config_flow_user_step_unknown_error():
    """Test that an unexpected exception maps to unknown error."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=Exception("Unexpected"),
    ):
        result = await flow.async_step_user(
            {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}
        )

    assert result["errors"] == {"base": "unknown"}


@pytest.mark.asyncio
async def test_config_flow_user_step_abort_flow_reraises():
    """Test that AbortFlow is re-raised (not swallowed)."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}

    with (
        patch(
            "custom_components.huawei_router_5g.config_flow._validate_credentials",
            side_effect=AbortFlow("already_configured"),
        ),
        pytest.raises(AbortFlow),
    ):
        await flow.async_step_user(
            {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}
        )


def test_async_get_options_flow():
    """Test that async_get_options_flow returns a HuaweiRouter5GOptionsFlow."""
    flow = HuaweiRouter5GConfigFlow()
    entry = MagicMock()
    options_flow = flow.async_get_options_flow(entry)
    assert isinstance(options_flow, HuaweiRouter5GOptionsFlow)


# ---------------------------------------------------------------------------
# HuaweiRouter5GOptionsFlow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_options_flow_init_success():
    """Test successful options flow init step saves new credentials."""
    entry = MagicMock()
    entry.title = "My Huawei Router"
    entry.options = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "old_password",
    }

    flow = HuaweiRouter5GOptionsFlow(entry)
    flow.hass = MagicMock()

    user_input = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "new_password",
    }

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        return_value={},
    ):
        result = await flow.async_step_init(user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PASSWORD] == "new_password"


@pytest.mark.asyncio
async def test_options_flow_init_shows_form_when_no_input():
    """Test that no user_input returns the form."""
    entry = MagicMock()
    entry.options = {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}

    flow = HuaweiRouter5GOptionsFlow(entry)
    flow.hass = MagicMock()

    result = await flow.async_step_init(None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"


@pytest.mark.asyncio
async def test_options_flow_invalid_auth():
    """Test that HuaweiAuthError maps to invalid_auth error."""
    entry = MagicMock()
    entry.options = {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}
    entry.title = "My Huawei Router"

    flow = HuaweiRouter5GOptionsFlow(entry)
    flow.hass = MagicMock()

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=HuaweiAuthError,
    ):
        result = await flow.async_step_init(
            {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "wrong"}
        )

    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_options_flow_cannot_connect():
    """Test that HuaweiConnectionError maps to cannot_connect error."""
    entry = MagicMock()
    entry.options = {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}
    entry.title = "My Huawei Router"

    flow = HuaweiRouter5GOptionsFlow(entry)
    flow.hass = MagicMock()

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=HuaweiConnectionError,
    ):
        result = await flow.async_step_init(
            {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}
        )

    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_options_flow_unknown_error():
    """Test that an unexpected exception maps to unknown error."""
    entry = MagicMock()
    entry.options = {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}
    entry.title = "My Huawei Router"

    flow = HuaweiRouter5GOptionsFlow(entry)
    flow.hass = MagicMock()

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=Exception("Surprise"),
    ):
        result = await flow.async_step_init(
            {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}
        )

    assert result["errors"] == {"base": "unknown"}


@pytest.mark.asyncio
async def test_options_flow_title_update():
    """Test that changing the name triggers an entry title update."""
    entry = MagicMock()
    entry.title = "Old Title"
    entry.options = {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}

    flow = HuaweiRouter5GOptionsFlow(entry)
    flow.hass = MagicMock()

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        return_value={},
    ):
        await flow.async_step_init(
            {
                "name": "New Title",
                CONF_HOST: "http://192.168.8.1",
                CONF_PASSWORD: "p",
            }
        )

    flow.hass.config_entries.async_update_entry.assert_called_once()


@pytest.mark.asyncio
async def test_config_flow_user_step_abort_flow():
    """Test that AbortFlow is re-raised (not swallowed)."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}

    with (
        patch(
            "custom_components.huawei_router_5g.config_flow._validate_credentials",
            side_effect=AbortFlow("already_configured"),
        ),
        pytest.raises(AbortFlow),
    ):
        await flow.async_step_user(
            {CONF_HOST: "http://192.168.8.1", CONF_PASSWORD: "p"}
        )


@pytest.mark.asyncio
async def test_config_flow_reauth_entry_not_found():
    """Test async_step_reauth when entry not found."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"entry_id": "missing_entry"}
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=None)

    result = await flow.async_step_reauth(None)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "entry_not_found"


@pytest.mark.asyncio
async def test_config_flow_reauth_entry_found():
    """Test async_step_reauth when entry is found (proceeds to reauth_confirm)."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    entry = MagicMock()
    entry.options = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "old",
    }
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    flow.context = {"entry_id": "valid_entry"}

    result = await flow.async_step_reauth(None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


@pytest.mark.asyncio
async def test_config_flow_reauth_confirm_invalid_auth():
    """Test async_step_reauth_confirm with invalid auth."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    entry = MagicMock()
    entry.options = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "old",
    }
    flow._reauth_entry = entry
    flow.context = {"entry_id": "test_entry_id"}

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=HuaweiAuthError,
    ):
        result = await flow.async_step_reauth_confirm(
            {
                CONF_HOST: "http://192.168.8.1",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "wrong",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_config_flow_reauth_confirm_cannot_connect():
    """Test async_step_reauth_confirm with cannot connect."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    entry = MagicMock()
    entry.options = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "old",
    }
    flow._reauth_entry = entry
    flow.context = {"entry_id": "test_entry_id"}

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=HuaweiConnectionError,
    ):
        result = await flow.async_step_reauth_confirm(
            {
                CONF_HOST: "http://192.168.8.1",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "wrong",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_config_flow_reauth_confirm_unknown_error():
    """Test async_step_reauth_confirm with unknown error."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    entry = MagicMock()
    entry.options = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "old",
    }
    flow._reauth_entry = entry
    flow.context = {"entry_id": "test_entry_id"}

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=Exception("Unexpected"),
    ):
        result = await flow.async_step_reauth_confirm(
            {
                CONF_HOST: "http://192.168.8.1",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "wrong",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


@pytest.mark.asyncio
async def test_config_flow_reconfigure_invalid_auth():
    """Test async_step_reconfigure with invalid auth."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"entry_id": "test_entry_id"}
    entry = MagicMock()
    entry.options = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "old",
    }
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=HuaweiAuthError,
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_HOST: "http://192.168.8.1",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "wrong",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_config_flow_reconfigure_cannot_connect():
    """Test async_step_reconfigure with cannot connect."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"entry_id": "test_entry_id"}
    entry = MagicMock()
    entry.options = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "old",
    }
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=HuaweiConnectionError,
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_HOST: "http://192.168.8.1",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "wrong",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_config_flow_reconfigure_unknown_error():
    """Test async_step_reconfigure with unknown error."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"entry_id": "test_entry_id"}
    entry = MagicMock()
    entry.options = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "old",
    }
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        side_effect=Exception("Unexpected"),
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_HOST: "http://192.168.8.1",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "wrong",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


@pytest.mark.asyncio
async def test_config_flow_reauth_confirm_success():
    """Test async_step_reauth_confirm success."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()
    entry = MagicMock()
    entry.options = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "old",
    }
    entry.entry_id = "test_entry_id"
    flow._reauth_entry = entry
    flow.context = {"entry_id": "test_entry_id"}

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        return_value={},
    ):
        result = await flow.async_step_reauth_confirm(
            {
                CONF_HOST: "http://192.168.8.1",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new",
            }
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    flow.hass.config_entries.async_update_entry.assert_called_once()
    flow.hass.config_entries.async_reload.assert_called_once_with("test_entry_id")


@pytest.mark.asyncio
async def test_config_flow_reconfigure_success():
    """Test async_step_reconfigure success."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()
    flow.context = {"entry_id": "test_entry_id"}
    entry = MagicMock()
    entry.options = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "old",
    }
    entry.entry_id = "test_entry_id"
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        return_value={},
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_HOST: "http://192.168.8.1",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new",
            }
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    flow.hass.config_entries.async_update_entry.assert_called_once()
    flow.hass.config_entries.async_reload.assert_called_once_with("test_entry_id")


# ---------------------------------------------------------------------------
# Host normalisation & blank-password retention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_step_strips_url_host():
    """Test that a URL entered as host is normalised before being stored."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = None

    user_input = {
        CONF_HOST: "https://192.168.8.1/",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "password",
    }

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        return_value={"mac": "DC:71:96:11:22:33", "model": "B535s-232"},
    ):
        result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_HOST] == "192.168.8.1"


@pytest.mark.asyncio
async def test_reconfigure_blank_password_keeps_stored():
    """Test that a blank password on reconfigure retains the stored value."""
    flow = HuaweiRouter5GConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()
    flow.context = {"entry_id": "test_entry_id"}
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.options = {
        CONF_HOST: "192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "stored_password",
    }
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    # User leaves the password blank and only changes the host format
    user_input = {
        CONF_HOST: "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "",
    }

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        return_value={},
    ):
        result = await flow.async_step_reconfigure(user_input)

    assert result["type"] == FlowResultType.ABORT
    _, kwargs = flow.hass.config_entries.async_update_entry.call_args
    assert kwargs["options"][CONF_PASSWORD] == "stored_password"
    assert kwargs["options"][CONF_HOST] == "192.168.8.1"


@pytest.mark.asyncio
async def test_options_flow_blank_password_keeps_stored():
    """Test that a blank password on the options flow retains the stored value."""
    entry = MagicMock()
    entry.title = "My Huawei Router"
    entry.options = {
        CONF_HOST: "192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "stored_password",
    }

    flow = HuaweiRouter5GOptionsFlow(entry)
    flow.hass = MagicMock()

    user_input = {
        CONF_HOST: "192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "",
    }

    with patch(
        "custom_components.huawei_router_5g.config_flow._validate_credentials",
        return_value={},
    ):
        result = await flow.async_step_init(user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PASSWORD] == "stored_password"
