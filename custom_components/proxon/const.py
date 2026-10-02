"""Constants for the Proxon integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "proxon"

CONF_SLAVE = "slave"
CONF_HAS_HNB = "has_hnb"
CONF_ZONE_COUNT = "zone_count"
CONF_ZBP_NAME = "zbp_name"
CONF_HNB_NAME = "hnb_name"
CONF_ZONE_NAMES = "zone_names"
# Optional per-zone PTC assignment (multi-select, PTC1-PTC10 = relays R1-R10
# of Heizmodul 1, Input 574) for the Heizelement-Status binary_sensor - see
# heizelement_status.py. A zone can have several PTCs, but each PTC belongs to
# at most one zone. Unlike zone_index (Modbus NBP address order), which PTC is
# wired to which room is up to the installer, so it can't be derived and must
# be entered per installation.
CONF_ZBP_PTCS = "zbp_ptcs"
CONF_HNB_PTCS = "hnb_ptcs"
CONF_ZONE_PTCS = "zone_ptcs"

DEFAULT_PORT = 502
DEFAULT_SLAVE = 41
DEFAULT_ZONE_COUNT = 8
MAX_ZONE_COUNT = 19
MAX_PTC = 10

# Holding 438 "Modbus schreiben erlaubt": 0=Nein, 1=Einige, 2=Ja/alle. Registers like
# Tastensperre only accept writes at the highest level (see tastensperre.py).
WRITE_LEVEL_ALL = 2

# Single poll interval for the whole device. The legacy proxon.yaml used many
# different scan_intervals (5-30s) per entity; modbus-connection polls a
# Component's fields together in as few requests as possible, so one shared
# interval for the whole device is simpler and still responsive.
UPDATE_INTERVAL_SECONDS = 15

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.CLIMATE,
]
