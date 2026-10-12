"""Intensivlüftung (Stoßlüftung): 60-Minuten-Schalter, Schnellstart-Buttons, freie Dauer.

Hand-written: laut Hersteller zählt das Gerät das Restzeit-Register nach dem
Start selbständig auf 0 zurück - es gibt kein separates Ein/Aus-Bit. Einschalten
schreibt die Dauer (Minuten) in dasselbe Register, das auch die verbleibende Zeit
ausliest; Ausschalten schreibt 0 und beendet die Lüftung vorzeitig. "Ein"
bedeutet schlicht: die Restzeit ist noch nicht auf 0 heruntergezählt.

Bedienung:
- Schalter "Intensivlüftung (60 Min.)": starten (60 Min.) / vorzeitig beenden.
- Buttons "Intensivlüftung 15/30/45 Minuten": starten mit fester Dauer.
- Zahl "Intensivlüftung Dauer" (1-360 Min.) + Button "Intensivlüftung starten":
  startet mit der eingestellten Dauer. Die Zahl ist ein reiner Merker in Home Assistant
  (wird über Neustarts hinweg wiederhergestellt), sie schreibt nichts ans Gerät.

Das Register erlaubt bis zu 1440 Minuten; die Eingabe ist bewusst auf 360 begrenzt.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import UnitOfTime
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import ProxonEntity, ProxonEntityDescription

INTENSIVLUEFTUNG_MINUTES = 60
PRESET_MINUTES = (15, 30, 45)
DAUER_MIN = 1
DAUER_MAX = 360  # the register allows 1440; limited on purpose


@dataclass(frozen=True, kw_only=True)
class _IntensivlueftungSwitchDescription(SwitchEntityDescription, ProxonEntityDescription):
    """Entity description for the Intensivlüftung boost switch."""


class ProxonIntensivlueftungSwitch(ProxonEntity, SwitchEntity):
    """60-Minuten-Intensivlüftung starten oder vorzeitig beenden."""

    entity_description: _IntensivlueftungSwitchDescription

    @property
    def is_on(self) -> bool:
        return bool(self._value)

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_write(INTENSIVLUEFTUNG_MINUTES)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_write(0)


INTENSIVLUEFTUNG_DESCRIPTION = _IntensivlueftungSwitchDescription(
    key="proxon_intensivlueftung",
    component="lueftung",
    field="proxon_intensivlueftung_restzeit",
    has_entity_name=True,
    translation_key="proxon_intensivlueftung",
)


# --- Schnellstart-Buttons, freie Dauer + Start ------------------------------------

_REGISTER = {
    "component": "lueftung",
    "field": "proxon_intensivlueftung_restzeit",
    "has_entity_name": True,
}


@dataclass(frozen=True, kw_only=True)
class _IntensivlueftungButtonDescription(ButtonEntityDescription, ProxonEntityDescription):
    """Button that starts an Intensivlüftung; ``minutes`` None = use the Dauer number."""

    minutes: int | None = None


@dataclass(frozen=True, kw_only=True)
class _IntensivlueftungDauerDescription(NumberEntityDescription, ProxonEntityDescription):
    """Entity description for the free Intensivlüftung duration."""


class ProxonIntensivlueftungButton(ProxonEntity, ButtonEntity):
    """Intensivlüftung mit fester oder eingestellter Dauer starten."""

    entity_description: _IntensivlueftungButtonDescription

    async def async_press(self) -> None:
        minutes = self.entity_description.minutes
        if minutes is None:
            minutes = self.coordinator.config_entry.runtime_data.intensiv_minutes
        await self._async_write(int(minutes))


class ProxonIntensivlueftungDauerNumber(ProxonEntity, NumberEntity, RestoreEntity):
    """Dauer (Minuten) für den Start-Button; wird nur in Home Assistant gemerkt."""

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


PRESET_DESCRIPTIONS = tuple(
    _IntensivlueftungButtonDescription(
        key=f"proxon_intensivlueftung_{minutes}_min",
        translation_key=f"proxon_intensivlueftung_{minutes}_min",
        minutes=minutes,
        **_REGISTER,
    )
    for minutes in PRESET_MINUTES
)
START_DESCRIPTION = _IntensivlueftungButtonDescription(
    key="proxon_intensivlueftung_start",
    translation_key="proxon_intensivlueftung_start",
    **_REGISTER,
)
DAUER_DESCRIPTION = _IntensivlueftungDauerDescription(
    key="proxon_intensivlueftung_dauer",
    translation_key="proxon_intensivlueftung_dauer",
    **_REGISTER,
)
