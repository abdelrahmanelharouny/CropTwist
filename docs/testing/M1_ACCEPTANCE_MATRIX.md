# M1 Acceptance Matrix — Data & AI Integration

Last audited: 2026-11-23 UTC  
Repository base at audit start: `main@d519c381e923f73df15acdb99872fdfc9a701a04`  
Live validation branch: `test/m1-safe-live-validation`

## Decision

**M1 is not closed yet.** Core adapters and evaluation harnesses are present in merged PRs, but code presence and mock-backed CI do not satisfy live-provider or scientific-quality acceptance.

## Verified evidence

| Workstream | Implementation | Evidence | Acceptance state |
|---|---|---|---|
| NASA HLS | Provider, CMR STAC discovery, Fmask-aware bounded reads | Latest completed credential-enabled evidence artifact: run 45084302760; 10 public metadata scenes found; one selected protected scene produced 0 observations, 0/1 scenes processed, sanitized `RasterioIOError`. The current rerun adds bounded HTTP range probes and a sanitized GDAL failure code to distinguish auth, transport, and asset failures. | Metadata verified; protected asset read not accepted; inspect the new run's sanitized failure code before changing raster/auth logic |
| Copernicus Sentinel-2 | CDSE STAC, SCL/radiometry handling, bounded S3 reads | Latest completed evidence artifact, run 45084302760: 87 Sentinel-2 L2A items; protected S3 read succeeded with 1 observation and 0 warnings for 2025-12-28. | Live protected asset-window verified |
| FAO WaPOR v3 | Public catalogue, Egypt L2 products, bounded tiled COG reader | Real L2-AETI-D COG window for 2026-11-D1: 1,681 valid pixels, 0 NoData pixels in the field window, EPSG:4326, source pixel size ~96.3 × 108.2 m, 100 m product spec, mm/day, scale 0.1, offset 0, CC BY-SA 4.0 | Live raster-window verified |
| OpenRouter / Groq | Both provider adapters and fixed-prompt diagnostics exist; M1 now probes these fallbacks instead of gating on Gemini | New exact-head run required after switching the workflow secrets and probe target; probes use only the fixed non-sensitive prompt. | At least one provider must return `live_verified`; both statuses are recorded separately. Gemini is retained as a later fallback, not an M1 gate |
| Presto | Input contract, lazy encoder, 128-D embedding path, classifier training harness | No independent numerical parity result against upstream implementation; no approved labeled training dataset selected/tracked | Scientific acceptance pending |
| E5 multilingual retrieval | Local E5 adapter and evaluator | No reviewed Arabic/English relevance-labelled corpus and no accepted Recall@5/@10, MRR, or nDCG report; semantic retrieval remains disabled | Quality acceptance pending |

The latest completed credential-enabled smoke artifact is run **45084302760**. It confirmed `secrets_used=true`, passed NASA/CDSE metadata discovery, verified a protected Sentinel-2 asset window (1 observation, 0 warnings), and verified the WaPOR Egypt COG window (1,681 valid pixels; 0 NoData). NASA HLS metadata discovery returned 10 scenes, but its selected protected asset read failed with sanitized `RasterioIOError` (0/1 scenes processed). Gemini returned HTTP 429 in the same run and is no longer the M1 LLM gate. The current exact-head rerun tests OpenRouter/Groq and emits sanitized NASA HTTP-range/GDAL failure evidence. These are distinct acceptance gates; only CDSE and WaPOR are currently accepted from that artifact.

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
