"""The Proxon (FWT2.0) Modbus integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from modbus_connection.tmodbus import connect_tcp

from .const import CONF_SLAVE, PLATFORMS
from .coordinator import (
    ProxonConfigEntry,
    ProxonDataUpdateCoordinator,
    ProxonRuntimeData,
)
from .model import ProxonDevice


async def async_setup_entry(hass: HomeAssistant, entry: ProxonConfigEntry) -> bool:
    """Set up Proxon from a config entry.

    We open our own Modbus TCP connection directly via modbus-connection
    (rather than sharing one through Home Assistant Core's `modbus`
    integration) because `async_get_unit`/`async_get_temporary_unit` are not
    yet available in released Home Assistant Core versions. This connection
    is dedicated to this config entry and closed again in
    async_unload_entry().
    """
    connection = await connect_tcp(entry.data[CONF_HOST], port=int(entry.data[CONF_PORT]))
    unit = connection.for_unit(int(entry.data[CONF_SLAVE]))

    device = ProxonDevice(unit)
    coordinator = ProxonDataUpdateCoordinator(hass, entry, device)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = ProxonRuntimeData(device=device, coordinator=coordinator, connection=connection)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ProxonConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.connection.close()
    return unloaded
