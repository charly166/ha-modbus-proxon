"""Constants for the Proxon integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "proxon"

CONF_SLAVE = "slave"

DEFAULT_PORT = 502
DEFAULT_SLAVE = 41

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
]
