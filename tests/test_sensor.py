"""Tests for client devices and their diagnostic sensors."""

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cisco_mobility_express.const import DOMAIN
from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import LAPTOP, PHONE

PHONE_MAC = PHONE.macaddr.lower()


def _register_trackers(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Register the phone tracker enabled and the laptop tracker disabled."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        DEVICE_TRACKER_DOMAIN, DOMAIN, PHONE_MAC, config_entry=entry, original_name="frank-phone"
    )
    registry.async_get_or_create(
        DEVICE_TRACKER_DOMAIN,
        DOMAIN,
        LAPTOP.macaddr,
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )


def _sensor_state(hass: HomeAssistant, mac: str, key: str):
    entity_id = er.async_get(hass).async_get_entity_id(SENSOR_DOMAIN, DOMAIN, f"{mac}_{key}")
    return entity_id and hass.states.get(entity_id)


async def test_device_and_sensors_for_enabled_tracker(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Only enabled trackers get a device with diagnostic sensors."""
    mock_config_entry.add_to_hass(hass)
    _register_trackers(hass, mock_config_entry)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    devices = dr.async_get(hass)
    device = devices.async_get_device_by_connection(
        (dr.CONNECTION_NETWORK_MAC, PHONE_MAC), mock_config_entry.entry_id
    )
    assert device.name == "frank-phone"
    assert not devices.async_get_device_by_connection(
        (dr.CONNECTION_NETWORK_MAC, LAPTOP.macaddr), mock_config_entry.entry_id
    )

    entities = er.async_get(hass)
    tracker_id = entities.async_get_entity_id(DEVICE_TRACKER_DOMAIN, DOMAIN, PHONE_MAC)
    assert entities.async_get(tracker_id).device_id == device.id

    assert _sensor_state(hass, PHONE_MAC, "ssid").state == "home"
    assert _sensor_state(hass, PHONE_MAC, "protocol").state == "802.11ac"
    assert _sensor_state(hass, PHONE_MAC, "access_point").state == "unknown"
    sensor = entities.async_get(
        entities.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, f"{PHONE_MAC}_ssid")
    )
    assert sensor.device_id == device.id
    assert sensor.entity_category is EntityCategory.DIAGNOSTIC
    assert not _sensor_state(hass, LAPTOP.macaddr, "ssid")


async def test_device_removed_when_tracker_disabled(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Disabling a tracker drops its device on the next reload."""
    mock_config_entry.add_to_hass(hass)
    _register_trackers(hass, mock_config_entry)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entities = er.async_get(hass)
    entities.async_update_entity(
        entities.async_get_entity_id(DEVICE_TRACKER_DOMAIN, DOMAIN, PHONE_MAC),
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert not dr.async_get(hass).async_get_device_by_connection(
        (dr.CONNECTION_NETWORK_MAC, PHONE_MAC), mock_config_entry.entry_id
    )
