#!/usr/bin/env python3
"""Compare CropTwist's TorchGeo Presto embeddings with NASA Harvest's original encoder.

Run in an environment with the optional ML dependencies installed and a local
clone of https://github.com/nasaharvest/presto available. The JSON fixture is
an array of CropHistoryRecord objects containing the same verified monthly
inputs for both implementations. No synthetic observations are generated.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
from importlib import metadata
import json
import math
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import torch


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(path: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="JSON array of validated CropHistoryRecord payloads")
    parser.add_argument("--presto-repo", type=Path, required=True, help="Local NASA Harvest presto repository clone")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--atol", type=float, default=1e-4)
    parser.add_argument("--rtol", type=float, default=1e-4)
    parser.add_argument("--report", type=Path, default=Path("artifacts/presto-parity-report.json"))
    args = parser.parse_args()

    repo = args.presto_repo.resolve()
    if not (repo / "presto" / "presto.py").is_file() or not (repo / "data" / "default_model.pt").is_file():
        parser.error("--presto-repo must contain presto/presto.py and data/default_model.pt")
    if not args.records.is_file():
        parser.error("--records file does not exist")
    if not (args.device == "cpu" or args.device.startswith("cuda")):
        parser.error("--device must be cpu or cuda[:index]")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        parser.error("CUDA requested but unavailable")

    api_root = Path(__file__).resolve().parents[1] / "mini-services" / "fieldshift-api"
    sys.path.insert(0, str(api_root))
    # The original NASA package is imported by its own source tree, not TorchGeo.
    sys.path.insert(0, str(repo))
    from app.intelligence.crop_history.contracts import CropHistoryRecord
    from app.intelligence.crop_history.presto import encode_records, load_pretrained
    from app.intelligence.crop_history.presto_inputs import build_presto_input

    original_module = importlib.import_module("presto")
    original_model = original_module.Presto.load_pretrained().to(args.device).eval()
    original_encoder = original_model.encoder.eval()
    torchgeo_bundle = load_pretrained(device=args.device)

    payload = json.loads(args.records.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        parser.error("--records must contain a non-empty JSON array")
    if len(payload) > 256:
        parser.error("parity fixtures are bounded to 256 records")

    records = [CropHistoryRecord.model_validate(row) for row in payload]
    prepared = [build_presto_input(record) for record in records]
    torchgeo_embeddings = encode_records(records, bundle=torchgeo_bundle, batch_size=args.batch_size)

    comparisons: list[dict[str, Any]] = []
    all_passed = True
    for index, (record, item, torchgeo_vector) in enumerate(zip(records, prepared, torchgeo_embeddings, strict=True)):
        x = torch.from_numpy(item["x"]).to(args.device)
        mask = torch.from_numpy(item["mask"]).to(args.device)
        dynamic_world = torch.from_numpy(item["dynamic_world"]).long().to(args.device)
        latlons = torch.from_numpy(item["latlons"]).to(args.device)
        month = torch.tensor([item["month"]], dtype=torch.long, device=args.device)
        with torch.inference_mode():
            reference = original_encoder(
                x=x,
                dynamic_world=dynamic_world,
                latlons=latlons,
                mask=mask,
                month=month,
                eval_task=True,
            ).detach().float().cpu().numpy()[0]
        candidate = np.asarray(torchgeo_vector, dtype=np.float32)
        if reference.shape != (128,) or candidate.shape != (128,):
            raise RuntimeError(f"record {index} returned unexpected shapes {reference.shape} and {candidate.shape}")
        delta = np.abs(reference - candidate)
        denominator = float(np.linalg.norm(reference) * np.linalg.norm(candidate))
        cosine = float(np.dot(reference, candidate) / denominator) if denominator > 0 else float("nan")
        passed = bool(np.allclose(reference, candidate, atol=args.atol, rtol=args.rtol))
        all_passed = all_passed and passed
        comparisons.append({
            "record_index": index,
            "field_id": record.field_id,
            "season_start": record.season_start.isoformat(),
            "max_abs_error": float(delta.max()),
            "mean_abs_error": float(delta.mean()),
            "cosine_similarity": cosine,
            "allclose": passed,
        })

    weights = repo / "data" / "default_model.pt"
    report = {
        "status": "passed" if all_passed else "failed",
        "reference": "NASA Harvest original Presto.load_pretrained().encoder(eval_task=True)",
        "candidate": "CropTwist TorchGeo adapter",
        "upstream_repo_revision": git_revision(repo),
        "upstream_weights_sha256": sha256_file(weights),
        "torch_version": torch.__version__,
        "torchgeo_version": metadata.version("torchgeo"),
        "device": args.device,
        "record_count": len(records),
        "embedding_dimension": 128,
        "atol": args.atol,
        "rtol": args.rtol,
        "records": comparisons,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if all_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
