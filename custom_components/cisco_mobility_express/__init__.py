"""The Cisco Mobility Express integration."""

from ciscomobilityexpress.ciscome import CiscoMobilityExpress
from ciscomobilityexpress.exceptions import CiscoMELoginError

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import PLATFORMS
from .coordinator import (
    CONNECTION_ERRORS,
    CiscoMEConfigEntry,
    CiscoMEDataUpdateCoordinator,
)


def create_controller(data: dict) -> CiscoMobilityExpress:
    """Connect and log in to the controller (blocking)."""
    return CiscoMobilityExpress(
        data[CONF_HOST],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data[CONF_SSL],
        data[CONF_VERIFY_SSL],
    )


async def async_setup_entry(hass: HomeAssistant, entry: CiscoMEConfigEntry) -> bool:
    """Set up Cisco Mobility Express from a config entry."""
    try:
        controller = await hass.async_add_executor_job(create_controller, entry.data)
    except CiscoMELoginError as err:
        raise ConfigEntryAuthFailed(err.message) from err
    except CONNECTION_ERRORS as err:
        raise ConfigEntryNotReady(f"Unable to connect to controller: {err}") from err

    coordinator = CiscoMEDataUpdateCoordinator(hass, entry, controller)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CiscoMEConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
