"""Compare CropTwist/TorchGeo embeddings with NASA Harvest's original Presto API.

Run from mini-services/fieldshift-api after installing requirements-ml.txt and
checking out the upstream NASA Harvest Presto repository (pinned revision in
the report). This is an evidence-producing command, not an automatic approval.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

from app.intelligence.crop_history.contracts import CropHistoryRecord
from app.intelligence.crop_history.presto import encode_records, load_pretrained
from app.intelligence.crop_history.presto_inputs import build_presto_input


def _load_records(path: Path, limit: int) -> list[CropHistoryRecord]:
    records: list[CropHistoryRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(CropHistoryRecord.model_validate(json.loads(line)))
            except Exception as exc:
                raise ValueError(f"invalid CropHistoryRecord at line {line_number}: {type(exc).__name__}") from None
            if len(records) > limit:
                raise ValueError(f"parity input exceeds --max-records={limit}")
    if not records:
        raise ValueError("parity input contains no records")
    return records


def _load_upstream_encoder(upstream_repo: Path, device: str) -> Any:
    repo = upstream_repo.resolve()
    if not (repo / "presto" / "__init__.py").is_file():
        raise ValueError("--upstream-repo must be a checkout of github.com/nasaharvest/presto")
    sys.path.insert(0, str(repo))
    try:
        from presto import Presto
    except Exception as exc:
        raise RuntimeError(
            "could not import the original NASA Harvest Presto package; install its pinned requirements"
        ) from exc
    model = Presto.load_pretrained()
    encoder = model.encoder.to(device)
    encoder.eval()
    return encoder


def _reference_embedding(encoder: Any, record: CropHistoryRecord, device: str) -> np.ndarray:
    item = build_presto_input(record)
    x = torch.from_numpy(item["x"]).to(device)
    mask = torch.from_numpy(item["mask"]).to(device)
    dynamic_world = torch.from_numpy(item["dynamic_world"]).long().to(device)
    latlons = torch.from_numpy(item["latlons"]).to(device)
    with torch.inference_mode():
        # This is the original upstream public eval-task pooling contract:
        # mask tokens, prepend lat/lon, run transformer, mean-pool, LayerNorm.
        result = encoder(
            x=x,
            dynamic_world=dynamic_world,
            latlons=latlons,
            mask=mask,
            month=item["month"],
            eval_task=True,
        )
    vector = result.detach().cpu().float().numpy().reshape(-1)
    if vector.shape != (128,) or not np.isfinite(vector).all():
        raise RuntimeError("upstream Presto returned an invalid 128-D embedding")
    return vector


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, help="JSONL of validated CropHistoryRecord objects")
    parser.add_argument("--upstream-repo", type=Path, required=True, help="local NASA Harvest Presto source checkout")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--max-records", type=int, default=64)
    parser.add_argument("--atol", type=float, default=1e-5)
    parser.add_argument("--rtol", type=float, default=1e-4)
    parser.add_argument("--output", type=Path, default=Path("presto-parity-report.json"))
    args = parser.parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA requested but unavailable")
    if not (0 < args.atol <= 1e-2 and 0 < args.rtol <= 1e-2):
        raise SystemExit("tolerances must be positive and no greater than 1e-2")
    records = _load_records(args.records, args.max_records)
    reference = _load_upstream_encoder(args.upstream_repo, args.device)
    candidate = load_pretrained(device=args.device)
    candidate_vectors = np.asarray(
        encode_records(records, bundle=candidate, batch_size=1), dtype=np.float64
    )
    rows = []
    for record, candidate_vector in zip(records, candidate_vectors, strict=True):
        reference_vector = _reference_embedding(reference, record, args.device).astype(np.float64)
        delta = np.abs(candidate_vector - reference_vector)
        max_abs = float(delta.max())
        mean_abs = float(delta.mean())
        cosine = _cosine(candidate_vector, reference_vector)
        passed = bool(np.allclose(candidate_vector, reference_vector, atol=args.atol, rtol=args.rtol))
        rows.append({
            "field_id": record.field_id,
            "season_start": record.season_start.isoformat(),
            "max_absolute_error": max_abs,
            "mean_absolute_error": mean_abs,
            "cosine_similarity": cosine,
            "allclose": passed,
        })
    report = {
        "status": "passed" if all(row["allclose"] for row in rows) else "failed",
        "reference": "NASA Harvest original Presto package: Presto.load_pretrained().encoder(eval_task=True)",
        "candidate": "TorchGeo Presto_Weights.PRESTO + CropTwist custom valid-token pooling",
        "input_schema": "presto-17ch-12m-v1",
        "record_count": len(rows),
        "device": args.device,
        "atol": args.atol,
        "rtol": args.rtol,
        "torch_version": torch.__version__,
        "numpy_version": np.__version__,
        "rows": rows,
        "limitations": [
            "This compares model inference on already-built inputs; it does not validate satellite ingestion or monthly compositing.",
            "Run on a reviewed set containing complete and partially masked modality patterns.",
            "Archive the upstream git commit, TorchGeo version, checkpoint hashes and this report with the release evidence.",
        ],
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, indent=2))
    print(f"report: {args.output}")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
