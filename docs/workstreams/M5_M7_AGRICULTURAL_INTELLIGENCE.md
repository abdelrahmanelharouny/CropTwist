# M5–M7 — Agricultural Intelligence

**Baseline:** `9357e06c381a4a52bd870d243e2bb2cf189c87d4`.
**Status:** Consolidated validation workstream; existing engines are to be audited before extending them.

## M5 — Rotation optimizer and scientific correctness

- Verify season-specific candidate scoring over the full planning horizon; no first-season coefficient reuse.
- Ensure interval-valued traits and missing dimensions are handled explicitly, not collapsed to point values or zero.
- Confirm hard constraints are solver assumptions and infeasibility maps back to named constraints; no silent relaxation.
- Compare solver objective, post-hoc evaluation and user-facing ranking semantics; never describe proxy objectives as measured yield/profit.
- Validate with synthetic adversarial fixtures and agronomist-reviewed Egyptian crop/season cases; use farm-disjoint and temporal holdouts for any learned component.
- Report feasibility, constraint violations, stability, runtime and sensitivity to weights; document deterministic seed/worker settings.

## M6 — Water and soil

- Reconcile current migrations, ORM models, routers, UI hooks and tests before modifying existing water/soil functionality.
- Validate water units and period compatibility across crop coefficient curves, ET0, effective rainfall, soil water holding and irrigation scheduling.
- Validate soil profile depth, layer arithmetic, coarse fragments, bulk density, SOC stock and nutrient mass balance with hand-calculated fixtures.
- Preserve evidence class, source, date, depth, units and uncertainty for every input.
- Missing soil/water evidence must produce explicit unknown/unevaluated outputs, never a fabricated positive score or recommendation.

## M7 — Scenarios, sensitivity, robust rotation and digital twin

- Keep scenario definitions and executions immutable, checksummed and tied to a pinned field-state observation manifest.
- Unsupported weather forecasts and climate projections must remain refused until a real provider and transformation method are validated.
- Sensitivity results must disclose parameter ranges, one-at-a-time/joint-grid semantics and uncertainty limitations.
- Robust rotation must optimize one shared plan across scenarios; per-scenario metrics are post-hoc evaluations, not separate hidden plans.
- Digital twin verification must walk boundary → field state → observations → features → scenarios → analyses → decisions and detect altered or missing artifacts.
- M7.8 remains blocked until a real forecast/projection source, licensing, temporal/spatial resolution and scientifically defined transformations are approved.

## Acceptance criteria

- Independent scientific test vectors reproduce all reported water/soil arithmetic and key optimizer constraints.
- No missing evidence is silently imputed; all rankings disclose evidence coverage and proxy dimensions.
- Replays verify immutable artifacts and stable checksums.
- Forecast/projection scenarios cannot be created from synthetic or historical-only sources.
- UI explanations accurately distinguish model objective, measured evidence and post-hoc assessment.
