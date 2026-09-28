# M37 — Add session sign-in and sign-out to the operator console

Status: ready-for-human
Completion: unverified

**Depends on:** [M36](M36-session-auth-backend.md).

**Outcome:** An operator signs in with the shared username/password and uses the existing console through the session API, without entering a bearer token.

## Input and output contract

- **Input:** M36's implemented auth routes and the [M34 browser contract](M34-frontend-api-contract.md), including a same-origin session cookie and CSRF token.
- **Output:** English-only sign-in, active-session restore after reload, explicit sign-out, and same-origin API requests carrying a session cookie and required CSRF header.
- **Failure output:** Invalid login shows a generic error without retaining the password; 401 clears all protected data from the page and returns to sign-in; 403 refreshes session status and reports the failed action without replaying a mutation. Network failure leaves a clear retry action.
- **Boundary:** This owns browser authentication state and UI interaction. M36 owns server authentication; M35 owns the four operational pages and end-to-end console review.

## Fixed work order and evidence

1. Replace token entry and bearer headers in the current console with labeled username/password fields, `POST /api/auth/login`, `GET /api/auth/session` on page load, and `POST /api/auth/logout`. Keep the CSRF token only in page memory; allow the browser to manage the HttpOnly cookie. Never store credentials, session IDs, or CSRF tokens in web storage, URL, HTML assets, or logs.
2. Route all protected API calls through one same-origin client that sends `X-CSRF-Token` on state-changing requests. Clear cached config, status, records, scans, and unsaved secret inputs on logout or 401. On 403, refresh session status and require an explicit retry for any mutation. Restore the operational view after reload only while the session is valid.
3. Review the sign-in flow with keyboard and narrow viewport, invalid credentials, a successful reload, logout, expired session, CSRF 403, and offline API. Inspect browser network/storage state for credential leaks and verify all visible auth text is English.

## Acceptance checks

- [ ] Login, reload with a valid session, logout, and expired-session recovery work without a token entry prompt or bearer header.
- [ ] 401 and logout remove protected content and credentials from the page; 403 never silently replays a mutation.
- [ ] Auth screens and messages are English, keyboard accessible, and usable on a narrow viewport.
- [ ] Browser inspection finds no password, session ID, or CSRF token in persistent storage, URL, static assets, or screenshots.

**Verification:** Review the UI on the same-origin local service with representative auth success/failure responses. M35 records access from the operator's separate network device.

## Comments

- 2026-09-28: Implemented the session sign-in UI against M36: page load checks `/api/auth/session`, credentials post to `/api/auth/login`, sign-out posts to `/api/auth/logout`, and all state-changing API calls include the in-memory CSRF token. Removed bearer-token handling. A 401 clears protected page data, cached responses, dialogs, and password inputs before returning to sign-in. A 403 refreshes session status and reports that the action was not repeated. Added focused offline contract checks in `tests/test_web_auth_contract.py`; browser interaction, browser storage/network inspection, and deployment checks remain pending, so completion is unverified.
- 2026-09-28: Code review added an explicit “Retry sign in” action after a network failure; the password stays only in the page input for that retry and remains cleared after invalid credentials. Review fixes passed the full 38-test suite and `node --check`. The deployed tailnet flow completed login, session restore, protected config read, and logout. Manual keyboard/narrow-viewport and browser storage/network inspection remain pending, so completion is unverified.
