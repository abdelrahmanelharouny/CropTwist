# Egypt and upstream data-source / license audit

**Audit date:** 2026-11-23  
**Scope:** CropTwist M1 crop-history training, Presto inputs and Egyptian reference validation.  
**Rule:** catalogue visibility is not a license grant; a source is not training-approved until its exact asset, version, terms and redistribution/derivative-use rights are recorded.

## Decision summary

| Source | Intended use | What is established | License / reuse decision | Current status |
|---|---|---|---|---|
| FAO Egypt crop-type mapping (Zankalon, Sidi Ghazi, Mallawi; 2023–2024) | Egyptian crop labels; independent spatial validation | FAO describes Sentinel-2 classification with ground-truth field data collected 2023-05-15 through 2024-10-15, produced with Egyptian Ministry of Water Resources and Irrigation and Ministry of Agriculture and Land Reclamation | The FAO landing page does not state the downloadable layer's exact license or redistribution/derivative conditions. CropTwist is a non-commercial research model, so do not reject this source solely because FAO's general terms restrict commercial reuse. Obtain the exact layer metadata and terms from the linked FAO Hand-in-Hand item; assess research use, adaptation/derived labels, attribution and redistribution separately before setting `label_license_verified=true`. | **Research candidate; item-level terms pending** |
| Copernicus Sentinel-1 GRD | VV/VH backscatter time series | CDSE STAC documents Sentinel-1 GRD discovery; CDSE product docs describe sigma0-ellipsoid processing; this product is not RTC and has no speckle filtering by default | Sentinel data are available on a free, full and open basis under the Sentinel Data Legal Notice. Preserve source/product, orbit, polarization, acquisition, processing level, calibration and attribution. Do not confuse portal content with Sentinel data: other portal materials may be non-commercial-only. | **Terms identified; monthly pipeline not implemented** |
| Copernicus Sentinel-2 L2A | B02/B03/B04/B05/B06/B07/B08/B8A/B11/B12 and SCL QA | L2A is BOA surface reflectance; native GSD differs by band (10/20/60 m); SCL contains cloud/shadow classes | Sentinel data free/open under Sentinel Data Legal Notice. Preserve processing baseline, band resolution, scale/offset, SCL mask, scene IDs and acquisition timestamps. | **Protected asset read verified; monthly Presto composite not implemented** |
| Open-Meteo ERA5 / ERA5-Land | Monthly temperature and precipitation inputs | Current adapter supports explicit model selection and daily aggregation; ERA5-Land and ERA5 are distinct products and must not be mixed silently | Open-Meteo attribution and CC BY 4.0 are recorded in provider provenance. Preserve exact product choice and native units. Reanalysis is a model estimate, not a station observation. | **Provider exists; Presto-specific monthly K/metre export not integrated** |
| FAO WaPOR v2 Level-3 Zankalon land-cover/crop layer | Candidate historical crop/land-cover reference for Zankalon only | Peer-reviewed Nile Delta work reports a 30 m, dekadal WaPOR v2 land-cover layer for Zankalon, with FAO fieldwork reference data; this is not the same product as the newer FAO Egypt 2023–2024 crop-type map. | Do not inherit WaPOR v3 L2 CC BY-SA 4.0 terms for a v2/L3 layer. Capture the exact v2 product record, item-level license and class legend before use. | **Candidate; version-specific terms not cleared** |
| FAO WaPOR v3 Egypt Level-2 products | Environmental covariates / water evidence, not crop labels | The current provider's live smoke artifact verified an Egypt L2 AETI-D COG window (CC BY-SA 4.0, mm/day, scale 0.1); the WaPOR v3 provider specification records CC BY-SA 4.0 for those v3 products. | This license evidence applies to the exact WaPOR v3 product records, not automatically to FAO crop-type reference maps or WaPOR v2 pilot layers. Preserve attribution and share-alike obligations for derivatives. | **Exact L2 product live-verified; not a crop-label source** |
| NASA/USGS SRTMGL1 / NASADEM | Static elevation and derived slope | USGS documents global 1 arc-second (~30 m) SRTM, WGS84 horizontal datum, EGM96 vertical datum, elevations in metres and one-degree tiles | Use the product's official NASA/USGS data-use terms and cite product/version. Do not substitute another DEM silently; record void-fill lineage. | **No first-party SRTM acquisition adapter found** |
| NASA Harvest Presto | Encoder weights and reference preprocessing | Upstream code is public; TorchGeo checkpoint is MIT-labelled; upstream input pipeline defines band order, normalization and NDVI | NASA Harvest's upstream repository exposes the MIT license and `data/default_model.pt`; preserve the upstream commit and checkpoint hash. Model-code/weight license does not license every source dataset used to pretrain or fine-tune it. The model license and training-data provenance remain separate governance records. Source: https://github.com/nasaharvest/presto | **Parity harness added; parity not yet executed** |
| CropHarvest v14 | General non-Egyptian pretraining / external validation candidate | NASA Harvest states 95,186 datapoints, 21 aggregated component datasets, with binary and multiclass labels; its component manifest lists geography, label counts and item-level source licenses | The package is CC BY-SA 4.0, while components include CC BY 4.0, CC BY 3.0, Etalab Open License, Open Government License, DL-DE->BY-2.0, LP DAAC terms and CC BY-SA 4.0. Do not treat the package license as proof that each component is independently reusable; select rows by source ID, retain attribution and separately assess ShareAlike/database terms before commercial redistribution or model release. | **Component manifest audited; no blanket commercial clearance; no Egypt-specific labels** |
| ESA WorldCereal 2021 global products | Independent coarse crop-type/temporary-cropland and irrigation cross-check | Official ESA describes 10 m annual temporary-crop extent and seasonal maize, winter-cereal/spring-cereal and irrigation products for 2021; products are assembled by agro-ecological zone and seasonal definitions differ across zones | Digital Earth Africa product specifications state CC BY 4.0. Preserve attribution, product/season/AEZ and confidence. These are model-derived maps, not field-survey labels; they distinguish only a limited set of crop groups and are 2021-only. Verify actual valid-pixel coverage for each Egyptian study polygon before use. Never treat map pixels as verified Egyptian field labels. | **License identified; Egypt coverage and local accuracy not yet verified; cross-check only** |
| WorldCereal Reference Data Module (RDM) public collections | Candidate source for in-situ crop-type reference observations, including possible Africa/Egypt records | Official RDM describes harmonized, curated in-situ datasets and a public REST collections endpoint; each collection has metadata, source attribution, license and privacy level | Review each collection's metadata and item-level license separately. Public access is not a blanket license; private/restricted records are not available for unrestricted reuse. This audit has not yet confirmed an Egypt collection or downloaded any record. | **High-priority discovery lead; Egypt availability and per-collection terms pending** |
| CAPMAS / Ministry of Agriculture / Egyptian agencies | Official crop area, crop definitions and classification crosswalks | Official statistics and administrative definitions can support class harmonization and aggregate plausibility checks | Publication availability does not automatically grant field-level label reuse. Capture the exact table/publication, methodology, geography, year, terms and any access restrictions. Aggregate statistics are not field labels. | **Candidate authority; no field-level training approval** |

