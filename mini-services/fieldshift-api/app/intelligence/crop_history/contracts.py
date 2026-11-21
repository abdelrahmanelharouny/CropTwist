"""Validated monthly Earth-observation records for crop-history modelling.

This module deliberately validates evidence and split keys only. It does not
claim a crop prediction until a trained, versioned model is loaded and evaluated.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CropCode = str
FeatureName = Literal["ndvi", "evi", "ndmi", "ndwi", "vv", "vh", "rainfall_mm", "temperature_c"]


class MonthlyCropFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)
    values: dict[FeatureName, float | None]
    valid_observation_count: int = Field(ge=0, le=10000)
    source_scene_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def require_evidence_for_values(self) -> "MonthlyCropFeatures":
        if self.valid_observation_count == 0 and any(value is not None for value in self.values.values()):
            raise ValueError("a month without valid observations cannot contain feature values")
        if any(value is not None and not (-1e6 <= value <= 1e6) for value in self.values.values()):
            raise ValueError("feature value is outside the supported numeric bound")
        return self


class CropHistoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(min_length=1, max_length=80)
    farm_group_id: str = Field(min_length=1, max_length=80)
    country_code: str = Field(min_length=2, max_length=3)
    geometry_hash: str = Field(min_length=16, max_length=128)
    season_start: date
    season_end: date
    label_crop_code: str | None = Field(default=None, max_length=40)
    label_source: Literal["verified_farmer_record", "official_statistics", "curated_reference"] | None = None
    label_confidence: float | None = Field(default=None, ge=0, le=1)
    months: list[MonthlyCropFeatures] = Field(min_length=1, max_length=36)

    @model_validator(mode="after")
    def validate_label_and_months(self) -> "CropHistoryRecord":
        if self.season_end < self.season_start:
            raise ValueError("season_end must not precede season_start")
        if (self.label_crop_code is None) != (self.label_source is None):
            raise ValueError("crop label and its source must be supplied together")
        if self.label_crop_code is None and self.label_confidence is not None:
            raise ValueError("unlabelled records cannot carry label confidence")
        keys = [(item.year, item.month) for item in self.months]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate monthly observations are not allowed")
        return self


def split_group_ids(records: list[CropHistoryRecord]) -> dict[str, list[str]]:
    """Return deterministic farm-level train/validation/test IDs.

    Grouping by farm, rather than field or image, prevents spatial leakage.
    A minimum of three distinct farm groups is required for a three-way split.
    """
    groups = sorted({record.farm_group_id for record in records})
    if len(groups) < 3:
        raise ValueError("at least three independent farm groups are required")
    train_end = max(1, int(len(groups) * 0.60))
    validation_end = max(train_end + 1, int(len(groups) * 0.80))
    validation_end = min(validation_end, len(groups) - 1)
    return {
        "train": groups[:train_end],
        "validation": groups[train_end:validation_end],
        "test": groups[validation_end:],
    }
