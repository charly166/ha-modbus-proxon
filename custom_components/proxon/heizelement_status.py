"""Heizelement-Status (PTC-Kanäle) als Binärsensor pro Zone.

Hand-written: the Heizelement `switch`/`climate` only grants *permission* for
a zone's PTC heating elements to switch on if needed to reach the target
temperature - it doesn't show whether they are actually heating right now.

That live status comes from the central PTC module ("Heizmodul 1", Input 574),
which has ten relay channels K1-K10 (Excel: "Bit0:R1 .. Bit9:R10"); each channel
feeds one or more PTCs of exactly one room (see the wiring diagram). Confirmed
on a real installation: the hour counters "PTC Heizmodul 1 Relais n" match the
plan (K1/K2 share a room and run identical hours, K10 is unused at 0 h).
Not to be confused with "Heizmodul 2" (Input 583), the unit's own three heating
stages - not room PTCs.

Which channels belong to which zone is **not** derivable from the zone's Modbus
NBP address/zone_index - it's how the installer wired the module (a room can use
several channels, e.g. the ZBP uses K1+K2). So the assignment is a separate,
explicitly user-configured multi-select per zone (see config_flow.py/zones.py),
left empty by default - no entity is created for a zone until it has at least
one channel assigned.

The sensor is on while *any* of the zone's channels is active; the individual
channels are exposed as attributes. (Config keys keep the historical name "ptcs".)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from .entity import ProxonEntity, ProxonEntityDescription
from .zones import ZoneInfo


@dataclass(frozen=True, kw_only=True)
class _HeizelementStatusDescription(BinarySensorEntityDescription, ProxonEntityDescription):
    """Entity description for a zone's Heizelement-Status binary_sensor."""

    ptcs: tuple[int, ...]  # channel numbers K1-K10 -> bit (n - 1) of Input 574


class ProxonHeizelementStatusBinarySensor(ProxonEntity, BinarySensorEntity):
    """Zeigt, ob mindestens ein PTC-Kanal dieser Zone gerade aktiv ist (heizt)."""

    entity_description: _HeizelementStatusDescription

    def _active_ptcs(self) -> list[int] | None:
        raw = self.coordinator.device.sonstiges_input.proxon_heizelement_status
        if raw is None:
            return None
        return [n for n in self.entity_description.ptcs if raw & (1 << (n - 1))]

    @property
    def is_on(self) -> bool | None:
        active = self._active_ptcs()
        return None if active is None else bool(active)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        active = self._active_ptcs()
        return {
            "zugeordnete_kanaele": [f"K{n}" for n in self.entity_description.ptcs],
            "aktive_kanaele": None if active is None else [f"K{n}" for n in active],
        }


def heizelement_status_entities(coordinator, zones: list[ZoneInfo]) -> list[ProxonHeizelementStatusBinarySensor]:
    """Build one Heizelement-Status entity per zone with at least one assigned PTC."""
    entities = []
    for zone in zones:
        if not zone.ptcs:
            continue
        component = "zbp" if zone.kind == "zbp" else "nb_zones_holding"
        description = _HeizelementStatusDescription(
            key=f"proxon_heizelement_status_{zone.slug}",
            component=component,
            field="heizelement",  # not actually read - is_on reads the PTC bitmask directly
            zone_index=zone.zone_index,
            ptcs=zone.ptcs,
            translation_key="proxon_zone_heizelement_status",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.HEAT,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        entities.append(ProxonHeizelementStatusBinarySensor(coordinator, description))
    _drop_unassigned(coordinator, {e.entity_description.key for e in entities})
    return entities


def _drop_unassigned(coordinator, keep: set[str]) -> None:
    """Remove registry entries of zones that no longer have PTCs assigned
    (the zone's device itself stays, so it wouldn't be cleaned up otherwise)."""
    hass = getattr(coordinator, "hass", None)
    if hass is None:
        return
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, coordinator.config_entry.entry_id):
        if (
            entity.domain == "binary_sensor"
            and entity.unique_id.startswith("proxon_heizelement_status_")
            and entity.unique_id not in keep
        ):
            registry.async_remove(entity.entity_id)
