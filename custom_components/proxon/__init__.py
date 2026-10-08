"""The Proxon (FWT2.0) Modbus integration."""

from __future__ import annotations

import logging
import re

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify as ha_slugify
from modbus_connection import ModbusTcpParams

from .const import CONF_SLAVE, CONF_ZONE_COUNT, DOMAIN, PLATFORMS
from .coordinator import (
    ProxonConfigEntry,
    ProxonDataUpdateCoordinator,
    ProxonRuntimeData,
)
from .model import ProxonDevice
from .tastensperre import writable_at
from .util import object_id_for, slugify
from .zones import zones_from_entry_data

_LOGGER = logging.getLogger(__name__)

# Entity IDs like "sensor.proxon" / "sensor.proxon_128": early versions created
# entities before their names resolved, so Home Assistant fell back to the
# platform name plus a duplicate counter - and keeps such IDs forever.
# (also matches the register-based IDs v0.9.0 briefly assigned, so they get upgraded to names)
_LEGACY_NUMBERED_ID = re.compile(r"^([a-z_]+)\.proxon(?:_(?:\d+|[34]x\d{4}))?$")


async def async_setup_entry(hass: HomeAssistant, entry: ProxonConfigEntry) -> bool:
    """Set up Proxon from a config entry.

    The Modbus connection is requested from Home Assistant Core's `modbus`
    integration (`async_get_unit`), so it shows up in the Modbus panel and is
    shared with any other integration talking to the same device. Core opens it
    lazily and closes it once the last config entry holding a unit on it unloads.
    """
    unit = async_get_unit(
        hass,
        entry,
        ModbusTcpParams(host=entry.data[CONF_HOST], port=int(entry.data[CONF_PORT])),
        int(entry.data[CONF_SLAVE]),
    )

    device = ProxonDevice(unit, zone_count=entry.data[CONF_ZONE_COUNT])
    coordinator = ProxonDataUpdateCoordinator(hass, entry, device)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = ProxonRuntimeData(
        device=device,
        coordinator=coordinator,
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

    _remove_stale_devices(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _migrate_legacy_entity_ids(hass, entry)
    return True


def _clean_base_ids(domain: str, entity) -> list[str]:
    """The entity_ids this entity would get without a collision suffix."""
    name = entity.name or entity.original_name
    if not name:
        return []
    bases = [f"{domain}.{ha_slugify(name)}"]  # how HA names entities without device prefix
    bases.append(f"{domain}.proxon_{slugify(name)}")  # our short IDs for central entities
    return bases


def legacy_id_renames(entries, register_tags: dict[str, str], taken: set[str]) -> dict[str, str]:
    """entity_id -> new entity_id for entities with numbered/suffixed legacy IDs.

    - ``sensor.proxon_128`` (AbtauDruck) becomes ``sensor.proxon_abtaudruck``; if
      that is taken, ``sensor.proxon_abtaudruck_3x0209``; without a usable name,
      ``sensor.proxon_3x0209``. Without a known register only the name-based ID.
    - ``sensor.proxon_aktueller_betrieb_2`` loses its collision number once the
      clean ID is free again (the clashing leftover entity is gone). The clean ID
      is derived from the entity's own name, never by stripping digits.
    Everything else (new-style IDs) is left alone.
    """
    renames: dict[str, str] = {}
    claimed = set(taken)
    for entity in entries:
        domain = entity.entity_id.split(".", 1)[0]
        match = _LEGACY_NUMBERED_ID.match(entity.entity_id)
        if match:
            object_id = object_id_for(
                domain,
                entity.name or entity.original_name,
                register_tags.get(entity.unique_id),
                lambda eid: eid in claimed,
            )
            new_id = f"{domain}.{object_id}" if object_id else None
        else:
            new_id = next(
                (
                    base
                    for base in _clean_base_ids(domain, entity)
                    if re.fullmatch(re.escape(base) + r"(?:_\d+)+", entity.entity_id) and base not in claimed
                ),
                None,
            )
        if new_id is None:
            continue
        claimed.add(new_id)
        renames[entity.entity_id] = new_id
    return renames


def _migrate_legacy_entity_ids(hass: HomeAssistant, entry: ProxonConfigEntry) -> None:
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    taken = {e.entity_id for e in registry.entities.values()} | {s.entity_id for s in hass.states.async_all()}
    renames = legacy_id_renames(entries, entry.runtime_data.register_tags, taken)
    for old_id, new_id in renames.items():
        registry.async_update_entity(old_id, new_entity_id=new_id)
    if renames:
        _LOGGER.info("Renamed %d legacy entity IDs to clean name-based IDs (e.g. %s)", len(renames), next(iter(renames.items())))


def stale_devices(devices, entry_id: str, zone_slugs: list[str]) -> list:
    """Devices of this entry that no longer belong to a configured zone.

    Home Assistant never deletes devices/entities by itself when an integration
    stops providing them, so e.g. lowering the number of NBP panels in
    "Neu konfigurieren" would otherwise leave the removed panels' devices
    behind. Central and T300 devices always stay.
    """
    keep = {entry_id, f"{entry_id}_t300", *(f"{entry_id}_zone_{slug}" for slug in zone_slugs)}
    stale = []
    for device in devices:
        ours = {ident for domain, ident in device.identifiers if domain == DOMAIN}
        if ours and not ours & keep:
            stale.append(device)
    return stale


def _remove_stale_devices(hass: HomeAssistant, entry: ProxonConfigEntry) -> None:
    registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(registry, entry.entry_id)
    for device in stale_devices(devices, entry.entry_id, [z.slug for z in entry.runtime_data.zones]):
        # Detaches this entry; the device (and with it its entities) goes away
        # unless another config entry also uses it.
        registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


def _read_write_level(coordinator: ProxonDataUpdateCoordinator) -> int | None:
    """Current Modbus write permission from the last poll, None if unreadable."""
    if coordinator.data is None or "modbus_status_holding" in coordinator.data.failed:
        return None
    return coordinator.device.modbus_status_holding.proxon_modbus_status


async def async_unload_entry(hass: HomeAssistant, entry: ProxonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
