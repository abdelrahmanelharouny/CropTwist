# CropTwist Project Control

**Snapshot:** 2026-11-22 (UTC+02:00)  
**Repository:** [abdelrahmanelharouny/CropTwist](https://github.com/abdelrahmanelharouny/CropTwist)  
**Default branch:** `main`  
**Current integration baseline:** `9357e06c381a4a52bd870d243e2bb2cf189c87d4` (M1-E Qwen/Ollama merge)

This file is the current coordination index. Historical reports dated 2026-11-14 and earlier are useful audit evidence, not the current release status. Always distinguish source implementation, CI, live integration, scientific validation and production acceptance.

## Current status

- **M1 Data & AI:** M1-A through M1-D foundations are integrated. M1-E local Qwen/Ollama is now merged in PR [#24](https://github.com/abdelrahmanelharouny/CropTwist/pull/24) after both backend/PostGIS and frontend CI jobs passed. Ollama remains disabled by default. Numerical parity, multilingual retrieval benchmark, live FAO/WaPOR reads and live provider checks remain evidence gates.
- **M2 Clean-room Release:** not accepted. Requires two independent clean database builds, two-pass migration idempotency, Alembic drift check, complete suites and authenticated browser journeys.
- **M3 GIS/Satellite:** partially implemented; direct HLS Fmask propagation, projected-CRS field-window correctness, quality-mask coverage and durable job lifecycle require verification.
- **M4 Knowledge/Evidence:** partially implemented; E5 is `intfloat/multilingual-e5-small` (384-D), with `query:`/`passage:` prefixes. Real Arabic/English judgments, retrieval metrics, citation checks and agronomist review remain.
- **M5–M7 Agricultural Intelligence:** engines exist; optimizer, water/soil arithmetic, scenario evidence and digital-twin integrity need consolidated scientific validation. M7.8 remains blocked until a real forecast/projection provider and method are approved.
- **P2/P3 SaaS:** implementation is partial. Tenant/RBAC/entitlement, billing, notification, analytics, API-key and webhook lifecycle need database-backed security and workflow acceptance.
- **Production:** not accepted. Durable object storage, supervised workers, managed database, email/payment providers, TLS/ingress, monitoring, backups and recovery evidence remain.
- **UI/UX:** mandatory pre-deployment gate. Existing redesign branch is stale and must not be merged wholesale; the clean UI/UX workstream starts from current main and must preserve API, route, tenant and evidence contracts.

## Active parallel workstreams

Each branch was created from the M1-E merge baseline. These are isolated work packages; a branch is not considered complete until implementation, tests and review evidence exist.

| Workstream | Branch | Scope |
|---|---|---|
| M2 | `work/m2-clean-room-release` | Clean-room build, migration repeatability, full suites, browser journeys |
| M3 | `work/m3-gis-satellite-reliability` | HLS/Sentinel processing, CRS, masks, raster windows, job reliability |
| M4 | `work/m4-knowledge-evidence` | Versioned knowledge, E5/RAG evaluation, Arabic/English evidence |
| M5–M7 | `work/m5-m7-agricultural-intelligence` | Optimizer, water/soil science, scenarios, sensitivity, digital twin |
| P2/P3 | `work/p2-p3-saas-hardening` | RBAC, tenancy, entitlements, billing, notifications, API/webhooks |
| UI/UX | `work/ui-ux-predeployment` | Responsive visual system, RTL, accessibility, interaction/browser QA |

Workstream acceptance specifications live under `docs/workstreams/`. UI/UX must be accepted before any production deployment; it is not a post-deployment polish task.

## Integration policy

1. Work independently on each branch; avoid shared-file collisions and stacked dependencies unless explicitly documented.
2. Rebase/port against the latest `main` before review; inspect the complete diff for unintended changes.
3. Run the relevant targeted tests, then the full CI suite on the exact head SHA.
4. Merge only after required CI succeeds and domain-specific acceptance evidence is attached.
5. Keep externally blocked gates open when credentials, live data, expert review or infrastructure are unavailable. Do not substitute mocked tests for live evidence.
6. Do not deploy until M2, required M3–M7/P2/P3 production gates, and the UI/UX pre-deployment gate are accepted.

## Current pending M1 documentation PR

PR [#27](https://github.com/abdelrahmanelharouny/CropTwist/pull/27) records the M1 acceptance board but was based on the pre-M1-E main SHA and needs refresh/revalidation after PR #24. Its frontend CI passed; backend/PostGIS/E2E was still running at the last check. Do not merge it until the branch is updated to the current baseline and its exact-head checks pass.

## Evidence discipline

For every milestone record: commit SHA; scope; exact commands and test counts; migration head/schema inventory; live-provider request IDs and provenance when applicable; browser evidence; known limitations; and the precise status among **Implemented**, **CI Passed**, **Live Verified**, **Scientifically Validated**, and **Production Accepted**.
