"""Tests for the Felicity Battery binary sensor platform."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from custom_components.felicity_battery.binary_sensor import _is_charging


async def test_binary_sensor_states(
    hass: HomeAssistant,
    mock_fsolar: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    freezer,
) -> None:
    """Snapshot the created binary sensor entities and their states."""
    freezer.move_to("2026-06-08 12:00:00+00:00")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    binary_entries = sorted(
        (e for e in entries if e.domain == "binary_sensor"),
        key=lambda e: e.entity_id,
    )
    assert binary_entries

    for entry in binary_entries:
        state = hass.states.get(entry.entity_id)
        assert state == snapshot(name=entry.entity_id)


def test_is_charging() -> None:
    """Positive current means charging."""
    assert _is_charging({"battCurr": 12.5}) is True
    assert _is_charging({"battCurr": -5.0}) is False
    assert _is_charging({"battCurr": 0}) is False
    assert _is_charging({}) is False
    assert _is_charging({"battCurr": "bad"}) is None
