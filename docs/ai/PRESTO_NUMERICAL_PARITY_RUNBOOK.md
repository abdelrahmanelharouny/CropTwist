## Upstream numerical parity command

A parity harness now exists at `scripts/verify_presto_numerical_parity.py`. It runs both implementations on the exact same already-normalized `CropHistoryRecord` tensors:
- Reference: NASA Harvest's original `Presto.load_pretrained().encoder(eval_task=True)`.
- Candidate: TorchGeo `Presto_Weights.PRESTO` plus CropTwist's custom token pooling.

Prepare a separate upstream checkout and install it using its own documented setup (the original package includes `data/default_model.pt` for `Presto.load_pretrained()`):

```bash
git clone https://github.com/nasaharvest/presto.git /opt/nasaharvest-presto
git -C /opt/nasaharvest-presto rev-parse HEAD
pip install -e /opt/nasaharvest-presto
pip install -r requirements-ml.txt
python scripts/verify_presto_numerical_parity.py ./reviewed-parity-records.jsonl \
  --upstream-repo /opt/nasaharvest-presto \
  --device cpu \
  --output ./presto-parity-report.json
```

Use a reviewed, non-sensitive input file with complete and partially masked modalities, distinct months and coordinates. Record the upstream commit and checkpoint hash beside the report. The default `atol=1e-5` and `rtol=1e-4` are initial strict numerical tolerances; if they fail, investigate implementation/checkpoint differences rather than widening tolerances to force a pass. The harness is not yet executed, and no parity claim is made.
