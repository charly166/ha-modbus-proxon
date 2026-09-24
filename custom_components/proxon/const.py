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

DEFAULT_PORT = 502
DEFAULT_SLAVE = 41
DEFAULT_ZONE_COUNT = 8
MAX_ZONE_COUNT = 19

DEFAULT_ZBP_NAME = "Zentrale"
DEFAULT_HNB_NAME = "Hauptraum"

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
