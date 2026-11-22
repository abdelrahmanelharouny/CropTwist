# M3 — GIS & Satellite Reliability

**Baseline:** `9357e06c381a4a52bd870d243e2bb2cf189c87d4`.
**Status:** Workstream acceptance specification; live provider access and raster runtime are not claimed.

## Critical engineering risks to close

- Direct HLS acquisition must preserve the Fmask asset reference from discovery through processing.
- Projected source rasters must never be sampled using untransformed EPSG:4326 field geometry.
- Raster reads must be field-windowed and bounded; do not load full scenes for a small field.
- CRS, affine transform, nodata, scale/offset, band order, resolution, pixel alignment and temporal support must be explicit in provenance.
- Sentinel-2 cloud/shadow/quality masks must be carried through processing and included in valid-pixel coverage.
- Distinguish HLS/Sentinel-derived observations from raw satellite measurements, reanalysis, farmer observations and synthetic fixtures.
- Job submission must not expose a raster job to a worker before its domain row commits; retries must be idempotent.

## Implementation and test sequence

1. Trace acquisition → asset selection → download → raster window → mask → index → zonal statistics → COG → API response.
2. Add projected-CRS fixtures with non-square pixels, non-zero origins, nodata edges and a field polygon that intersects only a bounded raster window.
3. Test Fmask cloud/shadow exclusion and assert contaminated pixels cannot contribute to statistics or valid coverage.
4. Test reprojection and rasterio window bounds; include a regression proving the old unprojected geometry path would fail.
5. Verify units, scale/offset, band naming/order and time support for each supported HLS/Sentinel product.
6. Test empty/no-overlap/all-nodata scenes as honest unavailable states, not zero-valued measurements.
7. Exercise worker transaction ordering, duplicate submission, crash/restart recovery and domain/generic job status reconciliation against PostGIS.
8. Run a live provider smoke only with explicitly configured operator credentials and a known field/time window; persist sanitized request IDs and provenance.

## Acceptance criteria

- Every raster-derived value has source/product/version, CRS, transform, units, time window, mask and processing lineage.
- Projected CRS and Fmask tests pass with real raster libraries and PostGIS.
- Field-windowed reads are bounded and deterministic.
- Invalid or unsupported imagery produces an explicit unavailable/quality state.
- Retry/restart tests prove no duplicate observations or orphaned processing jobs.
- Live acquisition evidence is separate from mocked CI evidence.

## Out of scope

No invented vegetation values, silent cloud-mask fallback, or claim of live NASA/CDSE readiness from contract tests alone.
