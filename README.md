# Musashi ingestion service and operator console

This repository is rebuilding a read-only ingestion service for Musashi Super ΣCM III and IV dispensers. It has an authenticated management API, a responsive operator console, a SQLite record spool, safe request adapters, independent machine workers, and MQTT/PostgreSQL/InfluxDB delivery adapters. The connected III has completed a limited real serial read cycle, and IV status reads have succeeded; full hardware acceptance, complete IV inventory, and the structured Influx schema round trip remain open ticket gates.

## Prerequisites

- Python 3.11 or newer and `uv`, `curl`, and `jq`, or Docker with Compose.
- Operator credentials from `OPERATOR_USERNAME` and `OPERATOR_PASSWORD`; local defaults are `admin` and `00000000`.
- For real III/IV reads, an operator-approved machine, serial device or restricted IV network, and evidenced channel/recipe counts.

## Local quickstart: one simulated read

From the repository root:

```sh
uv sync --locked
export OPERATOR_USERNAME=admin
export OPERATOR_PASSWORD='00000000'
uv run musashi-ingestion
```

In a second terminal, log in and make one synthetic read:

```sh
ORIGIN=http://127.0.0.1:8080
umask 077
COOKIE_JAR=$(mktemp)
trap 'rm -f "$COOKIE_JAR"' EXIT
LOGIN=$(curl -fsS -c "$COOKIE_JAR" -b "$COOKIE_JAR" -H "Origin: $ORIGIN" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"00000000"}' \
  "$ORIGIN/api/auth/login")
CSRF=$(printf '%s' "$LOGIN" | jq -r .csrf_token)
curl http://127.0.0.1:8080/health
curl -fsS -b "$COOKIE_JAR" -H "Origin: $ORIGIN" -H "X-CSRF-Token: $CSRF" \
  -H 'Content-Type: application/json' -d '{}' \
  http://127.0.0.1:8080/api/mock-read
curl -fsS -b "$COOKIE_JAR" http://127.0.0.1:8080/api/records
```

The mock request returns a `record_id`; the authenticated records response contains the same ID. Stop and restart the service, then query `/api/records` again. The default data directory is `./data`. This mock uses a synthetic D01 value and never opens a machine connection. `GET /health` is unauthenticated and reports process state separately from acquisition faults. Other `/api` routes require a browser session cookie; bearer tokens are no longer accepted.

## Device acquisition simulators

For per-machine output variables, raw response formats, and the spool record envelope, see [machine output formats](docs/reference/machine-output-formats.md). The [device protocol reference](docs/reference/device-protocols.md) documents the read-only request catalog and evidence levels.

For manual integration checks of normal destination delivery, outages, and backlog recovery across PostgreSQL, InfluxDB, and MQTT, see [destination delivery test cases](docs/reference/destination-delivery-test-cases.md).

For protocol-level acquisition development, `docker compose -f compose.dev.yml up -d --build` starts the app, both synthetic device services, MQTT, PostgreSQL, and InfluxDB. The dev launcher seeds III/IV machine entries and MQTT/PostgreSQL/InfluxDB destinations in a new dev volume; on an existing dev volume it adds only destination IDs that are missing. All three destinations point to the Compose services and keep credentials in permission-restricted files. Acquisition stays stopped until you start it in the operator console. Service credentials are configurable with the `DEV_MQTT_*`, `DEV_POSTGRES_*`, and `DEV_INFLUX_*` variables in `.env`; environment changes alone do not rotate credentials already initialized in the named volumes. The services publish only on host loopback by default: MQTT `127.0.0.1:1883`, PostgreSQL `127.0.0.1:5432`, and InfluxDB `127.0.0.1:8086`. Details and standalone options for the device services are in [`simulations/iii`](simulations/iii/README.md) and [`simulations/iv`](simulations/iv/README.md). Device responses are synthetic and do not verify firmware compatibility.

The API is bound to `127.0.0.1:8080` by default. `MUSASHI_BIND`, `MUSASHI_PORT`, and `MUSASHI_DATA_DIR` override those values. `OPERATOR_USERNAME` and `OPERATOR_PASSWORD` default to `admin` and `00000000`; explicitly blank values prevent startup. Set `MUSASHI_PUBLIC_ORIGIN` to the exact HTTPS origin when TLS terminates at a trusted reverse proxy. The proxy must preserve that host and origin; forwarded headers are not trusted. When configured, browser login must use that HTTPS origin, and direct backend HTTP is not an alternate browser login origin. Sessions are stored in memory, expire after 8 idle hours or 24 total hours, and are cleared on restart. Configuration updates use `PUT /api/config` with the current `revision`, `version: 1`, `machines`, and `destinations`; Start and Stop are `POST /api/control/start` and `/api/control/stop`. `GET /api/scans` shows recent inventory item coverage. Passwords belong in permission-restricted environment secrets; machine and destination secret references are redacted on read. Do not treat the retained `config/config.json` as a compatible configuration file.

