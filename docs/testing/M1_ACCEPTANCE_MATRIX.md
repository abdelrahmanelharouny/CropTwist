# M1 Acceptance Matrix — Data & AI Integration

Last audited: 2026-11-23 UTC  
Repository base at audit start: `main@4dd44dae19b54c68eb7963976701f3822545dfd5`  
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
| Presto | Input contract, lazy encoder, 128-D embedding path, classifier training harness | No independent numerical parity result yet. Two 2019 FAO-WaPOR Egypt collections found: 1,532 actual GeoParquet rows, 878 crop-specific EWOC-coded rows, 12 cross-collection polygon overlaps. Metadata declares CC_BY but license-reference field is blank; generic classes, class imbalance and missing group IDs remain. | Scientific acceptance pending; dataset candidate found, not approved for training |
| E5 multilingual retrieval | Local E5 adapter and evaluator | No reviewed Arabic/English relevance-labelled corpus and no accepted Recall@5/@10, MRR, or nDCG report; semantic retrieval remains disabled | Quality acceptance pending |

The latest successful credential-enabled live run **45095264042** confirmed OpenRouter and Groq as `live_verified` fallbacks, NASA HLS raster-window success (one observation from `HLS.S30.T36RTR.2025002T083341.v2.0`), protected Sentinel-2 success (one observation, zero warnings), and WaPOR COG-window success (1,681 valid pixels; zero NoData). No farmer/field data was sent to hosted LLMs. A previous CI run caught and fixed a provider-diagnostics test syntax issue. During this closure pass, exact-head CI and the M2 clean-room workflow are being run as release-safety checks; these software suites do not replace the scientific parity, ingestion, licensing, or model-evaluation evidence listed above.

## Scientific closure work added on 2026-11-23

- Added `scripts/verify_presto_numerical_parity.py`, which compares the CropTwist/TorchGeo embedding against the original NASA Harvest `Presto.load_pretrained().encoder(eval_task=True)` using identical validated records and emits per-record max/mean absolute error and cosine similarity. **Harness added; it has not been executed.**
- Added `docs/data/PRESTO_MONTHLY_INGESTION_SPEC.md`, pinning the upstream 17-channel order, raw units, normalization constants, monthly aggregation/QA/provenance contract and explicit missing providers. **Specification only; live S1/S2/ERA5/SRTM ingestion remains open.**
- Added `docs/data/EGYPTIAN_DATA_SOURCE_LICENSE_AUDIT_2026-11-23.md` and an automated nested-ZIP/GeoParquet discovery workflow. Two 2019 FAO-WaPOR Egypt field-survey collections were found and profiled: 898 + 634 rows, all geometries valid, 878 crop-specific EWOC-coded rows, 12 intersecting polygon pairs, strong class imbalance, and missing field IDs. The WorldCereal metadata declares CC_BY but its license-reference cell is blank. **Candidate only; do not mark labels license-verified or train until FAO source terms/attribution, raw-field mapping, and spatial grouping are confirmed.**
- Added `docs/ai/E5_BILINGUAL_CORPUS_ANNOTATION_PROTOCOL.md`. The evaluator is ready for judged data; the 300-query/500-passage corpus and human judgments have not been supplied or reviewed.

## Required to close M1

1. GitHub Actions secrets are now configured sufficiently for the workflow to attempt the protected checks (the evidence artifact confirms credentials were detected; no values are logged).
2. The protected NASA/CDSE reads and WaPOR read are demonstrated by run `45105049079`. OpenRouter and Groq are the only active hosted providers; Gemini is deferred and must not be probed or required. Never expose response bodies, headers, signed URLs, or secrets.
3. Complete the rights review for the two 2019 FAO-WaPOR Egypt field-label collections (CC_BY declared, license reference blank), preserve raw metadata, exclude generic EWOC codes, resolve 12 spatial intersections and missing grouping fields, then build a spatially grouped manifest. The 2023–2024 FAO Egypt map remains an additional candidate pending exact item terms. CropHarvest is not an Egypt ground-truth substitute; inspect component licenses before any use.
4. Create/review a bilingual agricultural relevance corpus for E5 and publish Recall@5/@10, MRR, and nDCG by language. Keep semantic retrieval disabled until it passes the agreed threshold.
5. Complete the exact-head CI and M2 clean-room PostGIS/browser gates now that the closure changes are in place. A passing software suite closes only the engineering regression gate; it does not replace Presto numerical parity, full monthly S1/S2/ERA5/SRTM ingestion, item-level data rights, or independent spatial-temporal model evaluation.

## Safety invariants

- No farmer/field data is sent to hosted LLMs. `CROPTWIST_AI_ALLOW_FIELD_DATA_TO_PROVIDERS=false` and `CROPTWIST_OPENROUTER_ALLOW_FIELD_DATA=false` remain in force.
- The smoke workflow uses only a fixed public Mallawi test polygon and fixed non-sensitive OpenRouter/Groq probe prompt.
- No production environment, production database, or production deployment is modified by this validation.
- A public catalogue response is not a protected asset read; synthetic fixtures are not live-provider evidence.
