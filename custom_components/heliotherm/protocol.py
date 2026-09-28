"""Async TCP client for the Heliotherm serial ASCII protocol.

Speaks the proprietary Heliotherm protocol directly over a transparent
serial-to-Ethernet bridge (e.g. Waveshare RS232-to-ETH in TCP Server mode).
No serial device, socat or HtREST required.

Frame format
------------
Request : 02 FD D0 E0 00 00 [len] [~CMD;] [checksum]
Response: 02 FD E0 D0 xx 00 [len] [~REPLY;\\r\\n] [checksum]

Checksum: for each byte b of (header + len + payload):
              cs ^= b
              cs ^= (b << 1) & 0xFF
"""
from __future__ import annotations

import asyncio
import logging
import re

_LOGGER = logging.getLogger(__name__)

REQUEST_HEADER = b"\x02\xfd\xd0\xe0\x00\x00"
RESPONSE_PREFIX = b"\x02\xfd\xe0\xd0"

LOGIN_CMD = "LIN"
LOGOUT_CMD = "LOUT"
SERIAL_CMD = "RID"

_VAL_RE = re.compile(r"VAL=([^,;]+)")
_US_RE = re.compile(r"\bUS=([^,;]+)")
_PAYLOAD_RE = re.compile(r"~([^;]*);")


class HeliothermError(Exception):
    """Base error for Heliotherm communication."""


class HeliothermConnectionError(HeliothermError):
    """Raised when the TCP connection fails."""


class HeliothermFramingError(HeliothermConnectionError):
    """Raised when the byte stream is desynchronized.

    This means the connection itself is in a bad state (stale bytes from a
    previous frame, a dropped byte, a half-closed socket) — it does NOT mean
    the requested register is unsupported. Callers must treat this as a
    connection-level failure and reconnect, never as "this parameter doesn't
    exist on this firmware".
    """


class HeliothermProtocolError(HeliothermError):
    """Raised when the pump returns a clean, well-framed error response
    (e.g. ERR,INVALID) or a well-framed reply with no VAL field.

    Unlike HeliothermFramingError, this means the frame itself parsed
    correctly — the pump genuinely rejected or has no data for this
    specific register. Safe to treat as "unsupported on this firmware".
    """


def calc_checksum(data: bytes) -> int:
    """Compute the Heliotherm frame checksum."""
    cs = 0
    for b in data:
        cs ^= b
        cs ^= (b << 1) & 0xFF
    return cs


# The complete set of commands this integration may send. build_request() is the
# only producer of outgoing frames, so anything else — including any request that
# carries VAL= — can never reach the heat pump.
_ALLOWED_CMD_RE = re.compile(r"LIN|LOUT|RID|(?:MP|SP),NR=\d+")


def build_request(cmd: str) -> bytes:
    """Build a complete request frame for a read-only command string."""
    if not _ALLOWED_CMD_RE.fullmatch(cmd):
        raise ValueError(f"Refusing to send non-read command: {cmd!r}")
    wrapped = f"~{cmd};".encode("ascii")
    data = REQUEST_HEADER + bytes([len(wrapped)]) + wrapped
    return data + bytes([calc_checksum(data)])


