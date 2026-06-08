"""The Felicity Battery integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_SN, CONF_PASSWORD, CONF_USERNAME, DEFAULT_SCAN_INTERVAL
from .coordinator import FelicityBatteryCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type FelicityConfigEntry = ConfigEntry[FelicityBatteryCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: FelicityConfigEntry) -> bool:
    """Set up Felicity Battery from a config entry."""
    coordinator = FelicityBatteryCoordinator(
        hass,
        entry=entry,
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        device_sn=entry.data[CONF_DEVICE_SN],
        scan_interval=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.fetch_device_info()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: FelicityConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
