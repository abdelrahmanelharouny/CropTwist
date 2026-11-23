# CropTwist Project Control

**Snapshot:** 2026-11-23 (UTC+02:00)  
**Repository:** [abdelrahmanelharouny/CropTwist](https://github.com/abdelrahmanelharouny/CropTwist)  
**Default branch:** `main`  
**Current integration baseline:** `4dd44dae19b54c68eb7963976701f3822545dfd5` (current main after M3/M4/M5–M7/P2/P3/UI-UX safety merges)

This file is the current coordination index. Historical reports dated 2026-11-14 and earlier are useful audit evidence, not the current release status. Always distinguish source implementation, CI, live integration, scientific validation and production acceptance.

## Current status

- **M1 Data & AI:** PR [#43](https://github.com/abdelrahmanelharouny/CropTwist/pull/43) and [#46](https://github.com/abdelrahmanelharouny/CropTwist/pull/46) are merged on current main. OpenRouter → Groq is the active provider order; Gemini is deferred; Ollama is disabled. NASA HLS, CDSE Sentinel-2 protected windows and WaPOR Egypt COG reads have live evidence. Scientific gates remain open: upstream Presto parity, provider-backed 12-month S1/S2/ERA5/SRTM ingestion, Egyptian label/license clearance, actual spatial/temporal classifier results and a human-reviewed bilingual E5 benchmark.
- **M2 Clean-room Release:** PR [#37](https://github.com/abdelrahmanelharouny/CropTwist/pull/37) merged. Exact-head CI, two-empty-PostGIS-database migration/idempotency/schema-parity, backend/E2E and clean frontend production build plus authenticated desktop English/mobile Arabic-RTL browser journeys passed on `017f53e5`.
- **M3 GIS/Satellite:** PR #32 merged a missing-CRS guard and acceptance notes. Live HLS/Sentinel asset reads, Fmask propagation, projected-CRS field-window correctness, quality-mask coverage and durable job lifecycle still require verification.
- **M4 Knowledge/Evidence:** PR #29 merged stratified Arabic/English retrieval evaluation. E5 is `intfloat/multilingual-e5-small` (384-D), with `query:`/`passage:` prefixes; reviewed relevance judgments, live retrieval evidence, citation checks and agronomist review remain.
- **M5–M7 Agricultural Intelligence:** PR #33 merged the M7.8 execution guard. Engines and scenarios exist; optimizer, water/soil arithmetic, scenario evidence and digital-twin integrity need consolidated scientific validation. M7.8 remains blocked until a real forecast/projection provider and method are approved.
- **P2/P3 SaaS:** PR #31 merged webhook SSRF/redirect regression hardening; PRs #19–23 integrated role-aware billing UX, notification pagination, interval scoring and analytics entitlement fixes. Live payment provider, production email and full end-to-end lifecycle acceptance remain.
- **Production:** not accepted. Staging API/Worker/PostGIS are online with TLS and bounded PostgreSQL raster storage. A staging S3 bucket exists, but the S3 switch and source update remain staged, not applied. PR #35's frontend and prior staging smoke checks passed; latest backend CI is still running. Production still requires its own S3 configuration, live provider secrets, email/payment providers, monitoring, backups and recovery evidence.
- **UI/UX:** PR #30 merged keyboard focus and reduced-motion support; full visual redesign and responsive/browser acceptance remain mandatory before production. The 104-file redesign branch is stale and must not be merged wholesale.

## Active parallel workstreams

These are isolated work packages. A branch is not considered complete until implementation, tests and review evidence exist. The M2 branch below must be refreshed from the current main baseline before integration.

| Workstream | Branch | Scope |
|---|---|---|
| M1 scientific closure | `work/m1-scientific-closure-2026-11-23` | Presto upstream parity harness, monthly source contract, Egyptian data/license audit, reviewed E5 corpus protocol |
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

PR [#35](https://github.com/abdelrahmanelharouny/CropTwist/pull/35) contains staging PostGIS TLS, storage smoke and the required boto3 dependency. Frontend CI and the previous staging smoke passed; latest exact-head backend CI remains in progress. Live staging smoke is manual-only so a PR check cannot pass against an unrelated deployed revision. PR [#36](https://github.com/abdelrahmanelharouny/CropTwist/pull/36) duplicates the boto3 dependency already included in #35 and should be closed after #35 is accepted. PR [#37](https://github.com/abdelrahmanelharouny/CropTwist/pull/37) is the current-main M2 clean-room candidate; exact-head backend checks are still in progress.

## Evidence discipline

For every milestone record: commit SHA; scope; exact commands and test counts; migration head/schema inventory; live-provider request IDs and provenance when applicable; browser evidence; known limitations; and the precise status among **Implemented**, **CI Passed**, **Live Verified**, **Scientifically Validated**, and **Production Accepted**.
