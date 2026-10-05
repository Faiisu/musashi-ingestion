#!/usr/bin/env python3
"""Serve synthetic Musashi IV HTTP read responses from the checked-in manifest."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import signal
import sys
import threading
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent


def response_for(path: str, manifest: dict, recipe_count: int, channel_count: int):
    responses = manifest["responses"]
    if path == "/v1/info/recipe/range":
        return "json", {"min": 0, "max": recipe_count - 1}
    if path == "/v1/info/channel/range":
        return "json", {"min": 0, "max": channel_count - 1}

    match = re.fullmatch(r"/v1/info/(recipe|channel)/data/([1-9][0-9]*)", path)
    if match:
        family, text_id = match.groups()
        item_id = int(text_id)
        count = recipe_count if family == "recipe" else channel_count
        protocol_limit = 100 if family == "recipe" else 400
        if item_id > min(count, protocol_limit):
            return None
        field = "recipe" if family == "recipe" else "ch"
        entry = {"no": item_id - 1, "synthetic": True}
        return "json", {field: [entry]}

    item = responses.get(path)
    if item is None:
        return None
    return item["kind"], item["body"]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "Musashi-IV-Simulator/1.0"
    manifest: dict
    recipe_count: int
    channel_count: int

    def do_GET(self):
        path = urlsplit(self.path).path
        if self.path != path:  # Query strings and alternate spellings are not in the catalog.
            self.send_error(404)
            return
        result = response_for(path, self.manifest, self.recipe_count, self.channel_count)
        if result is None:
            self.send_error(404)
            return
        kind, value = result
        if path == "/v1/time":
            body = value.encode("utf-8")
            content_type = "text/plain; charset=utf-8"
        elif kind == "tsv":
            body = value.encode("utf-8")
            content_type = "text/tab-separated-values; charset=utf-8"
        else:
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        print(f"GET {path} -> 200 ({kind}, {len(body)} bytes)", flush=True)

    def do_POST(self):
        self.send_error(405, "simulator is read-only")

    def log_message(self, fmt, *args):
        # Keep one concise line per read, without the default client-address noise.
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: loopback only)")
    parser.add_argument("--port", type=int, default=1024, choices=(1024, 1025, 1026))
    parser.add_argument("--recipes", type=int, default=100, help="simulated recipe capacity (1-100)")
    parser.add_argument("--channels", type=int, default=400, help="simulated channel capacity (1-400)")
    args = parser.parse_args()
    if not 1 <= args.recipes <= 100 or not 1 <= args.channels <= 400:
        parser.error("recipes must be 1-100 and channels must be 1-400")

    Handler.manifest = json.loads((ROOT / "responses.json").read_text(encoding="utf-8"))
    Handler.recipe_count = args.recipes
    Handler.channel_count = args.channels
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True

    def request_shutdown(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    print(f"Musashi IV simulator: http://{args.host}:{args.port}", flush=True)
    print(f"Configure model IV host={args.host}, port={args.port}, recipes={args.recipes}, channels={args.channels}", flush=True)
    print("Responses are synthetic; unknown paths return 404 and POST returns 405.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
