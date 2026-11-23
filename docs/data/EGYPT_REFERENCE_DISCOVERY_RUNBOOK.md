# Egypt reference-data discovery runbook

**Purpose:** find public Egypt-relevant crop reference collections and capture each source's own license before any training use.

## Primary discovery targets

1. WorldCereal RDM public collection catalog: https://ewoc-rdm-api.iiasa.ac.at/collections
2. WorldCereal harmonized reference data, Zenodo record 18769612 (version 1.1.0, published 2026-02-25): https://zenodo.org/records/18769612
3. FAO Egypt crop-type mapping page (Zankalon, Sidi Ghazi, Mallawi; 2023–2024): https://www.fao.org/agroinformatics/training-and-resources/data-sets/data-set-detail/new-crop-type-mapping-data-for-egypt/en
4. FAO Hand-in-Hand linked map item: https://data.apps.fao.org/?lang=en&share=f-52f1a421-df41-404a-b519-c0b7c4128ef4

The 2026 WorldCereal record groups individual harmonized reference collections into year/continent ZIP archives, including Africa archives for 2018–2025. The archive's accompanying metadata workbook must be checked because **each individual dataset retains the original data holder's license**. The archive-level Zenodo record is not a blanket license for every row or collection.

## Run the bounded discovery

From `mini-services/fieldshift-api`:

```bash
python scripts/discover_egypt_reference_data.py \
  --download-africa-archives \
  --output-dir .cache/egypt-reference-discovery \
  --output egypt-reference-discovery.json
```

The script:
- Queries the public RDM collections endpoint.
- Reads the Zenodo record metadata and selects Africa ZIPs only.
- Downloads only Africa archives no larger than 50 MB each (configurable up to 50 MB).
- Verifies each archive's declared size and MD5/SHA-256 when supplied.
- Scans CSV/text/JSON and XLSX metadata rows for Egypt, Egyptian localities and governorates.
- Emits collection IDs, matched metadata rows and any per-collection license values it finds.

It does not upload data, redistribute data, mark labels verified, or train a model. Keep the JSON report and source archive checksums as evidence. Review every match manually before using it.

## Label-quality decision

- A source with field observations, farmer declarations or independently reviewed parcel labels can be considered a candidate ground-truth source after provenance, temporal alignment, positional accuracy and license review.
- An automated crop map (including WorldCereal map products) is a **weak label / pseudo-label**, not in-situ ground truth. It can support a separately tracked weak-supervision experiment, never the final independent validation set.
- Country-level or governorate-level crop-area statistics can validate aggregate plausibility and class totals; they cannot be expanded into parcel-level labels.
- Do not mix CC BY, CC BY-SA, CC BY-NC, private, restricted and unclear-license sources in one training bundle. Record each source ID and license separately.

## FAO rights boundary

CropTwist is a **non-commercial research model**. FAO's general website terms describe reuse for private study, research, teaching and non-commercial products/services with attribution; adaptation, translation, resale and commercial reuse may require permission. FAO statistical-database terms are separate, and third-party content may carry different terms. Therefore, do not exclude the FAO Egypt map merely because commercial reuse is restricted. Treat it as a **research candidate pending item-level review**: obtain the exact linked asset metadata and class legend, identify the data holder and third-party rights, and separately confirm research use, adaptation/derived-label permissions, attribution and redistribution limits. Do not assume the general FAO website terms automatically license the downloadable map.

References:
- https://www.fao.org/contact-us/terms/
- https://www.fao.org/contact-us/terms/db-terms-of-use/en
- https://www.fao.org/hih-geospatial-platform/faqs/
- https://worldcereal.github.io/worldcereal-documentation/rdm/explore.html


## First live run (2026-11-23)

Workflow: [Egypt reference data discovery run #1](https://github.com/abdelrahmanelharouny/CropTwist/actions/runs/45157390222). The public RDM API returned zero public collections and zero Egypt/locality matches. All eight Africa archives for 2018–2025 were downloaded successfully, size/checksum validated, and scanned; 63 archive members were enumerated and the initial top-level metadata scan found no Egypt/locality text matches. A manual nested-ZIP review subsequently found two Egypt collections in the 2019 archive: 2019_egy_faowapor1_poly_111 (900 observations) and 2019_egy_faowapor2_poly_111 (634 observations), both from FAO WAPOR field data Egypt 2019 and declaring CC_BY in their metadata. The report and downloaded archive bundle are retained in artifact ID `14808543228` until 2026-12-23.

This is a bounded negative discovery result, not proof that no Egyptian features are embedded in any geometry or unindexed field. Review actual data attributes and spatial coverage before closing the source. No WorldCereal Egypt collection is approved for training from this run.


## Nested-archive finding and scanner correction

The first scan enumerated outer archive members but did not inspect the ZIP files nested inside Africa archives. Manual review of the 2019 Africa archive found:
- 2019_egy_faowapor1_poly_111 — 900 field-registered polygon observations, date 2019-08-05, declared CC_BY.
- 2019_egy_faowapor2_poly_111 — 634 field-registered polygon observations, dates 2019-03-14 to 2019-03-28, declared CC_BY.

The scanner is being updated to inspect nested collection ZIP names and their metadata workbooks. Treat the above as a manual discovery from the retained archive bundle until the corrected workflow artifact confirms the automated report. Both collections are research candidates, not yet training-approved: verify rights, parse GeoParquet attributes/geometries, check duplicate/overlapping fields, and construct spatial-temporal grouped splits.
