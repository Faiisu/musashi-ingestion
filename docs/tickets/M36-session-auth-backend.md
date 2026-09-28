# M36 — Replace operator bearer authentication with browser sessions

Status: ready-for-agent
Completion: unverified

**Depends on:** None; [ADR 0003](../adr/0003-shared-session-login-for-the-operator-console.md) is accepted.

**Outcome:** The management API authenticates the shared local operator account with a browser session. Login, logout, expiry, restart, and CSRF behavior follow the [browser API contract](M34-frontend-api-contract.md) without requiring completion of status, spool, or connection-test work.

## Input and output contract

- **Input:** `OPERATOR_USERNAME` and `OPERATOR_PASSWORD` from the environment, defaulting to `admin` and `00000000`; an optional trusted `MUSASHI_PUBLIC_ORIGIN` for a TLS-terminating proxy; browser JSON login and same-origin requests.
- **Output:** The M34 `POST /api/auth/login`, `GET /api/auth/session`, and `POST /api/auth/logout` responses; an opaque server-side session in an HttpOnly cookie; CSRF token and protected API authorization. A valid session lasts at most 8 hours idle or 24 hours total and does not survive server restart.
- **Failure output:** An explicitly blank username/password prevents startup; bad credentials return a generic 401; missing/invalid sessions return 401; cross-origin or missing/invalid CSRF protection on an authenticated mutation returns 403. Secrets, session IDs, and passwords do not appear in logs or response bodies.
- **Boundary:** This owns credential loading, auth routes, session store, cookie issuance, CSRF checks, and authorization middleware. M21 consumes that middleware for configuration and connection tests; M37 owns the browser sign-in UI. No individual accounts, external identity provider, external API-client contract, or bearer-token fallback is included.

## Fixed work order and evidence

1. Replace `OPERATOR_TOKEN` wiring in the service entry point, Compose, and `.env.example` with `OPERATOR_USERNAME` / `OPERATOR_PASSWORD`. Unset variables use the accepted defaults; explicitly blank values prevent startup. Ignore any old bearer token as an authorization method. Document the migration and current defaults when updating the README after implementation.
2. Implement the auth routes and cookie/CSRF contract specified by M34. Use unpredictable opaque session IDs stored only in server memory. Invalidate the current session on logout and every session on restart. Apply idle and absolute expiry to all protected routes. Use constant-time credential/session comparisons where applicable and generic login errors; do not add rate limiting, delay, lockout, or mandatory password change.
3. Validate `Origin` for every state-changing request, including login. After login, require `X-CSRF-Token` for state-changing requests and check authorization before CSRF so an anonymous protected request returns 401. Keep auth responses uncached. For direct HTTP, accept only the configured local management URL (`http://127.0.0.1:<published port>` in the default deployment) as both `Host` and `Origin`; reject a mismatched Host/Origin and requests for an unconfigured network name. When TLS ends at a proxy, require `MUSASHI_PUBLIC_ORIGIN` to be an explicit HTTPS scheme and authority with no user info, path, query, or fragment; reject invalid values at startup. Use it for Origin checks and the cookie's `Secure` flag, and do not trust client-supplied forwarding headers to choose the public scheme. With this setting, perform browser login through that HTTPS origin; direct backend HTTP remains for local health/operations checks, not an alternate browser login origin.
4. Exercise the auth route table with a local service: default and overridden credentials, explicitly blank settings, invalid login, old bearer rejection, session reload, logout, idle and absolute expiry with an injected clock, restart invalidation, CSRF and cross-origin rejection, cookie flags on HTTP and trusted HTTPS-proxy configurations, and no credential leakage. Record requests, status codes, safe headers, and evidence paths without recording real credentials.

## Scope and constraints

- Keep `/health` public and non-sensitive; protect topology/config/status/records/scans reads and all management writes. The known default `admin` / `00000000` has no login throttling and is permitted only behind a restricted management network under ADR 0003.
- The existing management origin remains loopback first. A public HTTPS origin may be configured only for a trusted reverse proxy; the deployment guide must describe the matching network boundary.

## Acceptance checks

- [ ] Login/session/logout responses, cookies, expiry, and restart invalidation match M34; a valid cookie authorizes existing protected routes, while bearer-only and anonymous requests receive 401.
- [ ] Bad credentials, explicitly blank configuration, unconfigured or mismatched Host/Origin, cross-origin requests, and missing/invalid CSRF tokens fail with the specified status and do not change configuration or acquisition state.
- [ ] The cookie is HttpOnly and SameSite=Strict, and is Secure for the configured HTTPS public origin; password and session ID do not appear in response bodies, URLs, or logs, and the CSRF token does not appear in URLs or logs. M37 verifies browser storage and assets.
- [ ] Compose, `.env.example`, service startup, and README describe the same credential variables and working login flow; a clean local startup needs no old `OPERATOR_TOKEN`.

**Verification:** Use a disposable local service and injected clock. Record the full auth/error table plus local HTTP and trusted HTTPS-proxy cookie evidence. This is software evidence; M35 owns operator-device access evidence.

## Comments

- 2026-09-28: Implemented browser session authentication and exercised the local service route table in `tests/test_api.py`; `PYTHONPATH=src python3 -m unittest discover -s tests -v` passed 34 tests. Coverage includes default and overridden credentials, blank configuration, invalid login, bearer rejection, session reload/logout/restart, injected idle and absolute expiry, Origin/Host/CSRF rejection, and HTTP/trusted-proxy cookie flags. `docker compose config`, `git diff --check`, and Python compile checks passed. Completion remains unverified pending browser UI integration and deployment/network evidence; response/log leakage inspection is also not recorded as separate evidence.
