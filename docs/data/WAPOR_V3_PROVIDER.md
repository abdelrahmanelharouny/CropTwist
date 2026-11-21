# FAO WaPOR v3 provider — implementation contract

## Official access path

The implementation follows FAO's official [WaPOR v3 API tutorial](https://github.com/un-fao/FAO-Water-Applications/blob/main/WaPOR/WaPORv3_API.ipynb) and [GISMGR 2.0 API reference](https://github.com/un-fao/FAO-Water-Applications/blob/main/WaPOR/FAO%20GISMGR%202.0%20-%20API%20Reference.pdf).

- Public catalogue root: `https://data.apps.fao.org/gismgr/api/v2/catalog/workspaces/WAPOR-3/mapsets`
- Mapset rasters: append `/{mapset_code}/rasters`
- FAO's notebook retrieves `downloadUrl` links that resolve to public Cloud Storage GeoTIFF/COG assets.
- The official notebook performs ordinary GET requests without an API token; no user credential is required for catalogue discovery.
- Pagination is represented by `response.links` entries with `rel=next`.

## What this branch implements

- Strict HTTPS host/path allowlisting for pagination and raster download links.
- Bounded pagination (50 pages / 100,000 items) and response-size limits.
- Product allowlisting against the CropTwist WaPOR v3 registry.
- Field-window-only COG reads using the existing CRS-aware geospatial reader; no whole-scene raster download.
- Field-polygon masking before statistics.
- Raw mean/median and valid/nodata pixel counts with source URL, mapset, raster ID, period code and native resolution.

## Scientific guardrails

- Raw raster values are always retained. Scale and unit precedence is: API raster metadata, GeoTIFF band tags, then the documented WaPOR v3 product specification. If either unit or scale remains unknown, physical-value summaries remain `null` and only raw statistics are exposed.
- Scaled mean/median are reported only when both a documented unit and scale factor are available; the raw mean/median remain alongside them for auditability.
- The scale/unit reference is [Digital Earth Africa's WaPOR v3 specification](https://docs.digitalearthafrica.org/en/latest/data_specs/WaPOR_specs.html), which documents units and scale factors per L1/L2 mapset.
- Do not map WaPOR AETI, transpiration or relative soil moisture to a CropTwist canonical variable until units, scale, temporal support and nodata semantics are confirmed from the live product metadata / technical documentation.
- WaPOR is satellite-derived water-productivity evidence, not independent field-yield ground truth.
- Level 1 RET is approximately 30 km, not 300 m. Egypt's useful national Level 2 layers are 100 m.
- The first implementation supports selected dekadal L1/L2 layers. It does not yet claim coverage for every catalogue mapset or every Level 3 pilot layer.

## Required live acceptance tests before production

1. Query the live catalogue and confirm the requested mapset exists and has recent rasters for the field's dates.
2. Read one known FAO sample COG and compare its metadata, CRS, transform, nodata and values against GDAL/rasterio.
3. Confirm the scale factor and units from the product's live metadata or official specification; compare one pixel with FAO's published example.
4. Test a polygon near the Egypt boundary and verify field mask, valid-pixel fraction and no pixels outside the polygon.
5. Store the raw asset URL, mapset/raster IDs, period, product version, CRS, resolution, scale/unit evidence and processing version in SourceProvenance.

No synthetic raster is accepted as evidence of live WaPOR availability.
