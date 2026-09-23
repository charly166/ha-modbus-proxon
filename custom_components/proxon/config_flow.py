"""Config flow for the Proxon integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.modbus import ModbusTcpParams, async_get_temporary_unit
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import CONF_SLAVE, DEFAULT_PORT, DEFAULT_SLAVE, DOMAIN
from .model import ProxonDevice

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
            NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_SLAVE, default=DEFAULT_SLAVE): NumberSelector(
            NumberSelectorConfig(min=1, max=247, mode=NumberSelectorMode.BOX)
        ),
    }
)


class ProxonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Proxon."""

    VERSION = 1

    async def _async_probe(self, data: dict[str, Any]) -> None:
        """Verify we can talk to the device without permanently opening a connection."""
        params = ModbusTcpParams(host=data[CONF_HOST], port=int(data[CONF_PORT]))
        async with async_get_temporary_unit(self.hass, params, int(data[CONF_SLAVE])) as unit:
            device = ProxonDevice(unit)
            # A cheap, always-present register: confirms the slave answers at all.
            await device.lueftung.async_update()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:{user_input[CONF_SLAVE]}"
            )
            self._abort_if_unique_id_configured()
            try:
                await self._async_probe(user_input)
            except Exception:
                _LOGGER.exception("Failed to connect to the Proxon Modbus unit")
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="Proxon", data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle re-configuration (e.g. the device's IP address changed)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._async_probe(user_input)
            except Exception:
                _LOGGER.exception("Failed to connect to the Proxon Modbus unit")
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(), data=user_input
                )

        return self.async_show_form(step_id="reconfigure", data_schema=STEP_USER_SCHEMA, errors=errors)
