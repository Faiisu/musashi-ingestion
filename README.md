# Musashi ingestion service and operator console

This repository is rebuilding a read-only ingestion service for Musashi Super ΣCM II and IV dispensers. It has an authenticated management API, a responsive operator console, a SQLite record spool, safe request adapters, independent machine workers, and MQTT/PostgreSQL/InfluxDB delivery adapters. Device reads have only been exercised with synthetic responses; limited MQTT and PostgreSQL service checks passed, while hardware compatibility and a full three-destination round trip remain open ticket gates.

## Prerequisites

- Python 3.11 or newer and `uv`, `curl`, and `jq`, or Docker with Compose.
- Operator credentials from `OPERATOR_USERNAME` and `OPERATOR_PASSWORD`; local defaults are `admin` and `00000000`.
- For real II/IV reads, an operator-approved machine, serial device or restricted IV network, and evidenced channel/recipe counts.

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

The API is bound to `127.0.0.1:8080` by default. `MUSASHI_BIND`, `MUSASHI_PORT`, and `MUSASHI_DATA_DIR` override those values. `OPERATOR_USERNAME` and `OPERATOR_PASSWORD` default to `admin` and `00000000`; explicitly blank values prevent startup. Set `MUSASHI_PUBLIC_ORIGIN` to the exact HTTPS origin when TLS terminates at a trusted reverse proxy. The proxy must preserve that host and origin; forwarded headers are not trusted. When configured, browser login must use that HTTPS origin, and direct backend HTTP is not an alternate browser login origin. Sessions are stored in memory, expire after 8 idle hours or 24 total hours, and are cleared on restart. Configuration updates use `PUT /api/config` with the current `revision`, `version: 1`, `machines`, and `destinations`; Start and Stop are `POST /api/control/start` and `/api/control/stop`. `GET /api/scans` shows recent inventory item coverage. Passwords belong in permission-restricted environment secrets; machine and destination secret references are redacted on read. Do not treat the retained `config/config.json` as a compatible configuration file.

## Operator console and network access

Open `http://127.0.0.1:8080/` on the host, or use a trusted HTTPS reverse proxy from a restricted network. Sign in with the configured operator username and password. The server sets an HttpOnly, SameSite=Strict cookie; the browser keeps the CSRF token in memory. Do not expose the default credentials outside a restricted management network. Connection-test actions are not available until M21's route is implemented.

For Compose, host port publishing stays on loopback by default. `MUSASHI_WEB_BIND` selects a specific host interface for LAN access; the checked-in `.env.example` keeps loopback as its default. Configure the exact `MUSASHI_PUBLIC_ORIGIN=https://...` when TLS terminates at a trusted reverse proxy, and keep both proxy and backend on a restricted network. The default credentials are deliberately weak and permitted only behind that network boundary. Direct LAN HTTP does not encrypt traffic.

## Container build

With `OPERATOR_USERNAME` / `OPERATOR_PASSWORD` set in `.env` as appropriate for the deployment, `docker compose build ingestion` builds the image. If omitted, Compose uses the documented local defaults. `docker compose up -d` starts the API and console on the selected host interface with a named persistent volume and a non-root container user. Compose does not map a serial device by default; add only the selected `/dev/serial/by-id/...` device for a site deployment. The IV controller speaks HTTP only, so restrict its network route. A successful image build is not evidence of host serial access or destination delivery.

## Current limits and evidence

The implementation defaults to a 2 MiB record limit and a 1 GiB SQLite spool quota; an oversized read or full spool faults acquisition instead of truncating data. MQTT messages default to at most 256 KiB including the envelope. These are provisional software guardrails, pending measured site capacity. Scan coverage and target delivery remain durable through SQLite. A destination failure keeps its assigned records pending; changed target settings receive a distinct identity. See the [working contract](docs/specs/rebuild-contract.md), [architecture](docs/architecture.md), and [ticket plan](docs/development-plan.md) for scope and open acceptance gates.

Run the checked-in synthetic regressions with `uv run python -m unittest discover -s tests -v`. Before the environment restricted sockets, the API restart test passed. The current socket-free subset passes 23 checks with `PYTHONPATH=src:tests .venv/bin/python -m unittest test_core test_devices test_ii_decode test_runtime test_iv_contract test_delivery test_recovery -v`; this includes a killed SQLite writer process, a live SQLite backup/restore, simulated destination outage and lost acknowledgment, and a simulated SQLite full error. The full discovery run currently fails only when its API test tries to create a socket (`PermissionError` in this environment). `docker compose build ingestion` passed before the latest source edits. The full M32 matrix and hardware checks have not run.
