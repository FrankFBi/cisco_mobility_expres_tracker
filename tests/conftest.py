"""Fixtures for Cisco Mobility Express tests."""

from collections import namedtuple
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cisco_mobility_express.const import DOMAIN
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)

ENTRY_DATA = {
    CONF_HOST: "192.168.10.150",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "secret",
    CONF_SSL: False,
    CONF_VERIFY_SSL: True,
}

Device = namedtuple("Device", ["macaddr", "clId", "ip", "SSID", "PT", "controller"])

PHONE = Device(
    "AA:BB:CC:DD:EE:01", "frank-phone", "192.168.10.20", "home", "802.11ac  ", "192.168.10.150"
)
LAPTOP = Device("aa:bb:cc:dd:ee:02", "", "192.168.10.21", "home", "802.11ax", "192.168.10.150")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in all tests."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for the controller."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=ENTRY_DATA[CONF_HOST],
        unique_id=ENTRY_DATA[CONF_HOST],
        data=ENTRY_DATA,
    )


@pytest.fixture
def mock_controller() -> Generator[MagicMock]:
    """Patch the library controller class used by setup and the config flow."""
    with patch(
        "custom_components.cisco_mobility_express.CiscoMobilityExpress",
        autospec=True,
    ) as controller_cls:
        controller = controller_cls.return_value
        controller.is_logged_in.return_value = True
        controller.get_associated_devices.return_value = [PHONE, LAPTOP]
        # Mobility Express without the classic detail page by default.
        controller.host_api_url = "http://192.168.10.150"
        controller.session = MagicMock()
        controller.session.get.return_value = MagicMock(status_code=404, text="")
        yield controller_cls
