"""Synthetic protocol fakes; these are not hardware captures."""

import json
import time
import unittest

from musashi_ingestion.devices.ii import ACK, ENQ, ETX, STX, IIProtocolError, IIReader, checksum
from musashi_ingestion.devices.iv import IVReadError, IVReader
from musashi_ingestion.runtime.supervisor import Supervisor


def ii_frame(payload):
    data = f"{len(payload):02X}".encode() + payload.encode()
    return STX + data + checksum(data) + ETX


class FakeSerial:
    def __init__(self, port, timeout, *, bad_checksum=False):
        frame = ii_frame("DA01SYNTHETIC")
        if bad_checksum:
            frame = frame[:-3] + b"00" + ETX
        self.incoming = bytearray(ACK + ACK + ENQ + frame)
        self.sent = bytearray()
        self.timeout = timeout

    def reset_input_buffer(self):
        pass

    def read(self, size):
        if not self.incoming:
            return b""
        value = bytes(self.incoming[:size])
        del self.incoming[:size]
        return value

    def write(self, data):
        self.sent.extend(data)

    def close(self):
        pass


class FakeHTTPResponse:
    def __init__(self, status=200, value=None):
        self.status = status
        self.data = json.dumps(value).encode()

    def getheader(self, key):
        return str(len(self.data)) if key == "Content-Length" else None

    def read(self, size):
        return self.data[:size]


class FakeHTTPConnection:
    def __init__(self, host, port, timeout):
        self.trace = []
        self.response = FakeHTTPResponse(200, {"min": 0, "max": 1})

    def request(self, method, path, headers=None):
        self.trace.append((method, path))

    def getresponse(self):
        return self.response

    def close(self):
        pass


class DeviceTests(unittest.TestCase):
    def test_first_ii_read_and_bad_checksum_are_bounded(self):
        fake = FakeSerial("/dev/serial/by-id/fake", 2)
        reader = IIReader("/dev/serial/by-id/fake", serial_factory=lambda port, timeout: fake)
        started = time.monotonic()
        result = reader.upload("D01", 1)
        self.assertLess(time.monotonic() - started, 2)
        self.assertTrue(result.payload.startswith("DA01"))
        self.assertIn(b"UL001D01", fake.sent)
        with self.assertRaises(ValueError):
            reader.upload("START")
        bad = IIReader("/dev/serial/by-id/fake",
                       serial_factory=lambda port, timeout: FakeSerial(port, timeout, bad_checksum=True))
        with self.assertRaises(IIProtocolError):
            bad.upload("D01")

    def test_ii_timeout_and_disconnect_abort_without_control_command(self):
        class TimeoutSerial(FakeSerial):
            def __init__(self, port, timeout):
                super().__init__(port, timeout)
                self.incoming.clear()

        timeout_port = TimeoutSerial("/dev/serial/by-id/fake", 0.1)
        reader = IIReader("/dev/serial/by-id/fake", timeout=0.1,
                          serial_factory=lambda port, timeout: timeout_port)
        with self.assertRaises(IIProtocolError):
            reader.upload("D01")
        self.assertNotIn(b"UL", timeout_port.sent)

        class DisconnectSerial(FakeSerial):
            def read(self, size):
                # First byte ACKs ENQ, then the peer disappears.
                if len(self.sent) > 1:
                    return b""
                return super().read(size)

        disconnected = DisconnectSerial("/dev/serial/by-id/fake", 0.1)
        reader = IIReader("/dev/serial/by-id/fake", timeout=0.1,
                          serial_factory=lambda port, timeout: disconnected)
        with self.assertRaises(IIProtocolError):
            reader.upload("D01")
        self.assertIn(b"UL001D01", disconnected.sent)
        self.assertNotIn(b"START", disconnected.sent)

    def test_ii_write_obeys_whole_request_deadline(self):
        class SlowWrite(FakeSerial):
            def __init__(self, port, timeout):
                super().__init__(port, timeout)
                self.write_timeout = timeout

            def write(self, data):
                time.sleep(0.02)
                return super().write(data)

        serial = SlowWrite("/dev/serial/by-id/fake", 0.01)
        reader = IIReader("/dev/serial/by-id/fake", timeout=0.01,
                          serial_factory=lambda port, timeout: serial)
        with self.assertRaises(IIProtocolError):
            reader.upload("D01")
        self.assertLess(serial.write_timeout, 0.011)

    def test_iv_read_has_exact_get_path_and_rejects_redirect(self):
        fake = FakeHTTPConnection("127.0.0.1", 1024, 2)
        reader = IVReader("127.0.0.1", connection_factory=lambda host, port, timeout: fake)
        result = reader.read("recipe_range")
        self.assertEqual(result.value, {"min": 0, "max": 1})
        self.assertEqual(fake.trace, [("GET", "/v1/info/recipe/range")])
        fake.response = FakeHTTPResponse(302, None)
        with self.assertRaises(IVReadError):
            reader.read("status", option="main")
        self.assertEqual(fake.trace[-1], ("GET", "/v1/status/main"))
        with self.assertRaises(ValueError):
            reader.read("current/dispense")

    def test_iv_count_and_payload_id_mismatch_are_rejected(self):
        machine = {"recipe_count": 2, "channel_count": 2}
        Supervisor._validate_iv_inventory(machine, ("recipe_range", None, None), {"min": 0, "max": 1})
        with self.assertRaises(ValueError):
            Supervisor._validate_iv_inventory(machine, ("recipe_range", None, None), {"min": 0, "max": 99})
        with self.assertRaises(ValueError):
            Supervisor._validate_iv_inventory(machine, ("channel_item", 1, None), {"ch": [{"no": 1}]})


if __name__ == "__main__":
    unittest.main()
