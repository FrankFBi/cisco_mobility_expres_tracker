"""Diagnostic sensors for the devices of enabled client trackers."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ALL_IPV6
from .coordinator import CiscoMEConfigEntry, CiscoMEDataUpdateCoordinator
from .devices import enabled_client_macs


@dataclass(frozen=True, kw_only=True)
class CiscoMESensorEntityDescription(SensorEntityDescription):
    """Describes a sensor backed by one controller field."""

    field: str
    value_fn: Callable[[Any], Any] = lambda value: value
    icon_fn: Callable[[Any], str | None] | None = None


def _signal_icon(value: Any) -> str | None:
    """Return a Wi-Fi strength icon: good from -65 dBm, fair to -80, weak below."""
    try:
        dbm = float(value)
    except (TypeError, ValueError):
        return None
    if dbm >= -65:
        return "mdi:wifi-strength-4"
    if dbm >= -80:
        return "mdi:wifi-strength-2"
    return "mdi:wifi-strength-1"


def _join_addresses(addresses: list[str] | None) -> str | None:
    """Join addresses into one state, cut to Home Assistant's 255-character limit."""
    if not addresses:
        return None
    joined = ", ".join(addresses)
    return joined if len(joined) <= 255 else joined[:255].rsplit(", ", 1)[0]


SENSORS = (
    CiscoMESensorEntityDescription(key="ipv4", translation_key="ipv4", field="ipv4"),
    CiscoMESensorEntityDescription(key="access_point", translation_key="access_point", field="AP"),
    CiscoMESensorEntityDescription(key="ssid", translation_key="ssid", field="SSID"),
    CiscoMESensorEntityDescription(key="protocol", translation_key="protocol", field="PT"),
    CiscoMESensorEntityDescription(key="band", translation_key="band", field="FB"),
    CiscoMESensorEntityDescription(
        key="signal_strength",
        translation_key="signal_strength",
        field="SS",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        icon_fn=_signal_icon,
    ),
)

IPV6_SENSOR = CiscoMESensorEntityDescription(
    key="ipv6", translation_key="ipv6", field="ipv6", value_fn=_join_addresses
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CiscoMEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for every client whose tracker is enabled."""
    coordinator = entry.runtime_data
    macs = enabled_client_macs(hass, entry)
    descriptions = SENSORS
    if entry.options.get(CONF_ALL_IPV6, False):
        descriptions = (*SENSORS, IPV6_SENSOR)
    else:
        registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if entity.domain == "sensor" and entity.unique_id.endswith(f"_{IPV6_SENSOR.key}"):
                registry.async_remove(entity.entity_id)
    async_add_entities(
        CiscoMEClientSensor(coordinator, mac, description)
        for mac in macs
        for description in descriptions
    )


class CiscoMEClientSensor(CoordinatorEntity[CiscoMEDataUpdateCoordinator], SensorEntity):
    """A controller-reported detail of a wireless client."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    entity_description: CiscoMESensorEntityDescription

    def __init__(
        self,
        coordinator: CiscoMEDataUpdateCoordinator,
        mac: str,
        description: CiscoMESensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._mac = mac
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = DeviceInfo(connections={(CONNECTION_NETWORK_MAC, mac)})

    @property
    def native_value(self) -> Any:
        """Return the value while the client is associated."""
        if client := self.coordinator.data.get(self._mac):
            return self.entity_description.value_fn(client.get(self.entity_description.field))
        return None

    @property
    def icon(self) -> str | None:
        """Return a value-dependent icon where the description has one."""
        if self.entity_description.icon_fn and (
            icon := self.entity_description.icon_fn(self.native_value)
        ):
            return icon
        return super().icon
