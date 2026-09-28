"""Shared test configuration.

Stubs out the Home Assistant package so the integration modules can be
imported and tested without a full HA installation.  The stubs use the real
enum values that HA uses, ensuring const.py comparisons still work.
"""
from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Make "custom_components.heliotherm.*" importable from the repository root.
sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Minimal HA enum stubs (must match HA's string values for entity comparisons)
# ---------------------------------------------------------------------------

class _SensorDeviceClass(str, Enum):
    TEMPERATURE = "temperature"
    PRESSURE = "pressure"
    DURATION = "duration"
    ENERGY = "energy"


class _SensorStateClass(str, Enum):
    MEASUREMENT = "measurement"
    TOTAL_INCREASING = "total_increasing"


class _BinarySensorDeviceClass(str, Enum):
    PROBLEM = "problem"
    RUNNING = "running"
    POWER = "power"
    HEAT = "heat"
    MOISTURE = "moisture"


class _NumberDeviceClass(str, Enum):
    TEMPERATURE = "temperature"
    DURATION = "duration"


class _NumberMode(str, Enum):
    BOX = "box"


class _Platform(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    NUMBER = "number"


# ---------------------------------------------------------------------------
# Stub modules — registered in sys.modules before any heliotherm import
# ---------------------------------------------------------------------------

def _mod(**attrs):
    m = MagicMock()
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


_sensor_mod = _mod(
    SensorDeviceClass=_SensorDeviceClass,
    SensorStateClass=_SensorStateClass,
    SensorEntity=object,
)

_binary_sensor_mod = _mod(
    BinarySensorDeviceClass=_BinarySensorDeviceClass,
    BinarySensorEntity=object,
)

_number_mod = _mod(
    NumberDeviceClass=_NumberDeviceClass,
    NumberEntity=object,
    NumberMode=_NumberMode,
)

class _DataUpdateCoordinator:
    """Minimal stub that allows DataUpdateCoordinator[T] generic syntax."""
    def __class_getitem__(cls, item):
        return cls
    def __init__(self, *args, **kwargs):
        pass


class _CoordinatorEntity:
    def __class_getitem__(cls, item):
        return cls
    def __init__(self, coordinator, *args, **kwargs):
        self.coordinator = coordinator


_coordinator_mod = _mod(
    DataUpdateCoordinator=_DataUpdateCoordinator,
    CoordinatorEntity=_CoordinatorEntity,
    UpdateFailed=Exception,
)

_device_registry_mod = _mod(DeviceInfo=dict)

sys.modules.update({
    "homeassistant":                             MagicMock(),
    "homeassistant.components":                  MagicMock(),
    "homeassistant.components.sensor":           _sensor_mod,
    "homeassistant.components.binary_sensor":    _binary_sensor_mod,
    "homeassistant.components.number":           _number_mod,
    "homeassistant.config_entries":              MagicMock(ConfigEntry=object),
    "homeassistant.const":                       _mod(Platform=_Platform),
    "homeassistant.core":                        MagicMock(),
    "homeassistant.exceptions":                  MagicMock(ConfigEntryNotReady=Exception),
    "homeassistant.helpers":                     MagicMock(),
    "homeassistant.helpers.device_registry":     _device_registry_mod,
    "homeassistant.helpers.update_coordinator":  _coordinator_mod,
    "homeassistant.helpers.entity_platform":     MagicMock(),
    "homeassistant.helpers.selector":            MagicMock(),
    "voluptuous":                                MagicMock(),
})
