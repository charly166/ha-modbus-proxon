"""Intensivlüftung (Stoßlüftung) als Schalter: 15/30/45/60 Minuten oder eingestellte Dauer.

Hand-written: laut Hersteller zählt das Gerät das Restzeit-Register nach dem
Start selbständig auf 0 zurück - es gibt kein separates Ein/Aus-Bit. Einschalten
schreibt die Dauer (Minuten) in dasselbe Register, das auch die verbleibende Zeit
ausliest; Ausschalten schreibt 0 und beendet die Lüftung vorzeitig. "Ein"
bedeutet schlicht: die Restzeit ist noch nicht auf 0 heruntergezählt.

Bedienung (alle Schalter schreiben in dasselbe Register 133):
- "Intensivlüftung (15/30/45/60 Min.)": starten mit fester Dauer / vorzeitig beenden.
- "Intensivlüftung (eingestellte Dauer)": startet mit der Zahl "Intensivlüftung Dauer"
  (1-360 Min.). Die Zahl ist ein reiner Merker in Home Assistant (wird über Neustarts
  hinweg wiederhergestellt), sie schreibt nichts ans Gerät.

Da das Gerät nur die Restzeit kennt, merkt sich die Integration, welcher Schalter die
laufende Lüftung gestartet hat, und zeigt nur diesen als "an" (siehe `intensiv_origin`).
Läuft die Lüftung ohne bekannten Auslöser (z. B. am Bedienteil gestartet oder nach einem
Neustart), steht der 60-Minuten-Schalter auf "an". Das Register erlaubt bis zu 1440
Minuten; die Eingabe ist bewusst auf 360 begrenzt.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import UnitOfTime
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import ProxonEntity, ProxonEntityDescription
from .tastensperre import _drop_stale

INTENSIVLUEFTUNG_KEY = "proxon_intensivlueftung"
INTENSIVLUEFTUNG_MINUTES = 60
PRESET_MINUTES = (15, 30, 45)
DAUER_MIN = 1
DAUER_MAX = 360  # the register allows 1440; limited on purpose
_REGISTER = {
    "component": "lueftung",
    "field": "proxon_intensivlueftung_restzeit",
    "has_entity_name": True,
}
# v0.14.0 had buttons under these keys; their registry entries are removed.
_OBSOLETE_BUTTON_KEYS = [f"proxon_intensivlueftung_{m}_min" for m in PRESET_MINUTES] + [
    "proxon_intensivlueftung_start"
]


@dataclass(frozen=True, kw_only=True)
class _IntensivlueftungSwitchDescription(SwitchEntityDescription, ProxonEntityDescription):
    """Entity description for an Intensivlüftung switch; ``minutes`` None = Dauer number."""

    minutes: int | None = INTENSIVLUEFTUNG_MINUTES


@dataclass(frozen=True, kw_only=True)
class _IntensivlueftungDauerDescription(NumberEntityDescription, ProxonEntityDescription):
    """Entity description for the free Intensivlüftung duration."""


class ProxonIntensivlueftungSwitch(ProxonEntity, SwitchEntity):
    """Intensivlüftung mit fester oder eingestellter Dauer starten oder vorzeitig beenden."""

    entity_description: _IntensivlueftungSwitchDescription

    def _handle_coordinator_update(self) -> None:
        # Restzeit back at 0: the run is over, forget who started it. (Read the polled
        # value, not a just-written optimistic one.)
        if getattr(self._component, self.entity_description.field) == 0:
            self.coordinator.config_entry.runtime_data.intensiv_origin = None
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool:
        remaining = self._value
        if not remaining:
            return False
        origin = self.coordinator.config_entry.runtime_data.intensiv_origin
        if origin is None:
            return self.entity_description.key == INTENSIVLUEFTUNG_KEY
        return origin == self.entity_description.key

    async def async_turn_on(self, **kwargs) -> None:
        runtime = self.coordinator.config_entry.runtime_data
        minutes = self.entity_description.minutes
        if minutes is None:
            minutes = runtime.intensiv_minutes
        previous = runtime.intensiv_origin
        runtime.intensiv_origin = self.entity_description.key
        try:
            await self._async_write(int(minutes))
        except Exception:
            runtime.intensiv_origin = previous
            raise

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_write(0)
        self.coordinator.config_entry.runtime_data.intensiv_origin = None


class ProxonIntensivlueftungDauerNumber(ProxonEntity, NumberEntity, RestoreEntity):
    """Dauer (Minuten) für den Schalter "eingestellte Dauer"; nur in Home Assistant gemerkt."""

    entity_description: _IntensivlueftungDauerDescription
    _attr_native_min_value = DAUER_MIN
    _attr_native_max_value = DAUER_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is None:
            return
        try:
            value = int(float(last.state))
        except (TypeError, ValueError):
            return
        self.coordinator.config_entry.runtime_data.intensiv_minutes = min(max(value, DAUER_MIN), DAUER_MAX)

    @property
    def native_value(self) -> float:
        return self.coordinator.config_entry.runtime_data.intensiv_minutes

    async def async_set_native_value(self, value: float) -> None:
        minutes = min(max(int(value), DAUER_MIN), DAUER_MAX)
        self.coordinator.config_entry.runtime_data.intensiv_minutes = minutes
        self.async_write_ha_state()


INTENSIVLUEFTUNG_DESCRIPTION = _IntensivlueftungSwitchDescription(
    key=INTENSIVLUEFTUNG_KEY,
    translation_key=INTENSIVLUEFTUNG_KEY,
    **_REGISTER,
)
PRESET_DESCRIPTIONS = tuple(
    _IntensivlueftungSwitchDescription(
        key=f"proxon_intensivlueftung_{minutes}_min",
        translation_key=f"proxon_intensivlueftung_{minutes}_min",
        minutes=minutes,
        **_REGISTER,
    )
    for minutes in PRESET_MINUTES
)
START_DESCRIPTION = _IntensivlueftungSwitchDescription(
    key="proxon_intensivlueftung_start",
    translation_key="proxon_intensivlueftung_start",
    minutes=None,
    **_REGISTER,
)
DAUER_DESCRIPTION = _IntensivlueftungDauerDescription(
    key="proxon_intensivlueftung_dauer",
    translation_key="proxon_intensivlueftung_dauer",
    **_REGISTER,
)


def intensivlueftung_switches(coordinator) -> list[ProxonIntensivlueftungSwitch]:
    """All Intensivlüftung switches (60 Min., presets, eingestellte Dauer)."""
    _drop_stale(coordinator, "button", _OBSOLETE_BUTTON_KEYS)
    return [
        ProxonIntensivlueftungSwitch(coordinator, d)
        for d in (INTENSIVLUEFTUNG_DESCRIPTION, *PRESET_DESCRIPTIONS, START_DESCRIPTION)
    ]
