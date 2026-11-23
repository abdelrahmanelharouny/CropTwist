# M1 Acceptance Matrix — Data & AI Integration

Last audited: 2026-11-23 UTC  
Repository base at audit start: `main@d519c381e923f73df15acdb99872fdfc9a701a04`  
Live validation branch: `test/m1-safe-live-validation`

## Decision

**Protected live-data reads and fallback LLM connectivity are demonstrated; full M1 acceptance remains open.** Latest completed smoke run `45105049079` verified NASA HLS, CDSE Sentinel-2, WaPOR, OpenRouter and Groq. The artifact does not include a Gemini probe. The active hosted-provider order is OpenRouter → Groq. Gemini is temporarily deferred and is not configured, probed, or required for acceptance. Ollama remains disabled. Implementation and scientific work remain open; tests are deferred until the remaining phases and redesign are complete.

## Verified evidence

| Workstream | Implementation | Evidence | Acceptance state |
|---|---|---|---|
| NASA HLS | Provider, CMR STAC discovery, Fmask-aware bounded reads | Run `45105049079`: scene `HLS.S30.T36RTR.2025002T083341.v2.0`; red/NIR/Fmask Range requests each returned 206 and one bounded observation was produced with zero warnings. | Live protected raster-window verified |
| Copernicus Sentinel-2 | CDSE STAC, SCL/radiometry handling, bounded S3 reads | Run `45105049079`: 87 L2A items; protected S3 read succeeded for `2025-12-28` with 1 observation and 0 warnings. | Live protected asset-window verified |
| FAO WaPOR v3 | Public catalogue, Egypt L2 products, bounded tiled COG reader | Run `45105049079`: Egypt L2 AETI-D window for `2026-11-D1`, 1,681 valid pixels, 0 NoData, EPSG:4326, ~96.3 × 108.2 m source pixels, mm/day, scale 0.1, offset 0, CC BY-SA 4.0. | Live raster-window verified |
| OpenRouter / Groq | Both provider adapters and fixed-prompt diagnostics; OpenRouter → Groq order; fixed probe budget 128 tokens | Run 45095264042: both providers returned `live_verified`; OpenRouter and Groq were independently verified as reachable providers. Gemini is temporarily deferred and excluded from the active chain. Field-data egress remains disabled. | Both configured providers live-verified; Gemini deferred |
| Presto | Input contract, lazy encoder, 128-D embedding path, classifier training harness | No independent numerical parity result against upstream implementation; no approved labeled training dataset selected/tracked | Scientific acceptance pending |
| E5 multilingual retrieval | Local E5 adapter and evaluator | No reviewed Arabic/English relevance-labelled corpus and no accepted Recall@5/@10, MRR, or nDCG report; semantic retrieval remains disabled | Quality acceptance pending |

The latest successful credential-enabled live run **45095264042** confirmed OpenRouter and Groq as `live_verified` fallbacks, NASA HLS raster-window success (one observation from `HLS.S30.T36RTR.2025002T083341.v2.0`), protected Sentinel-2 success (one observation, zero warnings), and WaPOR COG-window success (1,681 valid pixels; zero NoData). No farmer/field data was sent to hosted LLMs. A previous CI run caught and fixed a provider-diagnostics test syntax issue. Per the current execution decision, no further test suites are being run during implementation; exact-head CI and consolidated live verification are deferred until the remaining phases and redesign are complete.

## Required to close M1

1. GitHub Actions secrets are now configured sufficiently for the workflow to attempt the protected checks (the evidence artifact confirms credentials were detected; no values are logged).
2. The protected NASA/CDSE reads and WaPOR read are demonstrated by run `45105049079`. OpenRouter and Groq are the only active hosted providers; Gemini is deferred and must not be probed or required. Never expose response bodies, headers, signed URLs, or secrets.
3. Select and license-audit the Presto classifier dataset. Current proposal: CropHarvest for general training only after its component-dataset licenses are checked; FAO Egypt crop-type mapping as independent local validation only if its download and license are confirmed.
4. Create/review a bilingual agricultural relevance corpus for E5 and publish Recall@5/@10, MRR, and nDCG by language. Keep semantic retrieval disabled until it passes the agreed threshold.
5. Defer all regression suites until implementation phases and redesign are complete; run the consolidated verification pass afterward.

## Safety invariants

- No farmer/field data is sent to hosted LLMs. `CROPTWIST_AI_ALLOW_FIELD_DATA_TO_PROVIDERS=false` and `CROPTWIST_OPENROUTER_ALLOW_FIELD_DATA=false` remain in force.
- The smoke workflow uses only a fixed public Mallawi test polygon and fixed non-sensitive OpenRouter/Groq probe prompt.
- No production environment, production database, or production deployment is modified by this validation.
- A public catalogue response is not a protected asset read; synthetic fixtures are not live-provider evidence.
