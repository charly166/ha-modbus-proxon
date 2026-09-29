"""Derived Gerätefilter-Restlaufzeit sensors.

Hand-written (not generated): these are computed from two registers on the
`Geraetefilter` component (Standzeit in months, Nutzzeit in hours - see
registers_holding.py), not a 1:1 register mapping, so they don't fit the
generic ProxonSensorEntityDescription(component, field) pattern the rest of
sensor.py/binary_sensor.py use. Replaces the template sensor the integration
author previously used (see templates.yaml in the repository root, kept for
reference only) to convert "Nutzzeit" into a remaining-days figure.

Only imports from .entity (not .sensor/.binary_sensor) to avoid a circular
import, since the generated sensor.py/binary_sensor.py import from here.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime

from .entity import ProxonEntity, ProxonEntityDescription

# The register only states whole months (Excel: "Filterwechselintervall",
# 3-8 range) - 30 days/month is an approximation, there is no more precise
# figure available from the device.
DAYS_PER_MONTH = 30
FILTER_REMINDER_THRESHOLD_DAYS = 14


def _filter_tage(component) -> int | None:
    """Elapsed filter runtime in whole days, or None if the source is unknown.

    proxon_nutzzeit_fwt_geraetefilter is already in true hours (registers_holding.py
    applies the real hardware's x2 scale), so this is just hours -> days.
    """
    nutzzeit_stunden = component.proxon_nutzzeit_fwt_geraetefilter
    if nutzzeit_stunden is None:
        return None
    return round(nutzzeit_stunden / 24)


def _filter_resttage(component) -> int | None:
    """Remaining filter life in whole days, or None if either source value is unknown."""
    standzeit_monate = component.proxon_standzeit_fwt_geraetefilter
    filter_tage = _filter_tage(component)
    if standzeit_monate is None or filter_tage is None:
        return None
    resttage = standzeit_monate * DAYS_PER_MONTH - filter_tage
    return max(0, round(resttage))


@dataclass(frozen=True, kw_only=True)
class _FilterSensorDescription(SensorEntityDescription, ProxonEntityDescription):
    """Entity description for a computed filter-life sensor."""


class ProxonFilterTageSensor(ProxonEntity, SensorEntity):
    """Seit dem letzten Filterwechsel vergangene Tage (Nutzzeit umgerechnet)."""

    entity_description: _FilterSensorDescription

    @property
    def native_value(self) -> int | None:
        return _filter_tage(self._component)


FILTER_TAGE_DESCRIPTION = _FilterSensorDescription(
    key="proxon_filter_tage",
    component="geraetefilter",
    field="proxon_nutzzeit_fwt_geraetefilter",  # not read directly - see native_value above
    has_entity_name=True,
    translation_key="proxon_filter_tage",
    native_unit_of_measurement=UnitOfTime.DAYS,
    device_class=SensorDeviceClass.DURATION,
    state_class=SensorStateClass.TOTAL_INCREASING,
)


class ProxonFilterResttageSensor(ProxonEntity, SensorEntity):
    """Restlaufzeit des Gerätefilters in Tagen (Standzeit - Filter Tage)."""

    entity_description: _FilterSensorDescription

    @property
    def native_value(self) -> int | None:
        return _filter_resttage(self._component)


FILTER_RESTTAGE_DESCRIPTION = _FilterSensorDescription(
    key="proxon_filter_resttage",
    component="geraetefilter",
    field="proxon_nutzzeit_fwt_geraetefilter",  # not read directly - see native_value above
    has_entity_name=True,
    translation_key="proxon_filter_resttage",
    # Not EntityCategory.DIAGNOSTIC: this is the actionable "when do I need to
    # act" figure, not internal diagnostic detail - keep it a regular sensor so
    # it appears on the device's main entity list, not tucked away under
    # "Diagnose".
    native_unit_of_measurement=UnitOfTime.DAYS,
    device_class=SensorDeviceClass.DURATION,
    state_class=SensorStateClass.MEASUREMENT,
)


@dataclass(frozen=True, kw_only=True)
class _FilterBinarySensorDescription(BinarySensorEntityDescription, ProxonEntityDescription):
    """Entity description for the computed filter-reminder binary sensor."""


class ProxonFilterReminderBinarySensor(ProxonEntity, BinarySensorEntity):
    """An, wenn der Gerätefilter innerhalb der nächsten 14 Tage fällig wird."""

    entity_description: _FilterBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        resttage = _filter_resttage(self._component)
        if resttage is None:
            return None
        return resttage <= FILTER_REMINDER_THRESHOLD_DAYS


FILTER_REMINDER_DESCRIPTION = _FilterBinarySensorDescription(
    key="proxon_filter_wechsel_faellig",
    component="geraetefilter",
    field="proxon_nutzzeit_fwt_geraetefilter",  # not read directly - see is_on above
    has_entity_name=True,
    translation_key="proxon_filter_wechsel_faellig",
    device_class=BinarySensorDeviceClass.PROBLEM,
)
