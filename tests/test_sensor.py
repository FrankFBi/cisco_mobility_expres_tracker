"""Tests for client devices and their diagnostic sensors."""

from collections import namedtuple
from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cisco_mobility_express.const import CONF_ALL_IPV6, DOMAIN
from custom_components.cisco_mobility_express.sensor import _join_addresses
from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, SensorDeviceClass
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
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


WlcDevice = namedtuple("WlcDevice", ["macaddr", "clId", "SS", "ipv6"])
WLC_PHONE = WlcDevice(PHONE.macaddr, "frank-phone", -52, ["2001:db8::20", "fe80::1"])


async def test_signal_strength_sensor(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """SS becomes a signal strength sensor in dBm."""
    mock_controller.return_value.get_associated_devices.return_value = [WLC_PHONE]
    mock_config_entry.add_to_hass(hass)
    _register_trackers(hass, mock_config_entry)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = _sensor_state(hass, PHONE_MAC, "signal_strength")
    assert state.state == "-52"
    assert state.attributes["unit_of_measurement"] == SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    assert state.attributes["device_class"] == SensorDeviceClass.SIGNAL_STRENGTH
    assert not _sensor_state(hass, PHONE_MAC, "ipv6")


async def test_ipv6_sensor_follows_option(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The IPv6 sensor exists only while all IPv6 addresses are fetched."""
    mock_controller.return_value.get_associated_devices.return_value = [WLC_PHONE]
    mock_config_entry.add_to_hass(hass)
    _register_trackers(hass, mock_config_entry)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    hass.config_entries.async_update_entry(mock_config_entry, options={CONF_ALL_IPV6: True})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _sensor_state(hass, PHONE_MAC, "ipv6").state == "2001:db8::20, fe80::1"

    hass.config_entries.async_update_entry(mock_config_entry, options={CONF_ALL_IPV6: False})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not er.async_get(hass).async_get_entity_id(SENSOR_DOMAIN, DOMAIN, f"{PHONE_MAC}_ipv6")


def test_join_addresses_limit() -> None:
    """A long address list is cut at a separator within 255 characters."""
    addresses = [f"2001:db8::{i:x}" for i in range(40)]
    joined = _join_addresses(addresses)
    assert len(joined) <= 255
    assert joined.split(", ") == addresses[: len(joined.split(", "))]
    assert _join_addresses([]) is None
