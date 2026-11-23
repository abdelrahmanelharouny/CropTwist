# Egypt and upstream data-source / license audit

**Audit date:** 2026-11-23  
**Scope:** CropTwist M1 crop-history training, Presto inputs and Egyptian reference validation.  
**Rule:** catalogue visibility is not a license grant; a source is not training-approved until its exact asset, version, terms and redistribution/derivative-use rights are recorded.

## Decision summary

| Source | Intended use | What is established | License / reuse decision | Current status |
|---|---|---|---|---|
| FAO Egypt crop-type mapping (Zankalon, Sidi Ghazi, Mallawi; 2023–2024) | Egyptian crop labels; independent spatial validation | FAO describes Sentinel-2 classification with ground-truth field data collected 2023-05-15 through 2024-10-15, produced with Egyptian Ministry of Water Resources and Irrigation and Ministry of Agriculture and Land Reclamation | The FAO landing page does not state the downloadable layer's license or redistribution/derivative conditions. Obtain the exact layer metadata and terms from the linked FAO Hand-in-Hand item before downloading, redistributing, or setting `label_license_verified=true`. | **Not license-cleared** |
| Copernicus Sentinel-1 GRD | VV/VH backscatter time series | CDSE STAC documents Sentinel-1 GRD discovery; CDSE product docs describe sigma0-ellipsoid processing; this product is not RTC and has no speckle filtering by default | Sentinel data are available on a free, full and open basis under the Sentinel Data Legal Notice. Preserve source/product, orbit, polarization, acquisition, processing level, calibration and attribution. Do not confuse portal content with Sentinel data: other portal materials may be non-commercial-only. | **Terms identified; monthly pipeline not implemented** |
| Copernicus Sentinel-2 L2A | B02/B03/B04/B05/B06/B07/B08/B8A/B11/B12 and SCL QA | L2A is BOA surface reflectance; native GSD differs by band (10/20/60 m); SCL contains cloud/shadow classes | Sentinel data free/open under Sentinel Data Legal Notice. Preserve processing baseline, band resolution, scale/offset, SCL mask, scene IDs and acquisition timestamps. | **Protected asset read verified; monthly Presto composite not implemented** |
| Open-Meteo ERA5 / ERA5-Land | Monthly temperature and precipitation inputs | Current adapter supports explicit model selection and daily aggregation; ERA5-Land and ERA5 are distinct products and must not be mixed silently | Open-Meteo attribution and CC BY 4.0 are recorded in provider provenance. Preserve exact product choice and native units. Reanalysis is a model estimate, not a station observation. | **Provider exists; Presto-specific monthly K/metre export not integrated** |
| NASA/USGS SRTMGL1 / NASADEM | Static elevation and derived slope | USGS documents global 1 arc-second (~30 m) SRTM, WGS84 horizontal datum, EGM96 vertical datum, elevations in metres and one-degree tiles | Use the product's official NASA/USGS data-use terms and cite product/version. Do not substitute another DEM silently; record void-fill lineage. | **No first-party SRTM acquisition adapter found** |
| NASA Harvest Presto | Encoder weights and reference preprocessing | Upstream code is public; TorchGeo checkpoint is MIT-labelled; upstream input pipeline defines band order, normalization and NDVI | Model-code/weight license does not license every source dataset used to pretrain or fine-tune it. Preserve the upstream commit and checkpoint hash. | **Parity harness added; parity not yet executed** |
| CropHarvest | General crop-label training candidate | A multi-source crop dataset is a candidate, not an Egyptian official reference | Audit every component dataset and label source independently; aggregate repository license is not sufficient evidence for all constituent records. | **Not approved for training until component audit** |
| CAPMAS / Ministry of Agriculture / Egyptian agencies | Official crop area, crop definitions and classification crosswalks | Official statistics and administrative definitions can support class harmonization and aggregate plausibility checks | Publication availability does not automatically grant field-level label reuse. Capture the exact table/publication, methodology, geography, year, terms and any access restrictions. Aggregate statistics are not field labels. | **Candidate authority; no field-level training approval** |

## Source-specific interpretation

### FAO Egypt crop-type map

FAO's public description identifies three study areas and the 2023–2024 summer/winter seasons. It says the classification combines Sentinel-2 and ground-truth data and was produced with the Egyptian water-resources and agriculture ministries. This is strong provenance for an independent Egyptian evaluation source, but the landing page does **not** expose a clear license grant for the underlying downloadable data. Until the item-level metadata/terms are captured, treat the data as *discovery-only*: do not put it in a training CSV, redistribute it, or mark its license verified.

Source: https://www.fao.org/agroinformatics/training-and-resources/data-sets/data-set-detail/new-crop-type-mapping-data-for-egypt/en  
Linked item: https://data.apps.fao.org/?lang=en&share=f-52f1a421-df41-404a-b519-c0b7c4128ef4

### Copernicus Sentinel

The CDSE STAC endpoint documents the `sentinel-1-grd` and `sentinel-2-l2a` collections. Sentinel-1 GRD backscatter must not be described as terrain-flattened RTC: the documented sigma0-ellipsoid product is orthorectified with a Copernicus DEM but has no RTC or speckle filtering by default. Sentinel-2 L2A provides BOA reflectance and SCL; cloud/shadow masking must be applied before monthly statistics. Band resolutions differ, so all bands need a documented common-grid strategy before stacking.

Sources:
- https://documentation.dataspace.copernicus.eu/APIs/STAC.html
- https://documentation.dataspace.copernicus.eu/Data/Sentinel1.html
- https://dataspace.copernicus.eu/terms-and-conditions
- https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice

### ERA5 and SRTM

ERA5 and ERA5-Land are separate reanalysis products. Presto's upstream feature definition uses 2 m temperature in kelvin and total precipitation in metres, not CropTwist's canonical Celsius/mm fields without conversion. The conversion must happen once, be explicit, and be recorded. SRTM uses metres and EGM96 vertical datum; slope is derived from the selected DEM and must record algorithm, neighbourhood, edge/nodata treatment and output units.

Sources:
- https://open-meteo.com/en/docs/historical-weather-api
- https://www.usgs.gov/centers/eros/science/usgs-eros-archive-digital-elevation-shuttle-radar-topography-mission-srtm-1
- https://www.earthdata.nasa.gov/s3fs-public/2025-05/SRTM_Quick_Guide.pdf

## Mandatory label registry fields

Every candidate crop-label layer or record must carry:

- `source_id`, publisher, dataset title, stable item URL, release/version and retrieval date
- source geography, geometry/CRS, field or polygon identifier, crop season and reference period
- original class code/name, original legend and the versioned CropTwist class crosswalk
- collection method (field survey, administrative statistic, remote-sensing classification, farmer record)
- ground-truth status, positional/temporal uncertainty and known sampling bias
- exact license name, license URL or written permission, commercial-use status, derivative-use status, redistribution status and attribution
- reviewer, review date, review decision and evidence attachment

A boolean supplied by an operator is not itself proof. Keep `label_source_verified` and `label_license_verified` false until the referenced evidence has been reviewed.

## Release blockers

1. Obtain and archive FAO item-level license/terms and the class legend before using Egyptian labels.
2. Decide whether the Sentinel-1 product is accepted as sigma0-ellipsoid or whether an independently validated RTC product is required; never label the former RTC.
3. Implement and record one explicit S2 common-grid/resampling policy (10 m or 20 m) with SCL QA.
4. Add an SRTM/NASADEM adapter with EGM96 metadata, void handling and slope algorithm.
5. Keep model-weight license, source-data licenses and crop-label licenses as separate records.
