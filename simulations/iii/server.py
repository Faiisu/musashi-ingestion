#!/usr/bin/env python3
"""Serve synthetic Musashi III upload replies through a PTY or TCP serial bridge."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import select
import signal
import socketserver
import sys
import termios
import threading
import tty


STX, ETX, EOT, ENQ, ACK, CAN = (bytes((n,)) for n in (2, 3, 4, 5, 6, 24))
ROOT = Path(__file__).resolve().parent


def checksum(data: bytes) -> bytes:
    return f"{-sum(data) & 255:02X}".encode("ascii")


def frame(payload: str) -> bytes:
    body = payload.encode("ascii")
    data = f"{len(body):02X}".encode("ascii") + body
    return STX + data + checksum(data) + ETX


def read_byte(fd: int, stopping) -> bytes | None:
    while not stopping.is_set():
        readable, _, _ = select.select([fd], [], [], 0.2)
        if readable:
            try:
                value = os.read(fd, 1)
            except OSError:
                return None
            return value or None
    return None


def read_frame(fd: int, stopping, first: bytes | None = None) -> bytes | None:
    if first is None:
        first = read_byte(fd, stopping)
    if first != STX:
        return None
    data = bytearray()
    while not stopping.is_set():
        value = read_byte(fd, stopping)
        if value is None:
            return None
        if value == ETX:
            raw = bytes(data)
            try:
                declared = int(raw[:2].decode("ascii"), 16)
            except (ValueError, UnicodeError):
                return None
            if len(raw) < 6 or declared != len(raw) - 4 or raw[-2:] != checksum(raw[:-2]):
                return None
            return raw[2:-2]
        data.extend(value)
        if len(data) > 128:
            return None
    return None


def load_payloads() -> dict[str, str]:
    return json.loads((ROOT / "responses.json").read_text(encoding="utf-8"))["payloads"]


def run(fd: int, payloads: dict[str, str], channel_count: int, displayed_channel: int, stopping) -> None:
    while not stopping.is_set():
        first = read_byte(fd, stopping)
        if first is None:
            return
        if first == CAN:
            continue
        if first != ENQ:
            continue
        os.write(fd, ACK)
        request = read_frame(fd, stopping)
        if request is None:
            return
        try:
            command = request.decode("ascii")
            if len(command) != 8 or not command.startswith("UL"):
                raise ValueError("bad upload command")
            channel = int(command[2:5])
            code = command[5:]
            if code not in payloads or not 1 <= channel <= 100:
                raise ValueError("unsupported upload")
        except (UnicodeError, ValueError):
            os.write(fd, CAN + EOT)
            continue

        # Adapter expects a command ACK, then EOT / ENQ / ACK before the data frame.
        os.write(fd, ACK)
        if read_byte(fd, stopping) != EOT:
            return
        os.write(fd, ENQ)
        if read_byte(fd, stopping) != ACK:
            return

        if code in {"D01", "D02", "D03", "D04"} and channel > channel_count:
            response = f"A2{code[1:]}"
        else:
            response = payloads[code].format(channel=displayed_channel)
        os.write(fd, frame(response))
        if read_byte(fd, stopping) == ACK:
            # This final EOT is required before the next upload can begin.
            read_byte(fd, stopping)
        print(f"UL channel={channel:03d} code={code} -> {response}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("pty", "tcp"), default="pty")
    parser.add_argument("--host", default="127.0.0.1", help="TCP bind address")
    parser.add_argument("--port", type=int, default=9000, help="TCP port")
    parser.add_argument("--channels", type=int, default=4, help="simulated supported channel count (1-100)")
    parser.add_argument("--displayed-channel", type=int, default=1, help="channel reported by D06")
    args = parser.parse_args()
    if not 1 <= args.channels <= 100 or not 1 <= args.displayed_channel <= args.channels:
        parser.error("channels must be 1-100 and displayed-channel must be within that count")
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1-65535")

    payloads = load_payloads()
    stopping = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    if args.transport == "pty":
        signal.signal(signal.SIGTERM, lambda *_: stopping.set())
        master_fd, slave_fd = os.openpty()
        tty.setraw(slave_fd, termios.TCSANOW)
        device_path = os.ttyname(slave_fd)
        print("Musashi III simulator ready; waiting for UL uploads", flush=True)
        print(f"Pseudo-terminal: {device_path}", flush=True)
        print(f"Configure model III port={device_path}, channel_count={args.channels}", flush=True)
        try:
            run(master_fd, payloads, args.channels, args.displayed_channel, stopping)
        finally:
            os.close(master_fd)
            os.close(slave_fd)
    else:
        connection_lock = threading.Lock()

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                print(f"Serial client connected from {self.client_address[0]}", flush=True)
                with connection_lock:
                    run(self.request.fileno(), payloads, args.channels, args.displayed_channel, stopping)

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        server = Server((args.host, args.port), Handler)

        def stop_server(*_):
            stopping.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGINT, stop_server)
        signal.signal(signal.SIGTERM, stop_server)
        print(f"Musashi III simulator TCP serial endpoint: {args.host}:{args.port}", flush=True)
        print(f"Configure model III port=socket://musashi-iii:{args.port}, channel_count={args.channels}", flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        finally:
            server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