## Source-specific interpretation

### FAO Egypt crop-type map

FAO's public description identifies Zankalon, Side Ghazi and Mallawi, with 2023–2024 summer/winter seasons. It says the classification combines Sentinel-2 and ground-truth data and was produced with the Egyptian water-resources and agriculture ministries. Its landing-page sentence describing all three as being in the Nile Delta is geographically incorrect: Zankalon is in Sharqia, Sidi Ghazi is in Kafr El Sheikh (both Lower Egypt / Delta region), while Mallawi is in Minya in North Upper Egypt. This correction is supported by Egyptian government administrative records (Egyptian Survey Authority notice for Zankalon; Kafr El Sheikh administrative record for Sidi Ghazi; State Information Service references identifying Mallawi as in Minya). The exact FAO study polygons and their administrative intersections must still be taken from the linked item, not inferred from locality centroids. This is strong provenance for an independent Egyptian evaluation source, but the landing page does **not** expose a clear license grant for the underlying downloadable data. Until item-level metadata/terms are captured, treat the data as a *research candidate pending rights review*: do not redistribute it or mark its license verified. Non-commercial research use may be assessed once the exact item terms and third-party rights are confirmed.

Administrative cross-checks: https://cdn.vetogate.com/UploadCache/libfiles/580/5/0x0o/104.pdf (Egyptian Survey Authority notice lists Zankalon under Sharqia); https://aca.gov.eg/Media/News/2023/1/25/2023-638102552378243908-824.pdf (Kafr El-Sheikh table lists Sidi Ghazi); https://sis.gov.eg/en/media-center/news/pope-tawadros-inauguration-of-kom-maria-project-in-mallawi-important-addition-to-minya/ (State Information Service identifies Mallawi, Minya).

