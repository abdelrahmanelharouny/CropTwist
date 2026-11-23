"""Build a leakage-aware candidate manifest from the 2019 Egypt field labels.

This produces metadata only. It does not approve labels, assign train/test splits,
or create model features. The license remains unverified until FAO item terms
and attribution are archived.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


GENERIC_EWOC_CODES = frozenset({"1000000000", "1100000000", "6000000000", "7000000000"})


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        a, b = self.find(left), self.find(right)
        if a == b:
            return
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1


def is_crop_specific_ewoc(value: Any) -> bool:
    code = str(value).strip() if value is not None else ""
    return bool(code) and code not in GENERIC_EWOC_CODES


def stable_group_id(sample_ids: list[str]) -> str:
    digest = hashlib.sha256("|".join(sorted(sample_ids)).encode("utf-8")).hexdigest()
    return f"eg19-{digest[:16]}"


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def build_manifest(archives_dir: Path) -> dict[str, Any]:
    import pyarrow.parquet as pq
    import shapely

    rows: list[dict[str, Any]] = []
    geometries = []
    for archive_path in sorted(archives_dir.glob("WorldCereal_ReferenceData_*_Africa_*.zip")):
        with zipfile.ZipFile(archive_path) as outer:
            for nested_info in outer.infolist():
                collection_name = Path(nested_info.filename).name
                if nested_info.is_dir() or not collection_name.lower().endswith(".zip") or "_egy_" not in collection_name.lower():
                    continue
                collection_id = collection_name.removesuffix(".zip")
                with zipfile.ZipFile(io.BytesIO(outer.read(nested_info))) as collection:
                    for info in collection.infolist():
                        if info.is_dir() or not info.filename.lower().endswith(".geoparquet"):
                            continue
                        table = pq.read_table(io.BytesIO(collection.read(info)))
                        values = table.to_pydict()
                        geo = json.loads((table.schema.metadata or {})[b"geo"].decode("utf-8"))
                        geometry_column = geo.get("primary_column", "geometry")
                        for index, raw_wkb in enumerate(values[geometry_column]):
                            geometry = shapely.from_wkb(raw_wkb)
                            if geometry is None or geometry.is_empty or not bool(shapely.is_valid(geometry)):
                                raise ValueError(f"Invalid geometry in {collection_id} row {index}")
                            sample_id = str(values.get("sampleID", values.get("sample_id"))[index])
                            ewoc = str(values.get("ewoc_code", values.get("CT"))[index])
                            centroid = shapely.centroid(geometry)
                            normalized_wkb = shapely.to_wkb(shapely.normalize(geometry))
                            raw_attributes = {
                                name: _json_value(column[index])
                                for name, column in values.items()
                                if name != geometry_column
                            }
                            rows.append({
                                "collection_id": collection_id,
                                "sample_id": sample_id,
                                "ewoc_code": ewoc,
                                "crop_specific": is_crop_specific_ewoc(ewoc),
                                "label_status": "candidate" if is_crop_specific_ewoc(ewoc) else "excluded_generic",
                                "label_source": "curated_reference",
                                "label_license": "CC_BY",
                                "label_license_verified": False,
                                "region_id": "EGY_WAPOR_2019_FIELD_SURVEY_AREA",
                                "centroid_lat": float(centroid.y),
                                "centroid_lon": float(centroid.x),
                                "geometry_hash": hashlib.sha256(normalized_wkb).hexdigest(),
                                "geometry_wkb_hex": normalized_wkb.hex(),
                                "raw_attributes": raw_attributes,
                            })
                            geometries.append(geometry)

    if not rows:
        raise ValueError("No Egypt GeoParquet records found in downloaded Africa archives")

    uf = UnionFind(len(rows))
    grouping_reasons: dict[int, set[str]] = defaultdict(set)
    indexes_by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        attrs = row["raw_attributes"]
        h3 = attrs.get("h3_best_res_cell")
        if h3 not in (None, ""):
            indexes_by_key[("h3_best_res_cell", str(h3))].append(index)
        field_id = attrs.get("Field_ID")
        if field_id not in (None, ""):
            indexes_by_key[(f"Field_ID:{row['collection_id']}", str(field_id))].append(index)
        block_id = attrs.get("Block_ID")
        if block_id not in (None, ""):
            indexes_by_key[(f"Block_ID:{row['collection_id']}", str(block_id))].append(index)
    for (key_type, _), indexes in indexes_by_key.items():
        for index in indexes[1:]:
            uf.union(indexes[0], index)
            grouping_reasons[indexes[0]].add(key_type.split(":")[0])

    tree = shapely.STRtree(geometries)
    pairs = tree.query(geometries, predicate="intersects")
    spatial_pairs = 0
    for left, right in zip(pairs[0].tolist(), pairs[1].tolist()):
        if left >= right:
            continue
        intersection = shapely.intersection(geometries[left], geometries[right])
        if shapely.is_empty(intersection) or float(shapely.area(intersection)) <= 0:
            continue
        uf.union(left, right)
        grouping_reasons[left].add("positive_area_polygon_intersection")
        spatial_pairs += 1

    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(rows)):
        components[uf.find(index)].append(index)

    for members in components.values():
        group_id = stable_group_id([rows[index]["sample_id"] for index in members])
        reasons = sorted({
            reason
            for index in members
            for reason in grouping_reasons.get(index, set())
        })
        for index in members:
            rows[index]["spatial_group_id"] = group_id
            rows[index]["spatial_group_reasons"] = reasons or ["single_record_no_shared_key_detected"]

    class_counts = Counter(row["ewoc_code"] for row in rows if row["crop_specific"])
    group_class_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        if row["crop_specific"]:
            group_class_counts[row["spatial_group_id"]][row["ewoc_code"]] += 1

    return {
        "status": "candidate_only",
        "source": "WorldCereal 2019 Africa archive; nested FAO-WaPOR Egypt field collections",
        "total_rows": len(rows),
        "crop_specific_rows": sum(row["crop_specific"] for row in rows),
        "generic_or_non_crop_rows": sum(not row["crop_specific"] for row in rows),
        "spatial_group_count": len(components),
        "positive_area_intersection_pairs": spatial_pairs,
        "crop_class_counts": dict(sorted(class_counts.items())),
        "group_class_counts": {
            group: dict(sorted(counts.items()))
            for group, counts in sorted(group_class_counts.items())
        },
        "training_ready": False,
        "training_blockers": [
            "FAO source rights and attribution are not verified; metadata license-reference field is blank.",
            "Monthly Sentinel/ERA5/SRTM features have not been ingested for these polygons.",
            "The two collections cover one broad survey area and do not satisfy the three-independent-region evaluation gate.",
            "Generic EWOC codes are excluded from crop labels; rare classes need a reviewed taxonomy/aggregation policy.",
            "Spatially intersecting observations are grouped to prevent split leakage; missing field identifiers remain unresolved.",
            "Presto numerical parity against NASA Harvest has not been executed.",
        ],
        "records": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("egypt-candidate-manifest.json"))
    args = parser.parse_args()
    report = build_manifest(args.archives_dir)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "total_rows": report["total_rows"],
        "crop_specific_rows": report["crop_specific_rows"],
        "generic_or_non_crop_rows": report["generic_or_non_crop_rows"],
        "spatial_group_count": report["spatial_group_count"],
        "positive_area_intersection_pairs": report["positive_area_intersection_pairs"],
        "training_ready": report["training_ready"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
