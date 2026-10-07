"""Textsensoren für kleine Zahlen-Enums (Aktueller Betrieb, Geräte-Modell, Geräte-Typ).

Hand-written: die zugrunde liegenden Register sind bereits als Rohwert-Sensoren
vorhanden (0/1/2 usw.) und bleiben unverändert (Entity-Kontinuität); diese
Sensoren zeigen daneben den zugehörigen Text als `device_class: enum` an, damit
er in Dashboards und Automationen direkt lesbar ist.

- Aktueller Betrieb (Input 241):   0=Lüftungsbetrieb, 1=Heizbetrieb, 2=Kühlbetrieb
- Geräte-Modell (Holding 17):      0=FWT, 1=P
- Geräte-Typ (Holding 18):         0=Nur Heizen, 1=Heizen und Kühlen

Ein Wert außerhalb der bekannten Zuordnung ergibt den Zustand "unbekannt".
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .entity import ProxonEntity, ProxonEntityDescription


@dataclass(frozen=True, kw_only=True)
class _EnumSensorDescription(SensorEntityDescription, ProxonEntityDescription):
    """Entity description for a register value shown as text."""

    options_map: dict[int, str]
    # Option -> icon, so e.g. "Heizbetrieb" and "Kühlbetrieb" look different.
    state_icons: dict[str, str] | None = None


class ProxonEnumSensor(ProxonEntity, SensorEntity):
    """Registerwert als Text (nur lesbar)."""

    entity_description: _EnumSensorDescription

    @property
    def native_value(self) -> str | None:
        return self.entity_description.options_map.get(self._value)

    @property
    def icon(self) -> str | None:
        icons = self.entity_description.state_icons
        if icons and (state := self.native_value) in icons:
            return icons[state]
        return super().icon


def _description(key: str, component: str, field: str, options_map: dict[int, str], **kwargs) -> _EnumSensorDescription:
    return _EnumSensorDescription(
        key=key,
        component=component,
        field=field,
        has_entity_name=True,
        translation_key=key,
        device_class=SensorDeviceClass.ENUM,
        options=list(options_map.values()),
        options_map=options_map,
        **kwargs,
    )


AKTUELLER_BETRIEB_DESCRIPTION = _description(
    "proxon_aktueller_betrieb_text",
    "sonstiges_input",
    "proxon_aktueller_betrieb",
    {0: "lueftungsbetrieb", 1: "heizbetrieb", 2: "kuehlbetrieb"},
    state_icons={"lueftungsbetrieb": "mdi:fan", "heizbetrieb": "mdi:radiator", "kuehlbetrieb": "mdi:snowflake"},
)
GERAETE_MODELL_DESCRIPTION = _description(
    "proxon_geraete_modell_text",
    "hauptmenu_info",
    "geraete_modell_0_fwt_1_p",
    {0: "fwt", 1: "p"},
    entity_category=EntityCategory.DIAGNOSTIC,
)
GERAETE_TYP_DESCRIPTION = _description(
    "proxon_geraete_typ_text",
    "hauptmenu_info",
    "geraete_typ_0_nur_heizen_1_heizen_und_kuehlen",
    {0: "nur_heizen", 1: "heizen_und_kuehlen"},
    entity_category=EntityCategory.DIAGNOSTIC,
)

# Zustand 4-Wegeventil Heizen/Kühlen (Betriebswerte): 0 = Heizen, 1 = Kühlen.
VIERWEGEVENTIL_DESCRIPTION = _description(
    "proxon_vierwegeventil_text",
    "betriebswerte",
    "proxon_zustand_4_wegeventil_heizen_kuehlen",
    {0: "heizen", 1: "kuehlen"},
    state_icons={"heizen": "mdi:radiator", "kuehlen": "mdi:snowflake"},
)

ENUM_SENSOR_DESCRIPTIONS = (
    AKTUELLER_BETRIEB_DESCRIPTION,
    VIERWEGEVENTIL_DESCRIPTION,
    GERAETE_MODELL_DESCRIPTION,
    GERAETE_TYP_DESCRIPTION,
)
