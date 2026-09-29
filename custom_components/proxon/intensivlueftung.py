"""Intensivlüftung (60-Minuten-Stoßlüftung) als Schalter.

Hand-written: laut Hersteller zählt das Gerät das Restzeit-Register nach dem
Start selbständig auf 0 zurück - es gibt kein separates Ein/Aus-Bit. Einschalten
schreibt 60 (Minuten) in dasselbe Register, das auch die verbleibende Zeit
ausliest; Ausschalten schreibt 0 und beendet die Lüftung vorzeitig. "Ein"
bedeutet schlicht: die Restzeit ist noch nicht auf 0 heruntergezählt.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription

from .entity import ProxonEntity, ProxonEntityDescription

INTENSIVLUEFTUNG_MINUTES = 60


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
