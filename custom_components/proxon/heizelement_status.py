"""Heizelement-Status (PTC) als Binärsensor pro Zone: "heizt" wie in der Hersteller-App.

Hand-written: the Heizelement `switch`/`climate` only grants *permission* for
a zone's PTC heating elements to switch on if needed to reach the target
temperature - it doesn't show whether they are heating right now.

Die Hersteller-App unterscheidet pro Raum AUS / EIN / HEIZEN. "HEIZEN" ist laut
Messungen an einer Anlage:

- **Freigabe an** (Holding 253 + n) **und** das LED-Register des Raums
  ("NBE LEDsetpointlevel", Input 589 + 3n) meldet Stufe 6 (Bit 9, Wert 0x0200 im
  Highbyte; Stufe 5 = Raum am Sollwert, Stufe 4 = wärmer). Das ist die Anzeige des
  Bedienteils "Raum fordert Wärme" - das PTC-Relais muss dabei nicht gerade
  schalten (es lief z. B. nur 37 Minuten, obwohl der Raum länger zu kalt war).

Zusätzlich gilt der Raum als heizend, sobald eines der zugeordneten Relais am
zentralen PTC-Modul ("Heizmodul 1", Input 574, Kanäle K1-K10, Bit0 = K1 ...)
tatsächlich schaltet. Welche Kanäle zu welchem Raum gehören, ergibt sich aus der
Verkabelung (siehe config_flow.py/zones.py) und ist optional; die Attribute
`aktive_kanaele`/`zugeordnete_kanaele` zeigen sie. Not to be confused with
"Heizmodul 2" (Input 583), the unit's own three heating stages.

NBP/HNBP-Zonen bekommen den Sensor immer (die LED-Stufe braucht keine Zuordnung),
das ZBP nur, wenn ihm Kanäle zugeordnet sind (es hat kein LED-Register).
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
from homeassistant.helpers import entity_registry as er

from .entity import ProxonEntity, ProxonEntityDescription
from .zones import ZoneInfo

LED_BELOW_SETPOINT = 0x0200  # Bit 9 of the LED setpoint level: room is below its setpoint


@dataclass(frozen=True, kw_only=True)
class _HeizelementStatusDescription(BinarySensorEntityDescription, ProxonEntityDescription):
    """Entity description for a zone's Heizelement-Status binary_sensor."""

    ptcs: tuple[int, ...]  # channel numbers K1-K10 -> bit (n - 1) of Input 574
    has_led: bool  # NBP/HNBP zones have a LED setpoint level register


class ProxonHeizelementStatusBinarySensor(ProxonEntity, BinarySensorEntity):
    """Zeigt, ob das Heizelement dieses Raums heizt (wie die Hersteller-App)."""

    entity_description: _HeizelementStatusDescription

    def _active_ptcs(self) -> list[int] | None:
        raw = self.coordinator.device.sonstiges_input.proxon_heizelement_status
        if raw is None:
            return None
        return [n for n in self.entity_description.ptcs if raw & (1 << (n - 1))]

    def _led(self) -> int | None:
        if not self.entity_description.has_led:
            return None
        zone = self.coordinator.device.nb_zones_input.zones[self.entity_description.zone_index]
        return zone.led_sollwertstufe

    def _enabled(self) -> bool:
        return bool(self._component.heizelement)

    def _demand(self) -> bool:
        led = self._led()
        return led is not None and self._enabled() and bool(led & LED_BELOW_SETPOINT)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return not self.entity_description.has_led or "nb_zones_input" not in self.coordinator.data.failed

    @property
    def is_on(self) -> bool | None:
        active = self._active_ptcs() if self.entity_description.ptcs else []
        if active is None and not self.entity_description.has_led:
            return None
        return bool(active) or self._demand()

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        attrs: dict[str, Any] = {}
        if self.entity_description.ptcs:
            active = self._active_ptcs()
            attrs["zugeordnete_kanaele"] = [f"K{n}" for n in self.entity_description.ptcs]
            attrs["aktive_kanaele"] = None if active is None else [f"K{n}" for n in active]
        if self.entity_description.has_led:
            attrs["raum_fordert_waerme"] = self._demand()
            attrs["led_stufe"] = self._led()
        return attrs


def heizelement_status_entities(coordinator, zones: list[ZoneInfo]) -> list[ProxonHeizelementStatusBinarySensor]:
    """One Heizelement-Status per NBP/HNBP zone, and per ZBP with assigned channels."""
    entities = []
    for zone in zones:
        has_led = zone.kind == "nb"
        if not has_led and not zone.ptcs:
            continue
        component = "zbp" if zone.kind == "zbp" else "nb_zones_holding"
        description = _HeizelementStatusDescription(
            key=f"proxon_heizelement_status_{zone.slug}",
            component=component,
            field="heizelement",
            zone_index=zone.zone_index,
            ptcs=zone.ptcs,
            has_led=has_led,
            translation_key="proxon_zone_heizelement_status",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.HEAT,
        )
        entities.append(ProxonHeizelementStatusBinarySensor(coordinator, description))
    _drop_unassigned(coordinator, {e.entity_description.key for e in entities})
    return entities


def _drop_unassigned(coordinator, keep: set[str]) -> None:
    """Remove registry entries of zones that no longer get a Heizelement-Status
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
