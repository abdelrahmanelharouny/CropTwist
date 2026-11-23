# M1 Safe Live Validation Runbook

Status: executed against public providers and credential-enabled protected probes on 2026-11-23 UTC; **M1 remains open**. Latest completed run 45083517154 (commit `312db77d`) verified NASA/CDSE public metadata and a real WaPOR COG window (1,681 valid pixels; 0 NoData), detected configured credentials, but did not pass protected gates: NASA returned 0/1 scenes processed with one warning, CDSE returned sanitized `ProviderUnavailable`, and Gemini returned sanitized `provider_transient_http` with HTTP 503 after 21,049 ms. The fixed Gemini probe deadline is now 60s to cover the configured 25s request timeout, one retry and bounded backoff. The current code also emits only allowlisted NASA/CDSE failure reason codes. A fresh smoke run on the updated head is in progress. See the sanitized artifact attached to run 45083517154; credential detection is not provider acceptance.
Target: validate provider connectivity and bounded data reads without changing production state.

## Safety rules

- Run from a local, isolated development checkout or a disposable staging environment only.
- Never place credentials in source files, command-line arguments, notebooks, issue comments, CI logs, or chat.
- Load secrets from a local secret manager or an untracked .env file. Confirm .env is ignored by Git before running.
- Do not add credentials to Railway Production as part of this runbook. Do not deploy, enqueue production ingestion jobs, or write to production databases.
- Keep field/farmer data out of every hosted LLM probe. For the current M1 acceptance run, OpenRouter is preferred and Groq is the secondary fallback; Gemini is not an M1 gate while its upstream quota is unstable. Every probe sends only a fixed, non-sensitive test prompt.
- A provider is not accepted merely because authentication succeeds. Record the product, acquisition time, CRS, resolution, units/scale, valid-pixel count, provenance, and any warnings.
- Keep raw responses and logs sanitized. Never print request headers, environment values, signed URLs, S3 keys, bearer tokens, or full exception bodies.

## Credential-to-setting map

| Provider | Secret setting | Purpose |
|---|---|---|
| NASA Earthdata | CROPTWIST_EARTHDATA_BEARER_TOKEN | Protected NASA HLS asset reads; CMR STAC discovery itself is public |
| Copernicus CDSE | CROPTWIST_CDSE_S3_ACCESS_KEY | S3-compatible Sentinel-2 asset reads |
| Copernicus CDSE | CROPTWIST_CDSE_S3_SECRET_KEY | S3-compatible Sentinel-2 asset reads |
| OpenRouter (current preferred probe) | CROPTWIST_OPENROUTER_API_KEY | Preferred M1 LLM connectivity probe |
| Groq (secondary probe) | CROPTWIST_GROQ_API_KEY | Secondary M1 LLM connectivity probe |
| Gemini (deferred M1 gate) | CROPTWIST_GEMINI_API_KEY | Retained for later verification; not required to pass current M1 LLM gate |

Do not use the Copernicus account password in place of the S3 key pair. WaPOR v3 catalogue and public COG access do not require a user API key.

For the GitHub Actions protected-probe job, add these as **repository Actions secrets** (Settings → Secrets and variables → Actions), never as plain variables: `CROPTWIST_GROQ_API_KEY`, `CROPTWIST_OPENROUTER_API_KEY`, `CROPTWIST_EARTHDATA_BEARER_TOKEN`, `CROPTWIST_CDSE_S3_ACCESS_KEY`, and `CROPTWIST_CDSE_S3_SECRET_KEY`. The smoke probes OpenRouter first and Groq second, records both sanitized results, and passes the LLM gate when at least one returns `live_verified`.

## Phase 0 — local safety and offline regression

From mini-services/fieldshift-api:

~~~bash
# Confirm the local secret file is ignored before creating/populating it.
git check-ignore .env

# Run focused provider and safety regressions.
pytest -q \
  tests/contract/test_nasa_hls_provider_contract.py \
  tests/contract/test_sentinel2_provider_contract.py \
  tests/contract/test_wapor_v3_provider.py \
  tests/contract/test_wapor_v3_provider_adapter.py \
  tests/unit/test_provider_diagnostics.py \
  tests/unit/test_provider_adapters.py \
  tests/unit/test_embedding_adapters.py \
  tests/unit/test_embedding_eval.py \
  tests/unit/test_embedding_stratified_eval.py
~~~

Then run the existing satellite end-to-end integration coverage with its normal test fixtures:

~~~bash
pytest -q tests/integration/test_satellite_acquisition.py \
  tests/integration/test_satellite_processing.py
~~~

These are offline/mock-backed regression tests; passing them is not proof of external provider availability.

## Phase 1 — public metadata probes (no secrets required)

Use the executable public-only smoke (`python scripts/m1_public_data_smoke.py`) with its fixed, non-sensitive Mallawi test polygon and bounded 2025 window. The `M1 Public Data Smoke` GitHub Actions workflow runs the same probe on this PR. It verifies:

1. NASA CMR STAC returns HLSL30/HLSS30 metadata for the selected area and time window.
2. CDSE STAC returns Sentinel-2 L2A items for the same bounded area/time window.
3. WaPOR v3 returns the Egypt L2 AETI mapset, a current dekadal raster, and a real bounded COG window with valid pixels and consistent CRS/resolution/unit/scale metadata.

For each source, save only sanitized metadata: provider/product identifier, acquisition/period date, cloud cover if present, CRS, native resolution, and public documentation/license reference. Do not persist signed asset URLs.

## Phase 2 — protected asset reads (one scene / one small window)

The executable `m1_public_data_smoke.py` now performs these bounded reads automatically when the corresponding GitHub Actions secrets are present: one lowest-cloud NASA HLS scene selected from the public Mallawi metadata results, and a one-day Sentinel-2 L2A window. Missing secrets are reported as blocked, not passed.

