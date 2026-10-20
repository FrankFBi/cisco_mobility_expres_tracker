"""Data update coordinator for Cisco Mobility Express."""

from datetime import datetime, timedelta
import logging
from typing import Any

from ciscomobilityexpress.ciscome import CiscoMobilityExpress
from ciscomobilityexpress.exceptions import CiscoMELoginError, CiscoMEPageNotFoundError
from requests.exceptions import RequestException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client_details import ClientDetailsUnavailable, fetch_client_details, needs_detail_page
from .const import (
    ATTR_MAC,
    CONF_ALL_IPV6,
    CONF_IPV6_POLLING_INTERVAL,
    CONF_STALE_TRACKER_AGE,
    DOMAIN,
    IPV6_POLLING_INTERVAL,
    SCAN_INTERVAL,
    STALE_TRACKER_AGE,
)

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


def scan_interval(entry: ConfigEntry) -> timedelta:
    """Return the polling interval chosen for the entry."""
    return timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL.total_seconds()))


def ipv6_polling_interval(entry: ConfigEntry) -> timedelta:
    """Return how often each client's detail page is read for all IPv6 addresses."""
    return timedelta(
        minutes=entry.options.get(
            CONF_IPV6_POLLING_INTERVAL, IPV6_POLLING_INTERVAL.total_seconds() / 60
        )
    )


def stale_tracker_age(entry: ConfigEntry) -> timedelta:
    """Return how long a disabled tracker's client may be unseen before removal."""
    return timedelta(days=entry.options.get(CONF_STALE_TRACKER_AGE, STALE_TRACKER_AGE.days))


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
            update_interval=scan_interval(config_entry),
        )
        self.controller = controller
        self._details_supported = True
        self._listed: dict[str, dict[str, Any]] = {}
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
            format_mac(device[ATTR_MAC]): {
                key: value.strip() if isinstance(value, str) else value
                for key, value in device.items()
            }
            for device in (dev._asdict() for dev in devices)
        }
        if self._details_supported:
            await self._async_update_details(clients)
        return clients

    async def _async_update_details(self, clients: dict[str, dict[str, Any]]) -> None:
        """Merge IP and SSID from the client list, and detail pages when due."""
        now = dt_util.utcnow()
        refresh = ipv6_polling_interval(self.config_entry)
        all_ipv6 = self.config_entry.options.get(CONF_ALL_IPV6, False)
        self._details = {mac: d for mac, d in self._details.items() if mac in clients}
        due = [
            mac
            for mac in clients
            if mac not in self._details or now - self._details[mac][0] >= refresh
        ]
        try:
            self._listed, fetched = await self.hass.async_add_executor_job(
                fetch_client_details,
                self.controller.session,
                self.controller.host_api_url,
                due,
                all_ipv6,
            )
        except ClientDetailsUnavailable as err:
            _LOGGER.info("Client IP and SSID details are not available: %s", err)
            self._details_supported = False
            return
        except RequestException as err:
            _LOGGER.debug("Error fetching client details: %s", err)
        else:
            self._details.update({mac: (now, d) for mac, d in fetched.items()})

        for mac, client in clients.items():
            details = self._listed.get(mac, {})
            if (all_ipv6 or needs_detail_page(details)) and mac in self._details:
                details = {**details, **self._details[mac][1]}
            for key, value in details.items():
                client.setdefault(key, value)
