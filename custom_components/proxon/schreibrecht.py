"""Modbus-Schreibrecht-Status (Holding 438) als schreibgeschützter Enum-Sensor.

Hand-written: Register 438 ist kein generisches "Status"-Register (so hieß es
nur in der alten proxon.yaml) - es ist die geräteseitige Berechtigungsstufe
für Modbus-Schreibzugriffe (0=kein/1=einige/2=alle Register beschreibbar).
Erklärt, warum Schreibversuche wie die Tastensperre je nach Anlage mit
"Modbus Exception 0x03" fehlschlagen können, obwohl die Adresse stimmt -
siehe README. Die Berechtigung selbst lässt sich nur über den
Proxon/Zimmermann-Support ändern, nicht aus Home Assistant heraus, daher
absichtlich nur lesbar (kein select).
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)

from .entity import ProxonEntity, ProxonEntityDescription

SCHREIBRECHT_OPTIONS = {
    0: "kein_schreibzugriff",
    1: "eingeschraenkter_schreibzugriff",
    2: "voller_schreibzugriff",
}


@dataclass(frozen=True, kw_only=True)
class _SchreibrechtSensorDescription(SensorEntityDescription, ProxonEntityDescription):
    """Entity description for the Modbus write-permission status sensor."""


class ProxonSchreibrechtSensor(ProxonEntity, SensorEntity):
    """Aktuelle Modbus-Schreibberechtigung der Anlage (nur lesbar)."""

    entity_description: _SchreibrechtSensorDescription

    @property
    def native_value(self) -> str | None:
        return SCHREIBRECHT_OPTIONS.get(self._value)


SCHREIBRECHT_DESCRIPTION = _SchreibrechtSensorDescription(
    key="proxon_status_modbus",  # unchanged - continuity with the migrated proxon.yaml entity
    component="modbus_status_holding",
    field="proxon_modbus_status",
    has_entity_name=True,
    translation_key="proxon_modbus_schreibrecht",
    device_class=SensorDeviceClass.ENUM,
    options=list(SCHREIBRECHT_OPTIONS.values()),
)