class HeliothermClient:
    """Maintains a single TCP session with the heat pump."""

    def __init__(self, host: str, port: int, timeout: float = 5.0) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open the TCP connection and log in."""
        await self.disconnect()
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), self._timeout
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise HeliothermConnectionError(
                f"Cannot connect to {self._host}:{self._port}: {err}"
            ) from err

        reply = await self._transact(LOGIN_CMD)
        if "OK" not in reply:
            await self.disconnect()
            raise HeliothermProtocolError(f"Login rejected by heat pump: {reply}")
        _LOGGER.debug("Logged in to heat pump at %s:%s", self._host, self._port)

    async def disconnect(self) -> None:
        """Close the TCP connection, attempting a clean logout first."""
        if self._writer is not None and not self._writer.is_closing():
            try:
                self._writer.write(build_request(LOGOUT_CMD))
                await asyncio.wait_for(self._writer.drain(), 1.0)
            except (OSError, asyncio.TimeoutError):
                pass
            try:
                self._writer.close()
                await asyncio.wait_for(self._writer.wait_closed(), 2.0)
            except (OSError, asyncio.TimeoutError):
                pass
        self._reader = None
        self._writer = None

    async def _transact(self, cmd: str) -> str:
        """Send one command and return the decoded payload text."""
        if self._writer is None or self._reader is None:
            raise HeliothermConnectionError("Not connected")

        self._writer.write(build_request(cmd))
        try:
            await asyncio.wait_for(self._writer.drain(), self._timeout)
        except (OSError, asyncio.TimeoutError) as err:
            raise HeliothermConnectionError(f"Write failed: {err}") from err

        # Read the fixed 7-byte prologue (header + length), then the payload.
        try:
            head = await asyncio.wait_for(self._reader.readexactly(7), self._timeout)
            length = head[6]
            body = await asyncio.wait_for(
                self._reader.readexactly(length + 1), self._timeout
            )
        except asyncio.IncompleteReadError as err:
            raise HeliothermConnectionError("Connection closed by peer") from err
        except (OSError, asyncio.TimeoutError) as err:
            raise HeliothermConnectionError(f"Read timeout for '{cmd}': {err}") from err

        if not head.startswith(RESPONSE_PREFIX):
            # The byte stream is desynchronized — this is NOT "command not
            # supported", it means our read position no longer lines up with
            # a real frame boundary (e.g. stale bytes left over from a prior
            # request). Raising a connection-level error forces the caller
            # to reconnect instead of blacklisting whatever parameter we
            # happened to be asking for when the desync was noticed.
            raise HeliothermFramingError(f"Bad response header: {head.hex()}")

        payload = body[:length].decode("ascii", errors="replace")
        match = _PAYLOAD_RE.search(payload)
        text = match.group(1) if match else payload.strip()

        if text.startswith("ERR"):
            raise HeliothermProtocolError(f"Pump error for '{cmd}': {text}")
        return text

    async def command(self, cmd: str) -> str:
        """Send a command, reconnecting once if the session has dropped."""
        async with self._lock:
            if not self.connected:
                await self.connect()
            try:
                return await self._transact(cmd)
            except HeliothermConnectionError:
                _LOGGER.debug("Session lost, reconnecting for '%s'", cmd)
                await self.connect()
                return await self._transact(cmd)

    async def read_param(self, ptype: str, nr: int, dtype: str):
        """Read one data point and coerce it to the declared type.

        The pump's reply carries a ``US=`` (user-supported) field: ``US=1`` means
        the sensor/feature is installed and the value is real; ``US=0`` means it
        is not fitted on this unit and the pump returns a placeholder (e.g.
        ``-50.0``). Treating ``US=0`` as a clean protocol rejection lets the
        coordinator blacklist it exactly like an ``ERR,INVALID`` register — so it
        is polled once, skipped thereafter, and re-tested by the periodic recheck.
        """
        text = await self.command(f"{ptype},NR={nr}")
        us_match = _US_RE.search(text)
        if us_match and us_match.group(1).strip() == "0":
            raise HeliothermProtocolError(
                f"{ptype},NR={nr} not installed on this unit (US=0)"
            )
        match = _VAL_RE.search(text)
        if not match:
            raise HeliothermProtocolError(f"No VAL in response: {text}")
        raw = match.group(1).strip()
        if dtype == "BOOL":
            return bool(int(float(raw)))
        if dtype == "INT":
            return int(float(raw))
        return float(raw)

    async def read_serial(self) -> str:
        """Read the manufacturer serial number (used as the device identifier)."""
        text = await self.command(SERIAL_CMD)
        parts = text.split(",", 1)
        return parts[1].strip() if len(parts) > 1 else text.strip()

    async def read_sw_version(self) -> str:
        """Read the controller software version."""
        text = await self.command("SP,NR=9")
        match = _VAL_RE.search(text)
        return match.group(1).strip() if match else "unknown"
