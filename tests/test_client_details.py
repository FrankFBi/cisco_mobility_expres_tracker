"""Tests for IP and SSID details from the classic WLC client detail page."""

from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from requests.exceptions import ConnectionError as RequestsConnectionError

from custom_components.cisco_mobility_express.client_details import (
    fetch_client_details,
    parse_client_details,
    parse_client_list,
)
from custom_components.cisco_mobility_express.const import (
    CONF_ALL_IPV6,
    CONF_IPV6_POLLING_INTERVAL,
    DOMAIN,
    IPV6_POLLING_INTERVAL,
    SCAN_INTERVAL,
)
from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import ENTRY_DATA

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
    """Unlisted clients get their detail page every IPV6_POLLING_INTERVAL."""
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
    freezer.tick(IPV6_POLLING_INTERVAL)
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

    freezer.tick(IPV6_POLLING_INTERVAL)
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


async def test_client_list_read_every_poll(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """IP and SSID from the client list follow the polling interval."""
    session = _detail_session(mock_controller)
    session.get.return_value = MagicMock(status_code=200, text=LISTED_HTML)
    await _setup(hass, mock_config_entry)
    assert hass.states.get(ENTITY).attributes["ip"] == "10.104.28.157"

    session.get.return_value = MagicMock(
        status_code=200, text=LIST_HTML + _list_row(0, "94:27:70:d0:09:75", "10.104.28.200")
    )
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ENTITY).attributes["ip"] == "10.104.28.200"
    assert session.get.call_count == 2
    session.post.assert_not_called()


async def test_details_interval_option(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The IPv6 polling interval comes from the entry options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ENTRY_DATA[CONF_HOST],
        data=ENTRY_DATA,
        options={CONF_IPV6_POLLING_INTERVAL: 1},
    )
    session = _detail_session(mock_controller)
    await _setup(hass, entry)
    assert session.post.call_count == 1

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.post.call_count == 1

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.post.call_count == 2


def _list_row(
    index: int, mac: str, ip: str, ssid: str = "Bieling", protocol: str = "802.11ac(5 GHz)"
) -> str:
    """Return a client row as served by a real WLC's client list."""
    return (
        f'<INPUT type="text" name="1.{index}.2.ms_addr" class="statictextboxlink" readonly '
        f'SIZE="18" MAXLENGTH="18" VALUE="{mac}">\n'
        f'<INPUT type=TEXT name="1.{index}.2.ms_ipaddr" class="statictextboxlist" readonly '
        f'SIZE="46" MAXLENGTH="46" VALUE="{ip}">\n'
        f'<INPUT type="TEXT" name="1.{index}.2.lrad_name" VALUE="AP3-Garage">\n'
        f'<INPUT type="text" name="1.{index}.2.ms_profile" VALUE="{ssid}">\n'
        f'<INPUT type="text" name="1.{index}.2.ms_ssid" class="statictextboxlist" readonly '
        f'SIZE="21" MAXLENGTH="32" VALUE="{ssid}">\n'
        f'<INPUT type="TEXT" name="1.{index}.2.dot11_type" class="statictextboxlist" readonly '
        f'SIZE="15" MAXLENGTH="15" VALUE="{protocol}">\n'
    )


LISTED_HTML = (
    LIST_HTML
    + _list_row(0, "94:27:70:D0:09:75", "10.104.28.157")
    + _list_row(1, "38:8a:06:db:78:08", "fddb:0:104:28::8", protocol="802.11n(2.4 GHz)")
)


def test_parse_client_list() -> None:
    """IP and SSID of every client come from the list page."""
    assert parse_client_list(LISTED_HTML) == {
        "94:27:70:d0:09:75": {
            "ip": "10.104.28.157",
            "ipv4": "10.104.28.157",
            "SSID": "Bieling",
            "FB": "5GHz",
        },
        "38:8a:06:db:78:08": {
            "ip": "fddb:0:104:28::8",
            "ipv6": ["fddb:0:104:28::8"],
            "SSID": "Bieling",
            "FB": "2.4GHz",
        },
    }


