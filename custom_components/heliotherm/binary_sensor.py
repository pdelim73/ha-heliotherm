"""Binary sensor platform for the Heliotherm integration."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ALL_PARAMS, DOMAIN
from .coordinator import HeliothermCoordinator
from .entity import HeliothermEntity

# Device classes for the boolean data points that map onto HA semantics.
_DEVICE_CLASSES = {
    "stoerung": BinarySensorDeviceClass.PROBLEM,
    "verdichter": BinarySensorDeviceClass.RUNNING,
    "heizkreispumpe": BinarySensorDeviceClass.RUNNING,
    "eq_pumpe_ventilator": BinarySensorDeviceClass.RUNNING,
    "zirkulationspumpe_ww": BinarySensorDeviceClass.RUNNING,
    "hauptschalter": BinarySensorDeviceClass.POWER,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up every supported boolean data point as a binary sensor.

    Discovery has already run (first refresh), so only parameters this unit
    actually supports are created — not-installed / unimplemented registers get
    no entity at all rather than appearing as "unavailable".
    """
    coordinator: HeliothermCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HeliothermBinarySensor(coordinator, param)
        for param in ALL_PARAMS
        if param.dtype == "BOOL" and coordinator.is_supported(param.key)
    )


class HeliothermBinarySensor(HeliothermEntity, BinarySensorEntity):
    """A boolean heat pump data point."""

    def __init__(self, coordinator, param) -> None:
        super().__init__(coordinator, param)
        self._attr_device_class = _DEVICE_CLASSES.get(param.key)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self.param.key)
        return None if value is None else bool(value)
