"""Codegen: reads the Proxon FWT2.0 Modbus register list and the legacy proxon.yaml,
and (re)generates custom_components/proxon/registers_holding.py and registers_input.py.

Usage (from the repository root):

    python tools/generate_registers.py

Curation policy (see plans/... for the full rationale):

  * Every register already used by the legacy proxon.yaml is always carried over
    1:1 (same address/scale/signedness), grouped into a small number of
    modbus-connection ``Component`` classes by functional area.
  * A hand-picked set of *additional* registers is included on top of that:
    all hour counters (S01-S33), the bypass settings (G01-G03), device
    model/type (A03/A04) and the two zone target temperatures (A09/A10) from
    the Holding Register sheet, and the "operational" Input Register block
    (fan speeds, power/JAZ counters, mode/status/error codes, measurement
    temperatures T1-T14, valve positions, pressures, the two heating-module
    status blocks, and the status of the remote panels for the zones that are
    actually installed here).
  * Everything else (PID tuning parameters, test/service/date-time/HMI
    registers, the two time-schedule blocks, raw ADC/calibration registers,
    and unused remote-panel slots) is intentionally left out. Extend the
    ``EXTRA_HOLDING_INCLUDE`` / ``EXTRA_INPUT_INCLUDE`` rules below and re-run
    this script to add more registers later.

To keep this maintainable, this script writes real Python source (not just
data) - the generated files are meant to be read and tweaked by hand too.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
XLSX_PATH = REPO_ROOT / "Modbus Liste FWT2.0 ver2 - für Kunden.xlsx"
YAML_PATH = REPO_ROOT / "proxon.yaml"
OUT_DIR = REPO_ROOT / "custom_components" / "proxon"


# --------------------------------------------------------------------------
# Excel parsing
# --------------------------------------------------------------------------


@dataclass
class ExcelRegister:
    address: int
    name: str
    group: str  # e.g. "S01:Stundenzähler" (holding only, "" for input)
    writable: bool
    data_type: str  # "uint16" / "int16"
    scale: float
    unit: str
    comment: str
    ist_min: float | None = None
    ist_max: float | None = None


def _load_workbook() -> openpyxl.Workbook:
    # The file can briefly be locked by OneDrive right after it changes; retry once.
    import time

    last_exc: Exception | None = None
    for _ in range(3):
        try:
            return openpyxl.load_workbook(XLSX_PATH, data_only=True)
        except PermissionError as exc:  # pragma: no cover
            last_exc = exc
            time.sleep(1)
    assert last_exc is not None
    raise last_exc


def _parse_format_scale(fmt: str | None) -> float:
    """'*100' -> 0.01, '*10' -> 0.1, '*1' or empty -> 1.0."""
    if not fmt:
        return 1.0
    m = re.match(r"\*\s*([0-9.]+)", str(fmt).strip())
    if not m:
        return 1.0
    divisor = float(m.group(1))
    return 1.0 if divisor == 0 else 1.0 / divisor


def parse_holding(wb: openpyxl.Workbook) -> dict[int, ExcelRegister]:
    ws = wb["Holding Register"]
    out: dict[int, ExcelRegister] = {}
    for row in ws.iter_rows(min_row=5, values_only=True):
        code = row[0]
        if not code:
            continue
        address = int(str(code).split("x", 1)[1])
        writable = str(row[5] or "").strip().upper() == "R/W"
        out[address] = ExcelRegister(
            address=address,
            name=str(row[1] or "").strip(),
            group=str(row[2] or "").strip(),
            writable=writable,
            data_type=str(row[6] or "uint16").strip(),
            scale=_parse_format_scale(row[11]),
            unit=str(row[12] or "").strip(),
            comment=str(row[13] or "").strip(),
            ist_min=_as_float(row[9]),
            ist_max=_as_float(row[10]),
        )
    return out


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_input(wb: openpyxl.Workbook) -> dict[int, ExcelRegister]:
    ws = wb["Input Register"]
    out: dict[int, ExcelRegister] = {}
    for row in ws.iter_rows(min_row=5, values_only=True):
        code = row[0]
        if not code:
            continue
        address = int(str(code).split("x", 1)[1])
        out[address] = ExcelRegister(
            address=address,
            name=str(row[1] or "").strip(),
            group="",
            writable=False,
            data_type=str(row[3] or "int16").strip(),
            scale=_parse_format_scale(row[4]),
            unit=str(row[5] or "").strip(),
            comment=str(row[6] or "").strip(),
        )
    return out


# --------------------------------------------------------------------------
# Legacy proxon.yaml parsing -> "always include" set
# --------------------------------------------------------------------------


@dataclass
class LegacyEntity:
    platform: str  # "switch" | "sensor" | "binary_sensor"
    name: str
    unique_id: str
    address: int
    register_space: str  # "holding" | "input"
    data_type: str
    scale: float | None
    device_class: str | None
    unit: str | None


def parse_legacy_yaml() -> list[LegacyEntity]:
    text = YAML_PATH.read_text(encoding="utf-8")
    # The file starts with a commented-out top-level "modbus:" key and a
    # single list item below it - load it as a plain list of hub configs.
    docs = yaml.safe_load(text)
    if isinstance(docs, dict):
        hubs = docs.get("modbus", docs)
    else:
        hubs = docs
    hub = hubs[0] if isinstance(hubs, list) else hubs

    entities: list[LegacyEntity] = []
    for platform in ("switches", "sensors", "binary_sensors"):
        ha_platform = {"switches": "switch", "sensors": "sensor", "binary_sensors": "binary_sensor"}[platform]
        for item in hub.get(platform, []):
            input_type = item.get("input_type", "holding")
            register_space = "input" if input_type == "input" else "holding"
            entities.append(
                LegacyEntity(
                    platform=ha_platform,
                    name=item["name"],
                    unique_id=item["unique_id"],
                    address=item["address"],
                    register_space=register_space,
                    data_type=item.get("data_type", "uint16"),
                    scale=item.get("scale"),
                    device_class=item.get("device_class"),
                    unit=item.get("unit_of_measurement"),
                )
            )
    return entities


# --------------------------------------------------------------------------
# Additional (new) registers to include, on top of the legacy set
# --------------------------------------------------------------------------


def extra_holding_addresses(by_addr: dict[int, ExcelRegister]) -> list[int]:
    addrs: list[int] = []
    for addr, reg in by_addr.items():
        group_code = reg.group.split(":", 1)[0].strip()  # e.g. "S01", "A09"
        if group_code.startswith(("S", "G")) or group_code in ("A03", "A04", "A09", "A10"):  # Stundenzähler, Bypass, Gerätemodell/-typ, Soll Zone1/2
            addrs.append(addr)
    return sorted(addrs)


_INPUT_EXCLUDE_KEYWORDS = (
    "adc",
    "debug",
    "modbuserror",
    "modbusversion",
    "modbussubversion",
    "nopacketreceived",
    "lockoutreceive",
    "packeterror",
    "controllerversion",
    "controllersubversion",
    "softwareversion",
    "softwaresubversion",
    "modbusslavenogooddata",
    "fumodbuserror",
)

# Remote-panel ("Nebenbedienteil") *status* registers for the zones that are
# actually installed (matches the temperature sensors already migrated from
# proxon.yaml at addresses 590/593/596/599/602/605/608, plus the main panel
# at address 41/574/583 handled separately). LEDsetpointlevel and the unused
# NBE7-19 slots are intentionally skipped.
_INPUT_PANEL_STATUS_INCLUDE = {588, 591, 594, 597, 600, 603, 606}

# The "Heizmodul" (PTC) block: keep the operationally interesting fields,
# skip raw bit-input/relay-used/relay-test/address/model diagnostics.
_INPUT_HEIZMODUL_INCLUDE_SUFFIXES = ("Selbsttest-Ergebnis", "Status", "Temperatur", "Relais Status")


def extra_input_addresses(by_addr: dict[int, ExcelRegister]) -> list[int]:
    addrs: list[int] = []
    for addr, reg in by_addr.items():
        name_lower = reg.name.lower()
        if any(kw in name_lower for kw in _INPUT_EXCLUDE_KEYWORDS):
            continue
        if 450 <= addr <= 465:  # raw ADC calibration block
            continue
        if 570 <= addr <= 587:  # Heizmodul 1+2 diagnostics block
            if reg.name.startswith("Heizmodul") and reg.name.split(" ", 2)[-1] in _INPUT_HEIZMODUL_INCLUDE_SUFFIXES:
                addrs.append(addr)
            continue
        if 588 <= addr <= 650:  # remote panel (NBE) block
            if addr in _INPUT_PANEL_STATUS_INCLUDE:
                addrs.append(addr)
            continue
        if addr <= 269:  # main operational/diagnostic block
            addrs.append(addr)
    return sorted(addrs)


# --------------------------------------------------------------------------
# Identifier / entity-description helpers
# --------------------------------------------------------------------------

_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


def slugify(name: str) -> str:
    name = name.translate(_UMLAUT_MAP)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    name = re.sub(r"_+", "_", name)
    if not name:
        name = "reg"
    if name[0].isdigit():
        name = f"r_{name}"
    return name


def dedupe(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    i = 2
    while f"{base}_{i}" in used:
        i += 1
    used.add(f"{base}_{i}")
    return f"{base}_{i}"


UNIT_CONST_MAP = {
    "°C": ("UnitOfTemperature.CELSIUS", "homeassistant.const"),
    "%": ("PERCENTAGE", "homeassistant.const"),
    "Sekunden": ("UnitOfTime.SECONDS", "homeassistant.const"),
    "Minuten": ("UnitOfTime.MINUTES", "homeassistant.const"),
    "min": ("UnitOfTime.MINUTES", "homeassistant.const"),
    "std": ("UnitOfTime.HOURS", "homeassistant.const"),
    "d": ("UnitOfTime.DAYS", "homeassistant.const"),
    "ppm": ("CONCENTRATION_PARTS_PER_MILLION", "homeassistant.const"),
    "W": ("UnitOfPower.WATT", "homeassistant.const"),
    "Volt": ("UnitOfElectricPotential.VOLT", "homeassistant.const"),
    "Ampere": ("UnitOfElectricCurrent.AMPERE", "homeassistant.const"),
    "Pa": ("UnitOfPressure.PA", "homeassistant.const"),
    "bar": ("UnitOfPressure.BAR", "homeassistant.const"),
    "rpm": ("REVOLUTIONS_PER_MINUTE", "homeassistant.const"),
}


@dataclass
class FieldMeta:
    key: str  # unique_id (migrated) / translation_key (new)
    name: str  # German display name
    component_class: str
    field_name: str
    module: str  # "registers_holding" | "registers_input"
    platform: str  # "sensor" | "switch" | "binary_sensor" | "number"
    writable: bool
    unit: str
    signed: bool
    device_class: str | None  # e.g. "SensorDeviceClass.TEMPERATURE"
    state_class: str | None  # e.g. "SensorStateClass.MEASUREMENT"
    entity_category: str | None  # e.g. "EntityCategory.DIAGNOSTIC"
    migrated: bool
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None


def emit_field_line(field_name: str, address: int, reg: ExcelRegister, writable: bool, comment: str) -> str:
    signed = reg.data_type.strip().lower().startswith("int")
    scale = reg.scale
    unit = reg.unit.strip()
    kwargs = [f"signed={signed}"]
    if unit:
        kwargs.append(f"unit={unit!r}")
    if writable:
        kwargs.append("writable=True")
    kwargs_str = ", ".join(kwargs)
    if abs(scale - 1.0) > 1e-9:
        line = f"    {field_name} = gauge({address}, {scale!r}, {kwargs_str})"
    else:
        line = f"    {field_name} = integer({address}, {kwargs_str})"
    if comment:
        comment = comment.replace("\n", " ").strip()
        line += f"  # {comment}"
    return line


_DEVICE_CLASS_BY_LEGACY = {
    "temperature": ("SensorDeviceClass.TEMPERATURE", "SensorStateClass.MEASUREMENT"),
    "aqi": ("SensorDeviceClass.AQI", "SensorStateClass.MEASUREMENT"),
    "humidity": ("SensorDeviceClass.HUMIDITY", "SensorStateClass.MEASUREMENT"),
    "duration": ("SensorDeviceClass.DURATION", "SensorStateClass.TOTAL_INCREASING"),
}


def infer_device_class(unit: str) -> tuple[str | None, str | None]:
    if unit.strip() == "°C":
        return "SensorDeviceClass.TEMPERATURE", "SensorStateClass.MEASUREMENT"
    return None, None


def make_meta(
    *,
    key: str,
    name: str,
    component_class: str,
    field_name: str,
    module: str,
    platform: str,
    writable: bool,
    reg: ExcelRegister,
    entity_category: str | None,
    migrated: bool,
    legacy_device_class: str | None = None,
) -> FieldMeta:
    if legacy_device_class and legacy_device_class in _DEVICE_CLASS_BY_LEGACY:
        device_class, state_class = _DEVICE_CLASS_BY_LEGACY[legacy_device_class]
    else:
        device_class, state_class = infer_device_class(reg.unit)
    if platform != "sensor":
        state_class = None
    min_value = reg.ist_min if writable else None
    max_value = reg.ist_max if writable else None
    step = reg.scale if writable and abs(reg.scale - 1.0) > 1e-9 else (1.0 if writable else None)
    return FieldMeta(
        key=key,
        name=name,
        component_class=component_class,
        field_name=field_name,
        module=module,
        platform=platform,
        writable=writable,
        unit=reg.unit.strip(),
        signed=reg.data_type.strip().lower().startswith("int"),
        device_class=device_class,
        state_class=state_class,
        entity_category=entity_category,
        migrated=migrated,
        min_value=min_value,
        max_value=max_value,
        step=step,
    )


# --------------------------------------------------------------------------
# Component grouping
# --------------------------------------------------------------------------


@dataclass
class ComponentSpec:
    class_name: str
    register_space: str  # "holding" | "input"
    doc: str
    fields: list[str] = field(default_factory=list)
    meta: list[FieldMeta] = field(default_factory=list)


def build_holding_components(
    legacy: list[LegacyEntity], by_addr: dict[int, ExcelRegister], extra_addrs: list[int]
) -> list[ComponentSpec]:
    used_names: set[str] = set()

    def add(spec: ComponentSpec, addr: int, base_name: str, writable: bool, comment: str, *, entity_category: str | None) -> None:
        reg = by_addr.get(addr)
        if reg is None:
            raise KeyError(f"holding address {addr} not found in Excel list")
        fname = dedupe(slugify(base_name), used_names)
        spec.fields.append(emit_field_line(fname, addr, reg, writable, comment))
        platform = "number" if writable else "sensor"
        spec.meta.append(
            make_meta(
                key=f"proxon_{fname}",
                name=comment or base_name,
                component_class=spec.class_name,
                field_name=fname,
                module="registers_holding",
                platform=platform,
                writable=writable,
                reg=reg,
                entity_category=entity_category,
                migrated=False,
            )
        )

    legacy_holding = {e.address: e for e in legacy if e.register_space == "holding"}

    def add_legacy(spec: ComponentSpec, e: LegacyEntity) -> None:
        """Like add(), but falls back to the proxon.yaml metadata for
        addresses that aren't part of this Excel register list (e.g. the T300
        hot-water-tank module, which belongs to a different device variant),
        and always preserves the legacy platform/unique_id for continuity."""
        reg = by_addr.get(e.address)
        if reg is None:
            reg = ExcelRegister(
                address=e.address,
                name=e.name,
                group="",
                writable=False,
                data_type=e.data_type,
                scale=e.scale if e.scale is not None else 1.0,
                unit=e.unit or "",
                comment="Nicht in der FWT2.0-Registerliste (separates Modul, z.B. T300).",
            )
        writable = e.platform == "switch"
        fname = dedupe(slugify(e.name), used_names)
        spec.fields.append(emit_field_line(fname, e.address, reg, writable, reg.comment or e.name))
        spec.meta.append(
            make_meta(
                key=e.unique_id,
                name=e.name,
                component_class=spec.class_name,
                field_name=fname,
                module="registers_holding",
                platform=e.platform,
                writable=writable,
                reg=reg,
                entity_category=None,
                migrated=True,
                legacy_device_class=e.device_class,
            )
        )

    heizelemente = ComponentSpec(
        "HeizelementeSwitches",
        "holding",
        "Heizelemente (PTC) global + je Raum ein-/ausschalten. Migriert 1:1 aus proxon.yaml.",
    )
    tastensperre = ComponentSpec(
        "Tastensperre", "holding", "Tastensperre der Bedienteile je Raum. Migriert 1:1 aus proxon.yaml."
    )
    offset_temps = ComponentSpec(
        "OffsetTemperaturen",
        "holding",
        "Offset-/Soll-Temperaturen je Raum bzw. Zone. Migriert aus proxon.yaml, ergänzt um "
        "die Zonen-Sollwerte A09/A10.",
    )
    mittel_temps = ComponentSpec(
        "Mitteltemperaturen", "holding", "Gemittelte Raumtemperaturen je Raum. Migriert 1:1 aus proxon.yaml."
    )
    lueftung = ComponentSpec(
        "Lueftung", "holding", "Betriebsart, Lüfterstufe und Intensivlüftung. Migriert 1:1 aus proxon.yaml."
    )
    t300 = ComponentSpec(
        "T300Warmwasser", "holding", "T300 Warmwasser-Heizstab. Migriert 1:1 aus proxon.yaml."
    )
    geraetefilter = ComponentSpec(
        "Geraetefilter", "holding", "Standzeit/Nutzzeit des Gerätefilters. Migriert 1:1 aus proxon.yaml."
    )
    modbus_status = ComponentSpec(
        "ModbusStatusHolding", "holding", "Modbus-Statusregister. Migriert 1:1 aus proxon.yaml."
    )
    stundenzaehler = ComponentSpec(
        "Stundenzaehler",
        "holding",
        "Betriebsstundenzähler (S01-S33). Neu hinzugefügt (nicht in der bisherigen proxon.yaml).",
    )
    bypass = ComponentSpec(
        "Bypass", "holding", "Bypass-Einstellungen (G01-G03). Neu hinzugefügt."
    )
    hauptmenu = ComponentSpec(
        "HauptmenuInfo", "holding", "Gerätemodell/-typ (A03/A04). Neu hinzugefügt."
    )

    for addr, e in sorted(legacy_holding.items()):
        uid = e.unique_id
        if "heizelement" in uid and "tastensperre" not in uid:
            add_legacy(heizelemente, e)
        elif "tastensperre" in uid:
            add_legacy(tastensperre, e)
        elif "offsettemperatur" in uid:
            add_legacy(offset_temps, e)
        elif "mitteltemperatur" in uid:
            add_legacy(mittel_temps, e)
        elif uid in ("proxon_betriebsart", "proxon_luefterstufe") or "intensivlueftung" in uid:
            add_legacy(lueftung, e)
        elif "wasser" in uid or "heizstab" in uid or "kuehlung" in uid:
            add_legacy(t300, e)
        elif "geraetefilter" in uid:
            add_legacy(geraetefilter, e)
        elif "status_modbus" in uid:
            add_legacy(modbus_status, e)
        else:  # pragma: no cover - safety net, should not trigger
            add_legacy(lueftung, e)

    # New (not previously in proxon.yaml) registers. Bypass is exposed as a
    # writable "number" (installer/comfort tuning -> EntityCategory.CONFIG);
    # the new zone-2 setpoint is a writable "number" without a category (it's
    # a everyday comfort setpoint, like the existing offset temperatures);
    # hour counters and device model/type are read-only diagnostic sensors.
    for addr in extra_addrs:
        reg = by_addr[addr]
        group_code = reg.group.split(":", 1)[0].strip()
        if group_code.startswith("S"):
            add(stundenzaehler, addr, reg.name, False, reg.name, entity_category="EntityCategory.DIAGNOSTIC")
        elif group_code in ("A09", "A10"):
            add(offset_temps, addr, reg.name, True, reg.name, entity_category=None)
        elif group_code in ("A03", "A04"):
            add(hauptmenu, addr, reg.name, False, reg.name, entity_category="EntityCategory.DIAGNOSTIC")
        elif group_code.startswith("G"):
            add(bypass, addr, reg.name, True, reg.name, entity_category="EntityCategory.CONFIG")

    components = [
        heizelemente,
        tastensperre,
        offset_temps,
        mittel_temps,
        lueftung,
        t300,
        geraetefilter,
        modbus_status,
        stundenzaehler,
        bypass,
        hauptmenu,
    ]
    return [c for c in components if c.fields]


def build_input_components(
    legacy: list[LegacyEntity], by_addr: dict[int, ExcelRegister], extra_addrs: list[int]
) -> list[ComponentSpec]:
    used_names: set[str] = set()

    def add(spec: ComponentSpec, addr: int, base_name: str, comment: str, *, entity_category: str | None) -> None:
        reg = by_addr.get(addr)
        if reg is None:
            raise KeyError(f"input address {addr} not found in Excel list")
        fname = dedupe(slugify(base_name), used_names)
        spec.fields.append(emit_field_line(fname, addr, reg, False, comment))
        spec.meta.append(
            make_meta(
                key=f"proxon_{fname}",
                name=comment or base_name,
                component_class=spec.class_name,
                field_name=fname,
                module="registers_input",
                platform="sensor",
                writable=False,
                reg=reg,
                entity_category=entity_category,
                migrated=False,
            )
        )

    legacy_input = {e.address: e for e in legacy if e.register_space == "input"}

    def add_legacy(spec: ComponentSpec, e: LegacyEntity) -> None:
        reg = by_addr.get(e.address)
        if reg is None:
            reg = ExcelRegister(
                address=e.address,
                name=e.name,
                group="",
                writable=False,
                data_type=e.data_type,
                scale=e.scale if e.scale is not None else 1.0,
                unit=e.unit or "",
                comment="Nicht in der FWT2.0-Registerliste (separates Modul, z.B. T300).",
            )
        fname = dedupe(slugify(e.name), used_names)
        spec.fields.append(emit_field_line(fname, e.address, reg, False, reg.comment or e.name))
        spec.meta.append(
            make_meta(
                key=e.unique_id,
                name=e.name,
                component_class=spec.class_name,
                field_name=fname,
                module="registers_input",
                platform=e.platform,
                writable=False,
                reg=reg,
                entity_category=None,
                migrated=True,
                legacy_device_class=e.device_class,
            )
        )

    zonen_temps = ComponentSpec(
        "ZonenTemperaturen", "input", "Ist-Temperaturen je Raum/Zone. Migriert 1:1 aus proxon.yaml."
    )
    zuluft = ComponentSpec(
        "ZuAbluft", "input", "Zu-/Ab-/Fort-/Frischluft-Temperaturen, CO2, Luftfeuchte. Migriert 1:1 aus proxon.yaml."
    )
    warmwasser = ComponentSpec(
        "WarmwasserInput", "input", "T300 Warmwasser Ist-Temperaturen. Migriert 1:1 aus proxon.yaml."
    )
    heizstab_status = ComponentSpec(
        "HeizstabStatus", "input", "T300 Heizstab-/Kompressorstatus (binäre Sensoren). Migriert 1:1 aus proxon.yaml."
    )
    sonstiges = ComponentSpec(
        "SonstigesInput", "input", "Betriebsart, Lüfterstufe, Stromaufnahme u.a. Migriert 1:1 aus proxon.yaml."
    )
    betrieb = ComponentSpec(
        "Betriebswerte",
        "input",
        "Ventilatoren, Leistung, JAZ-Zähler, Betriebsart/Status/Fehlercodes, Messtemperaturen T1-T14, "
        "Ventilpositionen, Drücke. Neu hinzugefügt.",
    )
    heizmodule = ComponentSpec(
        "Heizmodule", "input", "Status/Temperatur/Selbsttest der beiden PTC-Heizmodule. Neu hinzugefügt."
    )
    bedienteile = ComponentSpec(
        "BedienteilStatus", "input", "Status der Bedienteile (Nebenbedienteile) je installierter Zone. Neu hinzugefügt."
    )

    for addr, e in sorted(legacy_input.items()):
        uid = e.unique_id
        if "ist_temperatur" in uid and "wasser" in uid:
            add_legacy(warmwasser, e)
        elif "ist_temperatur" in uid or "heizelement_status" in uid:
            add_legacy(zonen_temps, e)
        elif uid in (
            "proxon_temperatur_frischluft",
            "proxon_temperatur_zuluft",
            "proxon_temperatur_fortluft",
            "proxon_temperatur_abluft",
            "proxon_co2_wohnzimmer",
            "proxon_luftfeuchte_wohnzimmer",
        ):
            add_legacy(zuluft, e)
        elif uid in ("proxon_heizstab_status", "proxon_kompressor_status"):
            add_legacy(heizstab_status, e)
        else:
            add_legacy(sonstiges, e)

    for addr in extra_addrs:
        reg = by_addr[addr]
        if 570 <= addr <= 587:
            add(heizmodule, addr, reg.name, reg.name, entity_category="EntityCategory.DIAGNOSTIC")
        elif 588 <= addr <= 650:
            add(bedienteile, addr, reg.name, reg.name, entity_category="EntityCategory.DIAGNOSTIC")
        else:
            add(betrieb, addr, reg.name, reg.name, entity_category="EntityCategory.DIAGNOSTIC")

    components = [
        zonen_temps,
        zuluft,
        warmwasser,
        heizstab_status,
        sonstiges,
        betrieb,
        heizmodule,
        bedienteile,
    ]
    return [c for c in components if c.fields]


# --------------------------------------------------------------------------
# File rendering
# --------------------------------------------------------------------------

HEADER = '''"""AUTO-GENERATED by tools/generate_registers.py - do not edit by hand.

