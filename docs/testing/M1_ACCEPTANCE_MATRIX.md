# M1 Acceptance Matrix — Data & AI Integration

Last audited: 2026-11-23 UTC  
Repository base at audit start: `main@d519c381e923f73df15acdb99872fdfc9a701a04`  
Live validation branch: `test/m1-safe-live-validation`

## Decision

**M1 is not closed yet.** Core adapters and evaluation harnesses are present in merged PRs, but code presence and mock-backed CI do not satisfy live-provider or scientific-quality acceptance.

## Verified evidence

| Workstream | Implementation | Evidence | Acceptance state |
|---|---|---|---|
| NASA HLS | Provider, CMR STAC discovery, Fmask-aware bounded reads | Run 45092885136 found 10 scenes; red/NIR/Fmask one-byte HTTP Range probes each returned 206 with raster content, but GDAL's selected-scene read returned sanitized `RasterioIOError` / `raster_read_failed` (0/1 scenes processed). Current head retries up to 3 clearest candidates and records each sanitized result. | Metadata and asset endpoint access verified; raster-window acceptance pending bounded alternate-scene run |
| Copernicus Sentinel-2 | CDSE STAC, SCL/radiometry handling, bounded S3 reads | Latest completed evidence artifact, run 45084302760: 87 Sentinel-2 L2A items; protected S3 read succeeded with 1 observation and 0 warnings for 2025-12-28. | Live protected asset-window verified |
| FAO WaPOR v3 | Public catalogue, Egypt L2 products, bounded tiled COG reader | Real L2-AETI-D COG window for 2026-11-D1: 1,681 valid pixels, 0 NoData pixels in the field window, EPSG:4326, source pixel size ~96.3 × 108.2 m, 100 m product spec, mm/day, scale 0.1, offset 0, CC BY-SA 4.0 | Live raster-window verified |
| OpenRouter / Groq | Both provider adapters and fixed-prompt diagnostics exist; M1 now probes these providers instead of gating on Gemini | Run 45092885136 returned `provider_output_truncated` for both configured models because the diagnostic limited output to 16 tokens. Current head raises the fixed probe budget to 128 tokens; exact-head live verification is running. | At least one provider must return `live_verified`; both statuses are recorded separately. Gemini is retained as a later fallback, not an M1 gate |
| Presto | Input contract, lazy encoder, 128-D embedding path, classifier training harness | No independent numerical parity result against upstream implementation; no approved labeled training dataset selected/tracked | Scientific acceptance pending |
| E5 multilingual retrieval | Local E5 adapter and evaluator | No reviewed Arabic/English relevance-labelled corpus and no accepted Recall@5/@10, MRR, or nDCG report; semantic retrieval remains disabled | Quality acceptance pending |

The latest credential-enabled run **45092885136** confirmed `secrets_used=true`, protected Sentinel-2 asset-window success (1 observation, 0 warnings), and WaPOR COG-window success (1,681 valid pixels; 0 NoData). NASA HLS red/NIR/Fmask range probes all returned HTTP 206, but the GDAL field-window read failed with sanitized `raster_read_failed`; the current head now tries up to three clearest candidate scenes. Both OpenRouter and Groq were reached but returned `provider_output_truncated` because the fixed probe budget was only 16 tokens; the current head increases it to 128. New exact-head live validation is running. Only CDSE and WaPOR are accepted at this point.

## Required to close M1

1. GitHub Actions secrets are now configured sufficiently for the workflow to attempt the protected checks (the evidence artifact confirms credentials were detected; no values are logged).
2. Inspect the latest safe NASA/CDSE `reason_code` evidence and address the underlying raster/credential/asset issue; run the fixed OpenRouter/Groq probes and require at least one `live_verified`. Never expose response bodies, headers, signed URLs, or secrets.
3. Select and license-audit the Presto classifier dataset. Current proposal: CropHarvest for general training only after its component-dataset licenses are checked; FAO Egypt crop-type mapping as independent local validation only if its download and license are confirmed.
4. Create/review a bilingual agricultural relevance corpus for E5 and publish Recall@5/@10, MRR, and nDCG by language. Keep semantic retrieval disabled until it passes the agreed threshold.
5. Run the focused offline provider/embedding regression suite and attach the exact-head results.

## Safety invariants

- No farmer/field data is sent to hosted LLMs. `CROPTWIST_AI_ALLOW_FIELD_DATA_TO_PROVIDERS=false` and `CROPTWIST_OPENROUTER_ALLOW_FIELD_DATA=false` remain in force.
- The smoke workflow uses only a fixed public Mallawi test polygon and fixed non-sensitive OpenRouter/Groq probe prompt.
- No production environment, production database, or production deployment is modified by this validation.
- A public catalogue response is not a protected asset read; synthetic fixtures are not live-provider evidence.
