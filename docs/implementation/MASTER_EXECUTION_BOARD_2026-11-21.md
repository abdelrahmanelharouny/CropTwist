# CropTwist — Master Execution Board

**Snapshot:** 2026-11-21  
**Repository baseline:** `main` at `58110363da7da701339dbae11fcc81ba9413a609`  
**Purpose:** one cross-phase execution view. This board supplements historical milestone reports; it does not turn source presence into a verified release claim.

## Operating rules

1. Keep work on isolated branches and PRs. Do not commit directly to `main`.
2. A PR is not complete because it is mergeable. Require backend + frontend CI on the exact latest head SHA, then review the diff and migration effects.
3. Do not deploy or mutate production while CI, scientific validation, or provider verification is incomplete.
4. Keep synthetic fixtures, model-derived estimates, observations, and missing data visibly distinct.
5. Use parallel workstreams, but batch pushes per branch to avoid unnecessary Actions cancellation churn.

## Cross-phase status

| Area | Current status | Remaining acceptance gate |
|---|---|---|
| M0 — architecture/contracts | Existing architecture and ADRs are in place | Keep module boundaries and evidence contracts intact as new work lands |
| M1 — data + AI integration | Active Draft PRs #5, #11–14, #17–18 | Fix exact-head CI; complete E5 RAG contract; prove Presto label provenance; live provider probes remain external gates |
| M2 — clean-room release | Not accepted for a fresh release | Rebuild from current `main` + reviewed PRs in disposable PostGIS; run migrations twice + drift check; full tests; browser smoke; worker/report lifecycle; record exact SHA |
| M3 — geospatial/features | Existing M3 implementation; M1 satellite acquisition hardening remains open | Projected-CRS window tests, Fmask propagation, bounded reads, provider provenance and live acquisition |
| M4 — knowledge/evidence | Existing knowledge services; scientific audit findings remain | Version-conflict, regional-trait calculation/citation parity, evidence completeness and unit-safe numeric validation |
| M5 — rotation optimizer | Existing optimizer; regional/seasonal audit gaps remain | Two-season preference-reversal tests, missing-evidence admission gates, interval traits and solver/display objective parity |
| M6 — water/soil | M6A–M6C implementations exist in historical reports | Reconcile current main lineage and run the integrated regression suite; do not rely on report-only branch state |
| M7 — simulation/decision twin | M7.5–M7.7 reported complete; M7.8 explicitly blocked | No synthetic substitute for a real climate projection/forecast source; preserve honest missing-data behavior |
| P2 — advanced agricultural intelligence | Partial across knowledge, satellite, forecasting and decision workflows | Close regional/temporal correctness gaps and complete approved Presto/RAG evaluation before claiming predictive capability |
| P3 — commercial SaaS | Billing, reports, notifications, analytics, public API and webhooks exist in source | Exact role/tenant isolation, accurate pagination/quotas, durable worker semantics, localized UX, and live payment/email/storage provider validation |
| Release/operations | Historical Vercel/Railway release exists; current live state is not inferred | Fresh deployment only after clean-room acceptance, secrets/TLS/backup/monitoring checks and post-deploy smoke |

## Active parallel workstreams

### Lane A — CI and integration recovery
- PR #5: Sentinel-2 contract wording regression fixed; rerun exact-head CI.
- PR #11: Presto validation error wording aligned with its regression contract; rerun exact-head CI.
- PR #12: CI passed on the recorded head, but implementation still uses MiniLM rather than the selected multilingual E5 model/prefix contract. Do not merge.
- PR #13: WaPOR canonical period/read validation and stale test expectations corrected; rerun exact-head CI.
- PR #14: provider diagnostics CI passed on its recorded head; live connectivity still unverified.
- PR #17/#18: synthetic bridge tests now explicitly opt in to mocked non-sensitive requests; preserve fail-closed production defaults and rerun both stacked branches.

### Lane B — AI, privacy and evidence
- Finish multilingual E5 model registration, immutable revision/hash verification, query/passsage prefixes, and Arabic/English agricultural retrieval evaluation.
- Verify Presto feature schema, labels/licensing, spatial/temporal splits, and model evaluation; no trained crop classifier claim until this exists.
- Keep local Qwen opt-in and loopback-only; hosted providers must not receive sensitive farmer data without explicit approval.
- Extend evidence-bound numeric/citation validation to every user-visible AI narrative.

### Lane C — P2/P3 product correctness
- PR #19: role-aware Billing UI; member roles must not trigger admin-only billing requests.
- PR #20: SQL-side notification severity filtering so items, total and unread counts share one exact filtered result set.
- Continue report lifecycle, tenant isolation, API-key quotas, webhook delivery/retry, onboarding and analytics acceptance tests.
- Keep backend authorization authoritative; UI gating is not a security boundary.

### Lane D — M2 clean-room and operations
- Build from a clean checkout of the exact reviewed `main` SHA in an isolated environment.
- Run Alembic upgrade twice, current/head check, `alembic check`, full backend tests, frontend typecheck/lint/build and browser journeys.
- Validate API + separate worker behavior, report generation/download, queue recovery and tenant boundaries.
- Verify storage persistence, TLS ingress, secret handling, backups/restore, monitoring and spend limits.
- No production promotion until every release acceptance item has a recorded result.

## Known current boundaries

- WaPOR catalogue/raster access and physical unit/scale semantics still require live source verification.
- Sentinel-2/HLS code tests do not prove a real scene can be acquired and processed in production.
- Presto weights/embeddings do not constitute verified Egyptian crop labels or calibrated crop probabilities.
- Gemini/Groq/OpenRouter credentials and live provider quality/latency are not established by mocked tests.
- The billing provider is sandbox-only; no real payment processing is claimed.
- Notification email is an adapter seam until a delivery provider is configured and tested.
- M7.8 remains blocked until a compatible real forecast/projection provider is available.
- Railway/Vercel historical deployment records are not a live health check.

## Definition of done

A milestone is complete only when:
- implementation is on a reviewable branch and its diff matches the stated scope;
- focused regression tests and the full relevant CI jobs pass on the exact latest commit;
- migration impact is understood and validated on a disposable database where applicable;
- source, provenance, permissions, failure modes and limitations are documented;
- no live provider, production deployment, or model performance claim is made without direct evidence.

