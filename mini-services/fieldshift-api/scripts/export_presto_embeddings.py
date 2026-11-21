"""Export verified CropHistoryRecord JSONL into a Presto embedding CSV.

Run from mini-services/fieldshift-api after installing requirements-ml.txt:
    python scripts/export_presto_embeddings.py records.jsonl embeddings.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from app.intelligence.crop_history.contracts import CropHistoryRecord
from app.intelligence.crop_history.presto import encode_records, load_pretrained
from app.intelligence.crop_history.presto_inputs import PRESTO_INPUT_SCHEMA_VERSION
from app.intelligence.crop_history.training import validate_training_rows

EMBEDDING_DIMENSION = 128
CSV_FIELDS = [
    "field_id", "farm_group_id", "region_id", "country_code", "geometry_hash",
    "season_year", "crop_code", "label_source", "label_source_verified",
    "label_license", "label_license_verified", "valid_pixel_coverage",
    "embedding_model", "input_schema_version",
    *[f"embedding_{index}" for index in range(EMBEDDING_DIMENSION)],
]


def load_crop_history_jsonl(path: Path) -> list[CropHistoryRecord]:
    records: list[CropHistoryRecord] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = CropHistoryRecord.model_validate_json(line)
            except Exception as exc:
                raise ValueError(
                    f"invalid CropHistoryRecord at line {line_number}: {type(exc).__name__}"
                ) from None
            records.append(record)
            if len(records) > 4096:
                raise ValueError("input JSONL exceeds the 4096-record export bound")
    if not records:
        raise ValueError("input JSONL contains no crop-history records")
    return records


def _training_metadata(record: CropHistoryRecord, *, model_id: str) -> dict[str, Any]:
    if record.country_code.upper() != "EGY":
        raise ValueError(f"field {record.field_id} is not an Egyptian record")
    if not record.region_id or not record.region_id.strip():
        raise ValueError(f"field {record.field_id} is missing a verified region_id")
    if record.valid_pixel_coverage is None or not 0.2 <= record.valid_pixel_coverage <= 1.0:
        raise ValueError(f"field {record.field_id} has insufficient or missing valid-pixel coverage")
    if (
        not record.label_crop_code
        or not record.label_source
        or not record.label_source_verified
        or not record.label_license
        or not record.label_license_verified
    ):
        raise ValueError(f"field {record.field_id} lacks verified crop-label provenance")
    return {
        "field_id": record.field_id,
        "farm_group_id": record.farm_group_id,
        "region_id": record.region_id,
        "country_code": record.country_code.upper(),
        "geometry_hash": record.geometry_hash,
        "season_year": record.season_start.year,
        "crop_code": record.label_crop_code.strip().upper(),
        "label_source": record.label_source,
        "label_source_verified": True,
        "label_license": record.label_license,
        "label_license_verified": True,
        "valid_pixel_coverage": float(record.valid_pixel_coverage),
        "embedding_model": model_id,
        "input_schema_version": PRESTO_INPUT_SCHEMA_VERSION,
    }


def encode_training_rows(
    records: list[CropHistoryRecord],
    *,
    bundle: Any,
    batch_size: int = 16,
) -> list[dict[str, Any]]:
    if (
        not isinstance(records, list)
        or not records
        or len(records) > 4096
        or isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 128
    ):
        raise ValueError("Presto dataset size or batch size is outside the supported bound")
    field_ids = [record.field_id for record in records]
    if len(field_ids) != len(set(field_ids)):
        raise ValueError("training records contain duplicate field IDs")
    model_id = getattr(bundle, "model_id", None)
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("Presto model bundle is missing checkpoint identity")
    metadata = [_training_metadata(record, model_id=model_id) for record in records]
    rows: list[dict[str, Any]] = []
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        embeddings = encode_records(batch, bundle=bundle, batch_size=batch_size)
        if not isinstance(embeddings, list) or len(embeddings) != len(batch):
            raise ValueError("Presto returned an unexpected embedding count")
        for offset, embedding in enumerate(embeddings):
            values = [float(value) for value in embedding]
            if len(values) != EMBEDDING_DIMENSION or not all(math.isfinite(value) for value in values):
                raise ValueError("Presto returned an invalid 128-D embedding")
            row = dict(metadata[start + offset])
            row["embedding"] = values
            rows.append(row)
    validate_training_rows(rows)
    return rows


def write_training_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    **{
                        key: row[key]
                        for key in CSV_FIELDS
                        if not (key.startswith("embedding_") and key[len("embedding_"):].isdigit())
                    },
                    **{
                        f"embedding_{index}": row["embedding"][index]
                        for index in range(EMBEDDING_DIMENSION)
                    },
                })
        os.replace(temporary_name, output_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_jsonl", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    records = load_crop_history_jsonl(args.input_jsonl)
    bundle = load_pretrained(device=args.device)
    rows = encode_training_rows(records, bundle=bundle, batch_size=args.batch_size)
    write_training_csv(rows, args.output_csv)
    print(json.dumps({
        "status": "exported",
        "record_count": len(rows),
        "fields": len({row["field_id"] for row in rows}),
        "farms": len({row["farm_group_id"] for row in rows}),
        "regions": len({row["region_id"] for row in rows}),
        "crop_classes": sorted({row["crop_code"] for row in rows}),
        "embedding_dimension": EMBEDDING_DIMENSION,
        "embedding_model": bundle.model_id,
        "input_schema_version": PRESTO_INPUT_SCHEMA_VERSION,
        "output": str(args.output_csv),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
