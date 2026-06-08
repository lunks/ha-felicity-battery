"""Tests for the Felicity Battery config flow."""

from __future__ import annotations

import aiohttp
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.felicity_battery.const import (
    CONF_DEVICE_SN,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)

from .conftest import (
    DEVICE_LIST_ENDPOINT,
    DEVICE_SN,
    LOGIN_ENDPOINT,
    register_fsolar,
)

USER_INPUT = {
    CONF_USERNAME: "user@example.com",
    CONF_PASSWORD: "hunter2",
    CONF_SCAN_INTERVAL: 60,
}


async def test_user_form_shows(hass: HomeAssistant) -> None:
    """The initial user step should present a form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]


async def test_user_flow_single_device(
    hass: HomeAssistant, mock_fsolar: AiohttpClientMocker
) -> None:
    """A single device is auto-selected and an entry is created."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DEVICE_SN
    assert result["data"][CONF_DEVICE_SN] == DEVICE_SN
    assert result["data"][CONF_USERNAME] == "user@example.com"
    assert "Garage Battery" in result["title"]


async def test_user_flow_multi_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Multiple devices require a selection step."""
    register_fsolar(aioclient_mock, device_list="device_list_multi.json")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_SN: "SN999999"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "SN999999"
    assert "Shed Battery" in result["title"]


async def test_user_flow_invalid_auth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A login failure surfaces as invalid_auth."""
    aioclient_mock.post(
        LOGIN_ENDPOINT, json={"code": 401, "message": "bad credentials"}
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A connection error surfaces as cannot_connect."""
    aioclient_mock.post(LOGIN_ENDPOINT, exc=aiohttp.ClientError("boom"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_unknown_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An unexpected error surfaces as unknown."""
    aioclient_mock.post(LOGIN_ENDPOINT, exc=RuntimeError("kaboom"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_no_devices(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An empty device list surfaces as no_devices."""
    aioclient_mock.post(LOGIN_ENDPOINT, json={"code": 200, "data": {"token": "t"}})
    aioclient_mock.post(
        DEVICE_LIST_ENDPOINT, json={"code": 200, "data": {"dataList": []}}
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_devices"}


async def test_user_flow_duplicate_aborts(
    hass: HomeAssistant,
    mock_fsolar: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Configuring an already-configured device aborts."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
