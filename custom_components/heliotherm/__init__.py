"""The Heliotherm heat pump integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SP_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SP_INTERVAL,
    DOMAIN,
)
from .coordinator import HeliothermCoordinator
from .protocol import HeliothermClient, HeliothermError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Heliotherm from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    options = entry.options
    scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    sp_interval = options.get(CONF_SP_INTERVAL, DEFAULT_SP_INTERVAL)

    client = HeliothermClient(host, port)
    try:
        await client.connect()
        serial = await client.read_serial()
        sw_version = await client.read_sw_version()
    except HeliothermError as err:
        await client.disconnect()
        raise ConfigEntryNotReady(f"Cannot reach heat pump at {host}:{port}") from err

    coordinator = HeliothermCoordinator(
        hass, client, scan_interval, sp_interval, serial, sw_version
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: HeliothermCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
