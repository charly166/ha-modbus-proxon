"""Betriebsart select entity for the Proxon integration.

Hand-written (not generated): it is the only `select` entity, driven by the
`proxon_betriebsart` field on the generated `Lueftung` component (see
registers_holding.py) - a genuinely writable register the legacy proxon.yaml
could only expose as a read-only sensor (the old YAML `modbus:` platform has
no `select` platform).
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ProxonConfigEntry
from .entity import ProxonEntity, ProxonEntityDescription

# Excel: "Betriebsart (0=Aus, 1=EcoSommer, 2=EcoWinter, 9=Test)" - not contiguous.
BETRIEBSART_OPTIONS = {
    0: "aus",
    1: "eco_sommer",
    2: "eco_winter",
    9: "test",
}
BETRIEBSART_VALUES = {v: k for k, v in BETRIEBSART_OPTIONS.items()}


@dataclass(frozen=True, kw_only=True)
class ProxonSelectEntityDescription(SelectEntityDescription, ProxonEntityDescription):
    """Entity description for a Proxon register-backed select."""


class ProxonBetriebsartSelect(ProxonEntity, SelectEntity):
    """Betriebsart: Aus / EcoSommer / EcoWinter / Test."""

    entity_description: ProxonSelectEntityDescription

    @property
    def current_option(self) -> str | None:
        return BETRIEBSART_OPTIONS.get(self._value)

    async def async_select_option(self, option: str) -> None:
        await self._async_write(BETRIEBSART_VALUES[option])


BETRIEBSART_DESCRIPTION = ProxonSelectEntityDescription(
    key="proxon_betriebsart",
    component="lueftung",
    field="proxon_betriebsart",
    name="Proxon Betriebsart",
    has_entity_name=False,
    options=list(BETRIEBSART_VALUES),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ProxonConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Proxon Betriebsart select entity."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([ProxonBetriebsartSelect(coordinator, BETRIEBSART_DESCRIPTION)])
