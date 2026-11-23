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

FAO's general website terms permit reuse for private study, research, teaching and non-commercial products/services with attribution; translation, adaptation, resale and other commercial reuse require a permission request. FAO statistical-database terms separately impose restrictions against use to promote a commercial enterprise, even where CC BY 4.0 is the default license. Third-party data may carry different terms. Therefore, the FAO Egypt map is **not approved for CropTwist commercial training or redistribution** until the exact linked item metadata and data-owner terms are obtained and any necessary written permission is archived.

References:
- https://www.fao.org/contact-us/terms/
- https://www.fao.org/contact-us/terms/db-terms-of-use/en
- https://www.fao.org/hih-geospatial-platform/faqs/
- https://worldcereal.github.io/worldcereal-documentation/rdm/explore.html
