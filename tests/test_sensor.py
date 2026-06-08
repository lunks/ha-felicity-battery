"""Tests for the Felicity Battery sensor platform."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from custom_components.felicity_battery.sensor import (
    _capacity_wh,
    _cell_voltage_delta,
    _cell_voltages,
    _parse_timestamp,
    _safe_float,
)


async def test_sensor_states(
    hass: HomeAssistant,
    mock_fsolar: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    freezer,
) -> None:
    """Snapshot the created sensor entities and their states."""
    freezer.move_to("2026-06-08 12:00:00+00:00")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    sensor_entries = sorted(
        (e for e in entries if e.domain == "sensor"), key=lambda e: e.entity_id
    )
    assert sensor_entries

    for entry in sensor_entries:
        state = hass.states.get(entry.entity_id)
        assert state == snapshot(name=entry.entity_id)


async def test_sensor_names_from_translation_keys(
    hass: HomeAssistant,
    mock_fsolar: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Sensor names resolve from translation keys, not hard-coded names."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.garage_battery_state_of_charge")
    assert state is not None
    assert state.attributes["friendly_name"] == "Garage Battery State of Charge"


def test_safe_float() -> None:
    """_safe_float coerces or returns None."""
    assert _safe_float("3.5") == 3.5
    assert _safe_float(7) == 7.0
    assert _safe_float(None) is None
    assert _safe_float("nan-ish") is None


def test_cell_voltages_padding() -> None:
    """Padding values (32767) become None and mV converts to V."""
    data = {"bmsVoltageList": [3201, 3202, 32767, 3200, 3199, 3204, 3200, 3201]}
    volts = _cell_voltages(data)
    assert len(volts) == 8
    assert volts[0] == 3.201
    assert volts[2] is None


def test_cell_voltages_short_list_pads_none() -> None:
    """A short list is padded with None up to the real cell count."""
    volts = _cell_voltages({"bmsVoltageList": [3201, 3202]})
    assert len(volts) == 8
    assert volts[0] == 3.201
    assert volts[2] is None


def test_cell_voltage_delta() -> None:
    """Delta is max minus min of valid cells."""
    data = {"bmsVoltageList": [3200, 3210, 32767, 3190]}
    assert _cell_voltage_delta(data) == pytest.approx(0.02)


def test_cell_voltage_delta_no_data() -> None:
    """No valid cells yields None."""
    assert _cell_voltage_delta({"bmsVoltageList": []}) is None


def test_capacity_wh() -> None:
    """Capacity is Ah * V."""
    assert _capacity_wh({"battCapacity": 100.0, "battVolt": 51.2}) == pytest.approx(
        5120.0
    )
    assert _capacity_wh({"battCapacity": None, "battVolt": 51.2}) is None


def test_parse_timestamp_with_offset(freezer) -> None:
    """Timestamp parsing applies the supplied UTC offset."""
    freezer.move_to("2026-06-08 12:00:00")
    data = {"dataTimeStr": "2026-06-08 14:30:00"}
    parsed = _parse_timestamp(data, timedelta(hours=-3))
    assert parsed == datetime(
        2026, 6, 8, 14, 30, 0, tzinfo=timezone(timedelta(hours=-3))
    )


def test_parse_timestamp_default_utc() -> None:
    """Without an offset, the timestamp is UTC."""
    parsed = _parse_timestamp({"dataTimeStr": "2026-06-08 14:30:00"})
    assert parsed == datetime(2026, 6, 8, 14, 30, 0, tzinfo=UTC)


def test_parse_timestamp_bad_value() -> None:
    """Non-string or malformed timestamps return None."""
    assert _parse_timestamp({"dataTimeStr": None}) is None
    assert _parse_timestamp({"dataTimeStr": "not a date"}) is None
    assert _parse_timestamp({}) is None
