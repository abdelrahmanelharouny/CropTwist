from datetime import date
import csv

import pytest

from app.intelligence.crop_history.contracts import CropHistoryRecord, MonthlyCropFeatures
from scripts import export_presto_embeddings as encoder


def _record(index: int, region: str, crop: str) -> CropHistoryRecord:
    return CropHistoryRecord(
        field_id=f"field-{index}",
        farm_group_id=f"farm-{index}",
        country_code="EGY",
        geometry_hash=f"{index:016x}0123456789abcdef",
        region_id=region,
        valid_pixel_coverage=0.85,
        season_start=date(2025, 1, 1),
        season_end=date(2025, 12, 31),
        label_crop_code=crop,
        label_source="verified_farmer_record",
        label_source_verified=True,
        label_license="CC BY-SA 4.0",
        label_license_verified=True,
        label_confidence=0.95,
        months=[MonthlyCropFeatures(
            month=1,
            year=2025,
            values={"ndvi": 0.4},
            valid_observation_count=1,
        )],
    )


def test_encoder_builds_only_verified_egypt_training_rows(monkeypatch):
    records = [
        _record(0, "north", "WHEAT"),
        _record(1, "north", "CLOVER"),
        _record(2, "north", "MAIZE"),
        _record(3, "delta", "WHEAT"),
        _record(4, "delta", "CLOVER"),
        _record(5, "delta", "MAIZE"),
        _record(6, "south", "WHEAT"),
        _record(7, "south", "CLOVER"),
        _record(8, "south", "MAIZE"),
    ]
    monkeypatch.setattr(
        encoder,
        "encode_records",
        lambda batch, bundle, batch_size: [[float(index)] * 128 for index, _ in enumerate(batch)],
    )
    rows = encoder.encode_training_rows(
        records, bundle=type("Bundle", (), {"model_id": "torchgeo/presto:PRESTO"})(), batch_size=3
    )
    assert len(rows) == len(records)
    assert rows[0]["embedding_model"] == "torchgeo/presto:PRESTO"
    assert len(rows[0]["embedding"]) == 128
    assert rows[0]["label_source_verified"] is True
    assert len({row["region_id"] for row in rows}) == 3


def test_encoder_refuses_unverified_labels_before_model_inference(monkeypatch):
    record = _record(0, "north", "WHEAT")
    record.label_license_verified = False
    monkeypatch.setattr(
        encoder,
        "encode_records",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("model must not run")),
    )
    with pytest.raises(ValueError, match="verified crop label and license"):
        encoder.encode_training_rows(
            [record], bundle=type("Bundle", (), {"model_id": "torchgeo/presto:PRESTO"})()
        )


def test_training_csv_has_explicit_model_schema_and_embedding_columns(tmp_path):
    rows = [{
        "field_id": "field-1",
        "farm_group_id": "farm-1",
        "region_id": "north",
        "country_code": "EGY",
        "geometry_hash": "0123456789abcdef",
        "season_year": 2025,
        "crop_code": "WHEAT",
        "label_source": "verified_farmer_record",
        "label_source_verified": True,
        "label_license": "CC BY-SA 4.0",
        "label_license_verified": True,
        "valid_pixel_coverage": 0.85,
        "embedding_model": "torchgeo/presto:PRESTO",
        "input_schema_version": "presto-17ch-12m-v1",
        "embedding": [0.25] * 128,
    }]
    output = tmp_path / "nested" / "training.csv"
    encoder.write_training_csv(rows, output)
    with output.open(newline="", encoding="utf-8") as handle:
        saved = next(csv.DictReader(handle))
    assert saved["embedding_model"] == "torchgeo/presto:PRESTO"
    assert saved["input_schema_version"] == "presto-17ch-12m-v1"
    assert float(saved["embedding_127"]) == pytest.approx(0.25)



@pytest.mark.parametrize("bad_batch_size", [True, 1.5, "4", 0, 129])
def test_encoder_rejects_non_integer_or_out_of_range_batch_sizes(bad_batch_size):
    with pytest.raises(ValueError, match="batch size"):
        encoder.encode_training_rows(
            [_record(0, "north", "WHEAT")],
            bundle=type("Bundle", (), {"model_id": "torchgeo/presto:PRESTO"})(),
            batch_size=bad_batch_size,
        )