Source: https://www.fao.org/agroinformatics/training-and-resources/data-sets/data-set-detail/new-crop-type-mapping-data-for-egypt/en  
Linked item: https://data.apps.fao.org/?lang=en&share=f-52f1a421-df41-404a-b519-c0b7c4128ef4  
HiH data export policy: https://www.fao.org/hih-geospatial-platform/faqs/  
FAO website reuse terms: https://www.fao.org/contact-us/terms/  
FAO statistical database terms: https://www.fao.org/contact-us/terms/db-terms-of-use/en

### CropHarvest component-level licensing

NASA Harvest's current repository README says CropHarvest aggregates 21 source datasets; its `datasets.md` manifest exposes materially different source licenses. Examples include NASA Harvest's Rwanda/Kenya/Ethiopia/Sudan/Mali/Brazil/Tanzania/Togo binary labels under CC BY 4.0; French RPG under the Etalab Open License; a global cropland component under CC BY 3.0; Canada's Annual Crop Inventory under the Open Government License; Germany's DENETHOR under DL-DE->BY-2.0; and components under CC BY-SA 4.0 or LP DAAC terms. The aggregate repository itself is CC BY-SA 4.0. Therefore, CropHarvest is not approved as one undifferentiated training bundle for a commercial product. A source-filtered subset may be considered only after its own source terms, attribution, database rights and model/data distribution implications are reviewed. None of these records is Egyptian ground truth.

Sources: https://github.com/nasaharvest/cropharvest/blob/main/README.md ; https://github.com/nasaharvest/cropharvest/blob/main/datasets.md ; https://github.com/nasaharvest/cropharvest/blob/main/LICENSE.txt

### WorldCereal Reference Data Module (RDM)

The RDM is a better candidate for field-level validation than the WorldCereal 2021 map products: its public collections contain harmonized in-situ crop/land-cover reference data and the API exposes a public collection listing. Each collection carries its own source metadata, citation, license and privacy level. Public visibility does not grant one blanket license, and private/restricted records are not reusable as open data. The next data-discovery task is to query the public collections catalog for Egypt, Nile Delta / Minya localities and relevant years, then inspect each matching collection's metadata/license before downloading. No Egypt-specific collection is claimed as found yet.

Sources: https://ewoc-rdm-api.iiasa.ac.at/collections ; https://rdm.esa-worldcereal.org/api ; https://worldcereal.github.io/worldcereal-documentation/rdm/explore.html

### WorldCereal 2021

The official ESA collection offers annual temporary-crop extent and season-specific crop-type/irrigation layers for 2021 at 10 m. Crop-type products identify maize and cereals (wheat, barley and rye grouped together); they are not a full Egyptian crop taxonomy. Products are mosaicked by agro-ecological zone, and adjacent-zone seasonal maps are not directly comparable. Digital Earth Africa's product specification states CC BY 4.0. Use only as an independently derived, limited-class cross-check after checking valid-data coverage and the relevant AEZ/season for each Egyptian study polygon. It is not in-situ ground truth and must not be relabelled as verified field observations.

Sources: https://esa-worldcereal.org/en/products/global-maps ; https://docs.digitalearthafrica.org/en/latest/data_specs/ESA_World_Cereal_specs.html ; https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCereal_2021_MODELS_v100

### Copernicus Sentinel

The CDSE STAC endpoint documents the `sentinel-1-grd` and `sentinel-2-l2a` collections. Sentinel-1 GRD backscatter must not be described as terrain-flattened RTC: the documented sigma0-ellipsoid product is orthorectified with a Copernicus DEM but has no RTC or speckle filtering by default. Sentinel-2 L2A provides BOA reflectance and SCL; cloud/shadow masking must be applied before monthly statistics. Band resolutions differ, so all bands need a documented common-grid strategy before stacking.

Sources:
- https://documentation.dataspace.copernicus.eu/APIs/STAC.html
- https://documentation.dataspace.copernicus.eu/Data/Sentinel1.html
- https://dataspace.copernicus.eu/terms-and-conditions
- https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice

### WaPOR and crop-label separation

The CropTwist WaPOR v3 provider specification records CC BY-SA 4.0 for the v3 products it supports, and the current live artifact verified an Egypt Level-2 AETI-D window. That is useful environmental evidence, not a crop-class label. The WaPOR v2 Level-3 Zankalon land-cover layer is a separate product generation and must have its own item-level license check. Never transfer the v3 L2 license to v2 L3 or to the separate 2023–2024 FAO Egypt crop-type map.

Sources: https://docs.digitalearthafrica.org/en/latest/data_specs/WaPOR_specs.html ; https://www.mdpi.com/2673-4834/6/3/80 ; https://www.fao.org/in-action/remote-sensing-for-water-productivity/wapor-data/en

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

