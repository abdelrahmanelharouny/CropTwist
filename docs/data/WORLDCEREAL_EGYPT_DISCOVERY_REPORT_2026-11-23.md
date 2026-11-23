# WorldCereal Egypt reference discovery — 2026-11-23

**Workflow:** [Egypt reference data discovery #23](https://github.com/abdelrahmanelharouny/CropTwist/actions/runs/45166943547)  
**Artifact:** `egypt-reference-discovery-report`, ID `14815335882`  
**Source record:** [WorldCereal harmonized reference datasets v1.1.0](https://zenodo.org/records/18769612)

## Discovery outcome

The bounded run completed successfully. It downloaded all eight Africa archives (2018–2025), checked their declared byte sizes and MD5 checksums, scanned nested ZIPs and metadata workbooks, parsed GeoParquet members, and generated a candidate manifest.

Two Egypt collections were found in the 2019 Africa archive:

| Collection ID | GeoParquet rows | Metadata observation date | Declared source license |
|---|---:|---|---|
| `2019_egy_faowapor1_poly_111` | 898 | 2019-08-05 | `CC_BY` |
| `2019_egy_faowapor2_poly_111` | 634 | 2019-03-14 to 2019-03-28 | `CC_BY` |
| **Total** | **1,532** | **2019** | — |

Both metadata workbooks identify the original source as **FAO WAPOR - field data Egypt 2019**, provider FAO-WAPOR, observation method `FieldObservationSurvey`, and geometry type `FieldRegisteredPolygon`. Both declare `CC_BY` as the license type, but the license-reference URL is blank. Sampling design and validation status are both `Unknown`. The metadata also supplies the citation: *FAO WaPOR, 2022. Field data Egypt 2019* and the FAO WaPOR portal URL.

The declared `CC_BY` is materially different from having no license metadata, but it is not sufficient to mark the data license verified: the exact license version/reference and original data-holder rights must be confirmed. CropTwist is non-commercial research; commercial-use restrictions are not the reason for this hold. The outstanding issues are item-level rights, attribution, adaptation/derived-label permission and redistribution scope.

## Geometry and leakage QA

- All 1,532 GeoParquet geometries parsed as valid, non-empty WGS84 polygons.
- Collection 1 contains 898 parsed rows, although its metadata workbook reports 900 observations; investigate the two-row difference.
- Collection 2 contains 634 rows.
- There are 12 positive-area polygon intersections between the two collections and zero exact-equal geometry pairs.
- The candidate manifest's conservative union-find (H3, same-collection Field_ID/Block_ID and positive-area intersections) yields 3 spatial components. Only 2 components contain crop-specific labels: one has 877 labelled rows and the other is a singleton. The third is generic-only.
- The 12 cross-collection intersecting pairs and any connected spatial records must stay in the same partition; do not randomly split rows.

## Label QA

- 878 rows have crop-specific EWOC codes after excluding generic/non-crop codes.
- 654 rows are generic/non-crop and must not be treated as crop labels.
- Collection 1 has 598 null `CroType` values.
- Collection 2 has 20 missing `Field_ID` and `Block_ID` values.
- The source's crop-type and land-cover quality scores are constant at 93. They are source curation scores, not measured classifier accuracy or calibrated per-row probabilities.
- The collection metadata reports `FieldObservationSurvey`, but sampling design and validation remain unknown. Preserve this uncertainty in every downstream record.

## Spatial/temporal scope

The collections occupy one compact survey footprint (collection 1 bounds: 31.294260–31.574320 E, 30.484687–30.808660 N; collection 2 bounds: 31.237126–31.605252 E, 30.374918–30.731202 N). They do not provide three independent Egyptian regions. They can support data-pipeline development and carefully grouped exploratory work after rights confirmation, but **cannot alone support an independent spatial train/validation/test evaluation**.

The first collection has a single validity date (2019-08-05); the second spans 2019-03-14 to 2019-03-28. They are not a multi-year crop-history dataset. Monthly Sentinel-1/Sentinel-2/ERA5/SRTM features still need separate ingestion and provenance.

## RDM response caveat

The RDM request completed without an HTTP error, but the current report parser counted zero collections and zero Egypt matches. This is not proof that the RDM contains no public collections: inspect the endpoint response schema and pagination before making that conclusion. The positive Egypt discovery above comes from the nested 2019 Africa archive.

## Acceptance decision

**Candidate only — not training approved**

1. Obtain the exact FAO-WaPOR item-level license/version, source-holder confirmation and required attribution.
2. Confirm whether research use, derived-label adaptation and redistribution are separately permitted.
3. Resolve the 900-versus-898 row discrepancy and missing field identifiers without inventing values.
4. Review EWOC-to-CropTwist crop taxonomy and rare classes with an agronomist.
5. Acquire additional independent Egyptian regions and years; preserve connected spatial groups.
6. Ingest the full monthly satellite/climate/terrain features and execute Presto parity before model training.

The complete raw evidence bundle is retained in the GitHub Actions artifact. It contains the discovery JSON, all eight Africa ZIPs, GeoParquet profile and candidate manifest.
