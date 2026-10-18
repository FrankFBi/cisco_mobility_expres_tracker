"""Diagnostic sensors for the devices of enabled client trackers."""

from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import CiscoMEConfigEntry, CiscoMEDataUpdateCoordinator
from .devices import enabled_client_macs


@dataclass(frozen=True, kw_only=True)
class CiscoMESensorEntityDescription(SensorEntityDescription):
    """Describes a sensor backed by one controller field."""

    field: str


SENSORS = (
    CiscoMESensorEntityDescription(key="ipv4", translation_key="ipv4", field="ipv4"),
    CiscoMESensorEntityDescription(key="access_point", translation_key="access_point", field="AP"),
    CiscoMESensorEntityDescription(key="ssid", translation_key="ssid", field="SSID"),
    CiscoMESensorEntityDescription(key="protocol", translation_key="protocol", field="PT"),
    CiscoMESensorEntityDescription(key="band", translation_key="band", field="FB"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CiscoMEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for every client whose tracker is enabled."""
    coordinator = entry.runtime_data
    async_add_entities(
        CiscoMEClientSensor(coordinator, mac, description)
        for mac in enabled_client_macs(hass, entry)
        for description in SENSORS
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
    def native_value(self) -> str | None:
        """Return the value while the client is associated."""
        if client := self.coordinator.data.get(self._mac):
            return client.get(self.entity_description.field)
        return None
