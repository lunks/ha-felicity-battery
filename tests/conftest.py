"""Common fixtures for Felicity Battery tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    load_json_object_fixture,
)
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from custom_components.felicity_battery.const import (
    API_BASE_URL,
    CONF_DEVICE_SN,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DOMAIN,
    ENDPOINT_DEVICE_LIST,
    ENDPOINT_DEVICE_SNAPSHOT,
    LOGIN_URL,
)

LOGIN_ENDPOINT = f"{API_BASE_URL}{LOGIN_URL}"
DEVICE_LIST_ENDPOINT = f"{API_BASE_URL}{ENDPOINT_DEVICE_LIST}"
SNAPSHOT_ENDPOINT = f"{API_BASE_URL}{ENDPOINT_DEVICE_SNAPSHOT}"
PLANT_LIST_ENDPOINT = f"{API_BASE_URL}/app/plant/list_plant"

DEVICE_SN = "SN123456"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Use the Home Assistant snapshot extension.

    This pins the serializer to HA's ``StateSnapshot`` format so snapshots are
    deterministic and portable across machines (the default syrupy serializer
    bakes in the local timezone and varies by plugin load order).
    """
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture(autouse=True)
def _bypass_ssl_context() -> Generator[None]:
    """Avoid loading the bundled cert from disk during tests."""
    import ssl

    with patch(
        "custom_components.felicity_battery.ssl_context.get_ssl_context",
        return_value=ssl.create_default_context(),
    ):
        yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry for the Felicity Battery integration."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Felicity Battery",
        unique_id=DEVICE_SN,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "hunter2",
            CONF_DEVICE_SN: DEVICE_SN,
            CONF_SCAN_INTERVAL: 60,
        },
    )


def register_fsolar(
    aioclient_mock: AiohttpClientMocker,
    *,
    login: dict | None = None,
    device_list: str = "device_list.json",
    snapshot: str = "snapshot.json",
    plant_list: str = "plant_list.json",
) -> None:
    """Register the standard FSolar endpoints on the aiohttp mock."""
    aioclient_mock.post(
        LOGIN_ENDPOINT,
        json=login or load_json_object_fixture("login.json"),
    )
    aioclient_mock.post(
        DEVICE_LIST_ENDPOINT,
        json=load_json_object_fixture(device_list),
    )
    aioclient_mock.post(
        PLANT_LIST_ENDPOINT,
        json=load_json_object_fixture(plant_list),
    )
    aioclient_mock.post(
        SNAPSHOT_ENDPOINT,
        json=load_json_object_fixture(snapshot),
    )


@pytest.fixture
def mock_fsolar(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Register all FSolar endpoints with happy-path fixtures."""
    register_fsolar(aioclient_mock)
    return aioclient_mock
