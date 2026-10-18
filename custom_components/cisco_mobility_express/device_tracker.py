"""Device tracker entities for clients of a Cisco Mobility Express controller."""

from datetime import datetime
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_HOSTNAME,
    ATTR_MAC,
    DOMAIN,
    IP_ADDRESS_KEYS,
    PRUNE_INTERVAL,
    STALE_TRACKER_AGE,
)
from .coordinator import CiscoMEConfigEntry, CiscoMEDataUpdateCoordinator

LAST_SEEN_SAVE_DELAY = 60


def last_seen_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, float]]:
    """Return the store with the last time each client was seen."""
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.last_seen")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CiscoMEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a tracker entity for every client seen by the controller."""
    coordinator = entry.runtime_data
    tracked: set[str] = set()

    # Restore clients seen before that are not currently associated.
    restored: list[CiscoMEClient] = []
    for reg_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if reg_entry.platform == DOMAIN and reg_entry.unique_id not in tracked:
            tracked.add(reg_entry.unique_id)
            restored.append(
                CiscoMEClient(coordinator, reg_entry.unique_id, reg_entry.original_name)
            )
    async_add_entities(restored)

    @callback
    def async_add_new_clients() -> None:
        new: list[CiscoMEClient] = []
        for mac, client in coordinator.data.items():
            if mac not in tracked:
                tracked.add(mac)
                new.append(CiscoMEClient(coordinator, mac, client.get(ATTR_HOSTNAME)))
        async_add_entities(new)

    store = last_seen_store(hass, entry.entry_id)
    last_seen: dict[str, float] = await store.async_load() or {}

    @callback
    def async_mark_seen() -> None:
        now = dt_util.utcnow().timestamp()
        last_seen.update(dict.fromkeys(coordinator.data, now))
        store.async_delay_save(lambda: last_seen, LAST_SEEN_SAVE_DELAY)

    @callback
    def async_prune_stale_trackers(_: datetime | None = None) -> None:
        """Remove disabled trackers of clients not seen for STALE_TRACKER_AGE.

        A removed client is no longer in `tracked`, so it gets a new tracker
        when it connects again. Clients seen before this ran start counting now.
        """
        now = dt_util.utcnow().timestamp()
        registry = er.async_get(hass)
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if reg_entry.platform != DOMAIN or not reg_entry.disabled:
                continue
            mac = reg_entry.unique_id
            if now - last_seen.setdefault(mac, now) > STALE_TRACKER_AGE.total_seconds():
                registry.async_remove(reg_entry.entity_id)
                tracked.discard(mac)
                del last_seen[mac]
        store.async_delay_save(lambda: last_seen, LAST_SEEN_SAVE_DELAY)

    @callback
    def async_coordinator_updated() -> None:
        async_mark_seen()
        async_add_new_clients()

    async_coordinator_updated()
    async_prune_stale_trackers()
    entry.async_on_unload(coordinator.async_add_listener(async_coordinator_updated))
    entry.async_on_unload(
        async_track_time_interval(
            hass, async_prune_stale_trackers, PRUNE_INTERVAL, cancel_on_shutdown=True
        )
    )


class CiscoMEClient(CoordinatorEntity[CiscoMEDataUpdateCoordinator], ScannerEntity):
    """A wireless client associated to the controller."""

    def __init__(
        self,
        coordinator: CiscoMEDataUpdateCoordinator,
        mac: str,
        name: str | None,
    ) -> None:
        """Initialize the client entity."""
        super().__init__(coordinator)
        self._attr_mac_address = mac
        self._last_name = name or None

    @property
    def _client(self) -> dict[str, Any] | None:
        return self.coordinator.data.get(self._attr_mac_address)

    @property
    def is_connected(self) -> bool:
        """Return true if the client is associated to the controller."""
        return self._client is not None

    @property
    def hostname(self) -> str | None:
        """Return the client name reported by the controller."""
        if (client := self._client) and client.get(ATTR_HOSTNAME):
            self._last_name = client[ATTR_HOSTNAME]
        return self._last_name

    @property
    def name(self) -> str:
        """Return the entity name."""
        return self.hostname or self._attr_mac_address

    @property
    def ip_address(self) -> str | None:
        """Return the client IP address, if the controller reports it."""
        if client := self._client:
            for key in IP_ADDRESS_KEYS:
                if client.get(key):
                    return client[key]
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the raw client details (e.g. SSID, PT, devtype)."""
        if client := self._client:
            return {k: v for k, v in client.items() if k not in (ATTR_MAC, ATTR_HOSTNAME)}
        return None
