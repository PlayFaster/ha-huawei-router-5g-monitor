"""Tests for the Huawei Router 5G config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import AbortFlow, FlowResultType

from custom_components.huawei_router_5g.api import HuaweiAuthError, HuaweiConnectionError
from custom_components.huawei_router_5g.config_flow import (
    HuaweiRouter5GConfigFlow,
    HuaweiRouter5GOptionsFlow,
    _validate_credentials,
)
from custom_components.huawei_router_5g.const import DEFAULT_NAME, DOMAIN


# ---------------------------------------------------------------------------
# _validate_credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_credentials_success():
    """Test that _validate_credentials logs in, fetches data, and returns device info."""
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
    assert result["mac"] == "DC:71:96:11:22:33"
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
