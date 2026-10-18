"""Data update coordinator for Cisco Mobility Express."""

from datetime import datetime
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
from homeassistant.util import dt as dt_util

from .client_details import ClientDetailsUnavailable, fetch_client_details
from .const import ATTR_MAC, DETAILS_INTERVAL, DOMAIN, SCAN_INTERVAL

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
        self._details_supported = True
        self._details: dict[str, tuple[datetime, dict[str, Any]]] = {}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch associated clients, keyed by normalized MAC address."""
        try:
            devices = await self.hass.async_add_executor_job(self.controller.get_associated_devices)
        except CiscoMELoginError as err:
            raise ConfigEntryAuthFailed(err.message) from err
        except CONNECTION_ERRORS as err:
            raise UpdateFailed(f"Error communicating with controller: {err}") from err

        _LOGGER.debug("Cisco Mobility Express controller returned: %s", devices)
        clients = {
            format_mac(device[ATTR_MAC]): device for device in (dev._asdict() for dev in devices)
        }
        if self._details_supported:
            await self._async_update_details(clients)
        return clients

    async def _async_update_details(self, clients: dict[str, dict[str, Any]]) -> None:
        """Merge IP and SSID details, refreshing each client every DETAILS_INTERVAL."""
        now = dt_util.utcnow()
        self._details = {mac: d for mac, d in self._details.items() if mac in clients}
        due = [
            mac
            for mac in clients
            if mac not in self._details or now - self._details[mac][0] >= DETAILS_INTERVAL
        ]
        if due:
            try:
                fetched = await self.hass.async_add_executor_job(
                    fetch_client_details,
                    self.controller.session,
                    self.controller.host_api_url,
                    due,
                )
            except ClientDetailsUnavailable as err:
                _LOGGER.info("Client IP and SSID details are not available: %s", err)
                self._details_supported = False
                return
            except RequestException as err:
                _LOGGER.debug("Error fetching client details: %s", err)
            else:
                self._details.update({mac: (now, d) for mac, d in fetched.items()})

        for mac, (_, details) in self._details.items():
            for key, value in details.items():
                clients[mac].setdefault(key, value)
