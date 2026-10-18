"""Data update coordinator for Cisco Mobility Express."""

import logging
from typing import Any

from ciscomobilityexpress.ciscome import CiscoMobilityExpress
from ciscomobilityexpress.exceptions import CiscoMELoginError, CiscoMEPageNotFoundError
from requests.exceptions import RequestException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import ATTR_MAC, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type CiscoMEConfigEntry = ConfigEntry[CiscoMEDataUpdateCoordinator]

# The library returns [] for unexpected HTTP status codes, which then surfaces
# as TypeError/KeyError when the response is indexed.
CONNECTION_ERRORS = (
    RequestException,
    CiscoMEPageNotFoundError,
    KeyError,
    TypeError,
    ValueError,
)


class CiscoMEDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Poll the controller for associated wireless clients."""

    config_entry: CiscoMEConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: CiscoMEConfigEntry,
        controller: CiscoMobilityExpress,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.controller = controller

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch associated clients, keyed by normalized MAC address."""
        try:
            devices = await self.hass.async_add_executor_job(self.controller.get_associated_devices)
        except CiscoMELoginError as err:
            raise ConfigEntryAuthFailed(err.message) from err
        except CONNECTION_ERRORS as err:
            raise UpdateFailed(f"Error communicating with controller: {err}") from err

        _LOGGER.debug("Cisco Mobility Express controller returned: %s", devices)
        return {
            format_mac(device[ATTR_MAC]): device for device in (dev._asdict() for dev in devices)
        }
