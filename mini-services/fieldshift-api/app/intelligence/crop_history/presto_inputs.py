"""Prepare validated monthly crop records for the upstream Presto encoder.

Presto expects the exact 17-channel order and normalization used by NASA
Harvest. Missing modalities are represented by zero-filled values PLUS a
mask; zero is never used as an unmarked substitute for missing data.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from app.intelligence.crop_history.contracts import CropHistoryRecord

PRESTO_BANDS = (
    "vv_db", "vh_db",
    "b02_dn", "b03_dn", "b04_dn", "b05_dn", "b06_dn", "b07_dn", "b08_dn", "b8a_dn", "b11_dn", "b12_dn",
    "temperature_2m_k", "total_precipitation_m",
    "elevation_m", "slope_degrees",
)
PRESTO_CHANNELS = PRESTO_BANDS + ("ndvi",)
DYNAMIC_WORLD_MISSING = 9


def _month_sequence(start: date, count: int = 12) -> list[tuple[int, int]]:
    result = []
    year, month = start.year, start.month
    for _ in range(count):
        result.append((year, month))
        month += 1
        if month == 13:
            month = 1
            year += 1
    return result


def build_presto_input(record: CropHistoryRecord) -> dict[str, Any]:
    """Return one 12-month Presto batch, masks, Dynamic World and lat/lon."""
    if record.centroid_lat is None or record.centroid_lon is None:
        raise ValueError("Presto input requires a verified field centroid")
    month_keys = _month_sequence(record.season_start, 12)
    if record.season_end < record.season_start or (record.season_end.year, record.season_end.month) not in set(month_keys):
        raise ValueError("season date range must fit within the 12-month Presto window")
    by_month = {(item.year, item.month): item for item in record.months}
    outside = [key for key in by_month if key not in set(month_keys)]
    if outside:
        raise ValueError("crop-history months must fall within the 12-month Presto window")

    x = np.zeros((12, len(PRESTO_CHANNELS)), dtype=np.float32)
    mask = np.ones((12, len(PRESTO_CHANNELS)), dtype=np.float32)
    dynamic_world = np.full((12,), DYNAMIC_WORLD_MISSING, dtype=np.int64)

    # Raw upstream channels and exact NASA Harvest normalization constants.
    for timestep, key in enumerate(month_keys):
        month = by_month.get(key)
        raw = month.presto_bands if month else {}
        for channel_index, name in enumerate(PRESTO_BANDS):
            value = raw.get(name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
                raise ValueError(f"Presto input channel {name} must be finite numeric data")
            if name in ("vv_db", "vh_db"):
                normalized = (float(value) + 25.0) / 25.0
            elif name in ("b02_dn", "b03_dn", "b04_dn", "b05_dn", "b06_dn", "b07_dn", "b08_dn", "b8a_dn", "b11_dn", "b12_dn"):
                normalized = float(value) / 10000.0
            elif name == "temperature_2m_k":
                normalized = (float(value) - 272.15) / 35.0
            elif name == "total_precipitation_m":
                normalized = float(value) / 0.03
            elif name == "elevation_m":
                normalized = float(value) / 2000.0
            else:  # slope_degrees
                normalized = float(value) / 50.0
            x[timestep, channel_index] = normalized
            mask[timestep, channel_index] = 0.0
        if month and month.dynamic_world_class is not None:
            dynamic_world[timestep] = month.dynamic_world_class

        # NDVI is derived only when both reflectance inputs are present.
        red_index = PRESTO_BANDS.index("b04_dn")
        nir_index = PRESTO_BANDS.index("b08_dn")
        ndvi_index = len(PRESTO_BANDS)
        if mask[timestep, red_index] == 0 and mask[timestep, nir_index] == 0:
            red, nir = x[timestep, red_index], x[timestep, nir_index]
            denominator = nir + red
            if denominator > 0:
                x[timestep, ndvi_index] = (nir - red) / denominator
                mask[timestep, ndvi_index] = 0.0

    # SRTM is static. The upstream encoder consumes only the first temporal token.
    for name in ("elevation_m", "slope_degrees"):
        index = PRESTO_BANDS.index(name)
        valid_values = [x[t, index] for t in range(12) if mask[t, index] == 0]
        if valid_values:
            if max(valid_values) - min(valid_values) > 1e-5:
                raise ValueError(f"static Presto channel {name} changes within a season")
            x[0, index] = valid_values[0]
            mask[0, index] = 0.0
            x[1:, index] = 0.0
            mask[1:, index] = 1.0

    if np.all(mask == 1.0) and np.all(dynamic_world == DYNAMIC_WORLD_MISSING):
        raise ValueError("Presto input contains no valid observations")
    return {
        "x": x[None, :, :],
        "mask": mask[None, :, :],
        "dynamic_world": dynamic_world[None, :],
        "latlons": np.asarray([[record.centroid_lat, record.centroid_lon]], dtype=np.float32),
        "month": record.season_start.month - 1,
        "channels": PRESTO_CHANNELS,
        "missing_dynamic_world_class": DYNAMIC_WORLD_MISSING,
    }
