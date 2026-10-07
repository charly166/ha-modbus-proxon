"""DataUpdateCoordinator for the Proxon integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from modbus_connection.tmodbus import ModbusConnection

from .const import DOMAIN, UPDATE_INTERVAL_SECONDS
from .model import ProxonDevice
from .zones import ZoneInfo

_LOGGER = logging.getLogger(__name__)


@dataclass
class ProxonUpdateReport:
    """Result of one poll cycle: which components answered, which didn't."""

    failed: set[str] = field(default_factory=set)


class ProxonDataUpdateCoordinator(DataUpdateCoordinator[ProxonUpdateReport]):
    """Polls every Component on the shared ModbusUnit once per interval.

    A single register block that fails to read (device briefly busy, a
    component not fitted on this variant, ...) only marks that one
    Component's entities unavailable - see ProxonEntity.available in
    entity.py - it does not fail the whole update, unless *nothing*
    answered at all (likely a lost connection), matching the "soft failure"
    pattern used by Home Assistant's own `sofar` integration.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device: ProxonDevice) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.device = device
        # Last failed write (shown by the diagnostic sensor 'Letzter Schreibfehler').
        self.last_write_error: str | None = None
        self.last_write_error_at: datetime | None = None
        self.last_write_error_key: str | None = None
        self.write_error_count = 0

    def record_write_error(self, key: str, err: Exception) -> None:
        """Remember a failed write and tell the listening sensor."""
        self.last_write_error = f"{type(err).__name__}: {err}"[:255]
        self.last_write_error_at = dt_util.utcnow()
        self.last_write_error_key = key
        self.write_error_count += 1
        self.async_update_listeners()

    async def _async_update_data(self) -> ProxonUpdateReport:
        failed: set[str] = set()
        answered = False
        for component in self.device.components():
            attr_name = _attr_name_for(self.device, component)
            try:
                await component.async_update()
            except Exception as err:  # noqa: BLE001 - any backend/transport error marks this component down
                _LOGGER.debug("Component %s failed to update: %s", attr_name, err)
                failed.add(attr_name)
            else:
                answered = True

        if not answered:
            raise UpdateFailed("Keine Antwort von der Proxon-Anlage (Modbus-Verbindung geprüft?)")

        return ProxonUpdateReport(failed=failed)


def _attr_name_for(device: ProxonDevice, component: object) -> str:
    for name, value in vars(device).items():
        if value is component:
            return name
    return component.__class__.__name__


@dataclass
class ProxonRuntimeData:
    """Data stored on the config entry at runtime."""

    device: ProxonDevice
    coordinator: ProxonDataUpdateCoordinator
    connection: ModbusConnection
    zones: list[ZoneInfo]
    # Holding 438 as last read (None if it couldn't be read) - decides whether
    # level-2-only entities like Sperren Bedienteil are switches or read-only.
    write_level: int | None = None
    # unique_id -> register tag ("3x0209"), filled as entities are created; used
    # to migrate legacy numbered entity_ids (see __init__._migrate_legacy_entity_ids).
    register_tags: dict[str, str] = field(default_factory=dict)
    # entity_ids suggested to entities of this entry that are still being added
    # (not registered yet), so two entities with the same name don't pick the same ID.
    claimed_ids: set[str] = field(default_factory=set)


type ProxonConfigEntry = ConfigEntry[ProxonRuntimeData]
