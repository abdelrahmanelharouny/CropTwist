"""Strict dataset validation and spatial-temporal holdout helpers for crop history."""
from __future__ import annotations

import math
from typing import Any

EMBEDDING_DIM = 128
ALLOWED_LABEL_SOURCES = frozenset({
    "verified_farmer_record",
    "official_statistics",
    "curated_reference",
})


def validate_training_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("training dataset is empty")
    required = {
        "field_id", "farm_group_id", "region_id", "season_year",
        "crop_code", "label_source", "label_license", "valid_pixel_coverage",
    }
    seen: set[tuple[str, int]] = set()
    regions: set[str] = set()
    classes: set[str] = set()
    for index, row in enumerate(rows):
        missing = required - set(row)
        if missing:
            raise ValueError(f"row {index} is missing required metadata: {sorted(missing)}")
        for key in ("field_id", "farm_group_id", "region_id", "crop_code", "label_license"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError(f"row {index} has empty {key}")
        if row["label_source"] not in ALLOWED_LABEL_SOURCES:
            raise ValueError(f"row {index} has an unapproved label source")
        year = int(row["season_year"])
        key = (row["field_id"], year)
        if key in seen:
            raise ValueError("duplicate field-season records are not allowed")
        seen.add(key)
        coverage = float(row["valid_pixel_coverage"])
        if not math.isfinite(coverage) or not 0.2 <= coverage <= 1.0:
            raise ValueError("valid_pixel_coverage must be finite and between 0.2 and 1.0")
        embedding = row.get("embedding")
        if not isinstance(embedding, (list, tuple)) or len(embedding) != EMBEDDING_DIM:
            raise ValueError(f"row {index} must contain a {EMBEDDING_DIM}-D Presto embedding")
        if any(not math.isfinite(float(value)) for value in embedding):
            raise ValueError(f"row {index} contains non-finite embedding values")
        regions.add(row["region_id"])
        classes.add(row["crop_code"])
    if len(regions) < 3:
        raise ValueError("at least three independent regions are required for spatial holdout")
    if len(classes) < 3:
        raise ValueError("at least three crop classes are required for multiclass evaluation")


def spatial_temporal_holdout(
    rows: list[dict[str, Any]],
    *,
    held_out_region: str,
    target_year: int,
) -> tuple[list[int], list[int]]:
    """Train on earlier seasons outside one region; test on that region in target year."""
    train_indices = [
        i for i, row in enumerate(rows)
        if row["region_id"] != held_out_region and int(row["season_year"]) < target_year
    ]
    test_indices = [
        i for i, row in enumerate(rows)
        if row["region_id"] == held_out_region and int(row["season_year"]) == target_year
    ]
    if not train_indices or not test_indices:
        raise ValueError("spatiotemporal holdout has an empty train or test partition")
    train_farms = {rows[i]["farm_group_id"] for i in train_indices}
    test_farms = {rows[i]["farm_group_id"] for i in test_indices}
    if train_farms & test_farms:
        raise ValueError("farm groups overlap between spatial-temporal train and test")
    train_classes = {rows[i]["crop_code"] for i in train_indices}
    test_classes = {rows[i]["crop_code"] for i in test_indices}
    unseen = test_classes - train_classes
    if unseen:
        raise ValueError(f"test region contains crop classes absent from training: {sorted(unseen)}")
    return train_indices, test_indices