Re-run ``python tools/generate_registers.py`` from the repository root after
changing the curation rules in that script (e.g. to include more registers
from the Excel register list).
"""

from __future__ import annotations

from modbus_connection.model import Component, gauge, integer

'''


def render_component(spec: ComponentSpec) -> str:
    lines = [f"class {spec.class_name}(Component):"]
    lines.append(f'    """{spec.doc}"""')
    lines.append("")
    if spec.register_space == "input":
        lines.append('    register_space = "input"')
        lines.append("")
    lines.extend(spec.fields)
    lines.append("")
    return "\n".join(lines)


def render_file(components: list[ComponentSpec]) -> str:
    parts = [HEADER]
    parts.extend(render_component(c) for c in components)
    return "\n\n".join(p.rstrip() for p in parts) + "\n"


def camel_to_snake(name: str) -> str:
    s = re.sub(r"(?<!^)(?=[A-Z][a-z])", "_", name)
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    return s.lower()


def render_model(holding: list[ComponentSpec], input_: list[ComponentSpec]) -> str:
    lines = [
        '"""AUTO-GENERATED by tools/generate_registers.py - do not edit by hand."""',
        "",
        "from __future__ import annotations",
        "",
        "from modbus_connection.model import Device",
        "",
        "from . import registers_holding as rh",
        "from . import registers_input as ri",
        "",
        "",
        "class ProxonDevice(Device):",
        '    """Root device object: one attribute per Component, wired to the shared ModbusUnit."""',
        "",
        "    def __init__(self, unit) -> None:",
        "        super().__init__(unit)",
    ]
    for spec in holding:
        attr = camel_to_snake(spec.class_name)
        lines.append(f"        self.{attr} = rh.{spec.class_name}(unit)")
    for spec in input_:
        attr = camel_to_snake(spec.class_name)
        lines.append(f"        self.{attr} = ri.{spec.class_name}(unit)")
    lines.append("")
    all_components = holding + input_
    lines.append("    def components(self):")
    lines.append('        """All components, for async_update()/failure tracking."""')
    lines.append("        return (")
    for spec in all_components:
        attr = camel_to_snake(spec.class_name)
        lines.append(f"            self.{attr},")
    lines.append("        )")
    lines.append("")
    return "\n".join(lines) + "\n"


_SENSOR_DEVICE_CLASS_IMPORTS = "SensorDeviceClass, SensorEntityDescription, SensorStateClass"


def _fmt_kwarg(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    return f"{name}={value}"


def render_platform_file(platform: str, metas: list[FieldMeta]) -> str:
    """platform in {'sensor', 'switch', 'binary_sensor', 'number'}."""
    class_map = {
        "sensor": ("SensorEntityDescription", "ProxonSensorEntityDescription", "ProxonSensor"),
        "switch": ("SwitchEntityDescription", "ProxonSwitchEntityDescription", "ProxonSwitch"),
        "binary_sensor": (
            "BinarySensorEntityDescription",
            "ProxonBinarySensorEntityDescription",
            "ProxonBinarySensor",
        ),
        "number": ("NumberEntityDescription", "ProxonNumberEntityDescription", "ProxonNumber"),
    }
    base_desc, desc_name, entity_name = class_map[platform]
    ha_module = {
        "sensor": "homeassistant.components.sensor",
        "switch": "homeassistant.components.switch",
        "binary_sensor": "homeassistant.components.binary_sensor",
        "number": "homeassistant.components.number",
    }[platform]

    lines: list[str] = [
        '"""AUTO-GENERATED by tools/generate_registers.py - do not edit by hand."""',
        "",
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "",
    ]
    entity_base = base_desc.replace("EntityDescription", "Entity")
    if platform == "sensor":
        lines.append(f"from {ha_module} import SensorEntity, {_SENSOR_DEVICE_CLASS_IMPORTS}")
    else:
        lines.append(f"from {ha_module} import {entity_base}, {base_desc}")
    if any(m.entity_category for m in metas):
        lines.append("from homeassistant.const import EntityCategory")
    lines.append("from homeassistant.core import HomeAssistant")
    lines.append("from homeassistant.helpers.entity_platform import AddEntitiesCallback")
    lines.append("")
    lines.append("from .coordinator import ProxonConfigEntry")
    lines.append("from .entity import ProxonEntity, ProxonEntityDescription")
    lines.append("")
    lines.append("")
    lines.append("@dataclass(frozen=True, kw_only=True)")
    lines.append(f"class {desc_name}({base_desc}, ProxonEntityDescription):")
    lines.append('    """Entity description for a Proxon register-backed ' + platform + '."""')
    lines.append("")
    lines.append("")
    lines.append(f"class {entity_name}(ProxonEntity, {base_desc.replace('EntityDescription', 'Entity')}):")
    lines.append(f'    """A single Proxon {platform} entity."""')
    lines.append("")
    lines.append(f"    entity_description: {desc_name}")
    lines.append("")
    if platform in ("sensor", "number"):
        lines.append("    @property")
        lines.append("    def native_value(self):")
        lines.append("        return self._value")
        lines.append("")
    if platform == "number":
        lines.append("    async def async_set_native_value(self, value: float) -> None:")
        lines.append("        await self._async_write(value)")
        lines.append("")
    if platform in ("binary_sensor", "switch"):
        lines.append("    @property")
        lines.append("    def is_on(self) -> bool:")
        lines.append("        return bool(self._value)")
        lines.append("")
    if platform == "switch":
        lines.append("    async def async_turn_on(self, **kwargs) -> None:")
        lines.append("        await self._async_write(True)")
        lines.append("")
        lines.append("    async def async_turn_off(self, **kwargs) -> None:")
        lines.append("        await self._async_write(False)")
        lines.append("")
    lines.append("")
    lines.append(f"{platform.upper()}_DESCRIPTIONS: tuple[{desc_name}, ...] = (")
    for m in metas:
        kwargs = [
            f"key={m.key!r}",
            f"component={camel_to_snake(m.component_class)!r}",
            f"field={m.field_name!r}",
        ]
        if m.migrated:
            kwargs.append(f"name={m.name!r}")
            kwargs.append("has_entity_name=False")
        else:
            kwargs.append(f"translation_key={m.key!r}")
        if m.entity_category:
            kwargs.append(f"entity_category={m.entity_category}")
        if platform == "sensor":
            if m.unit:
                kwargs.append(f"native_unit_of_measurement={m.unit!r}")
            if m.device_class:
                kwargs.append(f"device_class={m.device_class}")
            if m.state_class:
                kwargs.append(f"state_class={m.state_class}")
        elif platform == "number":
            if m.unit:
                kwargs.append(f"native_unit_of_measurement={m.unit!r}")
            if m.min_value is not None:
                kwargs.append(f"native_min_value={m.min_value!r}")
            if m.max_value is not None:
                kwargs.append(f"native_max_value={m.max_value!r}")
            if m.step:
                kwargs.append(f"native_step={m.step!r}")
        kwargs_str = ",\n        ".join(kwargs)
        lines.append(f"    {desc_name}(")
        lines.append(f"        {kwargs_str},")
        lines.append("    ),")
    lines.append(")")
    lines.append("")
    lines.append("")
    lines.append("async def async_setup_entry(")
    lines.append("    hass: HomeAssistant, entry: ProxonConfigEntry, async_add_entities: AddEntitiesCallback")
    lines.append(") -> None:")
    lines.append(f'    """Set up Proxon {platform} entities."""')
    lines.append("    coordinator = entry.runtime_data.coordinator")
    lines.append(
        f"    async_add_entities({entity_name}(coordinator, d) for d in {platform.upper()}_DESCRIPTIONS)"
    )
    lines.append("")
    return "\n".join(lines) + "\n"


CONFIG_FLOW_STRINGS: dict = {
    "step": {
        "user": {
            "description": "Verbindung zur Proxon-Anlage (Modbus TCP, z.B. über einen seriellen Gateway).",
            "data": {"host": "Host / IP-Adresse", "port": "Port", "slave": "Modbus-Slave-Adresse"},
        },
        "reconfigure": {
            "description": "Verbindungsdaten der Proxon-Anlage aktualisieren.",
            "data": {"host": "Host / IP-Adresse", "port": "Port", "slave": "Modbus-Slave-Adresse"},
        },
    },
    "error": {"cannot_connect": "Verbindung zur Anlage fehlgeschlagen. Adresse/Port/Slave-ID prüfen."},
    "abort": {"already_configured": "Diese Anlage ist bereits eingerichtet.", "reconfigure_successful": "Verbindungsdaten aktualisiert."},
}

CONFIG_FLOW_STRINGS_EN: dict = {
    "step": {
        "user": {
            "description": "Connection to the Proxon unit (Modbus TCP, e.g. via a serial gateway).",
            "data": {"host": "Host / IP address", "port": "Port", "slave": "Modbus slave address"},
        },
        "reconfigure": {
            "description": "Update the Proxon unit's connection details.",
            "data": {"host": "Host / IP address", "port": "Port", "slave": "Modbus slave address"},
        },
    },
    "error": {"cannot_connect": "Failed to connect. Please check address/port/slave id."},
    "abort": {"already_configured": "This unit is already configured.", "reconfigure_successful": "Connection details updated."},
}


def render_strings(all_meta: list[FieldMeta], config_flow: dict) -> str:
    import json

    entity: dict[str, dict[str, dict]] = {}
    for m in all_meta:
        if m.migrated:
            continue  # migrated entities use a literal `name`, no translation needed
        entity.setdefault(m.platform, {})[m.key] = {"name": m.name}
    doc = {"config": config_flow, "entity": entity}
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    wb = _load_workbook()
    holding_by_addr = parse_holding(wb)
    input_by_addr = parse_input(wb)
    legacy = parse_legacy_yaml()

    extra_holding = extra_holding_addresses(holding_by_addr)
    extra_input = extra_input_addresses(input_by_addr)

    # Extra registers must not re-include anything already migrated.
    legacy_holding_addrs = {e.address for e in legacy if e.register_space == "holding"}
    legacy_input_addrs = {e.address for e in legacy if e.register_space == "input"}
    extra_holding = [a for a in extra_holding if a not in legacy_holding_addrs]
    extra_input = [a for a in extra_input if a not in legacy_input_addrs]

    holding_components = build_holding_components(legacy, holding_by_addr, extra_holding)
    input_components = build_input_components(legacy, input_by_addr, extra_input)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "registers_holding.py").write_text(render_file(holding_components), encoding="utf-8")
    (OUT_DIR / "registers_input.py").write_text(render_file(input_components), encoding="utf-8")
    (OUT_DIR / "model.py").write_text(render_model(holding_components, input_components), encoding="utf-8")

    all_meta: list[FieldMeta] = [m for c in holding_components + input_components for m in c.meta]
    for platform in ("sensor", "switch", "binary_sensor", "number"):
        metas = [m for m in all_meta if m.platform == platform]
        if not metas:
            continue
        (OUT_DIR / f"{platform}.py").write_text(render_platform_file(platform, metas), encoding="utf-8")

    (OUT_DIR / "strings.json").write_text(render_strings(all_meta, CONFIG_FLOW_STRINGS), encoding="utf-8")
    translations_dir = OUT_DIR / "translations"
    translations_dir.mkdir(exist_ok=True)
    (translations_dir / "de.json").write_text(render_strings(all_meta, CONFIG_FLOW_STRINGS), encoding="utf-8")
    (translations_dir / "en.json").write_text(render_strings([], CONFIG_FLOW_STRINGS_EN), encoding="utf-8")

    n_holding = sum(len(c.fields) for c in holding_components)
    n_input = sum(len(c.fields) for c in input_components)
    print(f"holding: {n_holding} fields in {len(holding_components)} components "
          f"({len(legacy_holding_addrs)} migrated + {len(extra_holding)} new)")
    print(f"input:   {n_input} fields in {len(input_components)} components "
          f"({len(legacy_input_addrs)} migrated + {len(extra_input)} new)")
    for platform in ("sensor", "switch", "binary_sensor", "number"):
        n = len([m for m in all_meta if m.platform == platform])
        print(f"{platform}: {n} entities")


if __name__ == "__main__":
    sys.exit(main())
