"""Base entity + entity description for the Proxon integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProxonDataUpdateCoordinator
from .zones import ZoneInfo

# Central, migrated sensors that physically sit on the ZBP (Zentralbedienpanel,
# registers 21/22) and so belong on the ZBP's zone device. Keyed by the
# description key = unique_id, so entity_ids/history stay unchanged.
ZBP_DEVICE_KEYS = frozenset({"proxon_co2_wohnzimmer", "proxon_luftfeuchte_wohnzimmer"})


def _zone_for(zones: list[ZoneInfo], component: str, zone_index: int | None, key: str = "") -> ZoneInfo | None:
    """Match an entity description back to the zone it belongs to, if any.

    ``zone_index`` (set only for "nb_zones_*" components) identifies an HNBP/
    NBPn zone; "zbp"/"zbp_input" (or a key in ZBP_DEVICE_KEYS) is always the
    one ZBP zone. Anything else is a central (non-zone) entity - returns None.
    """
    if zone_index is not None:
        return next((z for z in zones if z.kind == "nb" and z.zone_index == zone_index), None)
    if component in ("zbp", "zbp_input") or key in ZBP_DEVICE_KEYS:
        return next((z for z in zones if z.kind == "zbp"), None)
    return None


# T300 (Trinkwasserwärmepumpe) components - not a "zone" (no Area picker, not part
# of the dynamic HNBP/NBPn model), but still its own device rather than
# living on the central hub, per user feedback ("T300 wie ein eigener Raum").
# Names are the snake_case ProxonDevice attribute names from model.py.
T300_COMPONENTS = frozenset({"t300_warmwasser", "warmwasser_input", "heizstab_status", "t300_diagnose"})


@dataclass(frozen=True, kw_only=True)
class ProxonEntityDescription(EntityDescription):
    """Base description for every Proxon entity.

    ``component`` is the attribute name on ProxonDevice (see model.py),
    ``field`` is the attribute name on that Component (see registers_holding.py
    / registers_input.py, or zones.py for zone entities) that this entity
    reads (and, if writable, writes). ``zone_index`` is only set for entities
    that live on one instance of a repeating zone group (``component`` is then
    "nb_zones_holding" or "nb_zones_input", see zones.py) - None for
    single-instance components (including ZBP, which is its own component,
    not part of a repeating group).
    """

    component: str
    field: str
    zone_index: int | None = None


class ProxonEntity(CoordinatorEntity[ProxonDataUpdateCoordinator]):
    """Common base for all Proxon entities."""

    entity_description: ProxonEntityDescription
    _attr_should_poll = False

    def __init__(self, coordinator: ProxonDataUpdateCoordinator, description: ProxonEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = description.key
        entry = coordinator.config_entry
        zone = _zone_for(entry.runtime_data.zones, description.component, description.zone_index, description.key)
        if zone is not None:
            # One device per zone (room), so the device list shows "Büro",
            # "Wohnzimmer", etc. instead of everything being lumped under a
            # single "Proxon" device - entities then only need to carry their
            # function in their own name ("Ist-Temperatur"), since Home
            # Assistant prefixes it with the device name automatically.
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry.entry_id}_zone_{zone.slug}")},
                name=zone.name,
                manufacturer="Proxon",
                model="FWT2.0 Zone",
                suggested_area=zone.name,
            )
        elif description.component in T300_COMPONENTS:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry.entry_id}_t300")},
                name="T300",
                manufacturer="Proxon",
                model="T300 Trinkwasserwärmepumpe",
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry.entry_id)},
                name=entry.title,
                manufacturer="Proxon",
                model="FWT2.0",
            )

    @property
    def _component(self):
        comp = getattr(self.coordinator.device, self.entity_description.component)
        if self.entity_description.zone_index is not None:
            return comp.zones[self.entity_description.zone_index]
        return comp

    @property
    def _value(self):
        return getattr(self._component, self.entity_description.field)

    async def _async_write(self, value) -> None:
        await self._component.write(self.entity_description.field, value)
        await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.component not in self.coordinator.data.failed
