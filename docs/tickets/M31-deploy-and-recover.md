# M31 — Deploy, secure, back up, and restore the backend

Status: needs-triage
Completion: unverified

**Depends on:** [M21](M21-secure-configuration.md), [M26](M26-spool-recovery-and-identity.md), [M27](M27-multi-machine-scheduling.md), [M28](M28-mqtt-delivery.md), [M29](M29-postgres-delivery.md), [M30](M30-influx-delivery.md).

**Outcome:** An operator can reproduce a restricted Linux deployment, protect its management endpoint, and recover config plus pending data.

## Input and output contract

- **Input:** Locked package/container definitions, protected host/network and selected serial devices, operator credential and destination secret files, persistent config/spool volume, and documented backup window.
- **Output:** A reproducible install/upgrade/rollback and backup/restore guide with commands, expected health and fault signals, restored record IDs, scan coverage, pending assignments, and a successful replay to each selected destination.
- **Failure output:** Missing serial/network/service access, invalid secrets, disk/quota exhaustion, and failed restore are diagnosable without secret exposure or false healthy state.
- **Boundary:** This owns host operation and recovery evidence, including retention/backfill visibility. It does not establish real firmware support; M33 owns site/device acceptance. Upgrade of an unidentified historical spool is not assumed.

## Fixed work order and evidence

1. Deliver `docs/guides/deploy-and-recover.md` plus `scripts/backup.py` and `scripts/restore.py`. The guide uses the checked-in `Dockerfile` and M36-updated `compose.yml` on a clean Linux test host/VM, binds management to host loopback, sets `OPERATOR_USERNAME` and `OPERATOR_PASSWORD` through a local secret source (defaults `admin` / `00000000`), persists `/data`, and maps only explicitly selected serial device paths. For a TLS-terminating proxy, set the exact HTTPS `MUSASHI_PUBLIC_ORIGIN`, keep the backend bound to loopback, and verify the Secure session cookie and Origin/CSRF behavior through the public address. Explain that browser login uses the configured HTTPS origin when it is set; localhost backend HTTP is not a second browser login origin. Warn that the default password and absence of login throttling are unsafe on an untrusted network. Show exact install, health, login, authenticated status/Stop with cookie and CSRF header, upgrade, rollback, backup, restore, and replay commands with expected exit/result.
2. Stop acquisition and delivery before backup. Use SQLite's `Connection.backup()` into a temporary file, copy config and referenced secret files with mode 0600, record a manifest of SHA-256 hashes and schema/config revision, then atomically promote the backup directory. Restore requires the service stopped, verifies every hash before replacing data, restores file modes, and starts one service instance. Do not run original and restored spools concurrently against the same Influx bucket. On hash or schema mismatch, leave the active data untouched and report a named failure.
3. Evidence on a clean VM records non-root UID, only chosen device mapping, denied anonymous API, permitted authenticated API, HTTPS proxy cookie/Origin/CSRF behavior, fake IV and all three destination reachability, pseudo-serial open through the mapped path, container recreation, backup/restore of one pending record and one partial scan, replay with stable record ID, retention boundary, and a pending-only endpoint reroute. Missing test route yields a failed or blocked row, never a claimed success. M35 separately verifies access from the operator's device. The guide distinguishes simulated serial access from named hardware acceptance.

## Scope and constraints

- Package the management service and its same-origin UI. Run as non-root, map only selected serial devices, avoid privileged mode, and verify IV/network access under HTTP-only device constraints.
- Persist config, secret material, and SQLite spool with permissions and backup steps. Bind management to loopback or a protected interface by default; require an authenticated browser session for sensitive reads and writes (B02). Exercise login, session expiry, logout, and session invalidation after container recreation.
- Document tested install, upgrade, rollback, backup, restore, and fault diagnosis procedures. Avoid claiming a successful build alone proves host operation.

## Acceptance checks

- [ ] Fresh-host instructions start a healthy service; management is inaccessible without a valid session, HTTPS proxy access sets a Secure cookie and rejects cross-origin/CSRF failures, and deployment guidance clearly restricts network access because the accepted default password is weak and has no login throttling.
- [ ] Container recreation and restore preserve config, pending records, scan state, destination lane identity, and the retained-history backfill boundary.
- [ ] Serial test device works without privileged mode; external service and IV network checks report clear failures.
- [ ] An offline destination and a full spool produce actionable status without exposing credentials.
- [ ] Recovery instructions show the retained-history window, any backfill gap, and pending-only reroute result after a destination endpoint change.

**Verification:** Follow the guide on a clean test host/VM, back up live data, recreate, restore, and replay a pending record.

## Comments

- 2026-09-28: Non-root Dockerfile and loopback Compose build exist. Clean-host run, serial mapping, backup/restore, and offline/full-spool operations checks remain open. Synthetic checks do not establish hardware acceptance.
- 2026-09-28: A live `sqlite3.Connection.backup()` snapshot plus a copied static config file restored pending data, incomplete scan coverage, and the old target identity in a new directory (`tests/test_recovery.py`). A fake destination outage and lost acknowledgment retained pending data across spool reopen, then replayed it. Container recreation, secret-file backup, clean-host install, and actual service failure remain unverified; the current environment denies Docker access.
