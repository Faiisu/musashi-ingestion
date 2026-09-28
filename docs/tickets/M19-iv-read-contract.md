# M19 — Prove the Model IV safe HTTP contract with fixtures

Status: ready-for-agent
Completion: unverified

**Depends on:** None; can start now.

**Outcome:** An exact read request catalog and response fixtures cover every permitted IV data family without relying on the removed adapter.

## Input and output contract

- **Input:** The IV Ethernet API manual, configured model/port and typed channel or recipe ID ranges, plus labeled synthetic JSON, TSV, null, sparse, and fault responses.
- **Output:** A manual-cited allowlist of exact method/path templates and per-family response contracts, including URL ID versus payload numbering, size/deadline limits, and expected parsed or unavailable result.
- **Failure output:** Redirect, malformed or oversized body, timeout, forbidden action or screen path, and out-of-range ID yield a bounded rejection with no follow-up control request.
- **Boundary:** This catalogs permitted reads and fixtures; M24/M25 execute them, and M33 confirms firmware behavior on named devices.

## Fixed work order and evidence

1. Treat `src/musashi_ingestion/devices/iv.py` constants `STATUS`, `COMMON`, `DIAGNOSIS`, and `STATIC` as the enumerated software allowlist and `docs/reference/device-protocols.md` as its manual citation map. Enumerate 16 status paths, 2 machine/time paths, 12 common paths, 4 recipe/channel all/range paths, 2 exports, 3 diagnostic results, and typed per-ID templates. Record the printed manual page and response kind beside every row; a missing citation is an unresolved row.
2. Extend `tests/fixtures/iv_responses.json` with one success or explicit `null` response for each enumerated path family and fixed cases for partial `data/all`, missing ID, malformed range, oversized JSON, oversized TSV, timeout, redirect, malformed JSON, forbidden control GET, screen, POST, and out-of-range ID. For failure cases, expected output is one named error, zero follow-up requests, and a byte trace containing no forbidden path.
3. Compare the manifest's exact path set with `path_for`, `status_requests`, and `inventory_requests`; report missing/extra paths as failed rows. Payload `no` starts at 0 while URL IDs start at 1. Leave firmware-specific response variants for M33 with an explicit unknown label.

## Scope and constraints

- Review the [IV manual](../reference/device-protocols.md): status endpoints, machine/time, all common data and ranges, recipe/channel `data/all` and `/range`, bounded single-item fallbacks, export data/log, and diagnostic results.
- Record URL ID versus payload `no`, JSON/TSV/null/error variants, port range 1024–1026, HTTP-only transport, and the three-client limit. The site network must restrict access because device HTTPS is unavailable.
- Build exact path templates with typed IDs. Exclude `/v1/screen`, every write/action path including state-changing GETs, arbitrary URLs, redirects, and POST.

## Acceptance checks

- [ ] Each allowed and forbidden family has a manual citation and explicit evidence level.
- [ ] Synthetic fixtures include partial `data/all`, missing IDs, range responses, oversized export/log, timeout, redirect, and malformed content.
- [ ] The allowlist rejects control paths, screen images, out-of-range IDs, and user-supplied paths.
- [ ] Questions requiring real IV firmware are listed for site acceptance.

**Verification:** Compare the catalog and fixture manifest with the manual's Ethernet API section; inspect the entire allowed request set for machine-state changes.

## Comments

- 2026-09-28: IV exact-path adapter and synthetic redirect/forbidden-path checks exist in `src/musashi_ingestion/devices/iv.py` and `tests/test_devices.py`. Full response/fault fixture manifest and firmware questions remain open. Synthetic checks do not establish hardware acceptance.
- 2026-09-28: Added `tests/fixtures/iv_responses.json` and `tests/test_iv_contract.py` for sparse `data/all`, range, null, malformed JSON, oversized export, timeout, redirect, and forbidden paths. The catalog remains manual-derived; a full endpoint-by-endpoint manual citation review and real firmware checks remain open.
