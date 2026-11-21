from datetime import date

import numpy as np
import pytest

from app.intelligence.crop_history.contracts import CropHistoryRecord, MonthlyCropFeatures
from app.intelligence.crop_history.presto_inputs import (
    DYNAMIC_WORLD_MISSING,
    PRESTO_CHANNELS,
    build_presto_input,
)
from app.intelligence.crop_history.presto import _count_valid_encoder_tokens


def _record():
    return CropHistoryRecord(
        field_id="field-1",
        farm_group_id="farm-1",
        country_code="EGY",
        geometry_hash="0123456789abcdef",
        centroid_lat=30.1,
        centroid_lon=31.2,
        season_start=date(2025, 1, 1),
        season_end=date(2025, 12, 31),
        months=[
            MonthlyCropFeatures(
                month=1,
                year=2025,
                values={"ndvi": 0.2},
                valid_observation_count=1,
                presto_bands={
                    "vv_db": -10.0, "vh_db": -20.0,
                    "b02_dn": 1000.0, "b03_dn": 2000.0, "b04_dn": 5000.0,
                    "b05_dn": 5500.0, "b06_dn": 6000.0, "b07_dn": 6500.0,
                    "b08_dn": 7000.0, "b8a_dn": 7100.0, "b11_dn": 3000.0, "b12_dn": 2500.0,
                    "temperature_2m_k": 300.0, "total_precipitation_m": 0.03,
                    "elevation_m": 100.0, "slope_degrees": 5.0,
                },
                dynamic_world_class=4,
            )
        ],
    )


def test_presto_input_uses_upstream_17_channel_order_and_normalization():
    result = build_presto_input(_record())
    x = result["x"]
    mask = result["mask"]
    assert x.shape == (1, 12, 17)
    assert mask.shape == x.shape
    assert result["channels"] == PRESTO_CHANNELS
    assert x[0, 0, 0] == pytest.approx(0.6)  # VV: (value + 25) / 25
    assert x[0, 0, 2] == pytest.approx(0.1)  # B02: reflectance / 10000
    assert x[0, 0, 16] == pytest.approx(1 / 6, abs=1e-5)
    assert mask[0, 0, 16] == 0
    assert mask[0, 1, :].all()  # missing month is explicitly masked
    assert result["dynamic_world"][0, 0] == 4
    assert result["dynamic_world"][0, 1] == DYNAMIC_WORLD_MISSING
    assert result["latlons"][0, 0] == pytest.approx(30.1)
    assert result["latlons"][0, 1] == pytest.approx(31.2)
    assert result["month"] == 0


def test_presto_input_requires_verified_centroid():
    record = _record()
    record.centroid_lat = None
    with pytest.raises(ValueError, match="verified field centroid"):
        build_presto_input(record)


def test_presto_input_rejects_changing_static_elevation():
    record = _record()
    second = MonthlyCropFeatures(
        month=2, year=2025, values={}, valid_observation_count=1,
        presto_bands={"elevation_m": 150.0, "slope_degrees": 5.0},
    )
    record.months.append(second)
    with pytest.raises(ValueError, match="static Presto channel elevation_m"):
        build_presto_input(record)


def test_presto_input_refuses_records_outside_12_month_window():
    record = _record()
    record.months.append(
        MonthlyCropFeatures(month=2, year=2026, values={}, valid_observation_count=0)
    )
    with pytest.raises(ValueError, match="12-month Presto window"):
        build_presto_input(record)

def test_presto_input_rejects_physical_reflectance_in_dn_field():
    record = _record()
    record.months[0].presto_bands["b04_dn"] = 0.35
    with pytest.raises(ValueError, match="raw scaled DN"):
        build_presto_input(record)


@pytest.mark.parametrize("band,value", [("vv_db", -50.1), ("vv_db", 1.1), ("vh_db", -50.1), ("vh_db", 1.1)])
def test_presto_input_rejects_sentinel1_values_outside_upstream_normalization_range(band, value):
    record = _record()
    record.months[0].presto_bands[band] = value
    with pytest.raises(ValueError, match="outside its expected source-unit range"):
        build_presto_input(record)

@pytest.mark.parametrize(
    "latitude, longitude",
    [(float("nan"), 31.2), (30.1, float("inf")), (91.0, 31.2), (30.1, 181.0), (True, 31.2)],
)
def test_presto_input_rejects_invalid_field_centroids(latitude, longitude):
    record = _record()
    record.centroid_lat = latitude
    record.centroid_lon = longitude
    with pytest.raises(ValueError, match="finite verified field centroid"):
        build_presto_input(record)


def test_presto_input_rejects_duplicate_month_records():
    record = _record()
    record.months.append(record.months[0].model_copy(deep=True))
    with pytest.raises(ValueError, match="months must be unique"):
        build_presto_input(record)


@pytest.mark.parametrize("dynamic_class", [-1, 9, 10, True, 4.5])
def test_presto_input_rejects_invalid_dynamic_world_classes(dynamic_class):
    record = _record()
    record.months[0].dynamic_world_class = dynamic_class
    with pytest.raises(ValueError, match="Dynamic World class"):
        build_presto_input(record)


def test_presto_input_rejects_overflowing_raw_band_values():
    record = _record()
    record.months[0].presto_bands["b04_dn"] = 10**10000
    with pytest.raises(ValueError, match="finite numeric data"):
        build_presto_input(record)


def test_presto_valid_token_count_matches_all_present_band_groups():
    prepared = build_presto_input(_record())
    # 8 EO groups (including derived NDVI), one Dynamic World token and
    # one static SRTM token; the encoder adds its separate lat/lon token.
    assert _count_valid_encoder_tokens(prepared) == 10


def test_presto_valid_token_count_excludes_missing_groups_and_dynamic_world():
    record = _record()
    record.months = [
        MonthlyCropFeatures(
            month=1,
            year=2025,
            values={},
            valid_observation_count=1,
            presto_bands={"vv_db": -10.0, "vh_db": -20.0},
            dynamic_world_class=None,
        )
    ]
    prepared = build_presto_input(record)
    assert _count_valid_encoder_tokens(prepared) == 1
