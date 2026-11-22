# M1 Acceptance Matrix — Data & AI Integration

Last audited: 2026-11-23 UTC  
Repository base at audit start: `main@d519c381e923f73df15acdb99872fdfc9a701a04`  
Live validation branch: `test/m1-safe-live-validation`

## Decision

**M1 is not closed yet.** Core adapters and evaluation harnesses are present in merged PRs, but code presence and mock-backed CI do not satisfy live-provider or scientific-quality acceptance.

## Verified evidence

| Workstream | Implementation | Evidence | Acceptance state |
|---|---|---|---|
| NASA HLS | Provider, CMR STAC discovery, Fmask-aware bounded reads | Run 45079671333 (commit b82645d) attempted one protected HLS scene using configured credentials; 10 public metadata scenes found, but the selected scene produced 0 observations and 1 warning; coverage reports 0/1 scenes processed | Metadata verified; protected asset read attempted but not accepted; investigate scene/asset access and valid-pixel outcome |
| Copernicus Sentinel-2 | CDSE STAC, SCL/radiometry handling, bounded S3 reads | Run 45079671333 found 87 Sentinel-2 L2A items and attempted the protected S3 read; provider returned sanitized `ProviderUnavailable` | Metadata verified; protected S3 read attempted but failed; investigate CDSE S3 credentials/endpoint/asset path |
| FAO WaPOR v3 | Public catalogue, Egypt L2 products, bounded tiled COG reader | Real L2-AETI-D COG window for 2026-11-D1: 1,681 valid pixels, 0 NoData pixels in the field window, EPSG:4326, source pixel size ~96.3 × 108.2 m, 100 m product spec, mm/day, scale 0.1, offset 0, CC BY-SA 4.0 | Live raster-window verified |
| Gemini | Provider adapter and fixed-prompt diagnostic exist; Gemini is the first enabled external provider when loopback Ollama is disabled | Run 45079671333 attempted the fixed non-sensitive Gemini probe with credentials configured; probe returned sanitized `provider_transient_http` after 6,579 ms (not a timeout) | Live probe attempted but not accepted; verify key/model/network and provider timeout behavior |
| Presto | Input contract, lazy encoder, 128-D embedding path, classifier training harness | No independent numerical parity result against upstream implementation; no approved labeled training dataset selected/tracked | Scientific acceptance pending |
| E5 multilingual retrieval | Local E5 adapter and evaluator | No reviewed Arabic/English relevance-labelled corpus and no accepted Recall@5/@10, MRR, or nDCG report; semantic retrieval remains disabled | Quality acceptance pending |

The latest credential-enabled smoke is GitHub Actions run **45079671333** on commit `b82645d50212803d95243d460e0c800df0732f87**. It confirmed `secrets_used=true`, passed public NASA/CDSE metadata discovery and the live WaPOR COG-window read (1,681 valid pixels; 0 NoData), and attempted all three protected checks. NASA returned no valid observations for the selected scene (0/1 scenes processed; one warning); CDSE returned sanitized `ProviderUnavailable`; Gemini returned sanitized `provider_transient_http` after 6,579 ms. A follow-up diagnostics improvement now records only a validated numeric HTTP status (100–599) when available; the latest old run itself did not include that field, so a new probe run is still required. This is a changed Gemini failure mode versus the previous ~20-second timeout, but still not a pass. The sanitized `m1-public-data-smoke-evidence` artifact is attached to the run. These are attempted checks, not accepted passes.

## Required to close M1

1. GitHub Actions secrets are now configured sufficiently for the workflow to attempt the protected checks (the evidence artifact confirms credentials were detected; no values are logged).
2. Diagnose the current failed attempts: NASA HLS selected-scene asset/window validity, CDSE S3 credential/endpoint/asset access, and Gemini transient HTTP response (rerun the fixed probe using the new allowlisted numeric HTTP-status field (never expose response bodies, headers, URLs, or secrets)). Rerun the M1 Public Data Smoke workflow only after the specific causes are addressed.
3. Select and license-audit the Presto classifier dataset. Current proposal: CropHarvest for general training only after its component-dataset licenses are checked; FAO Egypt crop-type mapping as independent local validation only if its download and license are confirmed.
4. Create/review a bilingual agricultural relevance corpus for E5 and publish Recall@5/@10, MRR, and nDCG by language. Keep semantic retrieval disabled until it passes the agreed threshold.
5. Run the focused offline provider/embedding regression suite and attach the exact-head results.

## Safety invariants

- No farmer/field data is sent to hosted LLMs. `CROPTWIST_AI_ALLOW_FIELD_DATA_TO_PROVIDERS=false` and `CROPTWIST_OPENROUTER_ALLOW_FIELD_DATA=false` remain in force.
- The smoke workflow uses only a fixed public Mallawi test polygon and fixed non-sensitive Gemini prompt.
- No production environment, production database, or production deployment is modified by this validation.
- A public catalogue response is not a protected asset read; synthetic fixtures are not live-provider evidence.
