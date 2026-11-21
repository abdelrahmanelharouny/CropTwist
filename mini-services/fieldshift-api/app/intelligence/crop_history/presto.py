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
    model: Any
    encoder: Any
    model_id: str = "torchgeo/presto"
    weights_id: str = "Presto_Weights.PRESTO"


def load_pretrained(*, device: str = "cpu") -> PrestoModelBundle:
    """Load official pretrained weights lazily and fail with an actionable error."""
    try:
        from torchgeo.models import Presto_Weights, presto
    except ImportError as exc:
        raise RuntimeError(
            "Presto inference dependencies are optional; install requirements-ml.txt"
        ) from exc
    model = presto(weights=Presto_Weights.PRESTO)
    model = model.to(device)
    model.eval()
    encoder = model.encoder
    encoder.eval()
    return PrestoModelBundle(model=model, encoder=encoder)


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
