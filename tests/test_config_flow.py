"""Config flow tests."""

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

from ciscomobilityexpress.exceptions import CiscoMELoginError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from requests.exceptions import ConnectionError as RequestsConnectionError

from custom_components.cisco_mobility_express.const import (
    CONF_ALL_IPV6,
    CONF_IPV6_POLLING_INTERVAL,
    CONF_STALE_TRACKER_AGE,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from .conftest import ENTRY_DATA


async def test_user_flow(hass: HomeAssistant, mock_controller: MagicMock) -> None:
    """A successful login creates an entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == ENTRY_DATA["host"]
    assert result["data"] == ENTRY_DATA
    assert result["options"] == {CONF_SCAN_INTERVAL: 30}
    assert result["result"].unique_id == ENTRY_DATA["host"]


async def test_user_flow_scan_interval(hass: HomeAssistant, mock_controller: MagicMock) -> None:
    """The polling interval is stored as an option and limited to 30-300 s."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {**ENTRY_DATA, CONF_SCAN_INTERVAL: 10}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_SCAN_INTERVAL: 120}
    )
    assert result["data"] == ENTRY_DATA
    assert result["options"] == {CONF_SCAN_INTERVAL: 120}


async def test_options_flow(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Changing the polling interval applies to the running coordinator."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.runtime_data.update_interval == timedelta(seconds=30)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 301}
        )

    def _input(**changes: Any) -> dict[str, Any]:
        values = {
            CONF_SCAN_INTERVAL: 300,
            CONF_STALE_TRACKER_AGE: 60,
            CONF_ALL_IPV6: True,
            CONF_IPV6_POLLING_INTERVAL: 15,
        } | changes
        return {
            CONF_SCAN_INTERVAL: values[CONF_SCAN_INTERVAL],
            CONF_STALE_TRACKER_AGE: values[CONF_STALE_TRACKER_AGE],
            "ipv6": {
                CONF_ALL_IPV6: values[CONF_ALL_IPV6],
                CONF_IPV6_POLLING_INTERVAL: values[CONF_IPV6_POLLING_INTERVAL],
            },
        }

    for invalid in (
        {CONF_IPV6_POLLING_INTERVAL: 0},
        {CONF_IPV6_POLLING_INTERVAL: 16},
        {CONF_STALE_TRACKER_AGE: 0},
        {CONF_STALE_TRACKER_AGE: 61},
    ):
        with pytest.raises(InvalidData):
            await hass.config_entries.options.async_configure(result["flow_id"], _input(**invalid))
    result = await hass.config_entries.options.async_configure(result["flow_id"], _input())
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {
        CONF_SCAN_INTERVAL: 300,
        CONF_IPV6_POLLING_INTERVAL: 15,
        CONF_STALE_TRACKER_AGE: 60,
        CONF_ALL_IPV6: True,
    }
    assert mock_config_entry.runtime_data.update_interval == timedelta(seconds=300)


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (CiscoMELoginError("bad"), "invalid_auth"),
        (RequestsConnectionError(), "cannot_connect"),
        (TypeError(), "cannot_connect"),
        (RuntimeError(), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, mock_controller: MagicMock, side_effect: Exception, error: str
) -> None:
    """Errors are shown and the flow can recover."""
    mock_controller.side_effect = side_effect
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_controller.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The same controller cannot be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reauth updates the stored credentials."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_controller.side_effect = CiscoMELoginError("bad")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    mock_controller.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new"
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_reconfigure(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reconfigure changes host and SSL settings and keeps an empty password."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    mock_controller.side_effect = RequestsConnectionError
    new = {
        CONF_HOST: " 192.168.10.151 ",
        CONF_USERNAME: "other",
        CONF_SSL: True,
        CONF_VERIFY_SSL: False,
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], new)
    assert result["errors"] == {"base": "cannot_connect"}

    mock_controller.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], new)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data == {
        CONF_HOST: "192.168.10.151",
        CONF_USERNAME: "other",
        CONF_PASSWORD: "secret",
        CONF_SSL: True,
        CONF_VERIFY_SSL: False,
    }
    assert mock_config_entry.unique_id == "192.168.10.151"
    assert mock_config_entry.title == "192.168.10.151"
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_reconfigure_password(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A new password replaces the stored one."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_PASSWORD: "new"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new"
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_reconfigure_to_existing_host(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The host cannot be changed to another configured controller."""
    mock_config_entry.add_to_hass(hass)
    other = MockConfigEntry(
        domain=DOMAIN, unique_id="10.0.0.1", data={**ENTRY_DATA, CONF_HOST: "10.0.0.1"}
    )
    other.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_HOST: "10.0.0.1"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == ENTRY_DATA[CONF_HOST]
