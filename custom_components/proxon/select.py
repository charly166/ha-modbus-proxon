"""Select entities for the Proxon integration.

Hand-written (not generated): driven by writable registers the legacy
proxon.yaml could only expose as a read-only sensor (the old YAML `modbus:`
platform has no `select` platform) or that decode to a small enum of named
modes.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ProxonConfigEntry
from .entity import ProxonEntity, ProxonEntityDescription

# Confirmed by the user against their actual panel (not contiguous - matches
# the device firmware, not the Excel register list's "0=Aus, 1=EcoSommer,
# 2=EcoWinter, 9=Test" comment, which was misleading/outdated).
BETRIEBSART_OPTIONS = {
    0: "aus",
    1: "sommerbetrieb",
    2: "winterbetrieb",
    3: "eco_komfortbetrieb",
    4: "ofenbetrieb",
}
BETRIEBSART_VALUES = {v: k for k, v in BETRIEBSART_OPTIONS.items()}

# Excel (Holding 2002): "Betriebsart (0=AUS 1=AN)" - the T300
# (Trinkwasserwärmepumpe)'s own, separate operating mode, unrelated to the
# main unit's Betriebsart above. Earlier Excel versions listed more modes
# (Bedarf/Lüftungsstufe 1/2); the manufacturer's current documentation only
# has on/off.
T300_BETRIEBSART_OPTIONS = {
    0: "aus",
    1: "an",
}
T300_BETRIEBSART_VALUES = {v: k for k, v in T300_BETRIEBSART_OPTIONS.items()}


@dataclass(frozen=True, kw_only=True)
class ProxonSelectEntityDescription(SelectEntityDescription, ProxonEntityDescription):
    """Entity description for a Proxon register-backed select."""

    options_map: dict[int, str]


class ProxonEnumSelect(ProxonEntity, SelectEntity):
    """A select entity backed by a small integer-valued register."""

    entity_description: ProxonSelectEntityDescription

    @property
    def current_option(self) -> str | None:
        return self.entity_description.options_map.get(self._value)

    async def async_select_option(self, option: str) -> None:
        values = {v: k for k, v in self.entity_description.options_map.items()}
        await self._async_write(values[option])


BETRIEBSART_DESCRIPTION = ProxonSelectEntityDescription(
    key="proxon_betriebsart",
    component="lueftung",
    field="proxon_betriebsart",
    name="Proxon Betriebsart",
    has_entity_name=False,
    translation_key="proxon_betriebsart",
    options=list(BETRIEBSART_VALUES),
    options_map=BETRIEBSART_OPTIONS,
)

T300_BETRIEBSART_DESCRIPTION = ProxonSelectEntityDescription(
    key="proxon_betriebsart_t300",
    component="t300_warmwasser",
    field="betriebsart_t300",
    has_entity_name=True,
    translation_key="proxon_betriebsart_t300",
    options=list(T300_BETRIEBSART_VALUES),
    options_map=T300_BETRIEBSART_OPTIONS,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ProxonConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Proxon select entities."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            ProxonEnumSelect(coordinator, BETRIEBSART_DESCRIPTION),
            ProxonEnumSelect(coordinator, T300_BETRIEBSART_DESCRIPTION),
        ]
    )