Run only in a disposable local/staging environment with the credentials loaded from the secret manager.

### NASA HLS

- Select one real HLS scene returned by Phase 1; pin the scene ID and exact collection.
- Read only the smallest supported field window / raster window. Do not download the full scene.
- Confirm the Earthdata bearer token is used for the protected asset path and that GDAL/rasterio reads a valid pixel window.
- Confirm scale handling, Fmask masking, valid-pixel count, and SourceProvenance.
- If access fails, capture only the sanitized HTTP/status category and request identifier. Never log the bearer token or auth headers.

### Copernicus Sentinel-2

- Select one real sentinel-2-l2a STAC item and one s3://eodata asset.
- Read a tiny raster window through the configured CDSE S3 endpoint using the generated S3 key pair.
- Confirm CRS, transform, resolution, scale/offset handling, SCL mask, valid-pixel count, and provenance.
- Verify that the access/secret keys are not written to the Data Passport, database, URLs, or logs.
- Do not use a third-party asset host for this credential test.

### FAO WaPOR v3

- Use a current Egypt Level-2 dekadal product supported by the provider registry.
- Read a small polygon window from a public tiled COG.
- Check the GeoTIFF CRS, transform, nodata, tiling/overviews, units, scale, offset, and valid-pixel count.
- Compare catalogue/API/GeoTIFF metadata with the versioned product specification. If units or scale conflict, retain raw statistics and withhold scaled physical summaries.
- Preserve CC BY-SA 4.0 attribution in derived-data provenance.

A successful catalogue response is not a successful raster-read test. The public smoke performs a real WaPOR COG window read; NASA and CDSE remain metadata-only until their protected asset reads are run with the respective credentials. A synthetic or mocked raster is never evidence of live data availability.

## Phase 3 — OpenRouter/Groq LLM connectivity (fixed prompt only)

The public smoke workflow calls the existing sanitized `probe_provider("openrouter")` and `probe_provider("groq")` adapters when their API keys are present. OpenRouter is preferred; Groq is the secondary fallback. At least one must return `live_verified`. Missing keys are reported as blocked, never passed.

From mini-services/fieldshift-api, with the key loaded locally:

~~~bash
python scripts/probe_llm_providers.py --provider openrouter --provider groq
~~~

Expected acceptance: OpenRouter or Groq returns `live_verified`; both providers are tested and reported independently. Gemini remains configured as a later provider fallback but is not required for this M1 run. The probe uses a fixed, non-sensitive instruction and returns sanitized status evidence; it must not be used to submit field records, farmer notes, crop histories, or other user data.

Keep these independent data-sharing gates disabled unless separately reviewed and explicitly approved:

- CROPTWIST_AI_ALLOW_FIELD_DATA_TO_PROVIDERS=false
- CROPTWIST_OPENROUTER_ALLOW_FIELD_DATA=false
- CROPTWIST_AI_KNOWLEDGE_ALLOW_DOCUMENTS_TO_EMBEDDING_PROVIDER=false
- CROPTWIST_AI_KNOWLEDGE_ALLOW_QUERIES_TO_EMBEDDING_PROVIDER=false

A successful connectivity probe does not authorize sending user data or enabling the provider in production.

## Phase 4 — multilingual E5 retrieval quality

The evaluator is already available:

~~~bash
python scripts/evaluate_local_embeddings.py ./rag-benchmark.json
~~~

The JSON corpus must contain documents with id/text and queries with id/text/relevant_document_ids. Use Arabic, English, and mixed Arabic-English queries; report language slices separately. Compare the same judged corpus across BM25, multilingual E5, and hybrid retrieval where available. Report Recall@5/10, MRR, and nDCG. Do not enable semantic retrieval until the corpus has reviewed relevance labels and the benchmark passes the project's acceptance threshold.

No relevance-labelled corpus is currently bundled; therefore no E5 quality score is claimed by this runbook.

## Acceptance record

Record one row per provider with: test timestamp (UTC), environment name (never secret values), provider/product, test area identifier, date range, metadata discovery status, asset read status, CRS/resolution, units/scale verification, valid-pixel count, provenance completeness, sanitized error category, and reviewer.

Do not mark M1 external-data validation complete until NASA HLS and CDSE each pass a real protected asset-window read, WaPOR passes a real Egypt COG-window read, at least one of OpenRouter or Groq returns live_verified, and the offline regression suite passes. Fallback-provider status is recorded separately. E5 remains a separate quality gate requiring reviewed relevance judgements. The public smoke workflow proves discovery and the WaPOR read only; it does not replace protected HLS/CDSE reads, Gemini connectivity, Presto numerical parity, or the E5 judged-corpus benchmark. Run 45083517154 reported `provider_transient_http` with HTTP 503 at 21,049 ms. The outer probe deadline has since been raised to 60s so the configured request timeout/retry/backoff can complete. Never expose response bodies, headers, signed URLs, or secrets.


## Latest diagnostic refinement (2026-11-22)

The live HLS probe now performs bounded one-byte HTTP Range checks for each required asset independently (red, NIR and Fmask) before attempting the GDAL/rasterio field-window read. Evidence records only numeric HTTP status, raster-vs-other content-type class and whether the response honored Range; it never records asset URLs, response bodies, headers or credentials. This isolates per-asset access from GDAL's later COG/window handling. A fresh run on commit `c0275dbcfea4` is still required; the previous run on `777ab805b9` showed CDSE S3 window access succeeded, NASA's sampled asset HTTP Range returned 206 while the GDAL read failed with a sanitized generic raster error, Gemini returned HTTP 429, and WaPOR passed.
