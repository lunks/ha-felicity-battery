"""Sensor platform for Felicity Battery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import REAL_CELL_COUNT, REAL_TEMP_COUNT
from .coordinator import FelicityBatteryCoordinator
from .entity import FelicityBatteryEntity


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float, returning None if impossible."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _cell_voltages(data: dict[str, Any]) -> list[float | None]:
    """Extract real cell voltages in V from mV list."""
    voltages = data.get("bmsVoltageList", [])
    result: list[float | None] = []
    for i in range(REAL_CELL_COUNT):
        if i >= len(voltages):
            result.append(None)
            continue
        try:
            mv = float(voltages[i])
            if mv >= 32767:
                result.append(None)
            else:
                result.append(round(mv / 1000, 3))
        except (ValueError, TypeError):
            result.append(None)
    return result


def _cell_voltage_delta(data: dict[str, Any]) -> float | None:
    """Return max - min cell voltage."""
    volts = [v for v in _cell_voltages(data) if v is not None]
    if not volts:
        return None
    return round(max(volts) - min(volts), 3)


def _cell_voltage_attrs(data: dict[str, Any]) -> dict[str, Any]:
    """Return individual cell voltages as attributes."""
    volts = _cell_voltages(data)
    attrs: dict[str, Any] = {}
    for i, v in enumerate(volts):
        if v is not None:
            attrs[f"cell_{i + 1}"] = v

    valid = [(i + 1, v) for i, v in enumerate(volts) if v is not None]
    if valid:
        max_cell = max(valid, key=lambda x: x[1])
        min_cell = min(valid, key=lambda x: x[1])
        attrs["max_cell"] = max_cell[1]
        attrs["max_cell_number"] = max_cell[0]
        attrs["min_cell"] = min_cell[1]
        attrs["min_cell_number"] = min_cell[0]

    return attrs


def _cell_temps(data: dict[str, Any]) -> list[float | None]:
    """Extract real cell temperatures."""
    temps = data.get("cellTempList", [])
    result: list[float | None] = []
    for i in range(REAL_TEMP_COUNT):
        if i >= len(temps):
            result.append(None)
            continue
        try:
            val = float(temps[i])
            if val >= 3276.7:
                result.append(None)
            else:
                result.append(val)
        except (ValueError, TypeError):
            result.append(None)
    return result


def _temp_attrs(data: dict[str, Any]) -> dict[str, Any]:
    """Return individual cell temps as attributes."""
    temps = _cell_temps(data)
    attrs: dict[str, Any] = {}
    for i, t in enumerate(temps):
        if t is not None:
            attrs[f"sensor_{i + 1}"] = t
    return attrs


def _capacity_wh(data: dict[str, Any]) -> float | None:
    """Calculate capacity in Wh from Ah * V."""
    capacity_ah = _safe_float(data.get("battCapacity"))
    voltage = _safe_float(data.get("battVolt"))
    if capacity_ah is None or voltage is None:
        return None
    return capacity_ah * voltage


def _parse_timestamp(
    data: dict[str, Any], tz_offset: timedelta | None = None
) -> datetime | None:
    """Parse dataTimeStr to datetime using the plant's timezone."""
    value = data.get("dataTimeStr")
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone(tz_offset or timedelta(hours=0))
        )
    except ValueError:
        return None


@dataclass(frozen=True, kw_only=True)
class FelicitySensorDescription(SensorEntityDescription):
    """Describe a Felicity sensor."""

    value_fn: Callable[[dict[str, Any]], StateType | datetime]
    extra_attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSOR_DESCRIPTIONS: tuple[FelicitySensorDescription, ...] = (
    # --- Primary sensors (always visible) ---
    FelicitySensorDescription(
        key="state_of_charge",
        translation_key="state_of_charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: _safe_float(d.get("battSoc")),
    ),
    FelicitySensorDescription(
        key="state_of_health",
        translation_key="state_of_health",
        icon="mdi:battery-heart-variant",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: _safe_float(d.get("battSoh")),
    ),
    FelicitySensorDescription(
        key="voltage",
        translation_key="voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: _safe_float(d.get("battVolt")),
    ),
    FelicitySensorDescription(
        key="current",
        translation_key="current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: _safe_float(d.get("battCurr")),
    ),
    FelicitySensorDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: _safe_float(d.get("bmsPower")),
    ),
    FelicitySensorDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: _safe_float(d.get("tempMax")),
        extra_attrs_fn=_temp_attrs,
    ),
    FelicitySensorDescription(
        key="capacity",
        translation_key="capacity",
        icon="mdi:battery-high",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_capacity_wh,
    ),
    FelicitySensorDescription(
        key="cell_voltage_delta",
        translation_key="cell_voltage_delta",
        icon="mdi:battery-sync",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=_cell_voltage_delta,
        extra_attrs_fn=_cell_voltage_attrs,
    ),
    # --- Diagnostic sensors (disabled by default) ---
    FelicitySensorDescription(
        key="charge_voltage_limit",
        translation_key="charge_voltage_limit",
        icon="mdi:battery-arrow-up",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _safe_float(d.get("BMSLCVolt")),
    ),
    FelicitySensorDescription(
        key="discharge_voltage_limit",
        translation_key="discharge_voltage_limit",
        icon="mdi:battery-arrow-down",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _safe_float(d.get("BMSLDVolt")),
    ),
    FelicitySensorDescription(
        key="charge_current_limit",
        translation_key="charge_current_limit",
        icon="mdi:battery-arrow-up",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _safe_float(d.get("BMSLCCurr")),
    ),
    FelicitySensorDescription(
        key="discharge_current_limit",
        translation_key="discharge_current_limit",
        icon="mdi:battery-arrow-down",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _safe_float(d.get("BMSLDCurr")),
    ),
    FelicitySensorDescription(
        key="last_update",
        translation_key="last_update",
        icon="mdi:clock-check-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_parse_timestamp,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Felicity Battery sensors."""
    coordinator: FelicityBatteryCoordinator = entry.runtime_data

    async_add_entities(
        FelicityBatterySensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class FelicityBatterySensor(FelicityBatteryEntity, SensorEntity):
    """Representation of a Felicity Battery sensor."""

    entity_description: FelicitySensorDescription

    def __init__(
        self,
        coordinator: FelicityBatteryCoordinator,
        description: FelicitySensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_sn}_{description.key}"

    @property
    def native_value(self) -> StateType | datetime | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        if self.entity_description.key == "last_update":
            return _parse_timestamp(
                self.coordinator.data, self.coordinator.device_timezone
            )
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return None
        if self.entity_description.extra_attrs_fn is None:
            return None
        return self.entity_description.extra_attrs_fn(self.coordinator.data)
