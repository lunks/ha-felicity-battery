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

REAUTH_INPUT = {
    CONF_USERNAME: "new@example.com",
    CONF_PASSWORD: "newpass",
}
RECONFIGURE_INPUT = {
    CONF_USERNAME: "new@example.com",
    CONF_PASSWORD: "newpass",
    CONF_SCAN_INTERVAL: 30,
}

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


async def test_reauth_success(
    hass: HomeAssistant,
    mock_fsolar: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reauth re-logs-in and updates the stored credentials."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], REAUTH_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_USERNAME] == "new@example.com"
    assert mock_config_entry.data[CONF_PASSWORD] == "newpass"
    # The device SN is unchanged.
    assert mock_config_entry.data[CONF_DEVICE_SN] == DEVICE_SN


async def test_reauth_invalid_auth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A failed reauth login shows the form again with an error."""
    aioclient_mock.post(LOGIN_ENDPOINT, json={"code": 401, "message": "nope"})
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], REAUTH_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_unique_id_mismatch(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reauth that resolves a different device aborts with a mismatch."""
    register_fsolar(aioclient_mock, device_list="device_list_other.json")
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], REAUTH_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"


async def test_reconfigure_success(
    hass: HomeAssistant,
    mock_fsolar: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reconfigure updates credentials and scan interval."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], RECONFIGURE_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_USERNAME] == "new@example.com"
    assert mock_config_entry.data[CONF_SCAN_INTERVAL] == 30


async def test_reconfigure_unique_id_mismatch(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reconfigure resolving a different device aborts with a mismatch."""
    register_fsolar(aioclient_mock, device_list="device_list_other.json")
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], RECONFIGURE_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
