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


def _is_finite_numeric(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def validate_training_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("training dataset is empty")
    required = {
        "field_id", "farm_group_id", "region_id", "season_year",
        "crop_code", "label_source", "label_source_verified", "label_license", "label_license_verified", "valid_pixel_coverage", "embedding_model", "input_schema_version",
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
        if row["label_source"] not in ALLOWED_LABEL_SOURCES or row["label_source_verified"] is not True:
            raise ValueError(f"row {index} has an unverified or unapproved label source")
        if row["label_license_verified"] is not True:
            raise ValueError(f"row {index} has an unverified label license")
        if row["embedding_model"] != "torchgeo/presto:PRESTO":
            raise ValueError(f"row {index} uses an unsupported or mixed embedding model")
        if row["input_schema_version"] != "presto-17ch-12m-v1":
            raise ValueError(f"row {index} uses an unsupported Presto input schema")
        if isinstance(row["season_year"], bool) or not isinstance(row["season_year"], int):
            raise ValueError("season_year must be an integer year")
        year = row["season_year"]
        if not 2000 <= year <= 2100:
            raise ValueError("season_year is outside the supported range")
        key = (row["field_id"], year)
        if key in seen:
            raise ValueError("duplicate field-season records are not allowed")
        seen.add(key)
        raw_coverage = row["valid_pixel_coverage"]
        if not _is_finite_numeric(raw_coverage):
            raise ValueError("valid_pixel_coverage must be numeric, finite, and not boolean")
        coverage = float(raw_coverage)
        if not math.isfinite(coverage) or not 0.2 <= coverage <= 1.0:
            raise ValueError("valid_pixel_coverage must be finite and between 0.2 and 1.0")
        embedding = row.get("embedding")
        if not isinstance(embedding, (list, tuple)) or len(embedding) != EMBEDDING_DIM:
            raise ValueError(f"row {index} must contain a {EMBEDDING_DIM}-D Presto embedding")
        if any(not _is_finite_numeric(value) for value in embedding):
            raise ValueError(f"row {index} contains non-finite or non-numeric embedding values")
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
    if isinstance(target_year, bool) or not isinstance(target_year, int) or not 2000 <= target_year <= 2100:
        raise ValueError("target_year must be an integer year in the supported range")
    if not isinstance(held_out_region, str) or not held_out_region.strip():
        raise ValueError("held_out_region must be a non-empty region identifier")
    for index, row in enumerate(rows):
        year = row.get("season_year") if isinstance(row, dict) else None
        if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
            raise ValueError(f"row {index} season_year must be an integer year in the supported range")
    train_indices = [
        i for i, row in enumerate(rows)
        if row["region_id"] != held_out_region and row["season_year"] < target_year
    ]
    test_indices = [
        i for i, row in enumerate(rows)
        if row["region_id"] == held_out_region and row["season_year"] == target_year
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