## Operator console and network access

Open `http://127.0.0.1:8080/` on the host, or use a trusted HTTPS reverse proxy from a restricted network. Sign in with the configured operator username and password. The server sets an HttpOnly, SameSite=Strict cookie; the browser keeps the CSRF token in memory. Do not expose the default credentials outside a restricted management network. Connection-test actions are not available until M21's route is implemented.

Compose binds to `0.0.0.0` and allows wildcard origins by default so other network nodes can reach the operator console. `MUSASHI_WEB_BIND` can select a specific host interface and `MUSASHI_ALLOWED_ORIGINS` can restrict browser origins. Configure `MUSASHI_PUBLIC_ORIGIN=https://...` when TLS terminates at a trusted reverse proxy. Direct LAN HTTP does not encrypt traffic.

## Container build

With `OPERATOR_USERNAME` / `OPERATOR_PASSWORD` set in `.env` as appropriate for the deployment, `docker compose build ingestion` builds the image. If omitted, Compose uses the documented local defaults. `docker compose up -d` starts the API and console on the selected host interface with a named persistent volume and a non-root container user. Compose does not map a serial device by default; add only the selected `/dev/serial/by-id/...` device for a site deployment. The IV controller speaks HTTP only, so restrict its network route. A successful image build is not evidence of host serial access or destination delivery.

## Development with Compose

Use the standalone development Compose file from the repository root:

```sh
docker compose -f compose.dev.yml up -d --build
curl -fsS http://127.0.0.1:8081/health
docker compose -f compose.dev.yml logs -f ingestion
```

Open `http://<dev-host>:8081/` and sign in with `OPERATOR_USERNAME` / `OPERATOR_PASSWORD` from the shell or `.env` (defaults: `admin` / `00000000`). `MUSASHI_DEV_PORT` overrides host port 8081; `MUSASHI_DEV_BIND` overrides the host interface and defaults to `0.0.0.0` for access from other network nodes. Dev uses wildcard origins for testing and direct HTTP.

This file uses project name `musashi-dev` and a separate named data volume, so it can run alongside the normal Compose deployment. It mounts `./src` read-only and sets `PYTHONPATH=/app/src` so Python and console assets use the working tree. A small watcher polls source files and restarts the service when any file under `src` changes. The service process restarts, so browser sessions are cleared; SQLite data remains in the dev volume. After changing package dependencies or the Dockerfile, rerun `up -d --build`.

Refresh the browser after console changes. Stop the dev environment with `docker compose -f compose.dev.yml down`; its config and records persist. Add `--volumes` only when you intend to delete the dev data. Real device access still requires explicit serial mapping or a reachable IV network.

## Current limits and evidence

The implementation defaults to a 2 MiB record limit and a 1 GiB SQLite spool quota; an oversized read faults acquisition. When the spool reaches its quota, it reclaims SQLite space and evicts the oldest committed records, including pending deliveries, to accept new data without stopping acquisition. Evicted records are permanently lost from the delivery buffer; spool status reports a persistent `evicted_record_count`. Actual disk/SQLite write failures still fault acquisition. MQTT messages default to at most 256 KiB including the envelope. These are provisional software guardrails, pending measured site capacity. Scan coverage and target delivery remain durable through SQLite. A destination failure keeps its assigned records pending until delivery or quota eviction; changed target settings receive a distinct identity. See the [working contract](docs/specs/rebuild-contract.md), [architecture](docs/architecture.md), and [ticket plan](docs/development-plan.md) for scope and open acceptance gates.

Run the checked-in synthetic regressions with `uv run python -m unittest discover -s tests -v`. Before the environment restricted sockets, the API restart test passed. The current socket-free subset passes 23 checks with `PYTHONPATH=src:tests .venv/bin/python -m unittest test_core test_devices test_ii_decode test_runtime test_iv_contract test_delivery test_recovery -v`; this includes a killed SQLite writer process, a live SQLite backup/restore, simulated destination outage and lost acknowledgment, and a simulated SQLite full error. The full discovery run currently fails only when its API test tries to create a socket (`PermissionError` in this environment). `docker compose build ingestion` passed before the latest source edits. The full M32 matrix and hardware checks have not run.

Influx scan snapshots use the bounded source tag `inventory`; their individual scan ID remains in the fields and complete JSON body. Older stored series keep their previous tags.
