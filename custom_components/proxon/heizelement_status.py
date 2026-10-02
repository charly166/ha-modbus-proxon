"""Heizelement-Status (PTC-Relais) als Binärsensor pro Zone.

Hand-written: the Heizelement `switch`/`climate` only grants *permission* for
a zone's PTC heating element to switch on if needed to reach the target
temperature - it doesn't show whether the element is actually heating right
now. That live status is a per-relay bit in one of two bitmask registers
(Input 574 "Heizmodul 1", Input 583 "Heizmodul 2" - already migrated as the
raw sensors proxon_heizelement_status/_2, see registers_input.py), confirmed
by the Excel's own comment: "Bit0:R1 .. Bit9:R10" per module.

Which PTC relay (R1-R20) belongs to which zone is **not** derivable from the
zone's Modbus NBP address/zone_index - it's purely a function of how the
installer physically wired the heating module's relay outputs. Confirmed by
a real installation where this didn't line up with NBP numbering at all
(NBP2/NBP3 wired to R4/R3, swapped). So the relay number is a separate,
explicitly user-configured per-zone setting (see config_flow.py/zones.py),
left blank by default - no entity is created for a zone until its relay
number is set.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .entity import ProxonEntity, ProxonEntityDescription
from .zones import ZoneInfo


@dataclass(frozen=True, kw_only=True)
class _HeizelementStatusDescription(BinarySensorEntityDescription, ProxonEntityDescription):
    """Entity description for a zone's Heizelement-Status binary_sensor."""

    relay: int  # 1-10 -> Heizmodul 1 (Input 574), 11-20 -> Heizmodul 2 (Input 575)


class ProxonHeizelementStatusBinarySensor(ProxonEntity, BinarySensorEntity):
    """Zeigt, ob das PTC-Heizelement dieser Zone gerade tatsächlich heizt."""

    entity_description: _HeizelementStatusDescription

    @property
    def is_on(self) -> bool | None:
        relay = self.entity_description.relay
        sonstiges = self.coordinator.device.sonstiges_input
        if relay <= 10:
            raw, bit = sonstiges.proxon_heizelement_status, relay - 1
        else:
            raw, bit = sonstiges.proxon_heizelement_status_2, relay - 11
        if raw is None:
            return None
        return bool(raw & (1 << bit))


def heizelement_status_entities(coordinator, zones: list[ZoneInfo]) -> list[ProxonHeizelementStatusBinarySensor]:
    """Build one Heizelement-Status entity per zone with a configured relay."""
    entities = []
    for zone in zones:
        if zone.relay is None:
            continue
        component = "zbp" if zone.kind == "zbp" else "nb_zones_holding"
        description = _HeizelementStatusDescription(
            key=f"proxon_heizelement_status_{zone.slug}",
            component=component,
            field="heizelement",  # not actually read - is_on() above reads the relay bitmask directly
            zone_index=zone.zone_index,
            relay=zone.relay,
            translation_key="proxon_zone_heizelement_status",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.HEAT,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        entities.append(ProxonHeizelementStatusBinarySensor(coordinator, description))
    return entities
