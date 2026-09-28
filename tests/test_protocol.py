"""Tests for the Heliotherm frame codec and client logic.

These tests run against the pure Python protocol module — no Home Assistant
installation required.  They include capture-based regression tests that
verify byte-for-byte equality against real frames observed from the pump.

Reference frames (captured from a real pump; see docs/technical-design.md):
  LIN request : 02 FD D0 E0 00 00 05 7E 4C 49 4E 3B 4C  (checksum = 0x4C)
  RID request : 02 FD D0 E0 00 00 05 7E 52 49 44 3B 70  (checksum = 0x70)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.heliotherm.protocol import (
    HeliothermClient,
    HeliothermConnectionError,
    HeliothermFramingError,
    HeliothermProtocolError,
    REQUEST_HEADER,
    RESPONSE_PREFIX,
    build_request,
    calc_checksum,
)

# ── Known-good reference frames ──────────────────────────────────────────────
#   Structure: REQUEST_HEADER(6) | LEN(1) | ~CMD;(LEN) | CHECKSUM(1)
#   ~LIN; = 7E 4C 49 4E 3B  (5 bytes)
#   ~RID; = 7E 52 49 44 3B  (5 bytes)
LIN_FRAME = bytes.fromhex("02fdd0e00000057e4c494e3b4c")
RID_FRAME = bytes.fromhex("02fdd0e00000057e5249443b70")

# Never connected to — every test mocks the transport. RFC 6761 reserves
# ".invalid", so this can never resolve to a real host.
_HOST = "converter.invalid"


# ── Checksum ─────────────────────────────────────────────────────────────────

class TestCalcChecksum:
    def test_lin_frame(self):
        """Checksum over the LIN frame data must equal 0x4C."""
        assert calc_checksum(LIN_FRAME[:-1]) == 0x4C

    def test_rid_frame(self):
        """Checksum over the RID frame data must equal 0x70."""
        assert calc_checksum(RID_FRAME[:-1]) == 0x70

    def test_empty_data(self):
        assert calc_checksum(b"") == 0

    def test_single_byte_0x01(self):
        # b=0x01: cs = 0^0x01=0x01; cs ^= 0x02 → 0x03
        assert calc_checksum(bytes([0x01])) == 0x03

    def test_deterministic(self):
        data = b"\xde\xad\xbe\xef"
        assert calc_checksum(data) == calc_checksum(data)


# ── Frame builder ─────────────────────────────────────────────────────────────

class TestBuildRequest:
    def test_lin_matches_capture(self):
        assert build_request("LIN") == LIN_FRAME

    def test_rid_matches_capture(self):
        assert build_request("RID") == RID_FRAME

    def test_starts_with_request_header(self):
        assert build_request("MP,NR=0").startswith(REQUEST_HEADER)

    def test_length_byte_is_payload_length(self):
        cmd = "MP,NR=57"
        frame = build_request(cmd)
        expected_len = len(f"~{cmd};".encode("ascii"))
        assert frame[6] == expected_len

    def test_last_byte_is_valid_checksum(self):
        frame = build_request("SP,NR=83")
        assert calc_checksum(frame[:-1]) == frame[-1]

    def test_payload_is_tilde_wrapped(self):
        frame = build_request("LIN")
        length = frame[6]
        payload = frame[7: 7 + length].decode("ascii")
        assert payload == "~LIN;"


# ── Read-only guarantee ───────────────────────────────────────────────────────

class TestReadOnlyAllowlist:
    """build_request() is the only producer of outgoing frames; it must accept
    exactly the read commands this integration uses and refuse everything else."""

    @pytest.mark.parametrize("cmd", ["LIN", "LOUT", "RID", "SP,NR=9", "MP,NR=0", "SP,NR=375"])
    def test_read_commands_accepted(self, cmd):
        assert build_request(cmd).startswith(REQUEST_HEADER)

    def test_every_register_in_the_table_is_accepted(self):
        from custom_components.heliotherm.const import ALL_PARAMS
        for p in ALL_PARAMS:
            build_request(f"{p.ptype},NR={p.nr}")

    @pytest.mark.parametrize("cmd", [
        "SP,NR=83,VAL=50",          # a write
        "MP,NR=0,VAL=1",
        "SP,NR=13;SP,NR=13,VAL=0",  # smuggled second command
        "CLK", "ALC",               # controller commands this integration doesn't use
        "LOGIN", "sp,nr=1", "SP,NR=", "SP,NR=x", "", "RID\n",
    ])
    def test_everything_else_refused(self, cmd):
        with pytest.raises(ValueError):
            build_request(cmd)

    async def test_refused_command_puts_nothing_on_the_wire(self):
        writer = MagicMock()
        writer.is_closing.return_value = False
        writer.drain = AsyncMock()
        client = HeliothermClient(_HOST, 4196)
        client._reader = AsyncMock()
        client._writer = writer
        with pytest.raises(ValueError):
            await client._transact("SP,NR=83,VAL=50")
        writer.write.assert_not_called()


# ── Value / type coercion ────────────────────────────────────────────────────

class TestReadParamCoercion:
    def _client_with_response(self, response_text: str) -> HeliothermClient:
        client = HeliothermClient(_HOST, 4196)
        client.command = AsyncMock(return_value=response_text)
        return client

    async def test_float_coercion(self):
        client = self._client_with_response(
            "MP,NR=0,ID=0,NAME=Temp. Aussen,VAL=19.1,US=1"
        )
        result = await client.read_param("MP", 0, "FLOAT")
        assert result == pytest.approx(19.1)
        assert isinstance(result, float)

    async def test_int_coercion(self):
        client = self._client_with_response(
            "SP,NR=83,ID=76,NAME=WW Normaltemp.,VAL=45,US=1"
        )
        result = await client.read_param("SP", 83, "INT")
        assert result == 45
        assert isinstance(result, int)

    async def test_bool_true(self):
        client = self._client_with_response(
            "MP,NR=36,ID=36,NAME=Hauptschalter,VAL=1,US=1"
        )
        result = await client.read_param("MP", 36, "BOOL")
        assert result is True

    async def test_bool_false(self):
        client = self._client_with_response(
            "MP,NR=30,ID=30,NAME=Verdichter,VAL=0,US=1"
        )
        result = await client.read_param("MP", 30, "BOOL")
        assert result is False

    async def test_float_from_whole_number_string(self):
        """Pump may return whole-number floats without a decimal point."""
        client = self._client_with_response(
            "SP,NR=69,ID=62,NAME=HKR Soll_Raum,VAL=20,US=1"
        )
        result = await client.read_param("SP", 69, "FLOAT")
        assert result == pytest.approx(20.0)

    async def test_missing_val_raises_protocol_error(self):
        client = self._client_with_response("SP,NR=222,ID=,NAME=MKR2 Aktiviert")
        with pytest.raises(HeliothermProtocolError):
            await client.read_param("SP", 222, "INT")


# ── US= (user-supported) flag handling — efficiency / correctness ────────────

class TestUserSupportedFlag:
    """US=0 means the sensor/feature is not installed; the pump returns a
    placeholder value. read_param must reject US=0 as a clean protocol error so
    the coordinator skips it, rather than surfacing garbage like -50.0."""

    def _client_with_response(self, response_text: str) -> HeliothermClient:
        client = HeliothermClient(_HOST, 4196)
        client.command = AsyncMock(return_value=response_text)
        return client

    async def test_us0_raises_protocol_error_despite_valid_val(self):
        # Not-installed EQ sensor: has a VAL, but US=0 → must be rejected.
        resp = "MP,NR=6,ID=6,NAME=Temp. EQ_Eintritt,VAL=-50.0,MIN=-20.0,MAX=30.0,US=0"
        client = self._client_with_response(resp)
        with pytest.raises(HeliothermProtocolError):
            await client.read_param("MP", 6, "FLOAT")

    async def test_us1_returns_value_normally(self):
        resp = "MP,NR=0,ID=0,NAME=Temp. Aussen,VAL=19.1,US=1"
        client = self._client_with_response(resp)
        assert await client.read_param("MP", 0, "FLOAT") == pytest.approx(19.1)

    async def test_no_us_field_still_reads(self):
        # RID and some replies have no US field — absence must not block a read.
        resp = "SP,NR=9,ID=9,NAME=Softwareversion,VAL=2324"
        client = self._client_with_response(resp)
        assert await client.read_param("SP", 9, "INT") == 2324

    async def test_us_substring_not_falsely_matched(self):
        # A field like "STATUS=0" must not be read as US=0 (word-boundary guard).
        resp = "MP,NR=30,ID=30,NAME=Verdichter,STATUS=0,VAL=1,US=1"
        client = self._client_with_response(resp)
        assert await client.read_param("MP", 30, "BOOL") is True


# ── Frame parsing / header guard ──────────────────────────────────────────────

class TestFrameParsing:
    def _make_reader_writer(self, head: bytes, body: bytes):
        reader = AsyncMock()
        # readexactly is called twice: once for the 7-byte head, once for body
        reader.readexactly = AsyncMock(side_effect=[head, body])
        writer = MagicMock()
        writer.is_closing.return_value = False
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        return reader, writer

    async def test_bad_header_raises_framing_error(self):
        """Garbage in the first 7 bytes → HeliothermFramingError."""
        bad_head = b"\xAA\xBB\xCC\xDD\x00\x00\x05"
        body = b"~LIN;\r\n\x00"
        reader, writer = self._make_reader_writer(bad_head, body)

        client = HeliothermClient(_HOST, 4196)
        client._reader = reader
        client._writer = writer

        with pytest.raises(HeliothermFramingError):
            await client._transact("LIN")

    def test_framing_error_is_connection_error(self):
        """HeliothermFramingError is-a HeliothermConnectionError (design contract)."""
        assert issubclass(HeliothermFramingError, HeliothermConnectionError)

    async def test_err_response_raises_protocol_error(self):
        """A clean ERR,INVALID reply is a HeliothermProtocolError, not a framing error."""
        err_payload = b"~ERR,INVALID;\r\n"
        good_head = RESPONSE_PREFIX + b"\x00\x00" + bytes([len(err_payload)])
        body = err_payload + b"\x00"  # dummy checksum byte

        reader, writer = self._make_reader_writer(good_head, body)
        client = HeliothermClient(_HOST, 4196)
        client._reader = reader
        client._writer = writer

        with pytest.raises(HeliothermProtocolError):
            await client._transact("SP,NR=222")
