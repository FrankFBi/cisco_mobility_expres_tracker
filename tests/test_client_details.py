"""Tests for IP and SSID details from the classic WLC client detail page."""

from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from requests.exceptions import ConnectionError as RequestsConnectionError

from custom_components.cisco_mobility_express.client_details import parse_client_details
from custom_components.cisco_mobility_express.const import (
    DETAILS_INTERVAL,
    DOMAIN,
    SCAN_INTERVAL,
)
from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

DETAIL_HTML = (Path(__file__).parent / "fixtures" / "mobile_station_detail.html").read_text()
LIST_HTML = '<INPUT TYPE="hidden" NAME="csrf_token" SIZE="32" VALUE="TOKEN">'

# Shape of a client-table.html record from a real WLC.
WlcDevice = namedtuple("WlcDevice", ["macaddr", "clId", "SS", "AP", "controller"])
CLIENT = WlcDevice("94:27:70:d0:09:75", "94:27:70:d0:09:75", -73, "AP5", "192.168.10.150")
ENTITY = "device_tracker.94_27_70_d0_09_75"


def _with(ipv4: str, ipv6: str, ssid: str = "Bieling") -> str:
    html = DETAIL_HTML.replace('VALUE="10.104.28.157"', f'VALUE="{ipv4}"')
    html = html.replace("fddb:0:104:28:9627:70ff:fed0:975, fe80::9627:70ff:fed0:975, ", ipv6)
    return html.replace(
        'name="ms_ssid" class="statictextboxlist" readonly disabled SIZE="42" '
        'MAXLENGTH="32" VALUE="Bieling"',
        f'name="ms_ssid" VALUE="{ssid}"',
    )


def test_parse_ipv4_and_ipv6() -> None:
    """A dual-stack client reports IPv4 as its ip."""
    assert parse_client_details(DETAIL_HTML) == {
        "ip": "10.104.28.157",
        "ipv4": "10.104.28.157",
        "ipv6": ["fddb:0:104:28:9627:70ff:fed0:975", "fe80::9627:70ff:fed0:975"],
        "SSID": "Bieling",
    }


def test_parse_ipv6_only() -> None:
    """An IPv6-only client uses its global (not link-local) address."""
    details = parse_client_details(_with("0.0.0.0", "fe80::1, 2001:db8::5, "))
    assert details["ip"] == "2001:db8::5"
    assert "ipv4" not in details
    assert details["ipv6"] == ["fe80::1", "2001:db8::5"]


def test_parse_no_ip() -> None:
    """A client without addresses only gets its SSID."""
    assert parse_client_details(_with("Unknown", "")) == {"SSID": "Bieling"}
    assert parse_client_details(_with("0.0.0.0", "", ssid="")) == {}


def _detail_session(controller: MagicMock) -> MagicMock:
    session = controller.return_value.session
    session.get.return_value = MagicMock(status_code=200, text=LIST_HTML)
    session.post.return_value = MagicMock(status_code=200, text=DETAIL_HTML)
    controller.return_value.get_associated_devices.return_value = [CLIENT]
    return session


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        DEVICE_TRACKER_DOMAIN,
        DOMAIN,
        CLIENT.macaddr,
        config_entry=entry,
        suggested_object_id="94_27_70_d0_09_75",
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_details_added_to_entity(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """IP and SSID are merged in and refreshed every DETAILS_INTERVAL."""
    session = _detail_session(mock_controller)
    await _setup(hass, mock_config_entry)

    state = hass.states.get(ENTITY)
    assert state.attributes["ip"] == "10.104.28.157"
    assert state.attributes["ipv6"] == [
        "fddb:0:104:28:9627:70ff:fed0:975",
        "fe80::9627:70ff:fed0:975",
    ]
    assert state.attributes["SSID"] == "Bieling"
    assert state.attributes["AP"] == "AP5"
    post = session.post.call_args
    assert post.args[0] == "http://192.168.10.150/screens/apf/mobile_station_list.html"
    assert post.kwargs["data"]["csrf_token"] == "TOKEN"
    assert post.kwargs["data"]["selected_ms_addr"] == "94:27:70:d0:09:75"

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.post.call_count == 1
    assert hass.states.get(ENTITY).attributes["SSID"] == "Bieling"

    session.post.return_value = MagicMock(status_code=200, text=_with("0.0.0.0", "2001:db8::5"))
    freezer.tick(DETAILS_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.post.call_count == 2
    assert hass.states.get(ENTITY).attributes["ip"] == "2001:db8::5"


async def test_details_unsupported(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Controllers without the detail page are not asked again."""
    mock_controller.return_value.get_associated_devices.return_value = [CLIENT]
    session = mock_controller.return_value.session
    await _setup(hass, mock_config_entry)

    state = hass.states.get(ENTITY)
    assert state.state == "home"
    assert "ip" not in state.attributes
    assert "SSID" not in state.attributes

    freezer.tick(DETAILS_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.get.call_count == 1
    session.post.assert_not_called()


async def test_details_error_keeps_tracking(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A failing detail request does not affect presence."""
    session = _detail_session(mock_controller)
    session.post.side_effect = RequestsConnectionError()
    await _setup(hass, mock_config_entry)

    state = hass.states.get(ENTITY)
    assert state.state == "home"
    assert "ip" not in state.attributes
