"""Status-Entitäten als Binärsensoren und Schreibfehler-Anzeige.

Hand-written: viele Zustände liegen als 0/1-Rohwert-Sensoren mit der Pseudo-Einheit
"AUS/AN" in der Registerliste vor (Zustand Bypass, Erdwärme Zustand, Zustand
Magnetventil, ...). Hier werden sie zusätzlich als echte Binärsensoren mit passender
Geräteklasse angeboten - die Rohsensoren bleiben als Diagnose erhalten.

- Bypass (Zustand Bypass)               - Geräteklasse "offen"
- Erdwärme (Erdwärme Zustand)           - Geräteklasse "läuft"
- Magnetventil (Zustand Magnetventil)   - Geräteklasse "offen", Diagnose
- PTC-Relais aktiv                      - an, sobald irgendein Kanal des PTC-Moduls
                                          (Heizmodul 1, Input 574) aktiv ist

Dazu der Diagnosesensor "Letzter Schreibfehler" mit dem letzten fehlgeschlagenen
Modbus-Schreibzugriff (z. B. wegen zu niedrigem Modbus-Schreibrecht, Register 438).
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
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory

from .entity import ProxonEntity, ProxonEntityDescription


@dataclass(frozen=True, kw_only=True)
class _StatusBinaryDescription(BinarySensorEntityDescription, ProxonEntityDescription):
    """Entity description for a 0/1 register shown as binary sensor."""


class ProxonStatusBinarySensor(ProxonEntity, BinarySensorEntity):
    """0/1-Register als Binärsensor (nur lesbar)."""

    entity_description: _StatusBinaryDescription

    @property
    def is_on(self) -> bool | None:
        value = self._value
        return None if value is None else bool(value)


class ProxonPtcRelaisBinarySensor(ProxonStatusBinarySensor):
    """An, sobald irgendein Kanal des PTC-Moduls (Input 574) aktiv ist."""

    @property
    def is_on(self) -> bool | None:
        raw = self._value
        return None if raw is None else bool(raw & 0x3FF)  # Bit0-Bit9 = K1-K10


def _status(key: str, component: str, field: str, device_class: BinarySensorDeviceClass, **kwargs) -> _StatusBinaryDescription:
    return _StatusBinaryDescription(
        key=key,
        component=component,
        field=field,
        has_entity_name=True,
        translation_key=key,
        device_class=device_class,
        **kwargs,
    )


BYPASS_DESCRIPTION = _status(
    "proxon_bypass", "betriebswerte", "zustand_bypass", BinarySensorDeviceClass.OPENING
)
ERDWAERME_DESCRIPTION = _status(
    "proxon_erdwaerme", "betriebswerte", "erdwaerme_zustand", BinarySensorDeviceClass.RUNNING
)
MAGNETVENTIL_DESCRIPTION = _status(
    "proxon_magnetventil",
    "betriebswerte",
    "zustand_magnetventil_aus_an",
    BinarySensorDeviceClass.OPENING,
    entity_category=EntityCategory.DIAGNOSTIC,
)
PTC_RELAIS_DESCRIPTION = _status(
    "proxon_ptc_relais_aktiv", "sonstiges_input", "proxon_heizelement_status", BinarySensorDeviceClass.HEAT
)

STATUS_BINARY_ENTITIES: tuple[tuple[type[ProxonStatusBinarySensor], _StatusBinaryDescription], ...] = (
    (ProxonStatusBinarySensor, BYPASS_DESCRIPTION),
    (ProxonStatusBinarySensor, ERDWAERME_DESCRIPTION),
    (ProxonStatusBinarySensor, MAGNETVENTIL_DESCRIPTION),
    (ProxonPtcRelaisBinarySensor, PTC_RELAIS_DESCRIPTION),
)


@dataclass(frozen=True, kw_only=True)
class _WriteErrorDescription(SensorEntityDescription, ProxonEntityDescription):
    """Entity description for the last-write-error sensor."""


class ProxonLetzterSchreibfehlerSensor(ProxonEntity, SensorEntity):
    """Letzter fehlgeschlagener Schreibzugriff (Text); "keiner", wenn noch keiner auftrat."""

    entity_description: _WriteErrorDescription

    @property
    def available(self) -> bool:  # independent of any single register block
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> str:
        return self.coordinator.last_write_error or "keiner"

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        at = self.coordinator.last_write_error_at
        return {
            "zeitpunkt": at.isoformat() if at else None,
            "entitaet": self.coordinator.last_write_error_key,
            "anzahl": self.coordinator.write_error_count,
        }


LETZTER_SCHREIBFEHLER_DESCRIPTION = _WriteErrorDescription(
    key="proxon_letzter_schreibfehler",
    component="modbus_status_holding",
    field="proxon_modbus_status",  # not read - the value comes from the coordinator
    has_entity_name=True,
    translation_key="proxon_letzter_schreibfehler",
    entity_category=EntityCategory.DIAGNOSTIC,
)
