# M1-A Satellite Pipeline — Hardening Notes

**Scope:** NASA HLS v2 and Copernicus Sentinel-2 L2A acquisition/processing.
**Status:** implementation changes are on `fix/m1a-satellite-processing`; merge remains blocked pending the latest CI run and review. No live-provider success is claimed.

## Provider and raster correctness

- Sentinel-2 defaults to the current CDSE STAC API v1 endpoint: `https://stac.dataspace.copernicus.eu/v1`. The former `https://catalogue.dataspace.copernicus.eu/stac` endpoint was marked deprecated by CDSE effective 2025-11-17.
- Current CDSE item assets are S3 URIs (`s3://eodata/...`), not generic HTTPS COG URLs. GDAL reads them via `/vsis3/` and `AWS_S3_ENDPOINT=eodata.dataspace.copernicus.eu`, `AWS_VIRTUAL_HOSTING=FALSE`, and CDSE-generated S3 credentials.
- Sentinel-2 processing baseline resolution prefers the current `processing:version` property and falls back to legacy `s2:processing_baseline`.
- The STAC collection remains `sentinel-2-l2a`; the provider uses the `/search` endpoint and the STAC query extension for cloud-cover filtering.
- Mixed-resolution Sentinel-2 reflectance bands are aligned geospatially to the red 10 m grid; categorical SCL uses nearest-neighbour resampling. Index metadata reports the coarsest effective input resolution.
- Sentinel-2 reflectance conversion resolves per-band STAC/GeoTIFF scale-offset metadata first, then the processing-baseline rule. Missing offset and baseline metadata fail closed.
- HLS Fmask is required both by the direct HLS provider and the derived-product validation/derivation path. A missing QA asset cannot produce an observation described as quality-masked.
- HLS v2 bit 0 remains reserved; bits 1–4 are excluded; water is retained and counted; AOT levels are decoded as 00 climatology, 10 low, 01 medium, 11 high; high-AOT pixels are excluded according to the LP DAAC known-issues guidance.

## Credential and metadata boundary

- CDSE username/password are used only when the configured STAC host is an official CDSE STAC host and the token endpoint host is the official CDSE identity host.
- A CDSE bearer token is passed to GDAL only when every asset URL for that scene is HTTPS and hosted under `dataspace.copernicus.eu`. Alternate STAC providers must use their own signed asset URLs; CDSE credentials are not forwarded to them.
- Asset URL query strings/fragments and URL user-info are removed before writing asset references into observation metadata. Signed URLs remain transient inputs to the raster read and are not persisted.
- Raster/GDAL exception messages are not copied verbatim into API error details because they can contain signed URLs. Error type and scene ID are retained for diagnosis.

## Verification contract

The deterministic tests cover mixed-resolution alignment, SCL/Fmask masks, HLS Fmask propagation, southern-hemisphere geometry, Sentinel-2 `processing:version`/legacy baseline offsets, CDSE S3 URI translation and credential configuration, missing QA rejection, CDSE auth-host scoping and signed-URL metadata redaction.

CI must pass on the exact final branch head. These tests use synthetic GeoTIFF fixtures and mocked STAC/HTTP transports. They do **not** establish live CDSE connectivity, live Earthdata access, provider account entitlements, or correctness on production imagery. Those require a credentialed, explicitly authorized live smoke test after deployment configuration is reviewed.

## Primary provider references

- CDSE STAC API: https://documentation.dataspace.copernicus.eu/APIs/STAC.html
- CDSE S3 object storage: https://documentation.dataspace.copernicus.eu/APIs/S3.html
- CDSE OData authentication: https://documentation.dataspace.copernicus.eu/APIs/OData.html
- HLS v2 algorithms and QA: https://hls.gsfc.nasa.gov/algorithms/
- HLS v2 known issues: https://lpdaac.usgs.gov/documents/2435/HLS_v2.0_S30_known_issues_April2026.pdf
- Sentinel-2 L2A data quality/radiometry: https://sentiwiki.copernicus.eu/web/s2-processing
