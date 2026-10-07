"""Base entity + entity description for the Proxon integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProxonDataUpdateCoordinator
from .presentation import DEFAULT_DISABLED, GROUP_CATEGORY, look_for, rule_icon
from .util import object_id_for
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
    # Keyword-based fallback icons for entities without an explicit entry in
    # presentation.py; off for entities with their own icon logic (climate).
    _RULE_ICONS = True

    def __init__(self, coordinator: ProxonDataUpdateCoordinator, description: ProxonEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = description.key
        entry = coordinator.config_entry
        tags = getattr(entry.runtime_data, "register_tags", None)
        if tags is not None and (tag := self._register_tag()):
            tags[description.key] = tag
        zone = _zone_for(entry.runtime_data.zones, description.component, description.zone_index, description.key)
        self._in_zone = zone is not None
        self._apply_look(description)
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

    def _apply_look(self, description: ProxonEntityDescription) -> None:
        """Group (entity category) and icon from presentation.py."""
        look = look_for(description.key, description.translation_key)
        icon = look.icon if look else None
        if look and look.group is not None:
            self._attr_entity_category = GROUP_CATEGORY[look.group]
        if icon is None and self._RULE_ICONS and not description.icon and not getattr(description, "device_class", None):
            icon = rule_icon(description.key)
        if icon:
            self._attr_icon = icon
        if description.key in DEFAULT_DISABLED:
            self._attr_entity_registry_enabled_default = False

    def add_to_platform_start(self, hass, platform, parallel_updates) -> None:
        """Suggest a short ``<domain>.proxon_<name>`` entity_id for new central entities.

        Without this Home Assistant derives IDs from the device name
        (``sensor.system_ha_proxon_fwt_2_0_modbus_abtaudruck``); room entities keep
        that scheme, since their device name carries the room. Entities already in
        the registry keep their ID either way.
        """
        super().add_to_platform_start(hass, platform, parallel_updates)
        description = self.entity_description
        if self.entity_id is not None or self._in_zone or not description.has_entity_name:
            return
        registry = er.async_get(hass)
        if registry.async_get_entity_id(platform.domain, DOMAIN, description.key):
            return
        runtime = self.coordinator.config_entry.runtime_data
        name = self.name
        object_id = object_id_for(
            platform.domain,
            name if isinstance(name, str) else None,
            runtime.register_tags.get(description.key),
            lambda eid: eid in runtime.claimed_ids or registry.async_get(eid) is not None or hass.states.get(eid) is not None,
        )
        if object_id:
            self.entity_id = f"{platform.domain}.{object_id}"
            runtime.claimed_ids.add(self.entity_id)

    def _register_tag(self) -> str | None:
        """Modbus register of this entity's field in the register list's own
        notation: 3x0209 = input register 209, 4x0016 = holding register 16."""
        try:
            component = self._component
            address = component.resolved_fields[self.entity_description.field].address
            return f"{'3x' if component.register_space == 'input' else '4x'}{address:04d}"
        except (AttributeError, KeyError):
            return None

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
        try:
            await self._component.write(self.entity_description.field, value)
        except Exception as err:
            self.coordinator.record_write_error(self.entity_description.key, err)
            raise
        await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.component not in self.coordinator.data.failed
