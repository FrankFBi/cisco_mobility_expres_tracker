"""Config flow for Cisco Mobility Express."""

from collections.abc import Mapping
import logging
from typing import Any

from ciscomobilityexpress.exceptions import CiscoMELoginError
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from . import create_controller
from .const import (
    CONF_DETAILS_INTERVAL,
    CONF_STALE_TRACKER_AGE,
    DEFAULT_SSL,
    DEFAULT_VERIFY_SSL,
    DETAILS_INTERVAL,
    DOMAIN,
    MAX_DETAILS_INTERVAL,
    MAX_SCAN_INTERVAL,
    MAX_STALE_TRACKER_AGE,
    MIN_DETAILS_INTERVAL,
    MIN_SCAN_INTERVAL,
    MIN_STALE_TRACKER_AGE,
    SCAN_INTERVAL,
    STALE_TRACKER_AGE,
)
from .coordinator import CONNECTION_ERRORS

_LOGGER = logging.getLogger(__name__)


def _number(minimum: int, maximum: int, unit: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            unit_of_measurement=unit,
            mode=NumberSelectorMode.BOX,
        )
    )


SCAN_INTERVAL_SELECTOR = _number(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL, "s")
DEFAULT_SCAN_INTERVAL = int(SCAN_INTERVAL.total_seconds())
DEFAULT_OPTIONS = {
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    CONF_DETAILS_INTERVAL: int(DETAILS_INTERVAL.total_seconds() // 60),
    CONF_STALE_TRACKER_AGE: STALE_TRACKER_AGE.days,
}

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SSL, default=DEFAULT_SSL): bool,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): SCAN_INTERVAL_SELECTOR,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL): SCAN_INTERVAL_SELECTOR,
        vol.Required(CONF_DETAILS_INTERVAL): _number(
            MIN_DETAILS_INTERVAL, MAX_DETAILS_INTERVAL, "min"
        ),
        vol.Required(CONF_STALE_TRACKER_AGE): _number(
            MIN_STALE_TRACKER_AGE, MAX_STALE_TRACKER_AGE, "d"
        ),
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class CiscoMEConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cisco Mobility Express."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return CiscoMEOptionsFlow()

    async def _async_validate(self, data: dict[str, Any]) -> str | None:
        """Try to log in to the controller and return an error key on failure."""
        try:
            await self.hass.async_add_executor_job(create_controller, data)
        except CiscoMELoginError:
            return "invalid_auth"
        except CONNECTION_ERRORS:
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(user_input[CONF_HOST].lower())
            self._abort_if_unique_id_configured()
            data = {k: v for k, v in user_input.items() if k != CONF_SCAN_INTERVAL}
            if not (error := await self._async_validate(data)):
                return self.async_create_entry(
                    title=data[CONF_HOST],
                    data=data,
                    options={
                        CONF_SCAN_INTERVAL: int(
                            user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                        )
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication after the controller rejected the credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, **user_input}
            if not (error := await self._async_validate(data)):
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                REAUTH_SCHEMA, {CONF_USERNAME: entry.data[CONF_USERNAME]}
            ),
            description_placeholders={CONF_HOST: entry.data[CONF_HOST]},
            errors=errors,
        )


class CiscoMEOptionsFlow(OptionsFlow):
    """Change the intervals of a configured controller."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the polling, details and cleanup settings."""
        if user_input is not None:
            return self.async_create_entry(data={k: int(v) for k, v in user_input.items()})
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, {**DEFAULT_OPTIONS, **self.config_entry.options}
            ),
        )
