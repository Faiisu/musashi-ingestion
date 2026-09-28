# Musashi ingestion backend

This repository is rebuilding a read-only ingestion service for Musashi Super ΣCM II and IV dispensers. It has an authenticated management API, a SQLite record spool, safe request adapters, independent machine workers, and MQTT/PostgreSQL/InfluxDB delivery adapters. There is no frontend. Device reads have only been exercised with synthetic responses; limited MQTT and PostgreSQL service checks passed, while hardware compatibility and a full three-destination round trip remain open ticket gates.

## Prerequisites

- Python 3.11 or newer and `uv`, or Docker with Compose.
- A nonempty `OPERATOR_TOKEN`. Keep it out of the repository and logs.
- For real II/IV reads, an operator-approved machine, serial device or restricted IV network, and evidenced channel/recipe counts.

## Local quickstart: one simulated read

From the repository root:

```sh
uv sync --locked
export OPERATOR_TOKEN='replace-with-a-long-random-secret'
uv run musashi-ingestion
```

In a second terminal, using the same token:

```sh
export OPERATOR_TOKEN='replace-with-a-long-random-secret'
curl http://127.0.0.1:8080/health
curl -fsS -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H 'Content-Type: application/json' -d '{}' \
  http://127.0.0.1:8080/api/mock-read
curl -fsS -H "Authorization: Bearer $OPERATOR_TOKEN" \
  http://127.0.0.1:8080/api/records
```

The mock request returns a `record_id`; the authenticated records response contains the same ID. Stop and restart the service, then query `/api/records` again. The default data directory is `./data`. This mock uses a synthetic D01 value and never opens a machine connection. `GET /health` is unauthenticated and reports process state separately from acquisition faults. Other routes require the bearer token, including configuration and status reads.

The API is bound to `127.0.0.1:8080` by default. `MUSASHI_BIND`, `MUSASHI_PORT`, and `MUSASHI_DATA_DIR` override those values. `OPERATOR_TOKEN` must be nonempty or startup fails. Configuration updates use `PUT /api/config` with the current `revision`, `version: 1`, `machines`, and `destinations`; Start and Stop are `POST /api/control/start` and `/api/control/stop`. `GET /api/scans` shows recent inventory item coverage. Passwords and tokens belong in permission-restricted files referenced by `secret_ref`; the API redacts those references on read. Do not treat the retained `config/config.json` as a compatible configuration file.

## Container build

With a token in the shell, `docker compose build ingestion` builds the backend image. `docker compose up -d` starts it on host loopback port 8080 with a named persistent volume and a non-root container user. Compose does not map a serial device by default; add only the selected `/dev/serial/by-id/...` device for a site deployment. The IV controller speaks HTTP only, so restrict its network route. A successful image build is not evidence of host serial access or destination delivery.

## Current limits and evidence

The implementation defaults to a 2 MiB record limit and a 1 GiB SQLite spool quota; an oversized read or full spool faults acquisition instead of truncating data. MQTT messages default to at most 256 KiB including the envelope. These are provisional software guardrails, pending measured site capacity. Scan coverage and target delivery remain durable through SQLite. A destination failure keeps its assigned records pending; changed target settings receive a distinct identity. See the [working contract](docs/specs/rebuild-contract.md), [architecture](docs/architecture.md), and [ticket plan](docs/development-plan.md) for scope and open acceptance gates.

Run the checked-in synthetic regressions with `uv run python -m unittest discover -s tests -v`. Before the environment restricted sockets, the API restart test passed. The current socket-free subset passes 23 checks with `PYTHONPATH=src:tests .venv/bin/python -m unittest test_core test_devices test_ii_decode test_runtime test_iv_contract test_delivery test_recovery -v`; this includes a killed SQLite writer process, a live SQLite backup/restore, simulated destination outage and lost acknowledgment, and a simulated SQLite full error. The full discovery run currently fails only when its API test tries to create a socket (`PermissionError` in this environment). `docker compose build ingestion` passed before the latest source edits. The full M32 matrix and hardware checks have not run.