1. Obtain and archive FAO item-level terms and the class legend; review non-commercial research use, adaptation/derived-label permissions, attribution and redistribution separately before using Egyptian labels.
2. Decide whether the Sentinel-1 product is accepted as sigma0-ellipsoid or whether an independently validated RTC product is required; never label the former RTC.
3. Implement and record one explicit S2 common-grid/resampling policy (10 m or 20 m) with SCL QA.
4. Add an SRTM/NASADEM adapter with EGM96 metadata, void handling and slope algorithm.
5. Keep model-weight license, source-data licenses and crop-label licenses as separate records.


## Addendum: 2026 WorldCereal reference-data release and FAO reuse boundary

A newer WorldCereal harmonized reference-data release is available: Zenodo record 18769612, version 1.1.0, published 2026-02-25. It includes separate Africa ZIP archives for 2018, 2019, 2020, 2021, 2022, 2023, 2024 and 2025. The publisher explicitly states that each individual dataset retains the original data holder's license, recorded in the accompanying metadata workbook. This is a concrete discovery path beyond the earlier 2021 map product, but an Africa archive is not proof of Egypt coverage. The new bounded discovery script at `mini-services/fieldshift-api/scripts/discover_egypt_reference_data.py` queries the public RDM catalog and inspects the Africa archive metadata for Egypt/locality matches and per-collection license terms. No Egypt match is claimed until the script's report is produced and reviewed.

FAO's general website terms state that most website content can be reused for private study, research, teaching and non-commercial products/services with attribution; adaptation, translation, resale and other commercial reuse require permission. FAO corporate statistical database terms have separate restrictions against using those datasets to promote a commercial enterprise, even where CC BY 4.0 is the default, and third-party content may carry different terms. These general rules do not replace the exact FAO map item's metadata or the original data holder's terms. CropTwist is a non-commercial research model. Accordingly, commercial-use restrictions in FAO's general terms are not by themselves a reason to exclude the 2023–2024 Egypt map. The map remains pending item-level review: confirm the exact downloadable asset's terms, third-party rights, research-use scope, adaptation/derived-label permissions, attribution and any redistribution limits. Do not infer blanket permission from FAO's general website terms.

**Training fallback:** use the two 2019 FAO-WaPOR Egypt field-label collections as the first candidate for a controlled ingestion/evaluation spike, subject to item-level rights confirmation and GeoParquet quality checks. WorldCereal map products may be used only in an explicitly separated weak-supervision experiment (never as ground truth); official governorate crop statistics are aggregate plausibility checks only. Keep the crop classifier out of production until independent Egyptian field/parcel labels are validated. Presto representation learning and the crop-label classifier remain separate deliverables.

Sources: https://zenodo.org/records/18769612 ; https://www.fao.org/contact-us/terms/ ; https://www.fao.org/contact-us/terms/db-terms-of-use/en ; https://worldcereal.github.io/worldcereal-documentation/rdm/explore.html


## Live WorldCereal discovery result — 2026-11-23

A credential-free GitHub Actions run queried the public RDM catalog and downloaded/scanned all eight Africa archives exposed by Zenodo record 18769612 (years 2018–2025). The run completed with no API/download/checksum/scan errors:

- Public RDM collections returned: **0**
- Egypt/locality matches in RDM metadata: **0**
- Africa archives downloaded and checksum-verified: **8 / 8**
- Archive members scanned: **63**
- Egypt/locality text matches in archive metadata/text: **0**
- The first-pass scanner reported zero Egypt matches because it did not inspect nested per-collection ZIPs. Manual review of the downloaded 2019 Africa archive identified two Egyptian FAO-WaPOR collections (see corrected finding below).

