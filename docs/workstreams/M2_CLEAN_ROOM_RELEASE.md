# M2 — Clean-room Release Acceptance

**Baseline:** `main` after M1-E Qwen/Ollama merge (`9357e06c381a4a52bd870d243e2bb2cf189c87d4`).
**Status:** Gate definition only; no clean-room run is claimed by this document.

## Objective

Prove that a fresh checkout can build and run the complete CropTwist stack against a genuinely empty PostgreSQL 16 + PostGIS 3.5 database, without relying on a developer's local state, pre-existing volumes, cached generated files, or undocumented environment variables.

## Execution protocol

1. Create a disposable clean workspace from the exact candidate commit; record SHA, OS/runtime versions, Bun, Python, PostgreSQL/PostGIS and Docker versions.
2. Start a newly created empty database/volume. Confirm there are no application tables, extensions or migration rows other than the platform baseline.
3. Run `alembic upgrade head`; capture ordered revision output and resulting schema inventory.
4. Run `alembic upgrade head` a second time. It must be a no-op, with no duplicate DDL, data mutation, lock leak or failure.
5. Run `alembic check` and compare the database schema against all loaded ORM metadata, including P2/P3 models.
6. Run the complete backend suite against PostGIS, frontend typecheck/lint/tests/production build, LLM bridge typecheck, and API smoke/E2E jobs. Record exact commands, counts and exit codes.
7. Start the complete stack from clean configuration; verify web, API liveness/readiness, database connectivity, auth/session flow, tenant isolation, field creation, data upload/read, rotation analysis, scenario verification, reports and settings.
8. Execute browser journeys at desktop and narrow mobile widths, in English and Arabic/RTL. Capture console/network failures and screenshots.
9. Destroy the disposable environment and repeat from a second independent empty database to prove reproducibility.

## Acceptance criteria

- Two independent empty-database runs produce the same Alembic head and expected schema inventory.
- Second migration pass is idempotent; `alembic check` is clean.
- No required secret, file, cache, model, object or database state is implicitly read from a developer machine.
- Full backend/PostGIS, frontend, bridge, API and browser suites pass on the exact candidate SHA.
- No tenant boundary, authorization, or data-integrity regression appears in the end-to-end journeys.
- Artifacts include sanitized logs, migration inventory, test reports, browser screenshots, environment manifest and SHA.

## Explicit non-acceptance

A green PR CI job, a reused local database, a migration test with fixtures only, or a frontend-only browser smoke is not a clean-room release. Do not mark M2 accepted until all evidence above is attached.
