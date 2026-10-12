"""Button entities for the Proxon integration.

Hand-written: Schnellstart der Intensivlüftung (15/30/45 Minuten) und "Intensivlüftung
starten" mit der in der Zahl "Intensivlüftung Dauer" eingestellten Dauer, siehe
intensivlueftung.py.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ProxonConfigEntry
from .intensivlueftung import (
    PRESET_DESCRIPTIONS,
    START_DESCRIPTION,
    ProxonIntensivlueftungButton,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ProxonConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Proxon button entities."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            *(ProxonIntensivlueftungButton(coordinator, d) for d in PRESET_DESCRIPTIONS),
            ProxonIntensivlueftungButton(coordinator, START_DESCRIPTION),
        ]
    )
