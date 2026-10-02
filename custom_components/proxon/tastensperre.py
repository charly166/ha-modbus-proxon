"""Sperren Bedienteil (Tastensperre) - Schalter oder Anzeige, je nach Modbus-Schreibrecht.

Hand-written. Laut Registerliste (Spalten D/E/F pro Register) lässt sich die
Tastensperre (Holding 273-292) nur bei Modbus-Schreibrecht "Ja/alle" (Holding
438 = 2) beschreiben; bei 0 ("Nein") und 1 ("Einige") lehnt die Anlage jeden
Schreibversuch mit "Modbus Exception 0x03" ab.

Deshalb entscheidet das aktuell gelesene Schreibrecht, welche Plattform die
Entität bekommt:

- Schreibrecht 2: `switch` - bedienbar.
- sonst: `binary_sensor` - zeigt nur den Zustand an.

Das Schreibrecht wird bei jedem Poll mitgelesen (siehe __init__.py): ändert
es sich über die Schwelle "2" (z.B. weil der Support es hochgestuft hat), lädt
sich die Integration von selbst neu und die Entitäten wechseln die Plattform -
ohne dass der Nutzer etwas tun muss. Beide Varianten teilen sich die unique_id,
die jeweils andere Registry-Leiche wird beim Anlegen entfernt.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, WRITE_LEVEL_ALL
from .entity import ProxonEntity, ProxonEntityDescription


def writable_at(write_level: int | None) -> bool:
    """Whether Tastensperre (and other level-2-only registers) can be written."""
    return write_level is not None and write_level >= WRITE_LEVEL_ALL


@dataclass(frozen=True, kw_only=True)
class _TastensperreSwitchDescription(SwitchEntityDescription, ProxonEntityDescription):
    """Entity description for the writable Sperren-Bedienteil switch."""


@dataclass(frozen=True, kw_only=True)
class _TastensperreBinaryDescription(BinarySensorEntityDescription, ProxonEntityDescription):
    """Entity description for the read-only Sperren-Bedienteil status."""


class ProxonTastensperreSwitch(ProxonEntity, SwitchEntity):
    """Tastensperre eines Bedienteils - bedienbar (Schreibrecht 2)."""

    entity_description: _TastensperreSwitchDescription

    @property
    def is_on(self) -> bool:
        return bool(self._value)

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_write(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_write(False)


class ProxonTastensperreBinarySensor(ProxonEntity, BinarySensorEntity):
    """Tastensperre eines Bedienteils - nur Anzeige (Schreibrecht 0/1)."""

    entity_description: _TastensperreBinaryDescription

    @property
    def is_on(self) -> bool:
        return bool(self._value)


def _nb_zones(entry):
    return [z for z in entry.runtime_data.zones if z.kind == "nb"]


def _drop_stale(coordinator, other_domain: str, unique_ids: list[str]) -> None:
    registry = er.async_get(coordinator.hass)
    for unique_id in unique_ids:
        if entity_id := registry.async_get_entity_id(other_domain, DOMAIN, unique_id):
            registry.async_remove(entity_id)


def _common(zone) -> dict:
    return {
        "key": f"proxon_tastensperre_{zone.slug}",
        "component": "nb_zones_holding",
        "field": "tastensperre",
        "zone_index": zone.zone_index,
        "translation_key": "proxon_zone_tastensperre",
        "has_entity_name": True,
    }


def tastensperre_switches(coordinator, entry) -> list[ProxonTastensperreSwitch]:
    """Writable switches - only when the unit currently allows writing them."""
    zones = _nb_zones(entry)
    if not writable_at(entry.runtime_data.write_level):
        return []
    _drop_stale(coordinator, "binary_sensor", [f"proxon_tastensperre_{z.slug}" for z in zones])
    return [
        ProxonTastensperreSwitch(
            coordinator,
            _TastensperreSwitchDescription(**_common(z), entity_category=EntityCategory.CONFIG),
        )
        for z in zones
    ]


def tastensperre_binary_sensors(coordinator, entry) -> list[ProxonTastensperreBinarySensor]:
    """Read-only status - whenever writing isn't (known to be) allowed."""
    zones = _nb_zones(entry)
    if writable_at(entry.runtime_data.write_level):
        return []
    _drop_stale(coordinator, "switch", [f"proxon_tastensperre_{z.slug}" for z in zones])
    return [
        ProxonTastensperreBinarySensor(
            coordinator,
            _TastensperreBinaryDescription(**_common(z), entity_category=EntityCategory.DIAGNOSTIC),
        )
        for z in zones
    ]
