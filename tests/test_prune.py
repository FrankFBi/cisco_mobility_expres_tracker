"""Tests for removing disabled trackers of clients that are gone."""

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.cisco_mobility_express.const import CONF_STALE_TRACKER_AGE, DOMAIN
from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import ENTRY_DATA, LAPTOP, PHONE

PHONE_MAC = PHONE.macaddr.lower()


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up with the phone tracker enabled and the laptop tracker disabled."""
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(DEVICE_TRACKER_DOMAIN, DOMAIN, PHONE_MAC, config_entry=entry)
    registry.async_get_or_create(
        DEVICE_TRACKER_DOMAIN,
        DOMAIN,
        LAPTOP.macaddr,
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


def _tracker(hass: HomeAssistant, mac: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(DEVICE_TRACKER_DOMAIN, DOMAIN, mac)


async def test_stale_disabled_tracker_removed_and_recreated(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A disabled tracker unseen for 30 days is removed and comes back on reconnect."""
    await _setup(hass, mock_config_entry)
    controller = mock_controller.return_value

    controller.get_associated_devices.return_value = []
    await _advance(hass, freezer, timedelta(minutes=1))
    await _advance(hass, freezer, timedelta(days=29))
    assert _tracker(hass, LAPTOP.macaddr)

    await _advance(hass, freezer, timedelta(days=2))
    assert not _tracker(hass, LAPTOP.macaddr)
    assert _tracker(hass, PHONE_MAC), "enabled trackers are kept"

    controller.get_associated_devices.return_value = [LAPTOP]
    await _advance(hass, freezer, timedelta(minutes=1))
    entry = er.async_get(hass).async_get(_tracker(hass, LAPTOP.macaddr))
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_connected_disabled_tracker_kept(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A disabled tracker of a client that keeps connecting is not removed."""
    await _setup(hass, mock_config_entry)
    for _ in range(4):
        await _advance(hass, freezer, timedelta(days=10))
    assert _tracker(hass, LAPTOP.macaddr)


async def test_unknown_disabled_tracker_gets_grace_period(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Disabled trackers from before the cleanup existed start counting at setup."""
    mock_controller.return_value.get_associated_devices.return_value = [PHONE]
    await _setup(hass, mock_config_entry)
    await _advance(hass, freezer, timedelta(days=29))
    assert _tracker(hass, LAPTOP.macaddr)
    await _advance(hass, freezer, timedelta(days=2))
    assert not _tracker(hass, LAPTOP.macaddr)


async def test_stale_tracker_age_option(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The stale tracker age comes from the entry options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ENTRY_DATA[CONF_HOST],
        data=ENTRY_DATA,
        options={CONF_STALE_TRACKER_AGE: 2},
    )
    mock_controller.return_value.get_associated_devices.return_value = [PHONE]
    await _setup(hass, entry)
    await _advance(hass, freezer, timedelta(days=1))
    assert _tracker(hass, LAPTOP.macaddr)
    await _advance(hass, freezer, timedelta(days=2))
    assert not _tracker(hass, LAPTOP.macaddr)
