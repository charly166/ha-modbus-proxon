"""Native climate entities for the Proxon integration.

Hand-written (not generated): one per configured zone (ZBP + HNBP/NBPn),
replacing the external `hass-template-climate` + automations.yaml setup this
integration's author previously used (see climates.yaml/automations.yaml in
the repository root, kept for reference).

- ZBP sets an *absolute* target temperature (10-30°C) directly.
- HNBP/NBPn zones don't have an absolute setpoint register: their target
  temperature is their own Mitteltemperatur (running average) plus an
  Offset-Temperatur the device lets you adjust ±3°C. Both current_temperature
  and target_temperature are computed live from the latest poll - no
  automation/template is needed to keep them in sync, unlike the old setup.
- hvac_mode mirrors/controls the zone's own Heizelement switch (which also
  still exists as its own switch.* entity, unchanged).
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_TENTHS, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ProxonConfigEntry
from .entity import ProxonEntity, ProxonEntityDescription
from .zones import OFFSET_MAX, OFFSET_MIN, ZBP_SOLL_MAX, ZBP_SOLL_MIN, ZoneInfo


@dataclass(frozen=True, kw_only=True)
class ProxonZoneClimateDescription(ClimateEntityDescription, ProxonEntityDescription):
    """Entity description for a Proxon zone climate entity."""

    zone: ZoneInfo


class ProxonZoneClimate(ProxonEntity, ClimateEntity):
    """One zone's heating control, as a native climate entity."""

    entity_description: ProxonZoneClimateDescription
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_TENTHS
    _attr_hvac_modes = (HVACMode.OFF, HVACMode.HEAT)
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    def __init__(self, coordinator, description: ProxonZoneClimateDescription) -> None:
        super().__init__(coordinator, description)
        self._zone = description.zone
        if self._zone.kind == "zbp":
            self._attr_min_temp = ZBP_SOLL_MIN
            self._attr_max_temp = ZBP_SOLL_MAX
            self._attr_target_temperature_step = 0.5
        else:
            self._attr_target_temperature_step = 1.0

    @property
    def _input_component(self):
        if self._zone.kind == "zbp":
            return self.coordinator.device.zbp_input
        return self.coordinator.device.nb_zones_input.zones[self._zone.zone_index]

    @property
    def current_temperature(self) -> float | None:
        return self._input_component.ist_temperatur

    @property
    def target_temperature(self) -> float | None:
        if self._zone.kind == "zbp":
            return self._value  # `field` is "soll_temperatur", an absolute value
        return self._component.mitteltemperatur + self._value  # `field` is "offset_temperatur"

    @property
    def min_temp(self) -> float:
        if self._zone.kind == "zbp":
            return self._attr_min_temp
        return self._component.mitteltemperatur + OFFSET_MIN

    @property
    def max_temp(self) -> float:
        if self._zone.kind == "zbp":
            return self._attr_max_temp
        return self._component.mitteltemperatur + OFFSET_MAX

    async def async_set_temperature(self, **kwargs) -> None:
        target = kwargs.get(ATTR_TEMPERATURE)
        if target is None:
            return
        if self._zone.kind == "zbp":
            value = max(ZBP_SOLL_MIN, min(ZBP_SOLL_MAX, target))
        else:
            offset = target - self._component.mitteltemperatur
            value = max(OFFSET_MIN, min(OFFSET_MAX, offset))
        await self._async_write(value)

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self._component.heizelement else HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._component.write("heizelement", hvac_mode == HVACMode.HEAT)
        await self.coordinator.async_request_refresh()


def _zone_descriptions(zones: list[ZoneInfo]) -> list[ProxonZoneClimateDescription]:
    out: list[ProxonZoneClimateDescription] = []
    for zone in zones:
        component = "zbp" if zone.kind == "zbp" else "nb_zones_holding"
        field = "soll_temperatur" if zone.kind == "zbp" else "offset_temperatur"
        out.append(
            ProxonZoneClimateDescription(
                zone=zone,
                key=f"proxon_climate_{zone.slug}",
                component=component,
                field=field,
                zone_index=zone.zone_index,
                # No name of its own: this is the zone device's main entity,
                # so Home Assistant shows just the device name ("Büro", ...).
                has_entity_name=True,
                name=None,
            )
        )
    return out


async def async_setup_entry(
    hass: HomeAssistant, entry: ProxonConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up one climate entity per configured zone."""
    coordinator = entry.runtime_data.coordinator
    descriptions = _zone_descriptions(entry.runtime_data.zones)
    async_add_entities(ProxonZoneClimate(coordinator, d) for d in descriptions)
