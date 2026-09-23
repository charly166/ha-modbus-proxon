"""The Proxon (FWT2.0) Modbus integration."""

from __future__ import annotations

from homeassistant.components.modbus import ModbusTcpParams, async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import CONF_SLAVE, PLATFORMS
from .coordinator import (
    ProxonConfigEntry,
    ProxonDataUpdateCoordinator,
    ProxonRuntimeData,
)
from .model import ProxonDevice


async def async_setup_entry(hass: HomeAssistant, entry: ProxonConfigEntry) -> bool:
    """Set up Proxon from a config entry."""
    params = ModbusTcpParams(host=entry.data[CONF_HOST], port=entry.data[CONF_PORT])
    unit = await async_get_unit(hass, entry, params, entry.data[CONF_SLAVE])

    device = ProxonDevice(unit)
    coordinator = ProxonDataUpdateCoordinator(hass, entry, device)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = ProxonRuntimeData(device=device, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ProxonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
