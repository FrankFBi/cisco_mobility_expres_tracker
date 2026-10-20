"""Config flow tests."""

from datetime import timedelta
from unittest.mock import MagicMock

from ciscomobilityexpress.exceptions import CiscoMELoginError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from requests.exceptions import ConnectionError as RequestsConnectionError

from custom_components.cisco_mobility_express.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
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
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 300}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_SCAN_INTERVAL: 300}
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