async def test_details_from_client_list(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Listed clients need no detail page request."""
    session = _detail_session(mock_controller)
    session.get.return_value = MagicMock(status_code=200, text=LISTED_HTML)
    await _setup(hass, mock_config_entry)

    state = hass.states.get(ENTITY)
    assert state.attributes["ip"] == "10.104.28.157"
    assert state.attributes["SSID"] == "Bieling"
    assert state.attributes["FB"] == "5GHz"
    assert "ipv6" not in state.attributes
    assert session.get.call_count == 1
    session.post.assert_not_called()


async def test_controller_band_wins(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The band from the client list only fills in a missing FB."""
    session = _detail_session(mock_controller)
    session.get.return_value = MagicMock(status_code=200, text=LISTED_HTML)
    device = namedtuple("WlcDeviceFB", [*WlcDevice._fields, "FB"])
    mock_controller.return_value.get_associated_devices.return_value = [device(*CLIENT, "2.4GHz")]
    await _setup(hass, mock_config_entry)

    assert hass.states.get(ENTITY).attributes["FB"] == "2.4GHz"


async def test_all_ipv6_option(
    hass: HomeAssistant,
    mock_controller: MagicMock,
) -> None:
    """With all IPv6 enabled, each client's detail page is read too."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ENTRY_DATA[CONF_HOST],
        data=ENTRY_DATA,
        options={CONF_ALL_IPV6: True},
    )
    session = _detail_session(mock_controller)
    session.get.return_value = MagicMock(status_code=200, text=LISTED_HTML)
    await _setup(hass, entry)

    assert session.post.call_count == 1
    assert hass.states.get(ENTITY).attributes["ipv6"] == [
        "fddb:0:104:28:9627:70ff:fed0:975",
        "fe80::9627:70ff:fed0:975",
    ]
    assert hass.states.get(ENTITY).attributes["FB"] == "5GHz"


async def test_link_local_only_uses_detail_page(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An IPv6-only client listed with just fe80:: gets its global address."""
    session = _detail_session(mock_controller)
    session.get.return_value = MagicMock(
        status_code=200, text=LIST_HTML + _list_row(0, "94:27:70:d0:09:75", "fe80::1")
    )
    session.post.return_value = MagicMock(
        status_code=200, text=_with("0.0.0.0", "fe80::1, 2001:db8::5, ")
    )
    await _setup(hass, mock_config_entry)

    assert session.post.call_count == 1
    state = hass.states.get(ENTITY)
    assert state.attributes["ip"] == "2001:db8::5"
    assert state.attributes["ipv6"] == ["fe80::1", "2001:db8::5"]


def _total(count: int) -> str:
    return f'<INPUT type="hidden" name="total_entries" VALUE="{count}">'


def test_client_list_pages() -> None:
    """Every page of a paged client list is read, one GET per page."""
    pages = {
        None: LIST_HTML
        + _total(3)
        + _list_row(0, "aa:aa:aa:aa:aa:01", "10.0.0.1")
        + _list_row(1, "aa:aa:aa:aa:aa:02", "10.0.0.2"),
        2: LIST_HTML + _total(3) + _list_row(0, "aa:aa:aa:aa:aa:03", "10.0.0.3"),
    }
    session = MagicMock()
    session.get.side_effect = lambda url, params=None: MagicMock(
        status_code=200, text=pages[(params or {}).get("pgInd")]
    )
    listed, details = fetch_client_details(session, "http://wlc", [])
    assert {mac: d["ip"] for mac, d in listed.items()} == {
        "aa:aa:aa:aa:aa:01": "10.0.0.1",
        "aa:aa:aa:aa:aa:02": "10.0.0.2",
        "aa:aa:aa:aa:aa:03": "10.0.0.3",
    }
    assert session.get.call_count == 2
    assert session.get.call_args.kwargs["params"] == {"pgInd": 2}
    assert details == {}


def test_client_list_single_page() -> None:
    """A list that fits on one page costs one request."""
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=LISTED_HTML + _total(2))
    listed, _ = fetch_client_details(session, "http://wlc", [])
    assert len(listed) == 2
    assert session.get.call_count == 1
