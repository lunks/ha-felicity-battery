"""Binary sensor platform for Felicity Battery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FelicityBatteryCoordinator
from .entity import FelicityBatteryEntity


@dataclass(frozen=True, kw_only=True)
class FelicityBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Felicity binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[FelicityBinarySensorDescription, ...] = (
    FelicityBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: _is_charging(d),
    ),
)


def _is_charging(data: dict[str, Any]) -> bool | None:
    """Return true if the battery is charging (positive current)."""
    try:
        current = float(data.get("battCurr", 0))
        return current > 0
    except (ValueError, TypeError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Felicity Battery binary sensors."""
    coordinator: FelicityBatteryCoordinator = entry.runtime_data

    async_add_entities(
        FelicityBatteryBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class FelicityBatteryBinarySensor(FelicityBatteryEntity, BinarySensorEntity):
    """Representation of a Felicity Battery binary sensor."""

    entity_description: FelicityBinarySensorDescription

    def __init__(
        self,
        coordinator: FelicityBatteryCoordinator,
        description: FelicityBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_sn}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
