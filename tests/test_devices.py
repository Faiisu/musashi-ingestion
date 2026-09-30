"""Synthetic protocol fakes; these are not hardware captures."""

import json
import time
import unittest
from pathlib import Path

from musashi_ingestion.devices.ii import (ACK, CAN, ENQ, EOT, ETX, STX, IIDisconnected,
                                          IIProtocolError, IIReader, IIUnavailable, IITimeout, checksum,
                                          request_frame)
from musashi_ingestion.devices.iv import IVReadError, IVReader
from musashi_ingestion.runtime.supervisor import Supervisor


def ii_frame(payload):
    data = f"{len(payload):02X}".encode() + payload.encode()
    return STX + data + checksum(data) + ETX


class ScriptedSerial:
    def __init__(self, incoming, disconnect=False):
        self.incoming = bytearray(incoming)
        self.writes = []
        self.disconnect = disconnect

    def reset_input_buffer(self):
        pass

    def read(self, size):
        if self.disconnect and len(self.writes) >= 2 and not self.incoming:
            raise OSError("peer disconnected")
        if not self.incoming:
            return b""
        value = bytes(self.incoming[:size])
        del self.incoming[:size]
        return value

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def close(self):
        pass


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


class IIRequiresFinalEOTSerial:
    """Model a controller that will not accept the next upload until EOT."""

    def __init__(self):
        self.incoming = bytearray()
        self.writes = []
        self.ready = True
        self.awaiting_final_eot = False
        self.ack_writes = 0

    def reset_input_buffer(self):
        pass

    def read(self, size):
        if not self.incoming:
            return b""
        value = bytes(self.incoming[:size])
        del self.incoming[:size]
        return value

    def write(self, data):
        self.writes.append(data)
        if data == ENQ:
            if self.ready:
                self.incoming.extend(ACK)
                self.ready = False
                self.ack_writes = 0
        elif data.startswith(STX):
            code = next(code for code in ("D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08", "D09")
                        if code.encode() in data)
            self.incoming.extend(ACK + ENQ + ii_frame(f"DA{code[1:]}"))
        elif data == ACK:
            self.ack_writes += 1
            if self.ack_writes == 2:
                self.awaiting_final_eot = True
        elif data == EOT and self.awaiting_final_eot:
            self.awaiting_final_eot = False
            self.ready = True
        return len(data)

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
    def test_ii_ends_each_upload_before_starting_the_next(self):
        serial = IIRequiresFinalEOTSerial()
        reader = IIReader("/dev/serial/by-id/fake", timeout=0.05,
                          serial_factory=lambda port, timeout: serial)
        first = reader.upload("D05")
        second = reader.upload("D06")
        reader.close()
        self.assertEqual(first.payload, "DA05")
        self.assertEqual(second.payload, "DA06")
        self.assertEqual(serial.writes.count(EOT), 4)

    def test_ii_fault_fixture_matrix_and_safe_write_traces(self):
        fixtures = json.loads((Path(__file__).parent / "fixtures" / "ii_uploads.json").read_text())
        cases = {case["name"]: case for case in fixtures["faults"]}
        good = ii_frame("DA01P0987T00654V0321M2NSIGMA     ")
        payload = b"DA01P0987T00654V0321M2NSIGMA     "
        data = f"{len(payload) + 1:02X}".encode() + payload
        bad_length = STX + data + checksum(data) + ETX
        bad_checksum = good[:-3] + b"00" + ETX
        unsupported = ii_frame("A2")
        setup = {
            "bad_length": (ACK + ACK + ENQ + bad_length, False, IIProtocolError),
            "bad_checksum": (ACK + ACK + ENQ + bad_checksum, False, IIProtocolError),
            "timeout": (b"", False, IITimeout),
            "disconnect": (ACK, True, IIDisconnected),
            "unsupported_channel": (ACK + ACK + ENQ + unsupported, False, IIUnavailable),
        }
        symbolic = {ENQ: "ENQ", ACK: "ACK", EOT: "EOT", CAN: "CAN"}
        for name, (incoming, disconnect, error) in setup.items():
            with self.subTest(name):
                serial = ScriptedSerial(incoming, disconnect=disconnect)
                reader = IIReader("/dev/serial/by-id/fake", timeout=0.05,
                                  serial_factory=lambda port, timeout: serial)
                with self.assertRaises(error):
                    reader.upload("D01")
                trace = ["UL001D01" if item.startswith(STX) else symbolic[item]
                         for item in serial.writes]
                self.assertEqual(trace, cases[name]["write_trace"])
                self.assertTrue(all(item in (ENQ, ACK, EOT, CAN) or item.startswith(STX) and b"UL" in item
                                    for item in serial.writes))
        with self.assertRaises(ValueError):
            request_frame("D05", 2)

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
            Supervisor._validate_iv_inventory(machine, ("recipe_range", None, None), {"min": 0, "max": 0})
        with self.assertRaises(ValueError):
            Supervisor._validate_iv_inventory(machine, ("channel_item", 1, None), {"ch": [{"no": 1}]})


if __name__ == "__main__":
    unittest.main()
