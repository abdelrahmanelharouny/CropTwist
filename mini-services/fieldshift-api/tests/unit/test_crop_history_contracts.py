from datetime import date

import pytest
from pydantic import ValidationError

from app.intelligence.crop_history.contracts import (
    CropHistoryRecord,
    MonthlyCropFeatures,
    split_group_ids,
)


def _record(farm: str, field: str = "field-1") -> CropHistoryRecord:
    return CropHistoryRecord(
        field_id=field,
        farm_group_id=farm,
        country_code="EGY",
        geometry_hash="0123456789abcdef",
        season_start=date(2025, 1, 1),
        season_end=date(2025, 12, 31),
        label_crop_code="WHEAT",
        label_source="verified_farmer_record",
        label_source_verified=True,
        label_license="CC BY-SA 4.0",
        label_license_verified=True,
        label_confidence=0.95,
        months=[MonthlyCropFeatures(month=1, year=2025, values={"ndvi": 0.4}, valid_observation_count=2)],
    )


def test_month_with_no_valid_pixels_cannot_claim_values():
    with pytest.raises(ValidationError):
        MonthlyCropFeatures(month=1, year=2025, values={"ndvi": 0.5}, valid_observation_count=0)


def test_unlabelled_record_cannot_have_confidence():
    with pytest.raises(ValidationError):
        CropHistoryRecord(
            field_id="f", farm_group_id="farm", country_code="EGY",
            geometry_hash="0123456789abcdef",
            season_start=date(2025, 1, 1), season_end=date(2025, 12, 31),
            label_confidence=0.9,
            months=[MonthlyCropFeatures(month=1, year=2025, values={}, valid_observation_count=0)],
        )


def test_split_is_farm_level_deterministic_and_disjoint():
    records = [_record(f"farm-{i}", f"field-{i}") for i in range(10)]
    first = split_group_ids(records)
    second = split_group_ids(list(reversed(records)))
    assert first == second
    assert set(first["train"]).isdisjoint(first["validation"])
    assert set(first["train"]).isdisjoint(first["test"])
    assert set(first["validation"]).isdisjoint(first["test"])


def test_split_requires_independent_farm_groups():
    with pytest.raises(ValueError, match="three independent farm groups"):
        split_group_ids([_record("same"), _record("same", "field-2")])

def test_labelled_record_requires_verified_source_and_license():
    with pytest.raises(ValidationError, match="verified source and license"):
        CropHistoryRecord(
            field_id="f", farm_group_id="farm", country_code="EGY",
            geometry_hash="0123456789abcdef",
            season_start=date(2025, 1, 1), season_end=date(2025, 12, 31),
            label_crop_code="WHEAT", label_source="verified_farmer_record",
            months=[MonthlyCropFeatures(month=1, year=2025, values={}, valid_observation_count=0)],
        )


def test_farm_split_seed_changes_assignment_without_changing_group_membership():
    records = [_record(f"farm-{i}", f"field-{i}") for i in range(20)]
    first = split_group_ids(records, seed=11)
    same = split_group_ids(list(reversed(records)), seed=11)
    alternate = split_group_ids(records, seed=12)
    assert first == same
    assert first != alternate
    assert set(first["train"] + first["validation"] + first["test"]) == {
        record.farm_group_id for record in records
    }



@pytest.mark.parametrize("bad_value", [True, "30.1", float("nan"), float("inf"), 10**10000])
def test_record_centroid_and_coverage_reject_coerced_or_non_finite_values(bad_value):
    with pytest.raises(ValidationError):
        CropHistoryRecord(
            field_id="f",
            farm_group_id="farm",
            country_code="EGY",
            geometry_hash="0123456789abcdef",
            centroid_lat=bad_value,
            centroid_lon=31.2,
            valid_pixel_coverage=0.8,
            season_start=date(2025, 1, 1),
            season_end=date(2025, 12, 31),
            months=[MonthlyCropFeatures(month=1, year=2025, values={}, valid_observation_count=0)],
        )
    with pytest.raises(ValidationError):
        CropHistoryRecord(
            field_id="f",
            farm_group_id="farm",
            country_code="EGY",
            geometry_hash="0123456789abcdef",
            centroid_lat=30.1,
            centroid_lon=31.2,
            valid_pixel_coverage=bad_value,
            season_start=date(2025, 1, 1),
            season_end=date(2025, 12, 31),
            months=[MonthlyCropFeatures(month=1, year=2025, values={}, valid_observation_count=0)],
        )


@pytest.mark.parametrize("bad_value", [True, "0.4", float("nan"), float("inf"), 10**10000])
def test_monthly_feature_maps_reject_coerced_or_non_finite_values(bad_value):
    with pytest.raises(ValidationError):
        MonthlyCropFeatures(
            month=1,
            year=2025,
            values={"ndvi": bad_value},
            valid_observation_count=1,
        )
    with pytest.raises(ValidationError):
        MonthlyCropFeatures(
            month=1,
            year=2025,
            values={},
            presto_bands={"b04_dn": bad_value},
            valid_observation_count=1,
        )


def test_dynamic_world_class_rejects_boolean_and_numeric_string():
    for bad_value in (True, "4", 4.0):
        with pytest.raises(ValidationError):
            MonthlyCropFeatures(
                month=1,
                year=2025,
                values={},
                valid_observation_count=1,
                dynamic_world_class=bad_value,
            )
