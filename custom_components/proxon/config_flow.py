"""Config flow for the Proxon integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    AreaSelector,
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from modbus_connection import ModbusTcpParams

from .const import (
    CONF_HAS_HNB,
    CONF_HNB_NAME,
    CONF_HNB_PTCS,
    CONF_SLAVE,
    CONF_ZBP_NAME,
    CONF_ZBP_PTCS,
    CONF_ZONE_COUNT,
    CONF_ZONE_NAMES,
    CONF_ZONE_PTCS,
    DEFAULT_PORT,
    DEFAULT_SLAVE,
    DEFAULT_ZONE_COUNT,
    DOMAIN,
    MAX_PTC,
    MAX_ZONE_COUNT,
)
from .model import ProxonDevice
from .zones import ptcs_from_value

_LOGGER = logging.getLogger(__name__)

STEP_CONNECTION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            NumberSelector(NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)),
            vol.Coerce(int),
        ),
        vol.Required(CONF_SLAVE, default=DEFAULT_SLAVE): vol.All(
            NumberSelector(NumberSelectorConfig(min=1, max=247, mode=NumberSelectorMode.BOX)),
            vol.Coerce(int),
        ),
    }
)


def _zones_count_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HAS_HNB, default=defaults.get(CONF_HAS_HNB, True)): BooleanSelector(),
            vol.Required(CONF_ZONE_COUNT, default=defaults.get(CONF_ZONE_COUNT, DEFAULT_ZONE_COUNT)): vol.All(
                NumberSelector(NumberSelectorConfig(min=0, max=MAX_ZONE_COUNT, mode=NumberSelectorMode.BOX)),
                vol.Coerce(int),
            ),
        }
    )


def _area_field(key: str, default: str | None) -> vol.Marker:
    """A Required() marker with a default only if we actually have one -
    AreaSelector has no sensible universal fallback to guess at."""
    return vol.Required(key, default=default) if default is not None else vol.Required(key)


def _optional_area_field(key: str, default: str | None) -> vol.Marker:
    """Like _area_field(), but Optional() - left empty means this NBPn slot
    isn't physically installed (see zones_from_entry_data() in zones.py,
    which skips any zone_name_i that's missing/empty). Lets installations
    with gaps in their NBP numbering - e.g. NBP1-3 and NBP5-6 but no NBP4 -
    be configured without inventing a fake room for the missing slot."""
    return vol.Optional(key, default=default) if default is not None else vol.Optional(key)


def _ptc_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[{"value": str(n), "label": f"K{n}"} for n in range(1, MAX_PTC + 1)],
            multiple=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _optional_ptc_field(key: str, default: object) -> vol.Marker:
    """Optional multi-select of PTC module channels (K1-K10) for the Heizelement-Status
    binary_sensor - left empty means that zone gets no such entity. Unlike
    the Area, there's no sensible default to guess (see ZoneInfo.ptcs)."""
    stored = [str(n) for n in ptcs_from_value(default)]
    return vol.Optional(key, default=stored) if stored else vol.Optional(key)


# Form layout: one framed section per control panel (ZBP, HNBP, NBP1..NBPx), each
# with its Area and PTC multi-select, so it's obvious which PTCs belong to which
# room. The stored config entry data is unchanged (zbp_name/zone_names/...).
# Section keys double as the fallback heading if a translation is missing, so
# they read like the final label (no underscores, upper case).
SECTION_ZBP = "ZBP"
SECTION_HNB = "HNBP"
FIELD_AREA = "area"
FIELD_PTCS = "ptcs"


def _nbp_section_key(i: int) -> str:
    return f"NBP{i}"


def _panel_section(area_field: vol.Marker, ptc_default: object) -> section:
    return section(
        vol.Schema(
            {
                area_field: AreaSelector(),
                _optional_ptc_field(FIELD_PTCS, ptc_default): _ptc_selector(),
            }
        ),
        {"collapsed": False},
    )


def _zone_names_schema(has_hnb: bool, zone_count: int, defaults: dict[str, Any]) -> vol.Schema:
    """One framed section per panel: its Home Assistant Area (AreaSelector, not
    free text - so the zone and the Area used elsewhere in HA for the same room
    stay in sync) plus an optional PTC multi-select for the Heizelement-Status
    binary_sensor."""
    schema: dict[Any, Any] = {
        vol.Required(SECTION_ZBP): _panel_section(
            _area_field(FIELD_AREA, defaults.get(CONF_ZBP_NAME)),
            defaults.get(CONF_ZBP_PTCS, defaults.get("zbp_relay")),
        )
    }
    if has_hnb:
        schema[vol.Required(SECTION_HNB)] = _panel_section(
            _area_field(FIELD_AREA, defaults.get(CONF_HNB_NAME)),
            defaults.get(CONF_HNB_PTCS, defaults.get("hnb_relay")),
        )
    existing_names = defaults.get(CONF_ZONE_NAMES, [])
    existing_ptcs = defaults.get(CONF_ZONE_PTCS, defaults.get("zone_relays", []))
    for i in range(1, zone_count + 1):
        area_default = existing_names[i - 1] if i - 1 < len(existing_names) else None
        ptc_default = existing_ptcs[i - 1] if i - 1 < len(existing_ptcs) else None
        schema[vol.Required(_nbp_section_key(i))] = _panel_section(
            _optional_area_field(FIELD_AREA, area_default), ptc_default
        )
    return vol.Schema(schema)


class ProxonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Proxon.

    Three steps: connection (host/port/slave, probed live), zone counts (is a
    HNBP installed, how many NBPn zones), and zone names (one Home Assistant
    Area picker per configured zone). The same steps are reused for
    reconfigure.
    """

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._data: dict[str, Any] = {}

    def _is_reconfigure(self) -> bool:
        return self.source == "reconfigure"

    async def _async_probe(self, data: dict[str, Any]) -> None:
        """Verify we can talk to the device.

        The connection is borrowed from Home Assistant Core's `modbus`
        integration for the duration of the probe (shared if already open).
        """
        params = ModbusTcpParams(host=data[CONF_HOST], port=int(data[CONF_PORT]))
        async with async_get_temporary_unit(self.hass, params, int(data[CONF_SLAVE])) as unit:
            device = ProxonDevice(unit)
            # A cheap, always-present register block: confirms the slave answers at all.
            await device.zbp.async_update()

    async def _async_step_connection(self, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        defaults = dict(self._get_reconfigure_entry().data) if self._is_reconfigure() else {}
        if user_input is not None:
            try:
                await self._async_probe(user_input)
            except Exception:
                _LOGGER.exception("Failed to connect to the Proxon Modbus unit")
                errors["base"] = "cannot_connect"
            else:
                self._data.update(user_input)
                if not self._is_reconfigure():
                    await self.async_set_unique_id(
                        f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:{user_input[CONF_SLAVE]}"
                    )
                    self._abort_if_unique_id_configured()
                return await self.async_step_zones_count()

        step_id = "reconfigure" if self._is_reconfigure() else "user"
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(STEP_CONNECTION_SCHEMA, defaults),
            errors=errors,
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """First step of a fresh setup."""
        return await self._async_step_connection(user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """First step when reconfiguring an existing entry."""
        return await self._async_step_connection(user_input)

    async def async_step_zones_count(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """How many zones (Bedienteile) are installed."""
        defaults = dict(self._get_reconfigure_entry().data) if self._is_reconfigure() else {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_zone_names()

        return self.async_show_form(
            step_id="zones_count",
            data_schema=self.add_suggested_values_to_schema(_zones_count_schema(defaults), defaults),
        )

    async def async_step_zone_names(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """One name per configured zone."""
        has_hnb = self._data[CONF_HAS_HNB]
        zone_count = self._data[CONF_ZONE_COUNT]
        defaults = dict(self._get_reconfigure_entry().data) if self._is_reconfigure() else {}
        errors: dict[str, str] = {}

        if user_input is not None:
            zbp_in = user_input.get(SECTION_ZBP, {})
            hnb_in = user_input.get(SECTION_HNB, {})
            nbp_in = [user_input.get(_nbp_section_key(i), {}) for i in range(1, zone_count + 1)]

            zbp_name = zbp_in[FIELD_AREA]
            hnb_name = hnb_in.get(FIELD_AREA)
            zbp_ptcs = list(ptcs_from_value(zbp_in.get(FIELD_PTCS)))
            hnb_ptcs = list(ptcs_from_value(hnb_in.get(FIELD_PTCS)))
            # None for any NBPn left empty - that slot isn't installed (gaps in
            # the numbering, e.g. NBP1-3 + NBP5-6 but no NBP4, are valid).
            zone_names = [panel.get(FIELD_AREA) or None for panel in nbp_in]
            # Empty list for any zone without assigned PTCs - that zone simply
            # gets no Heizelement-Status binary_sensor.
            zone_ptcs = [list(ptcs_from_value(panel.get(FIELD_PTCS))) for panel in nbp_in]

            all_areas = [zbp_name, *([hnb_name] if has_hnb else []), *(n for n in zone_names if n is not None)]
            all_ptcs = [*zbp_ptcs, *(hnb_ptcs if has_hnb else []), *(p for ptcs in zone_ptcs for p in ptcs)]
            if len(set(all_areas)) != len(all_areas):
                errors["base"] = "duplicate_zone_names"
            elif len(set(all_ptcs)) != len(all_ptcs):
                # A PTC heating element is wired to exactly one room.
                errors["base"] = "duplicate_ptcs"
            else:
                self._data[CONF_ZBP_NAME] = zbp_name
                self._data[CONF_ZBP_PTCS] = zbp_ptcs
                if has_hnb:
                    self._data[CONF_HNB_NAME] = hnb_name
                    self._data[CONF_HNB_PTCS] = hnb_ptcs
                else:
                    self._data.pop(CONF_HNB_NAME, None)
                    self._data.pop(CONF_HNB_PTCS, None)
                self._data[CONF_ZONE_NAMES] = zone_names
                self._data[CONF_ZONE_PTCS] = zone_ptcs
                for legacy in ("zbp_relay", "hnb_relay", "zone_relays"):
                    self._data.pop(legacy, None)

                if self._is_reconfigure():
                    return self.async_update_reload_and_abort(self._get_reconfigure_entry(), data=self._data)
                return self.async_create_entry(title="HA Proxon FWT 2.0 Modbus", data=self._data)

        return self.async_show_form(
            step_id="zone_names",
            data_schema=_zone_names_schema(has_hnb, zone_count, defaults),
            errors=errors,
        )