Evidence: GitHub Actions run [45157390222](https://github.com/abdelrahmanelharouny/CropTwist/actions/runs/45157390222), artifact `egypt-reference-discovery-report` (artifact ID `14808543228`, SHA-256 `1499b92618629d2dfe1ec1c13981746a05e355dad68dd9809de3e6323828b392`).

**Interpretation limit:** the first scanner version missed nested collection ZIPs. The outer RDM endpoint returned zero records, but the 2019 Africa archive contains two Egypt collections identified by the `_egy_` country code and confirmed in their inner metadata workbooks. The corrected scanner now inspects nested ZIP names and workbooks. The 2023–2024 FAO Egypt map remains an additional candidate pending item-level terms and data retrieval.


## Confirmed Egyptian WorldCereal collections found in nested 2019 archive

Manual inspection of the downloaded and checksum-verified 2019 Africa archive found two nested Egypt collection ZIPs that the first scanner version missed:

| Collection ID | Original dataset | Observations | Observation dates | Bounding box (lon/lat) | Declared license |
|---|---|---:|---|---|---|
| 2019_egy_faowapor1_poly_111 | FAO WAPOR - field data Egypt 2019 | 900 | 2019-08-05 (field sheet collection 2019-08-03 to 2019-08-08) | 31.294260, 30.484687 to 31.574320, 30.808660 | CC_BY |
| 2019_egy_faowapor2_poly_111 | FAO WAPOR - field data Egypt 2019 | 634 | 2019-03-14 to 2019-03-28 | 31.237126, 30.374918 to 31.605252, 30.731202 | CC_BY |

Both metadata workbooks state:
- Observation method: FieldObservationSurvey
- Original geometry: FieldRegisteredPolygon; curated geometry: Polygon
- Original provider: FAO-WAPOR (FAO Water Productivity Open-access portal)
- Declared license type: CC_BY; license-reference cell is blank
- Required citation: FAO WaPOR, 2022. Field data Egypt 2019. https://www.fao.org/in-action/remote-sensing-for-water-productivity/en/
- WorldCereal curation PDFs report crop-type and land-cover confidence scores of 93, state that no filtering/corrections/geometry transformations were performed, and describe spatial accuracy validation using systematic random sampling and satellite imagery.

**Scientific disposition:** these are strong Egyptian field-label candidates and should be prioritized for an ingestion/evaluation spike. The declared CC_BY value is source metadata, not a substitute for archiving the underlying rights statement; verify the FAO source terms and attribution before training or redistribution. The two collections may overlap spatially and temporally; deduplicate/group by field ID and spatial intersection before any split. Do not count the 1,534 observations as 1,534 independent farms without inspecting the actual feature attributes. Parse the GeoParquet files, validate geometry and label distributions, and build spatial-temporal group splits before training.


## Automated GeoParquet QA — 2026-11-23

Corrected nested-archive workflow [45158997515](https://github.com/abdelrahmanelharouny/CropTwist/actions/runs/45158997515) successfully profiled both Egyptian GeoParquet files with PyArrow and Shapely. Artifact ID: 14808784478; SHA-256: 92988e61450802406615e0f9d1d98e04ee8dcaa10fdf6d9eaa97a000dcdeeb2e.

| Collection | Actual GeoParquet rows | Valid geometries | Crop-specific EWOC-coded rows* | Notable QA |
|---|---:|---:|---:|---|
| 2019_egy_faowapor1_poly_111 | 898 | 898/898 | 290 | Metadata says 900 observations (2-row discrepancy); 598 CroType values are null; 608 rows map to generic EWOC code 1000000000 |
| 2019_egy_faowapor2_poly_111 | 634 | 634/634 | 588 | 20 missing Field_ID and Block_ID values; 20 missing original FW_Date values; curated valid_time is populated |

*For this profile, generic/non-crop EWOC codes 1000000000, 1100000000, 6000000000 and 7000000000 are excluded from the crop-specific count. This is a QA rule for the candidate manifest, not a final label taxonomy.

Across both files: **1,532 actual rows**, all geometries parse and validate, no empty geometries, and no exact duplicate geometries across the collections. The spatial index found **12 cross-collection polygon pairs with positive-area intersections**. Those intersecting pairs must be assigned to the same spatial split group or reviewed/deduplicated; a random row split is prohibited.

The crop-specific EWOC code distribution is highly imbalanced. Collection 1 is dominated by rice (206) and maize (57); collection 2 by wheat (270), permanent leguminous crops (144), onions (47), oranges (37) and potatoes (26), with many classes having fewer than 10 examples. Do not claim a balanced 23-class training set or publish an accuracy metric from a random split.

The source's quality_score_ct and quality_score_lc are constant at 93 for every row in both files. Treat 93 as a source/curation score, **not** a per-observation probability or independently measured model accuracy. In collection 2, Field_ID has 20 non-null distinct IDs and 20 missing rows; Block_ID has 82 non-null distinct IDs and 20 missing rows. In collection 1, sampleID is unique per polygon but is not evidence of independent farms; H3 grouping fields cover only 2 coarse cells and 6 finer cells. Use spatial blocks/geometry intersections as the split unit, not sampleID.

**Decision:** candidate for a controlled research ingestion and representation-learning/evaluation spike after source-rights confirmation. It is not yet training-approved. Preserve original CT, LC, CroType, ewoc_code, validityTi, valid_time, sampleID, Field_ID, Block_ID, and null flags in the immutable raw layer. Build an explicit label mapping that excludes generic classes, then create spatially grouped splits and compare against the separate 2023–2024 FAO Egypt reference source.
