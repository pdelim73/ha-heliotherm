"""Data update coordinator for the Heliotherm integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MP_PARAMS, SP_PARAMS, HtParam
from .protocol import (
    HeliothermClient,
    HeliothermConnectionError,
    HeliothermError,
    HeliothermProtocolError,
)

_LOGGER = logging.getLogger(__name__)

# Gap between consecutive commands. The link runs at 19200 baud and the
# controller is from 2005 — pushing harder causes dropped frames.
_COMMAND_GAP = 0.05

# Every this many cycles, retry any *active* parameter that was blacklisted by a
# transient fault. Parameters found unsupported during the one-off discovery
# pass are never in the active groups, so they are not re-read here.
_RECHECK_INTERVAL = 30


class HeliothermCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the heat pump and shares one dataset across all entities.

    On the first poll the coordinator runs a **discovery pass** over the full
    parameter table and records which registers this specific unit actually
    supports (a register is "supported" when it returns a real value with the
    pump's ``US=1`` flag). Every later poll reads only that supported set, and
    entities are only created for it — so parameters that are not installed
    (``US=0``) or unimplemented on this firmware never appear in Home Assistant,
    not even as "unavailable", and never cost a round trip after discovery.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: HeliothermClient,
        scan_interval: int,
        sp_interval: int,
        serial: str,
        sw_version: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.serial = serial
        self.sw_version = sw_version
        self._sp_interval = max(1, sp_interval)
        self._cycle = 0
        self._unsupported: set[str] = set()
        # Until discovery completes, the active groups are the full table.
        self._active_mp: tuple[HtParam, ...] = MP_PARAMS
        self._active_sp: tuple[HtParam, ...] = SP_PARAMS
        self._discovered = False

    def is_supported(self, key: str) -> bool:
        """True if this register returned real data during discovery.

        Used by the entity platforms so only supported parameters get entities.
        """
        return key in (self.data or {})

    async def _read_group(
        self, params: tuple[HtParam, ...], data: dict[str, Any]
    ) -> None:
        """Read a group of parameters into the data dict.

        Only a clean, well-framed rejection from the pump (HeliothermProtocolError)
        blacklists a parameter. A HeliothermConnectionError — which includes
        HeliothermFramingError, raised when the byte stream desynchronizes —
        is a connection-level fault and must propagate so the whole cycle is
        abandoned and retried fresh, instead of blacklisting whatever
        parameter happened to be in flight when the desync was noticed.
        """
        for param in params:
            if param.key in self._unsupported:
                continue
            try:
                data[param.key] = await self.client.read_param(
                    param.ptype, param.nr, param.dtype
                )
            except HeliothermProtocolError as err:
                # The pump gave a clean, well-formed reply rejecting this
                # specific register — genuinely unsupported on this firmware or
                # not installed on this unit (US=0).
                _LOGGER.debug("Marking %s unsupported: %s", param.name, err)
                self._unsupported.add(param.key)
            except HeliothermConnectionError:
                raise
            except (ValueError, TypeError) as err:
                _LOGGER.debug("Cannot parse %s: %s", param.name, err)
                self._unsupported.add(param.key)
            await asyncio.sleep(_COMMAND_GAP)

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = dict(self.data or {})

        # The discovery pass reads the whole table once; every later cycle polls
        # only the parameters found supported then.
        discovering = not self._discovered
        mp_group = MP_PARAMS if discovering else self._active_mp
        sp_group = SP_PARAMS if discovering else self._active_sp
        read_settings = discovering or (self._cycle % self._sp_interval == 0)

        # Periodic self-heal: retry active parameters that a transient fault
        # blacklisted mid-life. Not-installed registers are excluded from the
        # active groups, so this never re-reads them.
        if (
            not discovering
            and self._cycle % _RECHECK_INTERVAL == 0
            and self._unsupported
        ):
            _LOGGER.debug(
                "Periodic recheck: re-testing %d blacklisted active parameter(s)",
                len(self._unsupported),
            )
            self._unsupported.clear()

        try:
            # Start every poll from a fresh, logged-in TCP session rather
            # than reusing one held open across the idle gap between polls.
            # On this hardware, holding a session idle for a full scan
            # interval has been observed to desynchronize the byte stream,
            # which previously corrupted every read for the rest of that
            # cycle.
            await self.client.connect()
            await self._read_group(mp_group, data)
            if read_settings:
                await self._read_group(sp_group, data)
        except HeliothermError as err:
            raise UpdateFailed(f"Communication with heat pump failed: {err}") from err
        finally:
            await self.client.disconnect()

        if discovering:
            # Lock in the supported set: only registers that returned real data.
            self._active_mp = tuple(p for p in MP_PARAMS if p.key in data)
            self._active_sp = tuple(p for p in SP_PARAMS if p.key in data)
            # The blacklist has served its discovery purpose; the active groups
            # now exclude the unsupported registers, so clear it for clean
            # mid-life self-heal accounting.
            self._unsupported.clear()
            self._discovered = True
            _LOGGER.debug(
                "Discovery complete: %d/%d MP and %d/%d SP parameters supported",
                len(self._active_mp), len(MP_PARAMS),
                len(self._active_sp), len(SP_PARAMS),
            )

        self._cycle += 1
        if not data:
            raise UpdateFailed("Heat pump returned no usable data")
        return data

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.client.disconnect()
