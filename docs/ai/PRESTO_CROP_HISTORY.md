# M1-B — Presto crop-history model integration

## Encoder choice

The initial encoder is NASA Harvest Presto, loaded through TorchGeo 0.10.1's
MIT-licensed `Presto_Weights.PRESTO` checkpoint. Model weights are fetched only
when an offline/ML worker explicitly calls `load_pretrained()`; the API image
does not install PyTorch or TorchGeo.

- Upstream: https://github.com/nasaharvest/presto
- TorchGeo API: https://docs.torchgeo.org/en/stable/api/models/presto.html
- Checkpoint repository: https://huggingface.co/torchgeo/presto
- Paper: https://arxiv.org/abs/2304.14065

## Input contract implemented

The adapter prepares one 12-month sequence per field with the upstream 17
channels, in order:

1. Sentinel-1 VV/VH in dB
2. Sentinel-2 B2/B3/B4/B5/B6/B7/B8/B8A/B11/B12 as scaled integer reflectance DN (not physical 0–1 reflectance)
3. ERA5 2 m temperature in Kelvin and total precipitation in metres
4. SRTM elevation in metres and slope in degrees
5. NDVI derived from B8 and B4

Normalization follows the upstream Presto pipeline: S1 dB shift/divide 25;
Sentinel-2 reflectance DN divide by 10,000; ERA5 temperature shift -272.15 and
divide by 35; precipitation divide by 0.03; SRTM elevation divide by 2,000;
slope divide by 50. Missing observations are zero-filled only alongside an
explicit per-channel mask. Dynamic World class 9 means unavailable. SRTM is
represented as the single static token expected by the encoder.

The input field names carry units (`vv_db`, `b04_dn`, `temperature_2m_k`, `total_precipitation_m`, `elevation_m`, `slope_degrees`) to prevent mixing already-scaled reflectance with raw DN. The field centroid is required and passed as latitude/longitude. Inputs outside
the 12-month sequence, invalid channel names, inconsistent static SRTM values,
or records with no usable modality fail closed.

## Inference behavior

The loader uses TorchGeo's pretrained encoder and reconstructs the original
Presto downstream pooling contract: average unnormalized valid tokens, then
apply the encoder LayerNorm once. TorchGeo's encoder compacts masked tokens and
requires equal valid-token counts within a tensor batch, so inference buckets
records by valid-token count before batching.

The output is a 128-D representation only. It is not a crop label, probability,
or confidence score. A crop classifier head is deliberately not shipped until
the FAO Egypt 2023–2024 reference layers, class legend, license and spatial
independence of labels are verified.

## Remaining model gates

- Add the complete Sentinel-2 band mapping (B05/B06/B07/B8A/B12) and Sentinel-1 VV/VH
  ingestion paths, plus SRTM elevation/slope and monthly ERA5 aggregation.
- Verify FAO Egypt reference label exports, class definitions and license.
- Train CatBoost/linear heads on Presto embeddings; compare Galileo Nano and
  OlmoEarth features only under identical spatial/temporal holdouts.
- Evaluate leave-one-area-out (Zankalon / Sidi Ghazi / Mallawi) and temporal
  holdout; report macro-F1, balanced accuracy, per-class metrics, calibration,
  coverage and abstention. No random neighbouring-pixel split.
- Benchmark CPU latency/memory and export to ONNX only after numerical parity
  against the upstream PyTorch encoder is demonstrated.

## Crop classifier evaluation harness

Once verified labels and Presto embeddings are assembled into a CSV with
`field_id`, `farm_group_id`, `region_id`, `season_year`, `crop_code`,
`label_source`, `label_source_verified`, `label_license`,\n`label_license_verified`, `valid_pixel_coverage`, `embedding_model`,\n`input_schema_version` and
`embedding_0..embedding_127`, run:

```bash
python scripts/train_crop_history_classifier.py ./egypt-presto-embeddings.csv
```

The script uses CatBoost on CPU and evaluates a strict leave-one-region-out
plus latest-season holdout. It requires explicitly verified label source/license flags, disjoint farm groups, class-complete
training and calibration partitions, and source/license metadata for every
label. Temperature scaling is fitted only on farm-disjoint calibration groups.
The report includes macro-F1, balanced accuracy, multiclass Brier score, ECE,
per-class F1 and abstention coverage/selective accuracy at a fixed 0.60
confidence threshold.

The script is an evaluation harness only: it does not save or promote a
production classifier. A fold blocked for missing classes or insufficient
independent farms is reported as blocked; it is never replaced by a random
pixel split.
## End-to-end embedding export

The export command accepts one validated `CropHistoryRecord` JSON object per
line. Labelled records must include a region, valid-pixel coverage, explicitly
verified label source and license. Install the optional ML dependencies, then
run from `mini-services/fieldshift-api`:

```bash
pip install -r requirements-ml.txt
python scripts/export_presto_embeddings.py ./crop-history.jsonl ./presto-embeddings.csv
python scripts/train_crop_history_classifier.py ./presto-embeddings.csv
```

The export is CPU-only, records the exact checkpoint and input-schema version,
and never writes raw field observations into the classifier CSV. It fails
closed for missing labels, license/source verification, region metadata or
coverage. The CatBoost stage then applies the spatial-temporal holdout and
calibration gates described above.
