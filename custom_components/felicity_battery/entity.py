"""Base entity for Felicity Battery integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FelicityBatteryCoordinator


class FelicityBatteryEntity(CoordinatorEntity[FelicityBatteryCoordinator]):
    """Base entity for Felicity Battery."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FelicityBatteryCoordinator) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_sn)},
            manufacturer="Felicity Solar",
            model=coordinator.device_model or "FLA24100",
            name=coordinator.device_alias or f"Felicity {coordinator.device_sn}",
            serial_number=coordinator.device_sn,
        )
