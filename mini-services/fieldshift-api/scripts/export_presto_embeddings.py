"""Export verified CropHistoryRecord JSONL into a Presto embedding CSV.

Run from mini-services/fieldshift-api after installing requirements-ml.txt:
    python scripts/export_presto_embeddings.py records.jsonl embeddings.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app.intelligence.crop_history.contracts import CropHistoryRecord
from app.intelligence.crop_history.presto import encode_records, load_pretrained
from app.intelligence.crop_history.presto_inputs import PRESTO_INPUT_SCHEMA_VERSION


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_jsonl", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    records: list[CropHistoryRecord] = []
    with args.input_jsonl.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = CropHistoryRecord.model_validate(json.loads(line))
            if not record.region_id or record.valid_pixel_coverage is None:
                raise ValueError(f"record on line {line_number} needs region_id and valid_pixel_coverage")
            if (
                record.label_crop_code is None
                or not record.label_source_verified
                or not record.label_license
                or not record.label_license_verified
            ):
                raise ValueError(f"record on line {line_number} lacks verified crop-label provenance")
            records.append(record)

    if not records:
        raise ValueError("input JSONL contains no labelled crop-history records")
    bundle = load_pretrained(device="cpu")
    embeddings = encode_records(records, bundle=bundle, batch_size=args.batch_size)

    fields = [
        "field_id", "farm_group_id", "region_id", "country_code", "geometry_hash",
        "season_year", "crop_code", "label_source", "label_source_verified",
        "label_license", "label_license_verified", "valid_pixel_coverage",
        "embedding_model", "input_schema_version",
        *[f"embedding_{index}" for index in range(128)],
    ]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record, vector in zip(records, embeddings, strict=True):
            row = {
                "field_id": record.field_id,
                "farm_group_id": record.farm_group_id,
                "region_id": record.region_id,
                "country_code": record.country_code,
                "geometry_hash": record.geometry_hash,
                "season_year": record.season_start.year,
                "crop_code": record.label_crop_code,
                "label_source": record.label_source,
                "label_source_verified": str(record.label_source_verified).lower(),
                "label_license": record.label_license,
                "label_license_verified": str(record.label_license_verified).lower(),
                "valid_pixel_coverage": record.valid_pixel_coverage,
                "embedding_model": bundle.model_id,
                "input_schema_version": PRESTO_INPUT_SCHEMA_VERSION,
            }
            row.update({f"embedding_{index}": value for index, value in enumerate(vector)})
            writer.writerow(row)
    print(json.dumps({
        "status": "exported",
        "record_count": len(records),
        "embedding_dimension": 128,
        "embedding_model": bundle.model_id,
        "input_schema_version": PRESTO_INPUT_SCHEMA_VERSION,
        "output": str(args.output_csv),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
