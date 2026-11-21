# CropTwist — Master Execution Board

**Snapshot:** 2026-11-21  
**Repository baseline:** latest verified merge on `main` is `9e82c5a55041a812a8457bda0e23b529c897f1d1` (M1-A + AI privacy fix merged after the prior baseline)  
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
| M1 — data + AI integration | M1-A (#5) merged; privacy fix (#17) merged; #11–14 and #18 remain separate | Complete Presto runtime parity; judged E5 retrieval benchmark; live satellite/WaPOR/provider checks remain explicit gates |
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
- PR #5: merged as `aa56505`; exact-head backend and frontend CI both passed. Live CDSE/HLS acquisition remains unverified.
- PR #11: current head `c5306c8`; frontend CI passed, backend pytest is running after two validation-message-only fixes. Keep Draft until backend finishes; numerical parity with upstream pretrained Presto is still a separate gate.
- PR #12: exact-head CI passed. It now implements pinned multilingual E5 (not MiniLM), SHA-256 verification and task prefixes; real warmup plus an agronomist-judged Arabic/English retrieval benchmark remain required.
- PR #13: exact-head CI passed. WaPOR live FAO raster smoke and live L2-RSM-D availability remain unverified.
- PR #14: exact-head CI passed. Gemini/Groq/OpenRouter credentials and authenticated connectivity probes remain unverified.
- PR #17: merged as `9e82c5a`; sensitive prompts are blocked from the legacy bridge unless the explicit external-provider approval gate is enabled.
- PR #18: exact-head CI passed, but remains stacked on the old PR #17 branch. Rebase/retarget after the squash merge before considering merge; local Qwen model/runtime quality and latency are unverified.

### Lane B — AI, privacy and evidence
- E5 implementation is present on PR #12 with immutable revision/hash verification and `passage:`/`query:` prefixes. Still run actual model warmup and a reviewed bilingual agricultural corpus benchmark before enabling semantic retrieval.
- Presto implementation is present on PR #11; verify pretrained-weight numerical parity with upstream `eval_task=True`, then source verified Egypt labels/licensing and run spatial/temporal evaluation. No crop classifier claim until all gates pass.
- Keep local Qwen opt-in and loopback-only; PR #17 now blocks sensitive legacy-bridge prompts unless explicit external-provider approval is enabled.
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

## Latest verified integration snapshot (2026-11-21)

| PR | Exact head / result | Current decision |
|---|---|---|
| #5 M1-A | `b3487981` — backend + frontend CI passed; merged as `aa56505` | Integrated; live satellite credentials/smoke still required |
| #11 M1-B Presto | `c5306c8b` — frontend passed; backend CI run #645 in progress | Hold Draft until backend is green and upstream pretrained-weight parity is demonstrated |
| #12 M1-C local E5 RAG | `531f30e5` — backend + frontend CI passed | Keep disabled pending warmup, reviewed corpus, bilingual retrieval metrics and host resource benchmark |
| #13 M1-D WaPOR | `01c755b6` — backend + frontend CI passed | Keep live-data claims blocked pending FAO raster smoke and L2-RSM-D verification |
| #14 M1-E provider diagnostics | `d1adf97c` — backend + frontend CI passed | Diagnostic code integrated only after merge; no provider is live-verified by mocked CI |
| #17 legacy bridge privacy | `42aab384` — backend + frontend CI passed; merged as `9e82c5a` | Integrated; sensitive legacy-bridge traffic is fail-closed without explicit approval |
| #18 local Qwen | `402cc65e` — backend + frontend CI passed | Stacked base still references pre-squash #17 branch; rebase/retarget required before merge |
| #22 interval-valued soil scoring | `7dfe17a7` — backend + frontend CI passed | P2 review candidate; conservative bounds, no invented midpoint |
| #23 analytics entitlement | `fb0432fd` — backend + frontend CI passed | P3 review candidate; server-side plan gate, no production mutation |

The GitHub workflow-run listing used for this snapshot exposes PR-triggered runs only; it does not establish the status of the post-merge `main` push workflow. Verify the resulting `main` CI separately before any release. PRs #11–14 still target the earlier `e32d0c3` base; re-check mergeability and exact-head CI after each sequential merge. PRs #22–23 target the pre-M1-A `5811036` baseline and also require post-merge integration review.

## Definition of done

A milestone is complete only when:
- implementation is on a reviewable branch and its diff matches the stated scope;
- focused regression tests and the full relevant CI jobs pass on the exact latest commit;
- migration impact is understood and validated on a disposable database where applicable;
- source, provenance, permissions, failure modes and limitations are documented;
- no live provider, production deployment, or model performance claim is made without direct evidence.

