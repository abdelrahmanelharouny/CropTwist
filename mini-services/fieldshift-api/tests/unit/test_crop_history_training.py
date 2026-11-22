import pytest

from app.intelligence.crop_history.training import (
    spatial_temporal_holdout,
    validate_training_rows,
)


def _row(field, farm, region, year, crop):
    return {
        "field_id": field,
        "farm_group_id": farm,
        "region_id": region,
        "season_year": year,
        "crop_code": crop,
        "label_source": "verified_farmer_record",
        "label_source_verified": True,
        "label_license": "CC BY-SA 4.0",
        "label_license_verified": True,
        "valid_pixel_coverage": 0.8,
        "embedding_model": "torchgeo/presto:PRESTO",
        "input_schema_version": "presto-17ch-12m-v1",
        "embedding": [0.1] * 128,
    }


def test_training_data_requires_source_license_and_presto_embedding():
    rows = [
        _row("f1", "farm1", "zankalon", 2023, "wheat"),
        _row("f2", "farm2", "sidi_ghazi", 2023, "maize"),
        _row("f3", "farm3", "mallawi", 2023, "clover"),
    ]
    validate_training_rows(rows)
    rows[0]["label_license"] = ""
    try:
        validate_training_rows(rows)
    except ValueError as exc:
        assert "label_license" in str(exc)
    else:
        raise AssertionError("missing label license must fail")


def test_spatiotemporal_holdout_keeps_region_year_and_farm_groups_disjoint():
    rows = [
        _row("f1", "farm1", "sidi_ghazi", 2023, "wheat"),
        _row("f2", "farm2", "mallawi", 2023, "maize"),
        _row("f3", "farm3", "zankalon", 2023, "clover"),
        _row("f4", "farm4", "zankalon", 2024, "wheat"),
    ]
    train, test = spatial_temporal_holdout(rows, held_out_region="zankalon", target_year=2024)
    assert train == [0, 1]
    assert test == [3]


def test_spatiotemporal_holdout_rejects_unseen_test_crop_class():
    rows = [
        _row("f1", "farm1", "sidi_ghazi", 2023, "wheat"),
        _row("f2", "farm2", "mallawi", 2023, "maize"),
        _row("f3", "farm3", "zankalon", 2024, "clover"),
    ]
    try:
        spatial_temporal_holdout(rows, held_out_region="zankalon", target_year=2024)
    except ValueError as exc:
        assert "absent from training" in str(exc)
    else:
        raise AssertionError("unseen crop classes must fail closed")

def test_training_data_blocks_unverified_label_provenance():
    rows = [
        _row("f1", "farm1", "zankalon", 2023, "wheat"),
        _row("f2", "farm2", "sidi_ghazi", 2023, "maize"),
        _row("f3", "farm3", "mallawi", 2023, "clover"),
    ]
    rows[0]["label_license_verified"] = False
    try:
        validate_training_rows(rows)
    except ValueError as exc:
        assert "unverified label license" in str(exc)
    else:
        raise AssertionError("unverified license must block training")



@pytest.mark.parametrize(
    "field,value,message",
    [
        ("season_year", "2023", "integer year"),
        ("season_year", 2023.5, "integer year"),
        ("valid_pixel_coverage", "0.8", "numeric, not boolean"),
        ("valid_pixel_coverage", True, "numeric, not boolean"),
    ],
)
def test_training_metadata_rejects_coerced_non_numeric_values(field, value, message):
    rows = [
        _row("f1", "farm1", "zankalon", 2023, "wheat"),
        _row("f2", "farm2", "sidi_ghazi", 2023, "maize"),
        _row("f3", "farm3", "mallawi", 2023, "clover"),
    ]
    rows[0][field] = value
    with pytest.raises(ValueError, match=message):
        validate_training_rows(rows)


def test_training_metadata_rejects_numeric_strings_in_embeddings():
    rows = [
        _row("f1", "farm1", "zankalon", 2023, "wheat"),
        _row("f2", "farm2", "sidi_ghazi", 2023, "maize"),
        _row("f3", "farm3", "mallawi", 2023, "clover"),
    ]
    rows[0]["embedding"][0] = "0.1"
    with pytest.raises(ValueError, match="non-finite or non-numeric"):
        validate_training_rows(rows)



def test_training_metadata_rejects_integer_values_that_overflow_float_conversion():
    rows = [
        _row("f1", "farm1", "zankalon", 2023, "wheat"),
        _row("f2", "farm2", "sidi_ghazi", 2023, "maize"),
        _row("f3", "farm3", "mallawi", 2023, "clover"),
    ]
    rows[0]["valid_pixel_coverage"] = 10**10000
    with pytest.raises(ValueError, match="numeric, not boolean, and finite"):
        validate_training_rows(rows)

    rows[0]["valid_pixel_coverage"] = 0.8
    rows[0]["embedding"][0] = 10**10000
    with pytest.raises(ValueError, match="non-finite or non-numeric"):
        validate_training_rows(rows)

@pytest.mark.parametrize("bad_year", ["2024", 2024.5, True])
def test_spatiotemporal_holdout_rejects_non_integer_season_years(bad_year):
    rows = [
        _row("f1", "farm1", "sidi_ghazi", 2023, "wheat"),
        _row("f2", "farm2", "mallawi", 2023, "maize"),
        _row("f3", "farm3", "zankalon", 2024, "clover"),
    ]
    rows[0]["season_year"] = bad_year
    with pytest.raises(ValueError, match="season_year must be an integer year"):
        spatial_temporal_holdout(rows, held_out_region="zankalon", target_year=2024)


def test_spatiotemporal_holdout_rejects_boolean_target_year():
    rows = [
        _row("f1", "farm1", "sidi_ghazi", 2023, "wheat"),
        _row("f2", "farm2", "mallawi", 2023, "maize"),
        _row("f3", "farm3", "zankalon", 2024, "clover"),
    ]
    with pytest.raises(ValueError, match="target_year must be an integer"):
        spatial_temporal_holdout(rows, held_out_region="zankalon", target_year=True)

def test_training_rows_reject_non_object_rows_and_malformed_label_source():
    with pytest.raises(ValueError, match="row 0 must be an object"):
        validate_training_rows([["not", "an", "object"]])

    row = _row("f1", "farm1", "north", 2023, "wheat")
    row["label_source"] = ["official_statistics"]
    rows = [
        row,
        _row("f2", "farm2", "south", 2023, "maize"),
        _row("f3", "farm3", "east", 2024, "clover"),
    ]
    with pytest.raises(ValueError, match="unverified or unapproved label source"):
        validate_training_rows(rows)


def test_spatiotemporal_holdout_rejects_missing_grouping_fields():
    rows = [
        _row("f1", "farm1", "north", 2023, "wheat"),
        _row("f2", "farm2", "south", 2023, "maize"),
        _row("f3", "farm3", "east", 2024, "clover"),
    ]
    del rows[0]["farm_group_id"]
    with pytest.raises(ValueError, match="farm_group_id must be a non-empty string"):
        spatial_temporal_holdout(rows, held_out_region="east", target_year=2024)



def test_training_metadata_rejects_finite_float64_embeddings_that_overflow_float32():
    rows = [
        _row("f1", "farm1", "zankalon", 2023, "wheat"),
        _row("f2", "farm2", "sidi_ghazi", 2023, "maize"),
        _row("f3", "farm3", "mallawi", 2023, "clover"),
    ]
    rows[0]["embedding"][0] = 1e300
    with pytest.raises(ValueError, match="float32-unrepresentable"):
        validate_training_rows(rows)
