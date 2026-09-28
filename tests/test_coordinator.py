"""Tests for the HeliothermCoordinator update logic.

Key regression covered here:
    A HeliothermFramingError (desynchronised byte stream) must propagate as a
    connection-level failure and abort the whole update cycle.  It must NOT be
    caught by the per-parameter exception handler that blacklists parameters.

This was the root cause of the "all sensors freeze on a flat line" bug
described in docs/TECHNICAL.md §5.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# conftest.py stubs HA modules before these imports happen.
from custom_components.heliotherm.const import MP_PARAMS, SP_PARAMS
from custom_components.heliotherm.coordinator import (
    HeliothermCoordinator,
    _RECHECK_INTERVAL,
)
from custom_components.heliotherm.protocol import (
    HeliothermConnectionError,
    HeliothermFramingError,
    HeliothermProtocolError,
)

# Small slices so tests don't iterate over all 26/35 params.
_ONE_MP = MP_PARAMS[:1]   # temp_aussen
_ONE_SP = SP_PARAMS[:1]   # liegenschaft
_THREE_MP = MP_PARAMS[:3]


# ---------------------------------------------------------------------------
# Minimal coordinator factory
# ---------------------------------------------------------------------------

def _make_coordinator() -> HeliothermCoordinator:
    """Return a coordinator wired to a mock client, bypassing HA machinery."""
    client = MagicMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.read_param = AsyncMock()
    client.write_param = AsyncMock()

    coord = HeliothermCoordinator.__new__(HeliothermCoordinator)
    coord.hass = MagicMock()
    coord.logger = MagicMock()
    coord.name = "heliotherm"
    coord.client = client
    coord.serial = "TEST-SERIAL"
    coord.sw_version = "2324"
    coord._sp_interval = 10
    coord._cycle = 0
    coord._unsupported: set[str] = set()
    coord._active_mp = MP_PARAMS
    coord._active_sp = SP_PARAMS
    coord._discovered = False
    coord.data = {}
    return coord


# Patch asyncio.sleep inside the coordinator so tests don't actually wait.
_NO_SLEEP = patch(
    "custom_components.heliotherm.coordinator.asyncio.sleep",
    new_callable=lambda: lambda *_: AsyncMock(return_value=None)(),
)


# ---------------------------------------------------------------------------
# Critical regression: framing error must not blacklist
# ---------------------------------------------------------------------------

class TestFramingErrorDoesNotBlacklist:
    async def test_framing_error_propagates(self):
        coord = _make_coordinator()
        coord.client.read_param.side_effect = HeliothermFramingError("desync")
        with _NO_SLEEP, pytest.raises(HeliothermConnectionError):
            await coord._read_group(_ONE_MP, {})

    async def test_framing_error_does_not_add_to_unsupported(self):
        coord = _make_coordinator()
        coord.client.read_param.side_effect = HeliothermFramingError("desync")
        try:
            with _NO_SLEEP:
                await coord._read_group(_ONE_MP, {})
        except HeliothermConnectionError:
            pass
        assert _ONE_MP[0].key not in coord._unsupported

    async def test_plain_connection_error_also_propagates(self):
        coord = _make_coordinator()
        coord.client.read_param.side_effect = HeliothermConnectionError("timeout")
        with _NO_SLEEP, pytest.raises(HeliothermConnectionError):
            await coord._read_group(_ONE_MP, {})
        assert _ONE_MP[0].key not in coord._unsupported


# ---------------------------------------------------------------------------
# Normal blacklisting (HeliothermProtocolError only)
# ---------------------------------------------------------------------------

class TestProtocolErrorBlacklists:
    async def test_protocol_error_adds_to_unsupported(self):
        coord = _make_coordinator()
        coord.client.read_param.side_effect = HeliothermProtocolError("ERR,INVALID")
        with _NO_SLEEP:
            await coord._read_group(_ONE_MP, {})   # must NOT raise
        assert _ONE_MP[0].key in coord._unsupported

    async def test_value_error_also_blacklists(self):
        coord = _make_coordinator()
        coord.client.read_param.side_effect = ValueError("cannot parse")
        with _NO_SLEEP:
            await coord._read_group(_ONE_MP, {})
        assert _ONE_MP[0].key in coord._unsupported

    async def test_blacklisted_param_is_skipped(self):
        coord = _make_coordinator()
        key = _ONE_MP[0].key
        coord._unsupported.add(key)
        data: dict = {}
        with _NO_SLEEP:
            await coord._read_group(_ONE_MP, data)
        coord.client.read_param.assert_not_awaited()
        assert key not in data


# ---------------------------------------------------------------------------
# Discovery: first poll locks in the supported set; unsupported are dropped
# ---------------------------------------------------------------------------

class TestDiscovery:
    async def test_discovery_excludes_unsupported_from_active_and_data(self):
        """A US=0/ERR register (simulated as MP NR=6) must be absent from the
        returned data and from the locked-in active groups."""
        coord = _make_coordinator()

        async def fake_read(ptype, nr, dtype):
            if ptype == "MP" and nr == 6:            # temp_eq_eintritt (US=0)
                raise HeliothermProtocolError("US=0")
            return 1.0

        coord.client.read_param = AsyncMock(side_effect=fake_read)
        with _NO_SLEEP:
            data = await coord._async_update_data()
        coord.data = data  # framework normally does this after the return

        assert coord._discovered is True
        assert "temp_eq_eintritt" not in data
        assert all(p.nr != 6 for p in coord._active_mp)
        assert coord.is_supported("temp_aussen") is True
        assert coord.is_supported("temp_eq_eintritt") is False

    async def test_unsupported_not_reread_after_discovery(self):
        """After discovery the unsupported register must never be requested
        again — not on a normal cycle, not across a recheck boundary."""
        coord = _make_coordinator()
        calls: list[tuple[str, int]] = []

        async def fake_read(ptype, nr, dtype):
            calls.append((ptype, nr))
            if ptype == "MP" and nr == 6:
                raise HeliothermProtocolError("US=0")
            return 1.0

        coord.client.read_param = AsyncMock(side_effect=fake_read)

        with _NO_SLEEP:
            coord.data = await coord._async_update_data()   # discovery cycle
        assert ("MP", 6) in calls                            # tried once

        # Run several more cycles, including a recheck-boundary one.
        calls.clear()
        for _ in range(_RECHECK_INTERVAL + 1):
            with _NO_SLEEP:
                coord.data = await coord._async_update_data()

        assert ("MP", 6) not in calls, "unsupported register re-read after discovery"

    async def test_discovery_reads_both_mp_and_sp(self):
        coord = _make_coordinator()
        coord.client.read_param = AsyncMock(return_value=1.0)
        with _NO_SLEEP:
            data = await coord._async_update_data()
        # Every MP and SP key should be present after a clean discovery.
        for p in MP_PARAMS + SP_PARAMS:
            assert p.key in data


# ---------------------------------------------------------------------------
# Data population
# ---------------------------------------------------------------------------

class TestDataPopulation:
    async def test_successful_read_stores_value(self):
        coord = _make_coordinator()
        coord.client.read_param.return_value = 19.1
        data: dict = {}
        with _NO_SLEEP:
            await coord._read_group(_ONE_MP, data)
        assert data[_ONE_MP[0].key] == pytest.approx(19.1)

    async def test_multiple_params_all_stored(self):
        coord = _make_coordinator()
        coord.client.read_param.return_value = 0.0
        data: dict = {}
        with _NO_SLEEP:
            await coord._read_group(_THREE_MP, data)
        for p in _THREE_MP:
            assert p.key in data

    async def test_unsupported_param_leaves_existing_value(self):
        """Last-known value must survive a cycle where the param is skipped."""
        coord = _make_coordinator()
        key = _ONE_MP[0].key
        coord._unsupported.add(key)
        data = {key: 99.9}
        with _NO_SLEEP:
            await coord._read_group(_ONE_MP, data)
        assert data[key] == pytest.approx(99.9)


# ---------------------------------------------------------------------------
# Const table integrity
# ---------------------------------------------------------------------------

class TestParamTableIntegrity:
    def test_no_duplicate_keys(self):
        from custom_components.heliotherm.const import ALL_PARAMS
        keys = [p.key for p in ALL_PARAMS]
        assert len(keys) == len(set(keys)), "Duplicate keys in parameter table"

    def test_no_duplicate_nr_within_ptype(self):
        from custom_components.heliotherm.const import ALL_PARAMS
        seen: dict = {}
        for p in ALL_PARAMS:
            identity = (p.ptype, p.nr)
            assert identity not in seen, (
                f"Duplicate ({p.ptype}, NR={p.nr}): {seen[identity]} and {p.key}"
            )
            seen[identity] = p.key

    def test_all_params_are_mp_or_sp(self):
        from custom_components.heliotherm.const import ALL_PARAMS
        for p in ALL_PARAMS:
            assert p.ptype in ("MP", "SP"), f"{p.key}: unexpected ptype {p.ptype!r}"

    def test_dtypes_valid(self):
        from custom_components.heliotherm.const import ALL_PARAMS
        for p in ALL_PARAMS:
            assert p.dtype in ("BOOL", "INT", "FLOAT"), (
                f"{p.key}: unexpected dtype {p.dtype!r}"
            )
