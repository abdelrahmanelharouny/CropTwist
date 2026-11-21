"""Validated monthly Earth-observation records for crop-history modelling.

This module deliberately validates evidence and split keys only. It does not
claim a crop prediction until a trained, versioned model is loaded and evaluated.
"""
from __future__ import annotations

from datetime import date
from random import Random
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CropCode = str
FeatureName = Literal["ndvi", "evi", "ndmi", "ndwi", "vv_db", "vh_db", "rainfall_mm", "temperature_c"]


class MonthlyCropFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)
    values: dict[FeatureName, float | None]
    valid_observation_count: int = Field(ge=0, le=10000)
    presto_bands: dict[str, float | None] = Field(default_factory=dict)
    dynamic_world_class: int | None = Field(default=None, ge=0, le=8)
    source_scene_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def require_evidence_for_values(self) -> "MonthlyCropFeatures":
        allowed_presto_bands = {
            "vv_db", "vh_db", "b02_dn", "b03_dn", "b04_dn", "b05_dn", "b06_dn", "b07_dn",
            "b08_dn", "b8a_dn", "b11_dn", "b12_dn", "temperature_2m_k",
            "total_precipitation_m", "elevation_m", "slope_degrees",
        }
        if set(self.presto_bands) - allowed_presto_bands:
            raise ValueError("unknown Presto input band")
        if self.valid_observation_count == 0 and (
            any(value is not None for value in self.values.values())
            or any(value is not None for value in self.presto_bands.values())
            or self.dynamic_world_class is not None
        ):
            raise ValueError("a month without valid observations cannot contain feature values")
        if any(
            value is not None and not (-1e6 <= value <= 1e6)
            for value in [*self.values.values(), *self.presto_bands.values()]
        ):
            raise ValueError("feature value is outside the supported numeric bound")
        return self


class CropHistoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(min_length=1, max_length=80)
    farm_group_id: str = Field(min_length=1, max_length=80)
    country_code: str = Field(min_length=2, max_length=3)
    geometry_hash: str = Field(min_length=16, max_length=128)
    centroid_lat: float | None = Field(default=None, ge=-90, le=90)
    centroid_lon: float | None = Field(default=None, ge=-180, le=180)
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
        if (self.centroid_lat is None) != (self.centroid_lon is None):
            raise ValueError("field centroid latitude and longitude must be supplied together")
        if (self.label_crop_code is None) != (self.label_source is None):
            raise ValueError("crop label and its source must be supplied together")
        if self.label_crop_code is None and self.label_confidence is not None:
            raise ValueError("unlabelled records cannot carry label confidence")
        keys = [(item.year, item.month) for item in self.months]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate monthly observations are not allowed")
        return self


def split_group_ids(records: list[CropHistoryRecord], *, seed: int = 42) -> dict[str, list[str]]:
    """Return reproducible farm-level splits without lexical/geographic ordering bias.

    Farms, not fields or images, are the split unit. A seeded shuffle makes the
    result independent of input order and avoids assigning adjacent/lexically
    similar farm identifiers to the same split. Persist this manifest with each run.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("split seed must be an integer")
    groups = sorted({record.farm_group_id for record in records})
    if len(groups) < 3:
        raise ValueError("at least three independent farm groups are required")
    Random(seed).shuffle(groups)
    train_end = max(1, int(len(groups) * 0.60))
    validation_end = max(train_end + 1, int(len(groups) * 0.80))
    validation_end = min(validation_end, len(groups) - 1)
    return {
        "train": sorted(groups[:train_end]),
        "validation": sorted(groups[train_end:validation_end]),
        "test": sorted(groups[validation_end:]),
    }
