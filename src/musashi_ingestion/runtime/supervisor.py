"""Independent machine workers with one serialized request lane per machine."""

from __future__ import annotations

import threading
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone

from musashi_ingestion.destinations import DeliveryWorker, create_destination
from musashi_ingestion.destinations.influx import MissingPointIdentity
from musashi_ingestion.config.store import validate_config
from musashi_ingestion.devices.ii import IIReader, IIUnavailable, channel_inventory_requests
from musashi_ingestion.devices.ii_decode import parse_upload
from musashi_ingestion.devices.iv import IVReader, inventory_requests, status_requests, path_for
from musashi_ingestion.pipeline.spool import SpoolError, make_record


def _utc():
    return datetime.now(timezone.utc).isoformat()


class Supervisor:
    def __init__(self, config_store, spool, *, ii_factory=IIReader, iv_factory=IVReader):
        self.config_store = config_store
        self.spool = spool
        self.ii_factory = ii_factory
        self.iv_factory = iv_factory
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._threads = {}
        self._states = {}
        self._target_ids = ()
        self._destination_status_ids = {}
        self._delivery_threads = {}
        self._delivery_states = {}

    def start(self):
        with self._lock:
            if any(t.is_alive() for t in (*self._threads.values(), *self._delivery_threads.values())):
                return self.status()
            config = self.config_store.load_runtime()
            validate_config(config)
            target_pairs = []
            for destination in config["destinations"]:
                identity = dict(destination)
                if destination.get("secret_ref"):
                    try:
                        identity["secret_digest"] = hashlib.sha256(Path(destination["secret_ref"]).read_bytes()).hexdigest()
                    except OSError:
                        identity["secret_digest"] = "unreadable"
                target_pairs.append((self.spool.register_target(destination["kind"], identity),
                                     destination, identity.get("secret_digest")))
            self._target_ids = tuple(target_id for target_id, _, _ in target_pairs)
            self._destination_status_ids = {target_id: destination["id"]
                                            for target_id, destination, _ in target_pairs}
            self._stop = threading.Event()
            self._threads = {}
            self._states = {}
            self._delivery_threads = {}
            self._delivery_states = {}
            for target_id, destination, secret_digest in target_pairs:
                self._delivery_states[target_id] = {"state": "starting", "error": None, "last_success": None}
                thread = threading.Thread(target=self._run_delivery,
                                          args=(target_id, destination, secret_digest, self._stop),
                                          name=f"delivery-{destination['id']}", daemon=True)
                self._delivery_threads[target_id] = thread
                thread.start()
            for machine in config["machines"]:
                ident = machine["id"]
                self._states[ident] = {"state": "starting", "last_attempt": None, "last_success": None,
                                       "error": None, "skipped_polls": 0, "poll_lag_seconds": 0}
                thread = threading.Thread(target=self._run_machine, args=(machine, self._stop),
                                          name=f"musashi-{ident}", daemon=True)
                self._threads[ident] = thread
                thread.start()
            return self.status()

    def stop(self, timeout=10):
        with self._lock:
            self._stop.set()
            threads = list(self._threads.values()) + list(self._delivery_threads.values())
        deadline = time.monotonic() + timeout
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        return self.status()

    def status(self):
        with self._lock:
            machines = {ident: dict(state) | {"worker_alive": self._threads[ident].is_alive()}
                        for ident, state in self._states.items()}
            destinations = {self._destination_status_ids.get(target_id, target_id):
                            dict(state) | {"worker_alive": self._delivery_threads[target_id].is_alive()}
                            for target_id, state in self._delivery_states.items()}
        spool = self.spool.stats()
        return {"running": any(item["worker_alive"] for item in machines.values()) and not self._stop.is_set(),
                "machines": machines, "destinations": destinations, "spool": spool,
                "acquisition_fault": spool["fault"] or next((s["error"] for s in machines.values() if s["state"] == "fault"), None)}

    def _run_delivery(self, target_id, config, expected_secret_digest, stop):
        destination = None
        try:
            while not stop.is_set():
                try:
                    if destination is None:
                        try:
                            current_digest = hashlib.sha256(Path(config["secret_ref"]).read_bytes()).hexdigest()
                        except OSError:
                            current_digest = None
                        if current_digest != expected_secret_digest or current_digest is None:
                            raise RuntimeError("destination secret changed; restart with a new target identity")
                        destination = create_destination(config)
                        with self._lock:
                            self._delivery_states[target_id].update(state="running", error=None)
                    sent = DeliveryWorker(self.spool, target_id, destination).drain(limit=10)
                    if sent:
                        with self._lock:
                            self._delivery_states[target_id]["last_success"] = _utc()
                    stop.wait(0.2 if sent else 1.0)
                except Exception as exc:
                    with self._lock:
                        error = str(exc) if isinstance(exc, MissingPointIdentity) else type(exc).__name__
                        self._delivery_states[target_id].update(state="fault", error=error)
                    if destination is not None and hasattr(destination, "close"):
                        try:
                            destination.close()
                        except Exception:
                            pass
                    destination = None
                    stop.wait(2.0)
        finally:
            if destination is not None and hasattr(destination, "close"):
                try:
                    destination.close()
                except Exception:
                    pass
            with self._lock:
                self._delivery_states[target_id]["state"] = "stopped"

    def _set(self, ident, **changes):
        with self._lock:
            self._states[ident].update(changes)

    def _commit(self, machine, record_type, source, value, *, channel_id=None, raw=None, quality=None):
        record = make_record(machine["id"], machine["model"], record_type, source,
                             {"value": value, "raw": raw, "scope": "channel" if channel_id else "machine",
                              "quality": quality or ("unavailable" if value is None else "good")}, channel_id=channel_id,
                             evidence_type="simulated" if machine.get("simulated") else "documented")
        return self.spool.commit(record, self._target_ids)

    def _commit_scan(self, machine, scan_id):
        snapshot = self.spool.scan_snapshot(scan_id)
        snapshot["state"] = "complete" if snapshot["completed_at"] else "partial"
        self._commit(machine, "scan", f"inventory:{scan_id}", snapshot,
                     quality="good" if snapshot["state"] == "complete" else "partial")

    def _run_machine(self, machine, stop):
        ident = machine["id"]
        reader = None
        try:
            if machine["model"] == "II":
                reader = self.ii_factory(machine["port"])
                plan = list(channel_inventory_requests(machine["channel_count"]))
                expected = [f"{code}:{channel}" for code, channel in plan]
            else:
                reader = self.iv_factory(machine["host"], machine.get("port", 1024))
                plan = list(inventory_requests())
                plan += [("recipe_item", n, None) for n in range(1, machine["recipe_count"] + 1)]
                plan += [("channel_item", n, None) for n in range(1, machine["channel_count"] + 1)]
                expected = [path_for(kind, item_id=item_id, option=option) for kind, item_id, option in plan]
            inventory = iter(zip(expected, plan))
            interval = float(machine.get("poll_interval_seconds", 1))
            inventory_interval = float(machine.get("inventory_interval_seconds", 3600))
            next_poll = time.monotonic()
            next_inventory = time.monotonic() + inventory_interval
            scan_id = self.spool.begin_scan(ident, "inventory", expected_items=expected)
            inventory_finished = False
            self._set(ident, state="running")
            while not stop.is_set():
                now = time.monotonic()
                if inventory_finished and now >= next_inventory:
                    scan_id = self.spool.begin_scan(ident, "inventory", expected_items=expected)
                    inventory = iter(zip(expected, plan))
                    inventory_finished = False
                    next_inventory = now + inventory_interval
                if now >= next_poll:
                    lag = max(0, now - next_poll)
                    skipped = int(lag // interval)
                    with self._lock:
                        prior = self._states[ident]["skipped_polls"]
                    self._set(ident, last_attempt=_utc(), poll_lag_seconds=lag,
                              skipped_polls=prior + skipped)
                    next_poll += (skipped + 1) * interval
                    try:
                        failures = self._poll(machine, reader)
                        self._set(ident, last_success=_utc() if not failures else self._states[ident]["last_success"],
                                  error="; ".join(failures) if failures else None)
                    except SpoolError:
                        raise
                    except Exception as exc:
                        self._set(ident, error=f"status read failed: {type(exc).__name__}: {exc}")
                if not inventory_finished:
                    try:
                        item_key, item = next(inventory)
                    except StopIteration:
                        try:
                            self.spool.finish_scan(scan_id)
                        except SpoolError:
                            self._set(ident, error="inventory scan partial")
                        self._commit_scan(machine, scan_id)
                        inventory_finished = True
                    else:
                        try:
                            source, value, channel_id, raw = self._read_inventory(machine, reader, item)
                            if machine["model"] == "IV":
                                self._validate_iv_inventory(machine, item, value)
                            record_id = self._commit(machine, "inventory", source, value,
                                                     channel_id=channel_id, raw=raw)
                            self.spool.record_scan_item(scan_id, item_key, record_id,
                                                        outcome="unsupported" if value is None else "ok")
                        except SpoolError:
                            raise
                        except IIUnavailable:
                            self.spool.record_scan_item(scan_id, item_key, outcome="unsupported")
                        except Exception as exc:
                            self.spool.record_scan_item(scan_id, item_key, outcome="failed")
                            self._set(ident, error=f"inventory read failed: {type(exc).__name__}: {exc}")
                stop.wait(max(0, next_poll - time.monotonic()))
            if not inventory_finished:
                self._commit_scan(machine, scan_id)
            self._set(ident, state="stopped")
        except Exception as exc:
            self._set(ident, state="fault", error=f"{type(exc).__name__}: {exc}")
        finally:
            if reader is not None and hasattr(reader, "close"):
                reader.close()

    def _poll(self, machine, reader):
        failures = []
        if machine["model"] == "II":
            def read_ii(code, channel=1):
                try:
                    response = reader.upload(code, channel)
                    return response, parse_upload(code, response.payload)
                except SpoolError:
                    raise
                except Exception as exc:
                    failures.append(f"{code}: {type(exc).__name__}")
                    self._commit(machine, "error", code,
                                 {"error_type": type(exc).__name__},
                                 channel_id=channel if code in ("D01", "D02", "D03", "D04") else None,
                                 quality="error")
                    return None

            first = read_ii("D06")
            if first:
                self._commit(machine, "status", "D06", first[1], raw=first[0].raw_frame.hex())
            for code in ("D05", "D07", "D08", "D09"):
                result = read_ii(code)
                if result:
                    self._commit(machine, "status", code, result[1], raw=result[0].raw_frame.hex())
            if first:
                channel = first[1]["displayed_channel"]
                buffered = []
                for code in ("D01", "D02", "D03", "D04"):
                    result = read_ii(code, channel)
                    if result:
                        buffered.append((code, result))
                second = read_ii("D06")
                if second:
                    self._commit(machine, "status", "D06", second[1], raw=second[0].raw_frame.hex())
                changed = not second or second[1]["displayed_channel"] != channel
                if changed:
                    failures.append("displayed channel changed or could not be confirmed")
                for code, (response, parsed) in buffered:
                    self._commit(machine, "status", code, parsed, channel_id=channel,
                                 raw=response.raw_frame.hex(),
                                 quality="incomplete" if changed else "good")
        else:
            for kind, item_id, option in status_requests():
                path = path_for(kind, item_id=item_id, option=option)
                try:
                    response = reader.read(kind, item_id=item_id, option=option)
                    self._commit(machine, "status", response.path, response.value,
                                 raw=response.raw.decode("utf-8"))
                except SpoolError:
                    raise
                except Exception as exc:
                    failures.append(f"{path}: {type(exc).__name__}")
                    self._commit(machine, "error", path,
                                 {"error_type": type(exc).__name__}, quality="error")
        return failures

    def _read_inventory(self, machine, reader, item):
        if machine["model"] == "II":
            code, channel = item
            response = reader.upload(code, channel)
            return f"{code}:{channel}", parse_upload(code, response.payload), channel, response.raw_frame.hex()
        kind, item_id, option = item
        response = reader.read(kind, item_id=item_id, option=option)
        return response.path, response.value, item_id, response.raw.decode("utf-8")

    @staticmethod
    def _validate_iv_inventory(machine, item, value):
        kind, item_id, _ = item
        family = "recipe" if kind.startswith("recipe") else "channel" if kind.startswith("channel") else None
        if family is None:
            return
        count = machine["recipe_count"] if family == "recipe" else machine["channel_count"]
        if kind.endswith("_range"):
            if (not isinstance(value, dict) or type(value.get("min")) is not int
                    or type(value.get("max")) is not int
                    or value["max"] - value["min"] + 1 != count
                    or value["min"] not in (0, 1)):
                raise ValueError(f"{family} range conflicts with configured count")
        if kind.endswith("_all") or kind.endswith("_item"):
            key = "recipe" if family == "recipe" else "ch"
            items = value.get(key) if isinstance(value, dict) and key in value else value
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list) or any(not isinstance(entry, dict) or type(entry.get("no")) is not int
                                                  for entry in items):
                raise ValueError(f"invalid {family} item shape")
            numbers = [entry["no"] for entry in items]
            if len(numbers) != len(set(numbers)) or any(not 0 <= number < count for number in numbers):
                raise ValueError(f"{family} response contains duplicate or unexpected ID")
            if kind.endswith("_item") and numbers != [item_id - 1]:
                raise ValueError(f"{family} URL ID and payload no disagree")
