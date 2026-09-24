"""Config flow for the Proxon integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)
from modbus_connection.tmodbus import connect_tcp

from .const import (
    CONF_HAS_HNB,
    CONF_HNB_NAME,
    CONF_SLAVE,
    CONF_ZBP_NAME,
    CONF_ZONE_COUNT,
    CONF_ZONE_NAMES,
    DEFAULT_HNB_NAME,
    DEFAULT_PORT,
    DEFAULT_SLAVE,
    DEFAULT_ZBP_NAME,
    DEFAULT_ZONE_COUNT,
    DOMAIN,
    MAX_ZONE_COUNT,
)
from .model import ProxonDevice
from .util import slugify

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


def _zone_names_schema(has_hnb: bool, zone_count: int, defaults: dict[str, Any]) -> vol.Schema:
    schema: dict[Any, Any] = {
        vol.Required(CONF_ZBP_NAME, default=defaults.get(CONF_ZBP_NAME, DEFAULT_ZBP_NAME)): TextSelector(),
    }
    if has_hnb:
        schema[vol.Required(CONF_HNB_NAME, default=defaults.get(CONF_HNB_NAME, DEFAULT_HNB_NAME))] = TextSelector()
    existing_names = defaults.get(CONF_ZONE_NAMES, [])
    for i in range(1, zone_count + 1):
        default = existing_names[i - 1] if i - 1 < len(existing_names) else f"Zone {i}"
        schema[vol.Required(f"zone_name_{i}", default=default)] = TextSelector()
    return vol.Schema(schema)


class ProxonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Proxon.

    Three steps: connection (host/port/slave, probed live), zone counts (is a
    HNBP installed, how many NBPn zones), and zone names (one text field per
    configured zone). The same steps are reused for reconfigure.
    """

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._data: dict[str, Any] = {}

    def _is_reconfigure(self) -> bool:
        return self.source == "reconfigure"

    async def _async_probe(self, data: dict[str, Any]) -> None:
        """Verify we can talk to the device using a short-lived connection.

        We open our own connection directly via modbus-connection rather
        than Home Assistant Core's `modbus` integration - see __init__.py
        for why - and close it again immediately after the probe.
        """
        connection = await connect_tcp(data[CONF_HOST], port=int(data[CONF_PORT]))
        try:
            unit = connection.for_unit(int(data[CONF_SLAVE]))
            device = ProxonDevice(unit)
            # A cheap, always-present register block: confirms the slave answers at all.
            await device.zbp.async_update()
        finally:
            await connection.close()

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
            zbp_name = user_input[CONF_ZBP_NAME]
            hnb_name = user_input.get(CONF_HNB_NAME)
            zone_names = [user_input[f"zone_name_{i}"] for i in range(1, zone_count + 1)]

            all_names = [zbp_name, *([hnb_name] if has_hnb else []), *zone_names]
            slugs = [slugify(n) for n in all_names]
            if len(set(slugs)) != len(slugs):
                errors["base"] = "duplicate_zone_names"
            else:
                self._data[CONF_ZBP_NAME] = zbp_name
                if has_hnb:
                    self._data[CONF_HNB_NAME] = hnb_name
                else:
                    self._data.pop(CONF_HNB_NAME, None)
                self._data[CONF_ZONE_NAMES] = zone_names

                if self._is_reconfigure():
                    return self.async_update_reload_and_abort(self._get_reconfigure_entry(), data=self._data)
                return self.async_create_entry(title="HA Proxon FWT 2.0 Modbus", data=self._data)

        return self.async_show_form(
            step_id="zone_names",
            data_schema=_zone_names_schema(has_hnb, zone_count, defaults),
            errors=errors,
        )
