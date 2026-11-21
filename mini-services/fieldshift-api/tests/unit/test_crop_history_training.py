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
