# M1 Acceptance Matrix — Data & AI Integration

Last audited: 2026-11-23 UTC  
Repository base at audit start: `main@d519c381e923f73df15acdb99872fdfc9a701a04`  
Live validation branch: `test/m1-safe-live-validation`

## Decision

**Protected live-data reads and fallback LLM connectivity are demonstrated; full M1 acceptance remains open.** Latest completed smoke run `45105049079` verified NASA HLS, CDSE Sentinel-2, WaPOR, OpenRouter and Groq. The artifact does not include a Gemini probe. The M1 branch now configures Gemini → Groq → OpenRouter, excludes Ollama from the default chain, and updates the smoke probe to require Gemini primary plus at least one verified fallback. Exact-head CI and the revised smoke must pass before this provider correction is accepted.

## Verified evidence

| Workstream | Implementation | Evidence | Acceptance state |
|---|---|---|---|
| NASA HLS | Provider, CMR STAC discovery, Fmask-aware bounded reads | Run `45105049079`: scene `HLS.S30.T36RTR.2025002T083341.v2.0`; red/NIR/Fmask Range requests each returned 206 and one bounded observation was produced with zero warnings. | Live protected raster-window verified |
| Copernicus Sentinel-2 | CDSE STAC, SCL/radiometry handling, bounded S3 reads | Run `45105049079`: 87 L2A items; protected S3 read succeeded for `2025-12-28` with 1 observation and 0 warnings. | Live protected asset-window verified |
| FAO WaPOR v3 | Public catalogue, Egypt L2 products, bounded tiled COG reader | Run `45105049079`: Egypt L2 AETI-D window for `2026-11-D1`, 1,681 valid pixels, 0 NoData, EPSG:4326, ~96.3 × 108.2 m source pixels, mm/day, scale 0.1, offset 0, CC BY-SA 4.0. | Live raster-window verified |
| OpenRouter / Groq | Both provider adapters and fixed-prompt diagnostics; Gemini → Groq → OpenRouter order; fixed probe budget 128 tokens | Run 45095264042: both providers returned `live_verified`; OpenRouter and Groq were independently verified as reachable fallbacks; Gemini remains the configured primary and must be probed separately for primary-provider acceptance. Field-data egress remains disabled. | Fallback connectivity verified; Gemini primary runtime acceptance is tracked separately |
| Presto | Input contract, lazy encoder, 128-D embedding path, classifier training harness | No independent numerical parity result against upstream implementation; no approved labeled training dataset selected/tracked | Scientific acceptance pending |
| E5 multilingual retrieval | Local E5 adapter and evaluator | No reviewed Arabic/English relevance-labelled corpus and no accepted Recall@5/@10, MRR, or nDCG report; semantic retrieval remains disabled | Quality acceptance pending |

The latest successful credential-enabled live run **45095264042** confirmed OpenRouter and Groq as `live_verified` fallbacks, NASA HLS raster-window success (one observation from `HLS.S30.T36RTR.2025002T083341.v2.0`), protected Sentinel-2 success (one observation, zero warnings), and WaPOR COG-window success (1,681 valid pixels; zero NoData). No farmer/field data was sent to hosted LLMs. A follow-up CI run caught a syntax error in the newly introduced provider-diagnostics test (literal `\\n` characters); the file was corrected in commit `92de913d9bf12f705604dbea818021da13ce7b23`. Exact-head CI and live smoke are rerunning.

## Required to close M1

1. GitHub Actions secrets are now configured sufficiently for the workflow to attempt the protected checks (the evidence artifact confirms credentials were detected; no values are logged).
2. The protected NASA/CDSE reads and WaPOR read are demonstrated by run `45105049079`. The revised smoke must probe Gemini as primary and Groq/OpenRouter as fallbacks; do not reuse the earlier fallback-only artifact as Gemini evidence. Never expose response bodies, headers, signed URLs, or secrets.
3. Select and license-audit the Presto classifier dataset. Current proposal: CropHarvest for general training only after its component-dataset licenses are checked; FAO Egypt crop-type mapping as independent local validation only if its download and license are confirmed.
4. Create/review a bilingual agricultural relevance corpus for E5 and publish Recall@5/@10, MRR, and nDCG by language. Keep semantic retrieval disabled until it passes the agreed threshold.
5. Run the focused offline provider/embedding regression suite and attach the exact-head results.

## Safety invariants

- No farmer/field data is sent to hosted LLMs. `CROPTWIST_AI_ALLOW_FIELD_DATA_TO_PROVIDERS=false` and `CROPTWIST_OPENROUTER_ALLOW_FIELD_DATA=false` remain in force.
- The smoke workflow uses only a fixed public Mallawi test polygon and fixed non-sensitive OpenRouter/Groq probe prompt.
- No production environment, production database, or production deployment is modified by this validation.
- A public catalogue response is not a protected asset read; synthetic fixtures are not live-provider evidence.
