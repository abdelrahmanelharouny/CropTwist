"""Discover Egypt-relevant public WorldCereal reference collections.

This is a discovery/audit tool, not a label-ingestion tool. It never marks a
collection as training-approved: every hit still needs item-level license,
provenance, geography, and quality review.

Run from mini-services/fieldshift-api:
    python scripts/discover_egypt_reference_data.py --download-africa-archives
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import httpx

RDM_COLLECTIONS_URL = "https://ewoc-rdm-api.iiasa.ac.at/collections"
ZENODO_RECORD_URL = "https://zenodo.org/api/records/18769612"
SEARCH_TERMS = (
    "egypt", "egyptian", "zankalon", "zankaloun", "sidi ghazi",
    "side ghazi", "mallawi", "minya", "sharqia", "kafr el sheikh",
)
MAX_RESPONSE_BYTES = 50 * 1024 * 1024
USER_AGENT = "CropTwist-Egypt-Reference-Discovery/1.0"


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).lower()


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _matching_records(payload: Any) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _walk_dicts(payload):
        serialized = _json_text(item)
        matched = [term for term in SEARCH_TERMS if term in serialized]
        if not matched:
            continue
        # Prefer objects that actually identify a collection or resource.
        if not any(key in item for key in ("id", "collection", "collection_id", "name", "title")):
            continue
        fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        hits.append({"matched_terms": matched, "record": item})
    return hits


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [
        "".join(node.itertext())
        for node in root.findall("x:si", ns)
    ]


def _scan_xlsx_bytes(data: bytes, source_name: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    from io import BytesIO

    with zipfile.ZipFile(BytesIO(data)) as book:
        shared = _read_shared_strings(book)
        for member in sorted(
            name for name in book.namelist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        ):
            root = ET.fromstring(book.read(member))
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for row in root.findall(".//x:sheetData/x:row", ns):
                cells: list[str] = []
                for cell in row.findall("x:c", ns):
                    value_node = cell.find("x:v", ns)
                    if value_node is None:
                        inline = cell.find("x:is", ns)
                        value = "".join(inline.itertext()) if inline is not None else ""
                    else:
                        value = value_node.text or ""
                        if cell.attrib.get("t") == "s":
                            try:
                                value = shared[int(value)]
                            except (ValueError, IndexError):
                                pass
                    cells.append(f"{cell.attrib.get('r', '')}={value}")
                joined = " | ".join(cells)
                lowered = joined.lower()
                matched = [term for term in SEARCH_TERMS if term in lowered]
                if matched:
                    hits.append({
                        "source_file": source_name,
                        "sheet": member,
                        "row": row.attrib.get("r"),
                        "matched_terms": matched,
                        "cells": cells,
                    })
    return hits


def _scan_archive(path: Path) -> dict[str, Any]:
    from io import BytesIO

    result: dict[str, Any] = {"archive": path.name, "members": [], "matches": []}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            result["members"].append({"name": name, "size": info.file_size})
            if info.file_size > 20 * 1024 * 1024:
                continue
            suffix = Path(name).suffix.lower()
            if suffix == ".xlsx":
                result["matches"].extend(_scan_xlsx_bytes(archive.read(name), name))
            elif suffix in {".csv", ".tsv", ".txt", ".json", ".xml"}:
                raw = archive.read(name)
                text = raw.decode("utf-8-sig", errors="replace")
                for line_number, line in enumerate(text.splitlines(), start=1):
                    lowered = line.lower()
                    matched = [term for term in SEARCH_TERMS if term in lowered]
                    if matched:
                        result["matches"].append({
                            "source_file": name,
                            "line": line_number,
                            "matched_terms": matched,
                            "text": line[:4000],
                        })
    return result


def _request_json(client: httpx.Client, url: str) -> Any:
    response = client.get(url, headers={"Accept": "application/json"})
    response.raise_for_status()
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ValueError(f"response exceeded {MAX_RESPONSE_BYTES} bytes: {url}")
    return response.json()


def _download_file(client: httpx.Client, file_info: dict[str, Any], output_dir: Path, max_bytes: int) -> Path:
    key = str(file_info.get("key", ""))
    url = str((file_info.get("links") or {}).get("self", ""))
    size = int(file_info.get("size") or 0)
    if not key.endswith(".zip") or not url.startswith("https://zenodo.org/"):
        raise ValueError("refusing unexpected Zenodo archive URL")
    if size <= 0 or size > max_bytes:
        raise ValueError(f"archive size is outside configured bound: {key} ({size} bytes)")
    response = client.get(url, headers={"Accept": "application/octet-stream"})
    response.raise_for_status()
    if len(response.content) != size:
        raise ValueError(f"download size mismatch for {key}")
    checksum = str(file_info.get("checksum") or "")
    if ":" in checksum:
        algorithm, expected = checksum.split(":", 1)
        if algorithm.lower() in {"md5", "sha256"}:
            digest = hashlib.new(algorithm.lower(), response.content).hexdigest()
            if digest.lower() != expected.lower():
                raise ValueError(f"{algorithm} checksum mismatch for {key}")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / Path(key).name
    target.write_bytes(response.content)
    return target


def discover(*, download_archives: bool, output_dir: Path, max_archive_mb: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "completed_with_findings",
        "rdm": {"url": RDM_COLLECTIONS_URL, "matches": [], "error": None},
        "zenodo": {"record_url": ZENODO_RECORD_URL, "africa_archives": [], "scans": [], "error": None},
        "decision": "Discovery only. No dataset is approved for training by this script.",
    }
    timeout = httpx.Timeout(60.0, connect=20.0)
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        try:
            rdm = _request_json(client, RDM_COLLECTIONS_URL)
            report["rdm"]["matches"] = _matching_records(rdm)
            report["rdm"]["collection_count"] = len(rdm) if isinstance(rdm, list) else None
        except Exception as exc:  # noqa: BLE001
            report["rdm"]["error"] = f"{type(exc).__name__}: {exc}"
        try:
            record = _request_json(client, ZENODO_RECORD_URL)
            files = record.get("files", []) if isinstance(record, dict) else []
            africa_files = [
                item for item in files
                if "africa" in str(item.get("key", "")).lower()
                and str(item.get("key", "")).lower().endswith(".zip")
            ]
            report["zenodo"]["africa_archives"] = [
                {"key": item.get("key"), "size": item.get("size"), "checksum": item.get("checksum")}
                for item in africa_files
            ]
            if download_archives:
                max_bytes = max_archive_mb * 1024 * 1024
                for item in africa_files:
                    size = int(item.get("size") or 0)
                    if size <= 0 or size > max_bytes:
                        continue
                    try:
                        archive_path = _download_file(client, item, output_dir, max_bytes)
                        report["zenodo"]["scans"].append(_scan_archive(archive_path))
                    except Exception as exc:  # noqa: BLE001
                        report["zenodo"]["scans"].append({
                            "archive": item.get("key"),
                            "error": f"{type(exc).__name__}: {exc}",
                        })
        except Exception as exc:  # noqa: BLE001
            report["zenodo"]["error"] = f"{type(exc).__name__}: {exc}"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-africa-archives", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path(".cache/egypt-reference-discovery"))
    parser.add_argument("--output", type=Path, default=Path("egypt-reference-discovery.json"))
    parser.add_argument("--max-archive-mb", type=int, default=50)
    args = parser.parse_args()
    if not 1 <= args.max_archive_mb <= 50:
        parser.error("--max-archive-mb must be between 1 and 50")
    report = discover(
        download_archives=args.download_africa_archives,
        output_dir=args.output_dir,
        max_archive_mb=args.max_archive_mb,
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "rdm_matches": len(report["rdm"]["matches"]),
        "rdm_error": report["rdm"]["error"],
        "africa_archives": len(report["zenodo"]["africa_archives"]),
        "archives_scanned": len(report["zenodo"]["scans"]),
        "archive_match_rows": sum(len(item.get("matches", [])) for item in report["zenodo"]["scans"]),
        "zenodo_error": report["zenodo"]["error"],
        "output": str(args.output),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report["rdm"]["error"] is None or report["zenodo"]["error"] is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
