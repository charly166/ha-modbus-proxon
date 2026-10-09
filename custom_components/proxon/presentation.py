"""Wie die Entitäten auf der Geräteseite gruppiert und beschriftet werden.

Home Assistant sortiert die Geräteseite allein nach der Entitätskategorie:

- **Steuerung**     - bedienbare Entitäten (Select/Schalter/Zahl) ohne Kategorie
- **Sensoren**      - nur lesbare Messwerte/Zustände ohne Kategorie
- **Konfiguration** - Einstellungen (`EntityCategory.CONFIG`)
- **Diagnose**      - alles Technische (`EntityCategory.DIAGNOSTIC`)

Die meisten Entitäten werden aus der Registerliste generiert und landen
dabei pauschal in "Diagnose" (oder ohne Kategorie). Diese Tabelle ordnet die
wirklich relevanten gezielt der passenden Gruppe zu und vergibt Icons; für alle
übrigen Diagnosewerte vergeben Stichwort-Regeln wenigstens ein passendes Icon.
Aufbau und Icon-Wahl orientieren sich an der MIT-lizenzierten Integration
Fummy1990/ha-lan-proxon (nur die Gruppierungsidee und MDI-Icon-Namen, kein Code).

Gesteuert wird alles über den Schlüssel (= unique_id) bzw. den translation_key der
Entitätsbeschreibung, siehe ProxonEntity.__init__.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from homeassistant.const import EntityCategory

STEUERUNG = "steuerung"
SENSOR = "sensor"
KONFIGURATION = "konfiguration"
DIAGNOSE = "diagnose"

GROUP_CATEGORY: dict[str, EntityCategory | None] = {
    STEUERUNG: None,
    SENSOR: None,
    KONFIGURATION: EntityCategory.CONFIG,
    DIAGNOSE: EntityCategory.DIAGNOSTIC,
}


@dataclass(frozen=True)
class Look:
    """Gruppe (None = Kategorie unverändert lassen) und Icon einer Entität."""

    group: str | None = None
    icon: str | None = None


def _l(group: str | None, icon: str | None = None) -> Look:
    return Look(group, icon)


LOOKS: dict[str, Look] = {
    # --- Steuerung ---------------------------------------------------------
    "proxon_betriebsart": _l(STEUERUNG, "mdi:home-thermometer"),
    "proxon_luefterstufe": _l(STEUERUNG, "mdi:fan"),
    "proxon_intensivlueftung": _l(STEUERUNG, "mdi:fan-plus"),
    "proxon_kuehlung": _l(STEUERUNG, "mdi:snowflake"),
    "proxon_zone_heizelement": _l(STEUERUNG, "mdi:radiator"),
    "proxon_zone_soll_temperatur": _l(STEUERUNG, "mdi:thermostat"),
    "proxon_zone_offset_temperatur": _l(STEUERUNG, "mdi:thermometer-plus"),
    # --- Konfiguration (Einstellungen der Trinkwasserwärmepumpe, Bypass, ...) ---
    "proxon_soll_temperatur_wasser": _l(KONFIGURATION, "mdi:water-thermometer"),
    "proxon_heizstab_temperatur": _l(KONFIGURATION, "mdi:water-boiler"),
    "proxon_heizstab": _l(KONFIGURATION, "mdi:water-boiler"),
    "proxon_legionellaschutz": _l(KONFIGURATION, "mdi:bacteria"),
    "proxon_betriebsart_t300": _l(KONFIGURATION, "mdi:water-boiler-auto"),
    "proxon_filterwechselintervall_t300": _l(KONFIGURATION, "mdi:air-filter"),
    "proxon_minimum_frischlufttemperatur_bypass_aus": _l(KONFIGURATION, "mdi:thermometer-low"),
    "proxon_bypasstemperatur_hysterese": _l(KONFIGURATION, "mdi:thermometer-lines"),
    "proxon_bypass_laufzeit_an_aus": _l(KONFIGURATION, "mdi:timer-cog-outline"),
    "proxon_zone_tastensperre": _l(None, "mdi:lock"),
    # --- Sensoren (wichtige Messwerte/Zustände, sichtbar statt in Diagnose) -------------
    "proxon_akt_drehzahl_zuluftventilator": _l(SENSOR, "mdi:fan"),
    "proxon_akt_drehzahl_abluftventilator": _l(SENSOR, "mdi:fan"),
    "proxon_akt_drehzahl_kompressor": _l(SENSOR, "mdi:heat-pump"),
    "proxon_akt_leistung_kompressor": _l(SENSOR, "mdi:heat-pump-outline"),
    "proxon_akt_ventilator_stufe_abluft": _l(SENSOR, "mdi:fan"),
    "proxon_lueftungsstufe_ventilator_zuluft": _l(SENSOR, "mdi:fan"),
    "proxon_intensivlueftung_restzeit": _l(SENSOR, "mdi:timer-sand"),
    "proxon_ist_temperatur_wasser": _l(SENSOR, "mdi:water-thermometer"),
    "proxon_ist_temperatur_wasser_unten": _l(SENSOR, "mdi:water-thermometer-outline"),
    "proxon_stromaufnahme_total": _l(SENSOR, "mdi:flash"),
    "proxon_filter_tage": _l(SENSOR, "mdi:air-filter"),
    "proxon_filter_resttage": _l(SENSOR, "mdi:air-filter"),
    "proxon_filter_wechsel_faellig": _l(None, "mdi:air-filter"),
    "proxon_zone_ist_temperatur": _l(None, None),
    "proxon_zone_mitteltemperatur": _l(None, "mdi:thermometer-lines"),
    "proxon_zone_heizelement_status": _l(SENSOR, "mdi:radiator"),
    # Binärsensoren / Zustände
    "proxon_kompressor_status": _l(SENSOR, "mdi:heat-pump"),
    "proxon_heizstab_status": _l(SENSOR, "mdi:water-boiler"),
    "proxon_r3_solar": _l(DIAGNOSE, "mdi:solar-power"),
    "proxon_r5_ventilator": _l(DIAGNOSE, "mdi:fan"),
    "proxon_r6_abtau": _l(DIAGNOSE, "mdi:snowflake-melt"),
    "proxon_heizelemente_global": _l(STEUERUNG, "mdi:radiator"),
    "proxon_bypass": _l(SENSOR, "mdi:valve"),
    "proxon_erdwaerme": _l(SENSOR, "mdi:home-thermometer-outline"),
    "proxon_magnetventil": _l(DIAGNOSE, "mdi:valve"),
    "proxon_ptc_relais_aktiv": _l(SENSOR, "mdi:radiator"),
    "proxon_vierwegeventil_text": _l(SENSOR, "mdi:valve"),
    "proxon_aktueller_betrieb_text": _l(SENSOR, "mdi:heat-pump"),
    # --- Diagnose, ein paar Besonderheiten ------------------------------------------
    "proxon_akteller_betrieb": _l(DIAGNOSE, "mdi:heat-pump"),
    "proxon_heizelement_status": _l(DIAGNOSE, "mdi:radiator"),
    "proxon_heizelement_status_2": _l(DIAGNOSE, "mdi:radiator"),
    "proxon_standzeit_fwt_geraetefilter": _l(DIAGNOSE, "mdi:air-filter"),
    "proxon_nutzzeit_fwt_geraetefilter": _l(DIAGNOSE, "mdi:air-filter"),
    "proxon_intensivlueftung_sollzeit": _l(DIAGNOSE, "mdi:timer"),
    "proxon_status_modbus": _l(DIAGNOSE, "mdi:pencil-lock-outline"),
    "proxon_letzter_schreibfehler": _l(DIAGNOSE, "mdi:alert-octagon-outline"),
    "proxon_energie_total": _l(None, "mdi:lightning-bolt"),
}

# Standardmäßig deaktiviert (Entität wird angelegt, ist aber in der Entitätsliste als
# "deaktiviert" markiert und lässt sich dort jederzeit aktivieren). Gilt nur für neu
# angelegte Entitäten - bereits vorhandene behalten ihren Zustand. Gründe: Debug-Werte, die
# sich ständig ändern (Recorder-Last), Platzhalter-/Unsinnswerte, Rohwerte mit besserer
# Ersatz-Entität und Funktionen, die auf vielen Anlagen dauerhaft 0 liefern.
DEFAULT_DISABLED: frozenset[str] = frozenset(
    {
        # Debug-Werte, ändern sich ständig
        "proxon_lscontrolpulsbreite",
        "proxon_lscontrolfuerrorinput",
        "proxon_delta_sauggas_verdampfer_temp",
        "proxon_delta_sauggas_kondensator_temp",
        "proxon_akt_max_leistung_kompressor",
        "proxon_fuerrorcounter",
        "proxon_powerfu",
        "proxon_powerpcb",
        # Platzhalter-/Unsinnswerte (Fühler nicht angeschlossen, Wert nie gesetzt)
        "proxon_t9_t_aul_vor_ewt",
        "proxon_tempzusatz1",
        "proxon_tempzusatz2",
        "proxon_adausentemp",
        "proxon_adsusaettemp",
        "proxon_fu_temperaturecabinet",
        "proxon_heizmodul_2_temperatur",
        "proxon_e_ventil_heizung_position",
        "proxon_e_ventil_kuehlung_position",
        "proxon_e_ventil_vorwaerme_position",
        "proxon_stepsetpointposcool",
        "proxon_stepsetpointposheat",
        "proxon_stepsetpointpospreh",
        "proxon_clockdate",
        "proxon_clockday",
        "proxon_clockhour",
        "proxon_clockmin",
        "proxon_clockmonth",
        # Rohwerte, für die es eine Text-/Binärsensor-Entität gibt
        "proxon_akteller_betrieb",
        "proxon_geraete_modell_0_fwt_1_p",
        "proxon_geraete_typ_0_nur_heizen_1_heizen_und_kuehlen",
        "proxon_zustand_4_wegeventil_heizen_kuehlen",
        "proxon_zustand_bypass",
        "proxon_erdwaerme_zustand",
        "proxon_zustand_magnetventil_aus_an",
        "proxon_heizelement_status",  # ersetzt durch "PTC-Relais aktiv"
        "proxon_fu_motorcurrent",  # doppelt zu "FU Motor Strom"
        # Funktionen, die oft dauerhaft 0 liefern
        "proxon_jaz_komp_1min",
        "proxon_jaz_komp_1_stunde",
        "proxon_jaz_komp_24_stunde",
        "proxon_jaz_komp_365_tage",
        "proxon_jaz_komp_days",
        "proxon_jaz_total_1min",
        "proxon_jaz_total_1_stunde",
        "proxon_jaz_total_24_stunde",
        "proxon_jaz_total_365_tage",
        "proxon_jaz_total_days",
        "proxon_stunden_umluft_an",
        "proxon_stunden_umluftfilter",
        "proxon_umluftaktive",
        "proxon_wptimerschonzeit",
        "proxon_wptimermindestlaufzeit",
        "proxon_wptimerabtaunachlauf",
        "proxon_wptimerentlastung",
        "proxon_wptimerauslauf",
        "proxon_wpabtautimer",
        "proxon_wpabtauschwellecounter",
        "proxon_wpminabtauintervalltimer",
        "proxon_restwpzusatzabtauverzzeit",
        "proxon_conwpstoptimer",
        "proxon_nachabtauleistungrestorevalue",
        "proxon_nachabtausuperheatrestorevalue",
        "proxon_nachabtaumaxsuperheat",
        "proxon_schieberresthaltezeit",
        "proxon_schieberverfahrauftrag",
        "proxon_schieberberechnungrestzeit",
        "proxon_zuluftsollzone1",
        "proxon_zuluftsollzone2",
        "proxon_fuinittimecounter",
        "proxon_furesettimecounter",
    }
)


# Stichwort-Regeln für alle Entitäten ohne eigenen Eintrag/Icon (nur Icon, Gruppe
# bleibt unverändert). Die erste passende Regel gewinnt.
_RULES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), icon)
    for pattern, icon in (
        (r"fehler|error|stoerung|fatal|alarm", "mdi:alert-circle-outline"),
        (r"firmware|version|modell|_typ_", "mdi:chip"),
        (r"clock|uhr", "mdi:clock-outline"),
        (r"abtau", "mdi:snowflake-melt"),
        (r"kompressor|komp_|jaz", "mdi:heat-pump"),
        (r"drehzahl|ventilator|luefter|lueftung|luft_stufe|regluft", "mdi:fan"),
        (r"ventil|schieber|bypass|magnet", "mdi:valve"),
        (r"druck|p14|p18|p19", "mdi:gauge"),
        (r"ptc|heizmodul|heizelement|heizstab|relais", "mdi:radiator"),
        (r"stunden", "mdi:counter"),
        (r"timer|zeit|counter", "mdi:timer-outline"),
        (r"leistung|power|strom|motor|fu_", "mdi:flash"),
        (r"temp|ueberhitzung|sauggas", "mdi:thermometer"),
        (r"t300|wasser|warmwasser", "mdi:water-boiler"),
        (r"co2", "mdi:molecule-co2"),
        (r"feuchte", "mdi:water-percent"),
    )
)


def look_for(key: str, translation_key: str | None) -> Look | None:
    """Explicit entry by unique_id/key first, then by translation_key."""
    return LOOKS.get(key) or (LOOKS.get(translation_key) if translation_key else None)


def rule_icon(key: str) -> str | None:
    """Keyword-based icon for an entity without an explicit entry."""
    for pattern, icon in _RULES:
        if pattern.search(key):
            return icon
    return None
