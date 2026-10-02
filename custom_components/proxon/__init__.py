"""The Proxon (FWT2.0) Modbus integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from modbus_connection.tmodbus import connect_tcp

from .const import CONF_SLAVE, CONF_ZONE_COUNT, PLATFORMS
from .coordinator import (
    ProxonConfigEntry,
    ProxonDataUpdateCoordinator,
    ProxonRuntimeData,
)
from .model import ProxonDevice
from .tastensperre import writable_at
from .zones import zones_from_entry_data


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

    device = ProxonDevice(unit, zone_count=entry.data[CONF_ZONE_COUNT])
    coordinator = ProxonDataUpdateCoordinator(hass, entry, device)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = ProxonRuntimeData(
        device=device,
        coordinator=coordinator,
        connection=connection,
        zones=zones_from_entry_data(hass, entry.data),
        write_level=_read_write_level(coordinator),
    )

    @callback
    def _reload_if_write_level_crossed() -> None:
        """The Modbus write permission (Holding 438) can be raised later (e.g. by
        Proxon support): when it crosses the level that unlocks Sperren
        Bedienteil, reload so those entities switch between read-only status
        and a real switch on their own."""
        new_level = _read_write_level(coordinator)
        if new_level is None:  # unreadable this cycle - keep what we have
            return
        was_writable = writable_at(entry.runtime_data.write_level)
        entry.runtime_data.write_level = new_level
        if writable_at(new_level) != was_writable:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(coordinator.async_add_listener(_reload_if_write_level_crossed))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _read_write_level(coordinator: ProxonDataUpdateCoordinator) -> int | None:
    """Current Modbus write permission from the last poll, None if unreadable."""
    if coordinator.data is None or "modbus_status_holding" in coordinator.data.failed:
        return None
    return coordinator.device.modbus_status_holding.proxon_modbus_status


async def async_unload_entry(hass: HomeAssistant, entry: ProxonConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.connection.close()
    return unloaded
