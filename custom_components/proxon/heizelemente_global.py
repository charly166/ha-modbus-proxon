"""Heizelemente Global freigeben - Schalter oder Anzeige, je nach Modbus-Schreibrecht.

Hand-written, gleiche Logik wie die Tastensperre (siehe tastensperre.py): Holding 325
lässt sich laut Registerliste nur bei Modbus-Schreibrecht "Ja/alle" (Holding 438 = 2)
beschreiben. Bei niedrigerem Schreibrecht lehnt die Anlage jeden Schreibversuch mit
"Modbus Exception 0x03" ab.

- Schreibrecht 2: `switch` - bedienbar.
- sonst: `binary_sensor` - zeigt nur den Zustand an.

Beide Varianten teilen sich die unique_id (und damit den Verlauf); die jeweils andere
Registry-Leiche wird beim Anlegen entfernt. Ändert sich das Schreibrecht über die Schwelle 2,
lädt sich die Integration neu (siehe __init__.py) und die Entität wechselt die Plattform.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription

from .entity import ProxonEntity, ProxonEntityDescription
from .tastensperre import _drop_stale, writable_at

KEY = "proxon_heizelemente_global"
_COMMON = {
    "key": KEY,
    "component": "lueftung",
    "field": "proxon_heizelemente_global",
    "name": "Proxon Heizelemente Global",
    "has_entity_name": False,
}


@dataclass(frozen=True, kw_only=True)
class _SwitchDescription(SwitchEntityDescription, ProxonEntityDescription):
    """Entity description for the writable Heizelemente-Global switch."""


@dataclass(frozen=True, kw_only=True)
class _BinaryDescription(BinarySensorEntityDescription, ProxonEntityDescription):
    """Entity description for the read-only Heizelemente-Global status."""


class ProxonHeizelementeGlobalSwitch(ProxonEntity, SwitchEntity):
    """Alle Heizelemente freigeben/sperren - bedienbar (Schreibrecht 2)."""

    entity_description: _SwitchDescription

    @property
    def is_on(self) -> bool:
        return bool(self._value)

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_write(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_write(False)


class ProxonHeizelementeGlobalBinarySensor(ProxonEntity, BinarySensorEntity):
    """Heizelemente global freigegeben - nur Anzeige (Schreibrecht 0/1)."""

    entity_description: _BinaryDescription

    @property
    def is_on(self) -> bool:
        return bool(self._value)


def heizelemente_global_switches(coordinator, entry) -> list[ProxonHeizelementeGlobalSwitch]:
    """The writable switch - only when the unit currently allows writing it."""
    if not writable_at(entry.runtime_data.write_level):
        return []
    _drop_stale(coordinator, "binary_sensor", [KEY])
    return [ProxonHeizelementeGlobalSwitch(coordinator, _SwitchDescription(**_COMMON))]


def heizelemente_global_binary_sensors(coordinator, entry) -> list[ProxonHeizelementeGlobalBinarySensor]:
    """Read-only status - whenever writing isn't (known to be) allowed."""
    if writable_at(entry.runtime_data.write_level):
        return []
    _drop_stale(coordinator, "switch", [KEY])
    return [ProxonHeizelementeGlobalBinarySensor(coordinator, _BinaryDescription(**_COMMON))]
