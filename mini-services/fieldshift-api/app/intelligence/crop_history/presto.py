"""Lazy loader for NASA Harvest Presto's pretrained remote-sensing encoder.

The API worker does not import TorchGeo or download weights at startup. ML
workers opt in by installing requirements-ml.txt and calling load_pretrained.
The loader returns the original model so callers use the upstream documented
forward contract rather than a locally reimplemented approximation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PrestoModelBundle:
    encoder: Any
    pool_norm: Any
    model_id: str = "torchgeo/presto:PRESTO"
    weights_id: str = "Presto_Weights.PRESTO"


def load_pretrained(*, device: str = "cpu") -> PrestoModelBundle:
    """Load official pretrained weights lazily and fail with an actionable error."""
    try:
        from torchgeo.models import Presto_Weights, presto
    except ImportError as exc:
        raise RuntimeError(
            "Presto inference dependencies are optional; install requirements-ml.txt"
        ) from exc
    import copy
    import torch

    model = presto(weights=Presto_Weights.PRESTO)
    model = model.to(device)
    model.eval()
    # Reproduce upstream Presto eval_task=True pooling: average unnormalized
    # valid tokens, then apply LayerNorm once to the pooled vector.
    encoder = copy.deepcopy(model.encoder)
    pool_norm = copy.deepcopy(model.encoder.norm)
    encoder.norm = torch.nn.Identity()
    encoder.eval()
    pool_norm.eval()
    del model  # discard unused decoder and original encoder to keep ML-worker RAM bounded
    return PrestoModelBundle(encoder=encoder, pool_norm=pool_norm)


def model_card() -> dict[str, str]:
    """Machine-readable attribution and model constraints."""
    return {
        "model": "NASA Harvest Presto via TorchGeo",
        "weights": "torchgeo/presto (Presto_Weights.PRESTO)",
        "upstream": "https://github.com/nasaharvest/presto",
        "paper": "https://arxiv.org/abs/2304.14065",
        "license": "MIT",
        "intended_use": "remote-sensing time-series representation learning",
        "warning": "Pretrained embeddings are not Egyptian crop labels or calibrated crop probabilities.",
    }

def encode_records(records: list[Any], *, bundle: PrestoModelBundle, batch_size: int = 32) -> list[list[float]]:
    """Generate pretrained 128-D pixel/field embeddings without training a head.

    This function intentionally returns embeddings only. It does not map them
    to crop classes or probabilities; that requires an independently labelled
    Egyptian training/evaluation set and a separately versioned classifier.
    """
    if not records or len(records) > 4096 or not 1 <= batch_size <= 128:
        raise ValueError("Presto inference batch is outside the supported bound")
    try:
        import numpy as np
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch is required in the optional ML worker") from exc
    from app.intelligence.crop_history.presto_inputs import build_presto_input

    prepared = [build_presto_input(record) for record in records]
    # TorchGeo's Presto encoder compacts masked tokens with a reshape, so every
    # sample in a tensor batch must have the same number of valid tokens.
    # Bucket by valid-token count before batching to avoid shape-dependent
    # failures when fields have different cloud/missing-modality patterns.
    from app.intelligence.crop_history.presto_inputs import PRESTO_BANDS

    groups = (
        ("S1", ("vv_db", "vh_db")),
        ("S2_RGB", ("b02_dn", "b03_dn", "b04_dn")),
        ("S2_Red_Edge", ("b05_dn", "b06_dn", "b07_dn")),
        ("S2_NIR_10m", ("b08_dn",)),
        ("S2_NIR_20m", ("b8a_dn",)),
        ("S2_SWIR", ("b11_dn", "b12_dn")),
        ("ERA5", ("temperature_2m_k", "total_precipitation_m")),
        ("NDVI", ("ndvi",)),
    )
    channel_index = {name: index for index, name in enumerate(PRESTO_BANDS)}
    ndvi_index = len(PRESTO_BANDS)
    buckets: dict[int, list[int]] = {}
    for index, item in enumerate(prepared):
        mask_array = item["mask"][0]
        valid_tokens = int((item["dynamic_world"][0] != 9).sum())
        for _, channels in groups:
            indices = [ndvi_index if name == "ndvi" else channel_index[name] for name in channels]
            valid_tokens += sum(1 for month_index in range(12) if not mask_array[month_index, indices].any())
        srtm_indices = [channel_index["elevation_m"], channel_index["slope_degrees"]]
        if not mask_array[0, srtm_indices].any():
            valid_tokens += 1
        buckets.setdefault(valid_tokens, []).append(index)

    outputs: list[list[float] | None] = [None] * len(prepared)
    device = next(bundle.encoder.parameters()).device
    for indices in buckets.values():
        for start in range(0, len(indices), batch_size):
            batch_indices = indices[start : start + batch_size]
            batch = [prepared[index] for index in batch_indices]
            x = torch.from_numpy(np.concatenate([item["x"] for item in batch], axis=0)).to(device)
            mask = torch.from_numpy(np.concatenate([item["mask"] for item in batch], axis=0)).to(device)
            dynamic_world = torch.from_numpy(
                np.concatenate([item["dynamic_world"] for item in batch], axis=0)
            ).long().to(device)
            latlons = torch.from_numpy(
                np.concatenate([item["latlons"] for item in batch], axis=0)
            ).to(device)
            months = torch.tensor([item["month"] for item in batch], dtype=torch.long, device=device)
            with torch.inference_mode():
                tokens, _, _ = bundle.encoder(
                    x=x,
                    dynamic_world=dynamic_world,
                    latlons=latlons,
                    mask=mask,
                    month=months,
                )
                embeddings = bundle.pool_norm(tokens.mean(dim=1))
            if embeddings.ndim != 2 or embeddings.shape[0] != len(batch) or embeddings.shape[1] != 128:
                raise RuntimeError("Presto encoder returned an invalid embedding shape")
            values = embeddings.detach().cpu().float().numpy()
            if not np.isfinite(values).all():
                raise RuntimeError("Presto encoder returned non-finite embeddings")
            for original_index, vector in zip(batch_indices, values, strict=True):
                outputs[original_index] = vector.tolist()
    if any(vector is None for vector in outputs):
        raise RuntimeError("Presto inference omitted one or more input records")
    return [vector for vector in outputs if vector is not None]
