"""Setup, polling and device tracker tests."""

from unittest.mock import MagicMock

from ciscomobilityexpress.exceptions import CiscoMELoginError
from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from requests.exceptions import ConnectionError as RequestsConnectionError

from custom_components.cisco_mobility_express.const import DOMAIN, SCAN_INTERVAL
from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_HOME, STATE_NOT_HOME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import LAPTOP, PHONE

PHONE_ENTITY = "device_tracker.frank_phone"
LAPTOP_ENTITY = "device_tracker.aa_bb_cc_dd_ee_02"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    # Tracker entities for MACs unknown to other integrations are created
    # disabled, so pre-register them as enabled.
    registry = er.async_get(hass)
    for mac in (PHONE.macaddr, LAPTOP.macaddr):
        registry.async_get_or_create(
            DEVICE_TRACKER_DOMAIN,
            DOMAIN,
            mac.lower(),
            config_entry=entry,
            original_name=None,
            suggested_object_id=("frank_phone" if mac == PHONE.macaddr else "aa_bb_cc_dd_ee_02"),
        )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_and_tracking(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Clients are home while associated and not_home once they leave."""
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    phone = hass.states.get(PHONE_ENTITY)
    assert phone.state == STATE_HOME
    assert phone.attributes["ip"] == "192.168.10.20"
    assert phone.attributes["mac"] == "aa:bb:cc:dd:ee:01"
    assert phone.attributes["host_name"] == "frank-phone"
    assert phone.attributes["SSID"] == "home"
    assert hass.states.get(LAPTOP_ENTITY).state == STATE_HOME

    mock_controller.return_value.get_associated_devices.return_value = [LAPTOP]
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    phone = hass.states.get(PHONE_ENTITY)
    assert phone.state == STATE_NOT_HOME
    assert phone.attributes["host_name"] == "frank-phone"
    assert "SSID" not in phone.attributes

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_new_client_creates_entity(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A client that appears later gets a (disabled by default) entity."""
    mock_controller.return_value.get_associated_devices.return_value = []
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    mock_controller.return_value.get_associated_devices.return_value = [PHONE]
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    entries = er.async_entries_for_config_entry(er.async_get(hass), mock_config_entry.entry_id)
    assert [e.unique_id for e in entries] == ["aa:bb:cc:dd:ee:01"]


async def test_setup_not_ready(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Connection errors retry setup later."""
    mock_controller.side_effect = RequestsConnectionError()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_auth_failed(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Bad credentials start a reauth flow."""
    mock_controller.side_effect = CiscoMELoginError("bad")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_poll_failure_marks_unavailable(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed poll makes entities unavailable instead of not_home."""
    await _setup(hass, mock_config_entry)
    mock_controller.return_value.get_associated_devices.side_effect = TypeError()
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(PHONE_ENTITY).state == "unavailable"
