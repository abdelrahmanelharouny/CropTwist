# M1 Acceptance Matrix — Data & AI Integration

Last audited: 2026-11-22 UTC  
Repository base at audit start: `main@d519c381e923f73df15acdb99872fdfc9a701a04`  
Live validation branch: `test/m1-safe-live-validation`

## Decision

**M1 is not closed yet.** Core adapters and evaluation harnesses are present in merged PRs, but code presence and mock-backed CI do not satisfy live-provider or scientific-quality acceptance.

## Verified evidence

| Workstream | Implementation | Evidence | Acceptance state |
|---|---|---|---|
| NASA HLS | Provider, CMR STAC discovery, Fmask-aware bounded reads | Public metadata smoke found 10 HLS scenes in the Mallawi test AOI, both HLSL30/HLSS30 collections, zero parser warnings | Metadata verified; protected Earthdata asset window pending |
| Copernicus Sentinel-2 | CDSE STAC, SCL/radiometry handling, bounded S3 reads | Public metadata smoke found 87 Sentinel-2 L2A items; latest acquisition 2025-12-28 | Metadata verified; protected CDSE S3 asset window pending |
| FAO WaPOR v3 | Public catalogue, Egypt L2 products, bounded tiled COG reader | Real L2-AETI-D COG window for 2026-11-D1: 1,681 valid pixels, 0 NoData pixels in the field window, EPSG:4326, source pixel size ~96.3 × 108.2 m, 100 m product spec, mm/day, scale 0.1, offset 0, CC BY-SA 4.0 | Live raster-window verified |
| Gemini | Provider adapter and fixed-prompt diagnostic exist; Gemini is the first enabled external provider when loopback Ollama is disabled | No Gemini key is currently available to the GitHub Actions run or Railway Staging | Live probe pending |
| Presto | Input contract, lazy encoder, 128-D embedding path, classifier training harness | No independent numerical parity result against upstream implementation; no approved labeled training dataset selected/tracked | Scientific acceptance pending |
| E5 multilingual retrieval | Local E5 adapter and evaluator | No reviewed Arabic/English relevance-labelled corpus and no accepted Recall@5/@10, MRR, or nDCG report; semantic retrieval remains disabled | Quality acceptance pending |

The public smoke run that produced the HLS/CDSE/WaPOR evidence is GitHub Actions run **45073936468** on commit `c5e810d25527287c30783693a60b714d9c911934`. Its sanitized evidence is uploaded as the `m1-public-data-smoke-evidence` artifact.

## Required to close M1

1. Add these as GitHub **Actions secrets** (never plain variables or source files): `CROPTWIST_GEMINI_API_KEY`, `CROPTWIST_EARTHDATA_BEARER_TOKEN`, `CROPTWIST_CDSE_S3_ACCESS_KEY`, `CROPTWIST_CDSE_S3_SECRET_KEY`.
2. Rerun the M1 Public Data Smoke workflow. It will execute a fixed non-sensitive Gemini probe, one bounded NASA HLS protected asset-window read, and a bounded CDSE S3 asset-window read when those secrets exist. Missing secrets are reported as blocked, not passed.
3. Select and license-audit the Presto classifier dataset. Current proposal: CropHarvest for general training only after its component-dataset licenses are checked; FAO Egypt crop-type mapping as independent local validation only if its download and license are confirmed.
4. Create/review a bilingual agricultural relevance corpus for E5 and publish Recall@5/@10, MRR, and nDCG by language. Keep semantic retrieval disabled until it passes the agreed threshold.
5. Run the focused offline provider/embedding regression suite and attach the exact-head results.

## Safety invariants

- No farmer/field data is sent to hosted LLMs. `CROPTWIST_AI_ALLOW_FIELD_DATA_TO_PROVIDERS=false` and `CROPTWIST_OPENROUTER_ALLOW_FIELD_DATA=false` remain in force.
- The smoke workflow uses only a fixed public Mallawi test polygon and fixed non-sensitive Gemini prompt.
- No production environment, production database, or production deployment is modified by this validation.
- A public catalogue response is not a protected asset read; synthetic fixtures are not live-provider evidence.
