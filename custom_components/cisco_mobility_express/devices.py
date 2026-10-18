"""Device registry entries for clients whose tracker is enabled."""

from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN


@callback
def enabled_client_macs(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str]:
    """Return {mac: name} for the enabled client trackers of this entry."""
    return {
        reg.unique_id: reg.name or reg.original_name or reg.unique_id
        for reg in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if reg.domain == DEVICE_TRACKER_DOMAIN and reg.platform == DOMAIN and not reg.disabled
    }


@callback
def async_sync_client_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create a device per enabled tracker and drop ours from the others.

    The tracker entity links itself to a registered device with its MAC, so
    the devices must exist before the device_tracker platform is set up.
    """
    registry = dr.async_get(hass)
    enabled = enabled_client_macs(hass, entry)
    for mac, name in enabled.items():
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={(dr.CONNECTION_NETWORK_MAC, mac)},
            name=name,
        )
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        macs = {value for kind, value in device.connections if kind == dr.CONNECTION_NETWORK_MAC}
        if macs and not macs & enabled.keys():
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
