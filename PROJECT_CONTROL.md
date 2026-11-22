# CropTwist Project Control

**Snapshot:** 2026-11-22 (UTC+02:00)  
**Repository:** [abdelrahmanelharouny/CropTwist](https://github.com/abdelrahmanelharouny/CropTwist)  
**Default branch:** `main`  
**Current integration baseline:** `d519c381e923f73df15acdb99872fdfc9a701a04` (current main after M3/M4/M5–M7/P2/P3/UI-UX safety merges)

This file is the current coordination index. Historical reports dated 2026-11-14 and earlier are useful audit evidence, not the current release status. Always distinguish source implementation, CI, live integration, scientific validation and production acceptance.

## Current status

- **M1 Data & AI:** M1-A through M1-D foundations are integrated. M1-E local Qwen/Ollama is now merged in PR [#24](https://github.com/abdelrahmanelharouny/CropTwist/pull/24) after both backend/PostGIS and frontend CI jobs passed. Ollama remains disabled by default. Numerical parity, multilingual retrieval benchmark, live FAO/WaPOR reads and live provider checks remain evidence gates.
- **M2 Clean-room Release:** CI passed on PR #28 head `1a09ac7` (two independent PostGIS databases, idempotent migrations, schema parity, full backend/E2E, frontend production build, desktop + Arabic RTL browser journeys). That head is 5 commits behind current main; port/rebase and rerun exact-head CI before merge.
- **M3 GIS/Satellite:** PR #32 merged a missing-CRS guard and acceptance notes. Live HLS/Sentinel asset reads, Fmask propagation, projected-CRS field-window correctness, quality-mask coverage and durable job lifecycle still require verification.
- **M4 Knowledge/Evidence:** PR #29 merged stratified Arabic/English retrieval evaluation. E5 is `intfloat/multilingual-e5-small` (384-D), with `query:`/`passage:` prefixes; reviewed relevance judgments, live retrieval evidence, citation checks and agronomist review remain.
- **M5–M7 Agricultural Intelligence:** PR #33 merged the M7.8 execution guard. Engines and scenarios exist; optimizer, water/soil arithmetic, scenario evidence and digital-twin integrity need consolidated scientific validation. M7.8 remains blocked until a real forecast/projection provider and method are approved.
- **P2/P3 SaaS:** PR #31 merged webhook SSRF/redirect regression hardening; PRs #19–23 integrated role-aware billing UX, notification pagination, interval scoring and analytics entitlement fixes. Live payment provider, production email and full end-to-end lifecycle acceptance remain.
- **Production:** not accepted. Staging API/Worker/PostGIS are online with TLS and bounded PostgreSQL raster storage. PR #35 is ready for review but not merged. Production still requires S3 bucket configuration, live provider secrets, email/payment providers, monitoring, backups and recovery evidence.
- **UI/UX:** PR #30 merged keyboard focus and reduced-motion support; full visual redesign and responsive/browser acceptance remain mandatory before production. The 104-file redesign branch is stale and must not be merged wholesale.

## Active parallel workstreams

These are isolated work packages. A branch is not considered complete until implementation, tests and review evidence exist. The M2 branch below must be refreshed from the current main baseline before integration.

| Workstream | Branch | Scope |
|---|---|---|
| M2 | `work/m2-clean-room-release-current-main` | Clean-room build, migration repeatability, full suites, browser journeys (refreshed from current main) |
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

PR [#35](https://github.com/abdelrahmanelharouny/CropTwist/pull/35) contains the staging PostGIS TLS and bounded storage deployment work. It is out of draft and all backend/frontend/staging smoke checks passed; it remains unmerged pending review. PR [#36](https://github.com/abdelrahmanelharouny/CropTwist/pull/36) fixes the missing boto3 dependency required by the existing S3 raster backend; CI is running.

## Evidence discipline

For every milestone record: commit SHA; scope; exact commands and test counts; migration head/schema inventory; live-provider request IDs and provenance when applicable; browser evidence; known limitations; and the precise status among **Implemented**, **CI Passed**, **Live Verified**, **Scientifically Validated**, and **Production Accepted**.
