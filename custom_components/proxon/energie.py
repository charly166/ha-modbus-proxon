"""Energieverbrauch (Wh) für das Energie-Dashboard, integriert aus der Stromaufnahme.

Hand-written: die Anlage meldet nur die momentane Leistung (Input 25, W), kein
Energiezähler-Register. Dieser Sensor bildet daraus - wie Home Assistants
"Integral"-Helfer (Trapez-Verfahren) - einen stetig steigenden Zähler in Wh und
stellt seinen Stand nach einem Neustart wieder her. Bewusst als eigener Sensor
statt als programmatisch angelegter Core-Helfer: er lebt und stirbt mit dieser
Integration und braucht keine Entity-ID-Auflösung der Leistungsquelle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from .entity import ProxonEntity, ProxonEntityDescription

# Liegen zwischen zwei Messwerten mehr als das (Verbindungsabbruch, Neustart),
# wird das Intervall nicht integriert - sonst würde ein einzelner alter Wert
# über die ganze Lücke hochgerechnet.
MAX_GAP_SECONDS = 300


@dataclass(frozen=True, kw_only=True)
class _EnergieSensorDescription(SensorEntityDescription, ProxonEntityDescription):
    """Entity description for the integrated energy sensor."""


class ProxonEnergieSensor(ProxonEntity, RestoreSensor):
    """Kumulierter Energieverbrauch in Wh (Trapez-Integration der Stromaufnahme)."""

    entity_description: _EnergieSensorDescription

    def __init__(self, coordinator, description: _EnergieSensorDescription) -> None:
        super().__init__(coordinator, description)
        self._energy_wh = 0.0
        self._last_sample: tuple[datetime, float] | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (data := await self.async_get_last_sensor_data()) is not None and data.native_value is not None:
            try:
                self._energy_wh = float(data.native_value)
            except (TypeError, ValueError):
                self._energy_wh = 0.0

    @property
    def native_value(self) -> float:
        return round(self._energy_wh, 3)

    def _integrate(self, now: datetime, power: float | None) -> None:
        if power is None:
            self._last_sample = None
            return
        # Eine Verbrauchsleistung kann nicht negativ sein; TOTAL_INCREASING
        # verlangt außerdem einen nie fallenden Zähler.
        power = max(power, 0.0)
        if self._last_sample is not None:
            last_time, last_power = self._last_sample
            seconds = (now - last_time).total_seconds()
            if 0 < seconds <= MAX_GAP_SECONDS:
                self._energy_wh += (last_power + power) / 2 * seconds / 3600
        self._last_sample = (now, power)

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.available:
            self._integrate(dt_util.utcnow(), self._value)
        else:
            self._last_sample = None
        super()._handle_coordinator_update()


ENERGIE_DESCRIPTION = _EnergieSensorDescription(
    key="proxon_energie_total",
    component="sonstiges_input",
    field="proxon_stromaufnahme_total",
    has_entity_name=True,
    translation_key="proxon_energie_total",
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    suggested_display_precision=1,
)
