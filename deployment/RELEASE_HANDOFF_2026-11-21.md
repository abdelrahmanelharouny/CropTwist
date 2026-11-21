# CropTwist — release handoff and four-hour execution gates

**As-of date:** 2026-11-21  
**Repository:** `abdelrahmanelharouny/CropTwist`  
**Production alias recorded by the previous release:** https://croptwist.vercel.app

## 1. Existing release — do not redeploy the stale branch

PR #4 (`release/croptwist-final-launch`) was merged on 2026-11-14. Its release record identifies tested PR head `5b689884684a5e8efe1588e79785e7d78c3dfbb3`, merge commit `e32d0c388e21e0c563dc375ecfed289b95f311f1`, and successful full CI run `43580314763`.

The PR #4 release record reports:
- Vercel alias `https://croptwist.vercel.app`, deployment `dpl_CfcWwWQWWfAKF2qsCLXZjPqrZMKv`.
- Railway API deployment `d01f9417-fbc1-47fa-9c1c-5d0622ee0711` and worker deployment `50946e68-1f54-4b89-b2d8-c90c8d92a739`, both reported successful at release time.
- API readiness 200 on PostgreSQL 16.16 / PostGIS 3.3.10, with expected and applied Alembic head `0029_durable_artifacts`.
- A fresh public demo login, current-user route and synthetic farm-list smoke test; and a clean PostGIS E2E with 92 assertions.

**Important:** those are historical release-time observations, not a live status check on 2026-11-21. Provider access is required to confirm whether the services are currently running and to deploy a new version.

The branch `feature/croptwist-free-deployment` is 40 commits behind `main` and has no unique commits ahead of it. Do not deploy or merge it. Use `main` plus the active reviewed PRs.

## 2. Current code integration status

The following workstreams remain separate Draft PRs; none is merged:

| PR | Branch | Scope | Current gate |
|---|---|---|---|
| #5 | `fix/m1a-satellite-processing` | HLS + Sentinel-2 hardening | CI pending |
| #11 | `feature/m1b-presto-crop-history` | Presto inputs/training | CI pending |
| #12 | `feature/m1c-local-e5-rag` | Local embeddings + tenant-safe RAG | CI pending |
| #13 | `feature/m1d-fao-wapor` | WaPOR scientific metadata | CI pending |
| #14 | `feature/m1e-llm-provider-hardening` | LLM diagnostics/provider safety | CI pending |

Do not merge a PR until both backend and frontend CI jobs complete successfully on its exact head SHA. `mergeable=true` is not a substitute for passing checks. If a PR fails, fix it on that branch and wait for a new run.

## 3. Four-hour release sequence

1. **Integration gate (first 45–60 min):** monitor all five PR checks; fix failures; review migration head and test output. Keep Draft status until green.
2. **Merge gate (next 30–45 min):** merge the five clean PRs one at a time, in order #5, #11, #12, #13, #14. After each merge, verify the resulting `main` SHA and rerun the required main-branch CI. Stop if any merge changes shared contracts unexpectedly.
3. **Release build (next 45–60 min):** deploy the verified `main` SHA to the existing Railway API and worker services, then deploy the matching frontend to Vercel. Do not mix frontend/backend commits.
4. **Production smoke (next 30–45 min):** verify `/api/v1/health` and readiness, DB/PostGIS connectivity, Alembic head, login/session, current-user, farm list, one synthetic recommendation flow, worker queue processing, and one report lifecycle. Check browser console and network failures.
5. **Buffer (remaining time):** fix only release-blocking regressions, redeploy the same verified SHA, and rerun the affected smoke checks. Do not add speculative features during the release window.

## 4. Known boundaries that must remain visible

- The previous release explicitly left live LLM providers disabled until safe credentials and authenticated probes are configured; rules-based responses were verified.
- Live satellite acquisition/imagery was not verified in the previous release record. Do not describe it as production-verified until a live scene can be acquired and processed.
- Reports/exports were limited by the previous hosting plan's entitlements.
- The Railway trial/cost estimate in the 2026-11-14 evaluation is historical. Confirm current balance, service status, persistence and expected 24-hour cost before redeployment.

## 5. Deployment access requirement

GitHub integration can prepare and review source changes, but it does not expose Railway or Vercel deployment controls. Connect the Railway and Vercel apps before attempting the actual deployment. Until those connections are confirmed and the provider reports success, do not claim a deployment is live.

## 6. Release acceptance

A release is accepted only when all are true:
- exact `main` SHA has successful backend + frontend CI;
- migrations are at the expected Alembic head and PostGIS is ready;
- API and worker deployments report success;
- Vercel serves the same release's frontend;
- production smoke checks pass;
- limitations above are documented rather than hidden.

**No waiver:** if CI remains queued or provider access is unavailable, report the blocker and preserve the last known-good release rather than promoting an unverified build.
