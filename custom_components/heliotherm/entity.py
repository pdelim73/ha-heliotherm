"""Shared entity base for the Heliotherm integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, HtParam
from .coordinator import HeliothermCoordinator


class HeliothermEntity(CoordinatorEntity[HeliothermCoordinator]):
    """Base class binding every entity to the one heat pump device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HeliothermCoordinator, param: HtParam) -> None:
        super().__init__(coordinator)
        self.param = param
        self._attr_unique_id = f"{coordinator.serial}_{param.key}"
        self._attr_name = param.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial)},
            manufacturer=MANUFACTURER,
            name=f"Heliotherm {coordinator.serial}",
            model="HP08E-WEB",
            sw_version=coordinator.sw_version,
            serial_number=coordinator.serial,
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data is not None
            and self.param.key in self.coordinator.data
        )
