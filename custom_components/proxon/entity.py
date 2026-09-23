"""Base entity + entity description for the Proxon integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProxonDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class ProxonEntityDescription(EntityDescription):
    """Base description for every Proxon entity.

    ``component`` is the attribute name on ProxonDevice (see model.py),
    ``field`` is the attribute name on that Component (see registers_holding.py
    / registers_input.py) that this entity reads (and, if writable, writes).
    """

    component: str
    field: str


class ProxonEntity(CoordinatorEntity[ProxonDataUpdateCoordinator]):
    """Common base for all Proxon entities."""

    entity_description: ProxonEntityDescription
    _attr_should_poll = False

    def __init__(self, coordinator: ProxonDataUpdateCoordinator, description: ProxonEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = description.key
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Proxon",
            model="FWT2.0",
        )

    @property
    def _component(self):
        return getattr(self.coordinator.device, self.entity_description.component)

    @property
    def _value(self):
        return getattr(self._component, self.entity_description.field)

    async def _async_write(self, value) -> None:
        await self._component.write(self.entity_description.field, value)
        await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.component not in self.coordinator.data.failed
