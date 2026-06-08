"""Tests for the Felicity Battery coordinator."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    load_json_object_fixture,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.felicity_battery.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
)
from custom_components.felicity_battery.coordinator import FelicityBatteryCoordinator

from .conftest import (
    DEVICE_SN,
    LOGIN_ENDPOINT,
    SNAPSHOT_ENDPOINT,
)


def _build_coordinator(
    hass: HomeAssistant, entry: MockConfigEntry
) -> FelicityBatteryCoordinator:
    """Create a coordinator wired to the mock entry."""
    return FelicityBatteryCoordinator(
        hass,
        entry=entry,
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        device_sn=DEVICE_SN,
        scan_interval=60,
    )


async def test_update_parses_snapshot(
    hass: HomeAssistant,
    mock_fsolar: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A successful update returns the parsed snapshot data."""
    mock_config_entry.add_to_hass(hass)
    coordinator = _build_coordinator(hass, mock_config_entry)

    data = await coordinator._async_update_data()
    assert data["battSoc"] == 87
    assert data["battVolt"] == 51.2


async def test_update_api_error_raises_update_failed(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A non-200 API code raises UpdateFailed."""
    aioclient_mock.post(LOGIN_ENDPOINT, json=load_json_object_fixture("login.json"))
    aioclient_mock.post(SNAPSHOT_ENDPOINT, json={"code": 500, "msg": "server error"})
    mock_config_entry.add_to_hass(hass)
    coordinator = _build_coordinator(hass, mock_config_entry)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_update_connection_error_raises_update_failed(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A transport error raises UpdateFailed."""
    aioclient_mock.post(LOGIN_ENDPOINT, json=load_json_object_fixture("login.json"))
    aioclient_mock.post(SNAPSHOT_ENDPOINT, exc=aiohttp.ClientError("boom"))
    mock_config_entry.add_to_hass(hass)
    coordinator = _build_coordinator(hass, mock_config_entry)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_update_expired_token_reauths_then_succeeds(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A 401 on snapshot triggers a re-login and a successful retry."""
    login_calls = {"n": 0}
    snapshot_calls = {"n": 0}

    async def login_side_effect(method, url, data) -> AiohttpClientMockResponse:
        login_calls["n"] += 1
        return AiohttpClientMockResponse(
            method, URL(url), json=load_json_object_fixture("login.json")
        )

    async def snapshot_side_effect(method, url, data) -> AiohttpClientMockResponse:
        snapshot_calls["n"] += 1
        if snapshot_calls["n"] == 1:
            return AiohttpClientMockResponse(
                method, URL(url), status=401, json={"code": 401, "msg": "expired"}
            )
        return AiohttpClientMockResponse(
            method, URL(url), json=load_json_object_fixture("snapshot.json")
        )

    aioclient_mock.post(LOGIN_ENDPOINT, side_effect=login_side_effect)
    aioclient_mock.post(SNAPSHOT_ENDPOINT, side_effect=snapshot_side_effect)
    mock_config_entry.add_to_hass(hass)
    coordinator = _build_coordinator(hass, mock_config_entry)

    data = await coordinator._async_update_data()
    assert data["battSoc"] == 87
    # Initial login + re-login after the 401.
    assert login_calls["n"] == 2
    # First snapshot (401) + retry after re-login.
    assert snapshot_calls["n"] == 2


async def test_update_persistent_auth_failure_raises(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A token still rejected after re-login raises ConfigEntryAuthFailed."""

    async def snapshot_side_effect(method, url, data) -> AiohttpClientMockResponse:
        # First call: HTTP 401 -> triggers re-login.
        # Retry: HTTP 200 but body still says code 401 -> auth failed.
        if snapshot_side_effect.calls == 0:
            snapshot_side_effect.calls += 1
            return AiohttpClientMockResponse(
                method, URL(url), status=401, json={"code": 401, "msg": "expired"}
            )
        return AiohttpClientMockResponse(
            method, URL(url), status=200, json={"code": 401, "msg": "still bad"}
        )

    snapshot_side_effect.calls = 0

    aioclient_mock.post(LOGIN_ENDPOINT, json=load_json_object_fixture("login.json"))
    aioclient_mock.post(SNAPSHOT_ENDPOINT, side_effect=snapshot_side_effect)
    mock_config_entry.add_to_hass(hass)
    coordinator = _build_coordinator(hass, mock_config_entry)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_fetch_device_info_parses_metadata(
    hass: HomeAssistant,
    mock_fsolar: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """fetch_device_info populates model, alias and timezone."""
    mock_config_entry.add_to_hass(hass)
    coordinator = _build_coordinator(hass, mock_config_entry)

    await coordinator.fetch_device_info()
    assert coordinator.device_model == "FLA24100-EU"
    assert coordinator.device_alias == "Garage Battery"
    # UTC-03:00 from the plant fixture.
    assert coordinator.device_timezone.total_seconds() == -3 * 3600


@pytest.mark.parametrize(
    ("tz_str", "expected_hours"),
    [
        ("UTC-03:00", -3.0),
        ("UTC+05:30", 5.5),
        ("UTC+00:00", 0.0),
        ("garbage", 0.0),
        ("", 0.0),
    ],
)
def test_parse_utc_offset(tz_str: str, expected_hours: float) -> None:
    """The UTC-offset parser handles signs, minutes and bad input."""
    offset = FelicityBatteryCoordinator._parse_utc_offset(tz_str)
    assert offset.total_seconds() == expected_hours * 3600
