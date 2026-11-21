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

1. Sentinel-1 VV, VH
2. Sentinel-2 B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12
3. ERA5 2 m temperature and total precipitation
4. SRTM elevation and slope
5. NDVI derived from B8 and B4

Normalization follows the upstream Presto pipeline: S1 shift/divide 25;
Sentinel-2 reflectance divide by 10,000; ERA5 temperature shift -272.15 and
divide by 35; precipitation divide by 0.03; SRTM elevation divide by 2,000;
slope divide by 50. Missing observations are zero-filled only alongside an
explicit per-channel mask. Dynamic World class 9 means unavailable. SRTM is
represented as the single static token expected by the encoder.

The field centroid is required and passed as latitude/longitude. Inputs outside
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
