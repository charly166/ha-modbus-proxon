<p align="center">
  <img src="HA_Proxon_FWT2.0_Modbus.png" alt="HA Proxon FWT 2.0 Modbus" width="480">
</p>

# HA Proxon FWT 2.0 Modbus

Home-Assistant-Integration für die Proxon-Wärmepumpe/Komfortlüftung **FWT2.0** über Modbus
TCP, nach dem seit 2026 empfohlenen ["modernisierten" Modbus-Architekturmuster von Home
Assistant](https://developers.home-assistant.io/blog/2026/07/05/modernizing-modbus/):
Register werden typisiert über [`modbus-connection`](https://home-assistant-libs.github.io/modbus-connection/)
modelliert, und alles wird über die Home-Assistant-Oberfläche (Config Flow) eingerichtet –
keine YAML-Bearbeitung mehr nötig.

Diese Integration ist **nicht** auf eine bestimmte Anlage zugeschnitten: ein
Einrichtungs-Assistent fragt beim Setup ab, wie viele Bedienteile/Zonen tatsächlich installiert
sind (die FWT2.0 unterstützt architektonisch 1 ZBP + 1 HNBP + bis zu 19 NBP-Zonen), und legt
Entitäten dafür dynamisch an - unabhängig davon, wie viele Räume die konkrete Anlage hat.

Der im Blogpost beschriebene zweite Baustein – eine über Home Assistant Cores eingebaute
`modbus`-Integration geteilte Verbindung (`async_get_unit`/`async_get_temporary_unit`) – ist
in aktuellen, veröffentlichten Home-Assistant-Versionen noch nicht enthalten (Stand geprüft:
Home Assistant 2026.9.3; `homeassistant.components.modbus` hat diese Funktionen dort noch
nicht). Diese Integration öffnet deshalb aktuell eine **eigene** Modbus-TCP-Verbindung direkt
über `modbus-connection` (`modbus_connection.tmodbus.connect_tcp`), statt sie mit anderen
Integrationen zu teilen. Sobald HA Core die geteilte Verbindung veröffentlicht, kann darauf
umgestellt werden (betrifft nur `__init__.py`/`config_flow.py`, nicht das Registermodell).

Diese Integration ersetzt die bisherige, handgepflegte `proxon.yaml` (`modbus:`-Plattform)
**und** die darauf aufbauenden `climate_template`-Entitäten/Automatisierungen (siehe
`climates.yaml`/`automations.yaml`/`templates.yaml`/`controls.yaml` im Projektverzeichnis,
nur als Referenz mitgeliefert, nicht Teil dieses Repos) - die Heizungssteuerung pro Zone gibt
es jetzt nativ als `climate`-Entität, ganz ohne die HACS-Erweiterung
[hass-template-climate](https://github.com/jcwillox/hass-template-climate) und ohne
Sync-Automatisierungen.

## Icon/Logo in Home Assistant

Seit Home Assistant 2026.3 können Custom-Integrationen ihr Icon/Logo direkt mitbringen, ohne
einen Pull Request beim offiziellen [home-assistant/brands](https://github.com/home-assistant/brands)
zu benötigen (siehe [Brands-Proxy-API-Ankündigung](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api)).
Dieses Repo enthält daher `custom_components/proxon/brand/` mit `icon.png`/`icon@2x.png`
(256×256/512×512, aus dem Logo-Zahnrad-Emblem zugeschnitten) und `logo.png`/`logo@2x.png`
(Querformat) - Home Assistant zeigt diese automatisch in der Integrationssuche, unter
Einstellungen → Geräte & Dienste und auf der Geräteseite an, sobald die Integration
installiert ist. Kein zusätzlicher Schritt nötig.

## Installation (HACS)

1. In HACS → Integrationen → ⋮ → *Benutzerdefinierte Repositories* → dieses Repository
   (`https://github.com/charly166/ha-modbus-proxon`) als Typ *Integration* hinzufügen.
2. "HA Proxon FWT 2.0 Modbus" installieren, Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → Integration hinzufügen → "Proxon" suchen.
4. **Schritt 1 - Verbindung**: Modbus Host/IP-Adresse, Modbus Port (Standard `502`, an euer
   Modbus-TCP-Gateway anpassen) und Modbus-Slave-Adresse (Standard `41`) eingeben.
5. **Schritt 2 - Zonenanzahl**: Ist ein Hauptnebenbedienpanel (HNBP) installiert? Wie viele
   Nebenbedienpanel (NBP1..NBPx) gibt es?
6. **Schritt 3 - Räume**: Für jede Zone (ZBP, ggf. HNBP, dann NBP1, NBP2, ... in dieser
   Reihenfolge - die Reihenfolge entscheidet über die Registerzuordnung, siehe unten) einen
   **Home-Assistant-Raum** aus einer Dropdown-Liste auswählen (nicht mehr frei eintippen).
   Existiert der Raum noch nicht, kann er direkt im Auswahlfeld neu angelegt werden.

Die Integration verwaltet ihre Modbus-TCP-Verbindung selbst (siehe Hinweis oben); es ist also
keine weitere Voraussetzung an eure Home-Assistant-Version bezüglich der `modbus`-Integration
zu erfüllen. Benötigt wird lediglich Python ≥3.12 (durch `modbus-connection`), was jede
aktuelle Home-Assistant-Installation ohnehin mitbringt.

Zonenanzahl/-namen lassen sich später jederzeit über *Einstellungen → Geräte & Dienste →
Proxon → Neu konfigurieren* ändern (derselbe 3-Schritte-Assistent).

## Zonenmodell: ZBP / HNBP / NBPn

| Rolle | Menge | Besonderheit |
|---|---|---|
| **ZBP** (Zentralbedienpanel) | genau 1, immer vorhanden | Gibt die **absolute** Grundtemperatur fürs ganze Haus vor (10-30°C). Kein Tastensperre-/Mitteltemperatur-Register. |
| **HNBP** (Hauptnebenbedienpanel) | 0 oder 1 | Technisch wie eine NBP-Zone modelliert (Mitteltemperatur + ±3°C Offset). Seine gemessene Temperatur beeinflusst aber zusätzlich, ob die ZBP-Zieltemperatur fürs ganze Haus erreicht wird (Zone-1/Zone-2-Regelkreis der Anlage) - eine reine Fachinfo, keine Sonderlogik im Code. |
| **NBPn** (Nebenbedienpanel) | 0-19 | Zieltemperatur = eigene Mitteltemperatur (laufender Durchschnitt) ± bis zu 3°C Offset, per `number`/`climate` einstellbar. |

Jede Zone bekommt, je nach Rolle: `switch` (Heizelement; ZBP+HNBP+NBPn), `switch` (Sperren
Bedienteil; nur HNBP/NBPn), `sensor` (Ist-Temperatur; alle), `sensor` (Mitteltemperatur; nur
HNBP/NBPn), `number` (Soll-/Offset-Temperatur; alle) und eine `climate`-Entität (alle), die
Ist-/Zieltemperatur und Heizelement-Status/-Steuerung zu einer normalen Thermostat-Karte
zusammenfasst - **live berechnet bei jeder Aktualisierung**, ganz ohne die Sync-
Automatisierungen der alten Lösung.

## Geräte-Struktur

Jede Zone ist ihr **eigenes Gerät** in Home Assistant, benannt nach dem im Assistenten
gewählten Raum (z.B. "Büro", "Wohnzimmer") - nicht alles unter einem einzigen "Proxon"-Gerät.
Die Entitäten selbst tragen dadurch nur noch ihre Funktion im Namen ("Ist-Temperatur",
"Offset-Temperatur", "Heizelement", "Sperren Bedienteil"); Home Assistant setzt den
Gerätenamen automatisch davor (z.B. "Büro Ist-Temperatur"). Die `climate`-Entität einer Zone
trägt gar keinen eigenen Namenszusatz - sie erscheint als Hauptentität direkt unter dem
Gerätenamen ("Büro").

Der **T300-Warmwasserboiler** ist, obwohl kein per Raum-Auswahl konfigurierbarer "Zone",
ebenfalls ein **eigenes Gerät** ("T300") - nicht Teil des zentralen Geräts. Alle übrigen,
wirklich zentralen Register (Lüftung, Bypass, Betriebsstundenzähler, Diagnosewerte, ...)
bleiben gemeinsam unter dem zentralen Gerät (Titel der Integration).

Neu angelegte Zonen-Geräte werden zusätzlich dem gewählten Home-Assistant-Raum vorgeschlagen
(`suggested_area`), damit sie dort direkt einsortiert erscheinen.

## T300-Warmwasserboiler

Seit einem Update der Registerliste ist der T300 vollständig dokumentiert. Das Gerät "T300"
bündelt jetzt:

- Die bereits zuvor migrierten 6 Entitäten (Soll-/Ist-Temperatur Wasser, Wasser Unten,
  Heizstab-Temperatur/-Schalter/-Status, Kompressor-Status).
- **Neu**: `select` "Betriebsart" (Aus/Bedarf/Lüftungsstufe 1/Lüftungsstufe 2),
  `number` "Filterwechselintervall T300" (Monate), `switch` "Legionellaschutz".
- **Neu**: ca. 80 Diagnose-Sensoren aus dem Kältekreis (Messtemperaturen T5/T6/T9/T11/T13,
  Drücke, Zustände, Fehlerzähler) sowie 3 zusätzliche Relais-Status (Solar/Ventilator/Abtau)
  als `binary_sensor`, alle als Diagnose-Entitäten (Kategorie "Diagnose", nicht im
  Standard-Dashboard sichtbar).

Wie beim Hauptcontroller bewusst ausgelassen: die zahlreichen Installateur-/PID-
Regelparameter und Datum/Uhrzeit-Register des T300-Abschnitts (z.B. `F-xx:Installateur Menü`,
`L-xx:LSC Menü`). Details/Adressen stehen als Kommentar in `tools/generate_registers.py`.

## Migration von der alten `proxon.yaml` (+ climate_template-Setup)

1. Den `modbus:`-Block (Inhalt von `proxon.yaml`) sowie die `climate_template`-Entitäten aus
   `climates.yaml` und die zugehörigen Automatisierungen aus `automations.yaml` aus eurer
   Home-Assistant-Konfiguration entfernen, dann Home Assistant neu starten.
2. Diese Integration wie oben beschrieben über die UI einrichten.
3. **Für den ursprünglichen Anlagenbesitzer** (8 Zonen: Wohnzimmer als ZBP, Partykeller als
   HNBP, dann Flur/Schlafzimmer/Büro/Lea/Vorraum/Werkstatt als NBP1-NBP6): Werden im
   Assistenten für jede Zone der jeweils **gleichnamige Home-Assistant-Raum** ausgewählt (in
   dieser Reihenfolge), ergeben sich für alle migrierten Entitäten
   (Heizelement/Sperren Bedienteil/Ist-Temperatur) in aller Regel **dieselben** `unique_id`s
   wie zuvor (z.B. `switch.proxon_heizelement_wohnzimmer`) - der Verlauf läuft nahtlos weiter.
   **Ausnahme Büro**: Falls euer Home-Assistant-Raum "Büro" mit Umlaut heißt, ergibt das
   `..._buero` statt des alten `..._buro` (die alte `proxon.yaml` hatte die `unique_id`s
   manuell ohne Umlaut vergeben, diese Integration transliteriert Umlaute zu "ue"/"oe"/"ae")
   - für exakte Kontinuität also entweder den Home-Assistant-Raum in "Buro" umbenennen, oder
   den einmaligen Entity-ID-Sprung für diese eine Zone in Kauf nehmen. Die neuen
   `number`/`climate`-Entitäten für die Zonen-Zieltemperatur sind davon unabhängig
   grundsätzlich neu (siehe nächster Punkt).
4. **Entity-Kontinuität, Details**: Für alle migrierten *zentralen* (nicht zonengebundenen)
   Entitäten wurden die exakt gleichen `unique_id`s und Anzeigenamen wie in der alten
   `proxon.yaml` übernommen. Solange sich daraus die gleiche `entity_id` ergibt, läuft der
   Verlauf nahtlos weiter; sonst kann die neue Entität unter Einstellungen → Entitäten
   manuell auf die alte `entity_id` umbenannt werden.
5. **Bewusste Brüche gegenüber der alten `proxon.yaml`** (alle mit Absicht, um native, sauber
   bedienbare Entitäten zu bekommen statt der alten Sensor+Helfer+Automatisierung-Behelfslösung):
   - `Proxon Betriebsart`, `Proxon Lüfterstufe`, `Proxon Soll-Temperatur Wasser` und
     `Proxon Heizstab Temperatur` waren Nur-Lese-Sensoren (mit `input_number`/`input_select`-
     Hilfsentitäten und Automatisierungen davor, weil die alte YAML-`modbus`-Integration keine
     `number`/`select`-Plattform kennt) - sie sind jetzt direkt schreibbare `select`- bzw.
     `number`-Entitäten. Die `input_number`/`input_select`-Helfer und die zugehörigen
     Sync-Automatisierungen aus `automations.yaml` werden nicht mehr gebraucht.
   - Die Zonen-Offset-/Solltemperatur (`Proxon Offsettemperatur <Raum>`) war ein Nur-Lese-
     Sensor, ist jetzt eine schreibbare `number`-Entität (und Teil der `climate`-Entität) -
     ersetzt die alte `climate_template` + `modbus.write_register`-Automatisierung.
   - `Proxon Ist-Temperatur 590` (ein unbenannter Duplikat-Sensor derselben physischen
     HNBP-Temperatur, die schon unter `Proxon Ist-Temperatur Partykeller` lief) entfällt -
     die neue, zonenbasierte Ist-Temperatur nutzt einheitlich die 590er-Registerreihe.
6. Zwei kleine, durch den Abgleich mit der offiziellen Registerliste gefundene Korrekturen:
   - `Proxon Standzeit FWT Gerätefilter` (Adresse 460): Einheit ist **Monate**, nicht Tage wie
     zuvor in der YAML vermerkt. Der Wert selbst ändert sich nicht, nur die Einheit.
   - `Proxon Ist-Temperatur Wasser` / `Proxon Temperatur Wasser Unten` (Adressen 813/814):
     Ein in der Registerliste zwischenzeitlich ergänzter T300-Abschnitt bestätigte den in der
     alten YAML verwendeten Rohwert-Offset (`offset: -100`) - dieser wurde bislang beim
     Generieren **nicht** übernommen (ein Fehler aus der ersten Version dieser Integration,
     v0.0.1/v0.0.2), wodurch beide Werte ca. 10°C zu hoch angezeigt wurden. Mit diesem Update
     korrekt.
7. **Betriebsart-Werte korrigiert**: Die Registerliste kommentiert Adresse 16 mit
   "0=Aus, 1=EcoSommer, 2=EcoWinter, 9=Test" - laut Rückmeldung vom eigenen Bedienpanel gilt
   tatsächlich 0=Aus, 1=Sommerbetrieb, 2=Winterbetrieb, 3=ECO Komfortbetrieb, 4=Ofenbetrieb.
   Die `select`-Entität "Proxon Betriebsart" nutzt jetzt diese korrigierten Werte.
8. **Gerätefilter-Sensoren gefixt**: `Proxon Standzeit FWT Gerätefilter` hatte
   `device_class: duration` zusammen mit der (korrekten) Einheit "Monate" - Home Assistant
   akzeptiert für diese Geräteklasse aber nur Sekunden/Minuten/Stunden/Millisekunden/
   Mikrosekunden/Tage, keine Monate, und protokollierte deswegen eine Warnung. Die
   Geräteklasse wurde entfernt (Einheit "Monate" bleibt). `Proxon Nutzzeit FWT Gerätefilter`
   hatte durch das Excel-Update zwischenzeitlich seine Einheit verloren (Registerliste lässt
   sie dort leer) - fällt jetzt korrekt auf "h" (Stunden) zurück.
9. **Neu: Gerätefilter-Restlaufzeit + Erinnerung** (ersetzt den bisherigen Template-Sensor aus
   `templates.yaml`): `sensor.proxon_geraetefilter_resttage` berechnet die verbleibenden Tage
   aus Standzeit (Monate × 30 Tage, Näherung) minus bisheriger Nutzzeit (Stunden ÷ 24) - live,
   ohne Template. `binary_sensor.proxon_geraetefilter_wechsel_faellig` schaltet auf "Ein",
   sobald die Restlaufzeit ≤ 14 Tage beträgt. Für die eigentliche Benachrichtigung (z.B. per
   Telegram) diesen Binärsensor in einer eigenen Automatisierung auslösen - die Integration
   versendet selbst keine Benachrichtigungen (HA-Konvention).
10. **`Sperren Bedienteil` ist jetzt ein `binary_sensor`, kein `switch` mehr**: Auf echter
    Hardware lässt sich die Tastensperre eines NBP/HNBP grundsätzlich nicht per Modbus setzen
    (jeder Schreibversuch schlägt mit "Modbus Exception 0x03" fehl, unabhängig von der Zone) -
    das Sperren/Entsperren geschieht ausschließlich am Hauptbedienpanel (HBE) selbst. Die
    Entität zeigt den aktuellen Sperrzustand weiterhin an, ist aber nicht mehr schreibbar. Nach
    dem Update die alte, jetzt verwaiste `switch.proxon_tastensperre_<zone>`-Entität unter
    Einstellungen → Entitäten löschen; die neue `binary_sensor.proxon_tastensperre_<zone>`
    behält dieselbe `unique_id`.

## Umfang / Kuration der Register

Die vollständige Registerliste (`Modbus Liste FWT2.0 ver2 - für Kunden.xlsx`) umfasst über 450
Holding- und über 850 Input-Register (inkl. eines zwischenzeitlich ergänzten T300-Abschnitts).
Diese Integration deckt einen **kuratierten, erweiterten** Ausschnitt davon ab: alle bisher in
`proxon.yaml` genutzten *zentralen* Register 1:1, plus u.a. alle Betriebsstundenzähler,
Bypass-Einstellungen, Gerätemodell/-typ, den gesamten "operativen" Input-Register-Block
(Ventilatoren, Leistung/JAZ, Messtemperaturen T1–T14, Ventilstellungen, Drücke,
Heizmodul-Status) - sowie, dynamisch je nach Zonenanzahl, alle Zonen-Register (Heizelement,
Tastensperre, Ist-/Mittel-/Offset-Temperatur, Status).

Bewusst ausgelassen: PID-Regelparameter, Test-/Service-/Bedienteil-/Datum-&-Uhrzeit-Register,
die beiden Zeitprogramm-Blöcke (>100 Zeit-Slots), rohe ADC-/Kalibrierregister sowie - beim
T300-Abschnitt - die zahlreichen Installateur-/PID-Regel-/Datum-Uhrzeit-Register (siehe
Abschnitt "T300-Warmwasserboiler" oben für das, was dort *wurde* übernommen). Details und
Begründung stehen als Kommentar am Anfang von
[`tools/generate_registers.py`](tools/generate_registers.py).

**Weitere (zentrale) Register selbst ergänzen**: `custom_components/proxon/registers_holding.py`,
`registers_input.py`, `model.py` sowie die Excel-kuratierten Teile von
`sensor.py`/`switch.py`/`binary_sensor.py`/`number.py` werden von `tools/generate_registers.py`
erzeugt (nicht von Hand bearbeiten - die Datei beginnt mit `AUTO-GENERATED`). Um weitere
Register zu ergänzen: die Ein-/Ausschlussregeln in `extra_holding_addresses()` /
`extra_input_addresses()` in diesem Skript anpassen und

```bash
pip install openpyxl pyyaml
python tools/generate_registers.py
ruff check --fix custom_components tools
```

im Projektverzeichnis erneut ausführen. Die Zonen-Register (`zones.py`, `climate.py`,
`select.py`) sind dagegen von Hand gepflegt, nicht generiert - sie hängen nicht von der
Excel-Kuration ab.

## Architektur-Hinweise

- **Ein Koordinator**: Statt der vielen unterschiedlichen `scan_interval`-Werte der alten
  YAML pollt eine einzelne `DataUpdateCoordinator`-Instanz alle Register einmal pro 15
  Sekunden (`UPDATE_INTERVAL_SECONDS` in `const.py`). `modbus-connection` fasst dabei pro
  Component benachbarte Register zu möglichst wenigen Leseanfragen zusammen.
- **Weicher Fehlerzustand**: Antwortet ein einzelner Registerblock nicht (Gerät kurz
  beschäftigt, Variante ohne bestimmtes Modul, ...), werden nur die betroffenen Entitäten
  `unavailable`, nicht die gesamte Integration – siehe `coordinator.py`/`entity.py`.
- **Dynamisches Zonenmodell**: `zones.py` nutzt `modbus_connection.model.repeating_group()`,
  um zur Laufzeit (abhängig von der im Config Flow gewählten Zonenanzahl) so viele
  `NbZone`/`NbZoneInput`-Instanzen zu erzeugen wie nötig - ein fester Adress-Versatz
  (`stride`) pro Zonenindex, kein Codegen pro Anlage.
- **Schreibbare Register**: Alle Schalter (`switch.py`), Bypass-Einstellungen,
  Betriebsart/Lüfterstufe/Wassertemperaturen sowie die Zonen-Solltemperaturen (`number.py`,
  `select.py`, `climate.py`) schreiben über `Component.write(field, value)` der
  `modbus-connection`-Bibliothek.

## Grenzen dieser Umsetzung

Diese Integration wurde ohne Zugriff auf die reale Proxon-Anlage und ohne laufende
Home-Assistant-Instanz entwickelt. Geprüft wurde dabei:

- Python-Syntax aller Dateien (`py_compile`) und Lint (`ruff check`, sauber).
- **Alle Python-Module wurden gegen die echten, per `pip install` bezogenen Pakete
  `modbus-connection==4.12.1` und `homeassistant==2026.9.3` importiert** (nicht nur
  Syntaxprüfung) – das deckt Tippfehler bei Funktions-/Klassennamen und falsche
  Import-Pfade zuverlässig auf.
- Die Register-Dekodierung (`model.py`/`registers_*.py`/`zones.py`) wurde end-to-end mit
  `modbus_connection.mock.MockModbusConnection` getestet: Werte schreiben → lesen → skalieren
  ergibt die erwarteten Ergebnisse, inklusive dynamischer Zonenanzahl (0, 1, mehrere Zonen)
  und Schreibpfaden (Schalter, Zahlenfelder).
- Die `climate`-Entität wurde ebenso end-to-end gegen eine simulierte Verbindung getestet:
  Ist-/Zieltemperatur-Berechnung für ZBP (absolut) und HNBP/NBPn (Mittel+Offset), Clamping am
  ±3°C-Limit, sowie die Schreibpfade für Zieltemperatur und Heizmodus.

**Nicht** geprüft werden konnte ein echter Verbindungsaufbau zur Anlage über das reale
Netzwerk/Gateway, das tatsächliche Laden in einer laufenden Home-Assistant-Instanz mit allen
Abhängigkeiten (Frontend-Übersetzungen, Geräte-Registry-Verhalten, der mehrstufige Config-Flow-
Assistent in der echten UI), oder das Verhalten mit mehr als der ursprünglich verifizierten
Zonenzahl auf echter Hardware. Bitte nach der Installation die Basisfunktionen
(Verbindungsaufbau im Assistenten, ein paar Sensor-Werte, ein Schalter, eine `climate`-Karte)
verifizieren, bevor die alte Konfiguration endgültig gelöscht wird.

**Bekannte Klasse von Fehlern, die sich so nicht vorab erkennen lässt**: `modbus-connection`
fasst mehrere Felder eines Components automatisch zu einem einzigen Leseblock zusammen, wenn
sie nah genug beieinander liegen (`Component.max_gap`, Standard 16 Register). Das ist korrekt,
solange auch die Register *zwischen* den beiden Feldern auf der Anlage existieren – ist das
nicht der Fall, lehnt die reale Hardware den zusammengefassten Lesevorgang mit "Illegal Data
Address" (Modbus Exception Code 2) ab, obwohl beide Einzelregister für sich valide sind. Dieser
Fehler tritt ausschließlich am echten Gerät auf (der Mock kennt nur die tatsächlich
beschriebenen Register, nicht deren "Lücken"), wurde bei `Geraetefilter`
(Standzeit/Nutzzeit, Register 460/469) durch Live-Debug-Logging gegen die Anlage des
Integrations-Autors entdeckt und dort mit `max_gap = 0` (erzwingt getrennte Lesevorgänge)
behoben. Sollten weitere Sensoren dauerhaft `Nicht verfügbar` bleiben, bitte das
Debug-Protokoll der Integration aktivieren (⋮ am Integrationseintrag → "Debug-Protokoll
aktivieren", danach in den Protokollen "Unveränderte Protokolle anzeigen" für die
DEBUG-Zeilen) und nach `Modbus exception code 2` suchen – das identifiziert das betroffene
Component eindeutig.
