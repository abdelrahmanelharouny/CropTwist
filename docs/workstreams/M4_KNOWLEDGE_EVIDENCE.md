# M4 — Knowledge & Evidence

**Baseline:** `9357e06c381a4a52bd870d243e2bb2cf189c87d4`.
**Status:** Acceptance definition; no benchmark or agronomist approval is implied.

## Knowledge integrity

- A request must resolve one active knowledge-pack version; crop traits, water parameters, calendars, rules and citations must not be mixed across versions.
- Global and country/region-specific values must have deterministic precedence and preserve the selected source.
- Reference values remain `reference` until reviewed by a qualified agronomist for the target agro-ecological context.
- Missing, stale, conflicting, unsupported or unevaluated dimensions must remain visible; they cannot be silently converted to zero or positive eligibility.

## Retrieval and multilingual evidence

The current local embedding foundation uses `intfloat/multilingual-e5-small` (384 dimensions) with required `query:` and `passage:` prefixes. Preserve model identity, pinned revision, normalization, vector dimension and index version in the persisted embedding contract. BGE-M3 is a challenger, not an implicit default.

Build a reviewed retrieval corpus spanning Egyptian agronomy in Egyptian Arabic, Modern Standard Arabic and English. Every document needs provenance, publication date, geography/crop applicability, license, review status and stable source ID.

## Evaluation plan

1. Create a human-reviewed query set by language, crop, season and evidence type; include paraphrases, spelling variation and Arabic morphology.
2. Record gold source passages and expected citations; split train/dev/test by source document to prevent leakage.
3. Measure Recall@k, Precision@k, MRR and nDCG by language and crop; report confidence intervals and failure examples.
4. Measure citation correctness, answerability detection, unsupported-answer refusal, lexical fallback behavior, cold/warm latency, peak RSS and embedding throughput.
5. Test tenant isolation, pack-version isolation, re-embedding idempotence, cache invalidation and model-revision migration.
6. Compare E5 with BGE-M3 only on the same corpus, judgments, hardware and retrieval settings.
7. Require agronomist review for numeric crop thresholds, water values, calendars and management claims before changing validation status.

## Acceptance criteria

- Retrieval benchmark is reproducible and stratified by Arabic/English; no aggregate-only score hides a language failure.
- Citations resolve to the exact versioned source passage and are correct for the claim.
- Unsupported numeric claims are rejected or replaced by a deterministic evidence-gap explanation.
- Model and corpus revisions are pinned and auditable.
- Knowledge packs cannot mix values from superseded versions.
- No tenant or farm data crosses retrieval boundaries.

## Non-acceptance

A passing mock test, embedding generation success, or fluent LLM answer is not evidence of retrieval quality or agronomic validity.
