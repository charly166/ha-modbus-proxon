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
# Optional per-zone PTC relay number (1-20: R1-R10 -> Heizmodul 1/Holding
# Input 574, R11-R20 -> Heizmodul 2/Input 583) for the Heizelement-Status
# binary_sensor - see heizelement_status.py. Unlike zone_index (Modbus NBP
# address order), the relay number is purely a function of how the
# installer physically wired the PTC relays, so it can't be derived or
# defaulted and must be entered per installation.
CONF_ZBP_RELAY = "zbp_relay"
CONF_HNB_RELAY = "hnb_relay"
CONF_ZONE_RELAYS = "zone_relays"

DEFAULT_PORT = 502
DEFAULT_SLAVE = 41
DEFAULT_ZONE_COUNT = 8
MAX_ZONE_COUNT = 19
MAX_RELAY = 20

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
