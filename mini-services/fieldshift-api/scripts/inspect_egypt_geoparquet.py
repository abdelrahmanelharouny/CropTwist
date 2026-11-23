"""Profile nested Egypt WorldCereal GeoParquet collections without training.

Run after discover_egypt_reference_data.py:
    python scripts/inspect_egypt_geoparquet.py --archives-dir egypt-reference-archives
"""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import shapely


def _display(value: Any) -> str:
    if value is None:
        return "<null>"
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _counts(values: list[Any], limit: int = 100) -> dict[str, Any]:
    counts = Counter(_display(value) for value in values)
    return {
        "unique_count": len(counts),
        "null_count": sum(count for key, count in counts.items() if key == "<null>"),
        "top_values": [{"value": key, "count": count} for key, count in counts.most_common(limit)],
    }


def _profile_geoparquet(data: bytes, collection_id: str, member_name: str) -> dict[str, Any]:
    table = pq.read_table(io.BytesIO(data))
    schema_metadata = table.schema.metadata or {}
    raw_geo = schema_metadata.get(b"geo")
    if raw_geo is None:
        raise ValueError("GeoParquet metadata key 'geo' is missing")
    geo = json.loads(raw_geo.decode("utf-8"))
    geometry_column = geo.get("primary_column", "geometry")
    if geometry_column not in table.column_names:
        raise ValueError(f"primary geometry column {geometry_column!r} is absent")

    values = table.to_pydict()
    raw_geometries = values[geometry_column]
    geometries = []
    parse_errors = 0
    for raw in raw_geometries:
        if raw is None:
            geometries.append(None)
            continue
        try:
            geometries.append(shapely.from_wkb(raw))
        except Exception:
            parse_errors += 1
            geometries.append(None)

    non_null = [geom for geom in geometries if geom is not None]
    valid = sum(bool(shapely.is_valid(geom)) for geom in non_null)
    empty = sum(bool(shapely.is_empty(geom)) for geom in non_null)
    bounds = None
    if non_null:
        bound_rows = [shapely.bounds(geom).tolist() for geom in non_null if not shapely.is_empty(geom)]
        if bound_rows:
            bounds = [
                min(row[0] for row in bound_rows),
                min(row[1] for row in bound_rows),
                max(row[2] for row in bound_rows),
                max(row[3] for row in bound_rows),
            ]

    excluded = {geometry_column}
    attributes = {name: vals for name, vals in values.items() if name not in excluded}
    label_candidates = [
        name for name in attributes
        if name.lower() in {"ct", "crop", "crop_type", "crop_type_code", "cropclass", "crop_class"}
    ]
    id_candidates = [
        name for name in attributes
        if name.lower() in {"sampleid", "field_id", "fieldid", "block_id", "parcel_id", "farm_id"}
    ]
    temporal_candidates = [
        name for name in attributes
        if any(token in name.lower() for token in ("date", "validity", "time", "year", "month"))
    ]

    return {
        "collection_id": collection_id,
        "member": member_name,
        "row_count": table.num_rows,
        "columns": table.column_names,
        "geometry_column": geometry_column,
        "geo_metadata": geo,
        "geometry": {
            "non_null_count": len(non_null),
            "parse_error_count": parse_errors,
            "valid_count": valid,
            "invalid_count": len(non_null) - valid,
            "empty_count": empty,
            "bounds_wgs84_or_declared_crs": bounds,
        },
        "label_distributions": {name: _counts(attributes[name]) for name in label_candidates},
        "identifier_uniqueness": {name: _counts(attributes[name]) for name in id_candidates},
        "temporal_fields": {name: _counts(attributes[name], limit=30) for name in temporal_candidates},
        "null_counts": {
            name: sum(value is None for value in vals)
            for name, vals in attributes.items()
        },
    }


def inspect_archives(archives_dir: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "running",
        "scope": "Nested Egypt collection GeoParquet files only; profile is not training approval.",
        "collections": [],
        "errors": [],
    }
    for archive_path in sorted(archives_dir.glob("WorldCereal_ReferenceData_*_Africa_*.zip")):
        try:
            with zipfile.ZipFile(archive_path) as outer:
                for nested_info in outer.infolist():
                    nested_name = Path(nested_info.filename).name
                    if nested_info.is_dir() or not nested_name.lower().endswith(".zip") or "_egy_" not in nested_name.lower():
                        continue
                    with zipfile.ZipFile(io.BytesIO(outer.read(nested_info))) as collection:
                        geoparquet_members = [
                            info for info in collection.infolist()
                            if not info.is_dir() and info.filename.lower().endswith(".geoparquet")
                        ]
                        for info in geoparquet_members:
                            report["collections"].append(
                                _profile_geoparquet(
                                    collection.read(info),
                                    nested_name.removesuffix(".zip"),
                                    f"{archive_path.name}!/{nested_name}!/{info.filename}",
                                )
                            )
        except Exception as exc:
            report["errors"].append({
                "archive": archive_path.name,
                "error": f"{type(exc).__name__}: {exc}",
            })
    report["status"] = "completed" if report["collections"] and not report["errors"] else "partial_failure"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("egypt-geoparquet-profile.json"))
    args = parser.parse_args()
    report = inspect_archives(args.archives_dir)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "collections": len(report["collections"]),
        "rows": sum(item["row_count"] for item in report["collections"]),
        "errors": report["errors"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
