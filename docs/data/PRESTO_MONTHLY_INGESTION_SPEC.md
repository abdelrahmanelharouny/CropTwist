# Presto monthly input ingestion: exact upstream contract

**Status:** implementation specification; this document does not claim provider-backed monthly ingestion is complete.  
**Upstream reference:** NASA Harvest Presto, `presto/dataops/pipelines/s1_s2_era5_srtm.py`, pinned at the exact commit recorded with each parity run.

## Non-negotiable compatibility contract

The upstream Presto pipeline defines the following dynamic and static inputs. CropTwist's current `presto-17ch-12m-v1` schema contains the same 16 physical channels plus derived NDVI, but the current provider adapters do not yet populate all channels from live monthly sources.

| Group | Required source variables | Raw units / expected values | Presto normalization |
|---|---|---|---|
| Sentinel-1 | VV, VH | dB; upstream expected range approximately -50 to +1 | `(dB + 25) / 25` |
| Sentinel-2 | B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12 | scaled reflectance DN; DN = 10000 × reflectance | `DN / 10000` |
| ERA5 | 2 m temperature, total precipitation | Kelvin; metres | `(K - 272.15) / 35`; `m / 0.03` |
| SRTM | elevation, slope | metres; degrees | `elevation / 2000`; `slope / 50` |
| Derived | NDVI from B8 and B4 | unitless | `(B8 - B4) / (B8 + B4)`; denominator <= 0 is unavailable, not a fabricated value |

The upstream band order after removing B1, B9 and B10 is S1 VV/VH; S2 B2/B3/B4/B5/B6/B7/B8/B8A/B11/B12; ERA5 temperature/precipitation; SRTM elevation/slope; NDVI. Do not reorder channels or silently substitute reflectance in [0,1] for raw DN.

## Monthly aggregation policy to implement

1. Define one UTC calendar-month interval per timestep. Store start inclusive and end exclusive; do not use local time.
2. Sentinel-1: discover GRD scenes intersecting the field, preserve orbit direction, relative orbit, polarization and acquisition IDs; filter invalid/no-data pixels; convert the declared backscatter coefficient to dB only once. Monthly composite reducer and orbit-mixing policy must be pinned and recorded. CDSE sigma0-ellipsoid is not RTC and is not speckle-filtered by default.
3. Sentinel-2: discover L2A scenes, read the ten required bands plus SCL; mask no-data, saturated/defective, cloud shadow, medium/high-probability cloud, cirrus and snow/ice classes; retain clear-pixel counts and valid-area fraction. Resample 20 m bands to the chosen common grid using a documented method; never upsample and claim extra information.
4. ERA5: choose exactly one product per run (ERA5 or ERA5-Land). Aggregate native hourly values to calendar-month statistics with explicit semantics: temperature mean in K; precipitation sum in metres. Record hourly sample count and missing hours.
5. SRTM: acquire one pinned DEM version; derive slope once from the same elevation grid with a pinned algorithm and neighbourhood. Treat both values as static across all months; fail on conflicting values or unrecorded void fill.
6. NDVI: calculate from monthly clear-sky B8/B4 composites after harmonization. Preserve the source composite IDs and QA mask used by both bands.
7. Reproject all raster operations using field geometry transformed into the raster CRS; use bounded windows, explicit nodata and affine transform. Do not sample a projected raster with raw EPSG:4326 coordinates.
8. Monthly outputs must include per-channel value, unit, QA status, valid-pixel count/coverage, source item IDs, product/version, CRS, transform, resampling method, reducer, retrieval timestamp and checksum.
9. Missing data remain masked. Do not zero-fill until the Presto tensor adapter, where zero is paired with the exact boolean mask.

## Data products and current code reality

- Sentinel-2 L2A provider exists and has protected asset-window evidence. It is not yet a full monthly ten-band Presto compositor.
- Sentinel-1 provider is absent from the current first-party provider tree.
- Open-Meteo historical provider exists, but the Presto K/metre monthly aggregate is not wired into crop-history records.
- SRTM provider is absent from the current first-party provider tree.
- NASA HLS is an existing alternative source, not a substitute for Presto's exact S1/S2 channel contract.
- Current CropTwist schema uses 12 monthly timesteps; the original public Presto training pipeline can use a 24-step 2020–2021 sequence. Model parity must therefore compare identical tensors first, then a separate scientific decision must pin whether the CropTwist downstream task uses 12 or 24 months.

## Evidence required before calling ingestion complete

- One end-to-end 12-month field fixture from each supported Egyptian area, with live product item IDs and all 17 channels accounted for.
- Per-month S1/S2 clear-pixel QA and coverage; no missing channel may be silently represented as zero without mask.
- ERA5 monthly-hour completeness and correct K/metre conversions.
- SRTM elevation/slope source/version, EGM96 datum and slope-method provenance.
- CRS/window tests on projected and geographic source rasters, nodata edges, non-square pixels and no-overlap cases.
- Deterministic rerun: identical source item IDs and config produce identical values/checksum; a changed source revision produces a new manifest.
- No random pixel split for any downstream classifier.
