"""Sensor platform for the Heliotherm integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ALL_PARAMS, DOMAIN
from .coordinator import HeliothermCoordinator
from .entity import HeliothermEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up every supported non-boolean data point as a sensor.

    Discovery has already run (first refresh), so only parameters this unit
    actually supports are created — not-installed / unimplemented registers get
    no entity at all rather than appearing as "unavailable".
    """
    coordinator: HeliothermCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HeliothermSensor(coordinator, param)
        for param in ALL_PARAMS
        if param.dtype != "BOOL" and coordinator.is_supported(param.key)
    )


class HeliothermSensor(HeliothermEntity, SensorEntity):
    """A numeric heat pump data point."""

    def __init__(self, coordinator, param) -> None:
        super().__init__(coordinator, param)
        self._attr_native_unit_of_measurement = param.unit
        self._attr_device_class = param.device_class
        self._attr_state_class = param.state_class
        self._attr_suggested_display_precision = 1 if param.dtype == "FLOAT" else 0

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.param.key)
