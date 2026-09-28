"""Bounded, read-only Super Sigma CM II upload transport.

D01 parsing was observed in the retained example. Other payload layouts still need
manual-derived fixtures and hardware confirmation; their validated bytes are returned.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Callable, Iterator
import time

STX, ETX, EOT, ENQ, ACK, CAN = (bytes((n,)) for n in (2, 3, 4, 5, 6, 24))
CHANNEL_UPLOADS = frozenset(("D01", "D02", "D03", "D04"))
MACHINE_UPLOADS = frozenset(("D05", "D06", "D07", "D08", "D09"))


class IIProtocolError(Exception):
    pass


class IIUnavailable(IIProtocolError):
    pass


@dataclass(frozen=True)
class IIResponse:
    code: str
    channel: int | None
    payload: str
    raw_frame: bytes


def checksum(payload: bytes) -> bytes:
    return f"{-sum(payload) & 255:02X}".encode("ascii")


def request_frame(code: str, channel: int = 1) -> bytes:
    if code not in CHANNEL_UPLOADS | MACHINE_UPLOADS:
        raise ValueError("unsupported upload code")
    if type(channel) is not int or not 1 <= channel <= 100:
        raise ValueError("channel must be an integer from 1 to 100")
    body = f"UL{channel:03d}{code}".encode("ascii")
    data = f"{len(body):02X}".encode("ascii") + body
    return STX + data + checksum(data) + ETX


def channel_inventory_requests(channel_count: int) -> Iterator[tuple[str, int]]:
    """Require evidenced capacity; never silently assume all 100 channels exist."""
    if type(channel_count) is not int or not 1 <= channel_count <= 100:
        raise ValueError("channel_count must be an evidenced integer from 1 to 100")
    for channel in range(1, channel_count + 1):
        for code in ("D01", "D02", "D03", "D04"):
            yield code, channel


class IIReader:
    """One serial request lane. Factory receives selected port and finite timeout."""

    def __init__(self, port: str, serial_factory: Callable | None = None,
                 timeout: float = 2.0, max_frame_bytes: int = 128):
        if not isinstance(port, str) or not port.startswith("/dev/serial/by-id/") or port.endswith("/") or ".." in port.split("/"):
            raise ValueError("select an explicit /dev/serial/by-id device")
        if not 0 < timeout <= 30 or not 16 <= max_frame_bytes <= 65535:
            raise ValueError("invalid serial bounds")
        self.port, self.timeout, self.max_frame_bytes = port, timeout, max_frame_bytes
        self._factory = serial_factory or self._open_serial
        self._serial = None
        self._lock = Lock()
        self._deadline = None

    @staticmethod
    def _open_serial(port: str, timeout: float):
        import serial  # optional runtime dependency
        return serial.Serial(port=port, baudrate=9600, bytesize=8, parity="N",
                             stopbits=1, timeout=timeout, write_timeout=timeout)

    def close(self) -> None:
        with self._lock:
            self._close_unlocked()

    def _close_unlocked(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None

    def _read_byte(self) -> bytes:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise IIProtocolError("serial request deadline exceeded")
        if hasattr(self._serial, "timeout"):
            self._serial.timeout = min(self.timeout, remaining)
        value = self._serial.read(1)
        if len(value) != 1:
            raise IIProtocolError("serial response timed out or disconnected")
        return value

    def _write(self, data: bytes) -> None:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise IIProtocolError("serial request deadline exceeded")
        if hasattr(self._serial, "write_timeout"):
            self._serial.write_timeout = min(self.timeout, remaining)
        written = self._serial.write(data)
        if written is not None and written != len(data):
            raise IIProtocolError("incomplete serial write")
        if time.monotonic() > self._deadline:
            raise IIProtocolError("serial request deadline exceeded")

    def _frame(self, first: bytes | None = None) -> tuple[str, bytes]:
        if first is None:
            first = self._read_byte()
        if first != STX:
            raise IIProtocolError("expected STX")
        data = bytearray()
        while True:
            byte = self._read_byte()
            if byte == ETX:
                break
            data.extend(byte)
            if len(data) > self.max_frame_bytes:
                raise IIProtocolError("frame exceeds byte limit")
        try:
            raw = bytes(data)
            text = raw.decode("ascii")
            count = int(text[:2], 16)
        except (ValueError, UnicodeError) as exc:
            raise IIProtocolError("invalid ASCII frame") from exc
        if len(raw) < 6 or count != len(raw) - 4 or raw[-2:] != checksum(raw[:-2]):
            raise IIProtocolError("invalid length or checksum")
        return text[2:-2], STX + raw + ETX

    def upload(self, code: str, channel: int = 1) -> IIResponse:
        outgoing = request_frame(code, channel)
        with self._lock:
            self._deadline = time.monotonic() + self.timeout
            try:
                if self._serial is None:
                    self._serial = self._factory(self.port, self.timeout)
                if hasattr(self._serial, "reset_input_buffer"):
                    self._serial.reset_input_buffer()
                self._write(ENQ)
                if self._read_byte() != ACK:
                    raise IIProtocolError("expected initial ACK")
                self._write(outgoing)
                response = self._read_byte()
                if response == STX:
                    command, _ = self._frame(response)
                    if command.startswith("A2"):
                        raise IIUnavailable("controller rejected upload")
                    if command != "A0":
                        raise IIProtocolError("unexpected command acknowledgement")
                    self._write(ACK)
                elif response != ACK:
                    raise IIProtocolError("unexpected command acknowledgement")
                self._write(EOT)
                response = self._read_byte()
                if response == ENQ:
                    self._write(ACK)
                    response = self._read_byte()
                payload, raw = self._frame(response)
                if payload.startswith("A2"):
                    raise IIUnavailable("controller rejected upload")
                if not payload.startswith("DA" + code[1:]):
                    raise IIProtocolError("unexpected upload response code")
                self._write(ACK)
                # EOT may be absent on the observed device; do not block for it.
                return IIResponse(code, channel if code in CHANNEL_UPLOADS else None, payload, raw)
            except Exception:
                if self._serial is not None:
                    try:
                        if time.monotonic() < self._deadline:
                            self._write(CAN)
                            self._write(EOT)
                    except Exception:
                        pass
                    self._close_unlocked()
                raise
            finally:
                self._deadline = None
