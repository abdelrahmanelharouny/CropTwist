from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from scripts.discover_egypt_reference_data import _matching_records, _scan_archive, _scan_xlsx_bytes
from scripts.build_egypt_candidate_manifest import UnionFind, is_crop_specific_ewoc, stable_group_id


def test_rdm_discovery_matches_locality_and_preserves_license_metadata() -> None:
    payload = {
        "features": [
            {
                "id": "2024_egypt_reference_01",
                "properties": {
                    "title": "Crop reference observations - Mallawi",
                    "country": "Egypt",
                    "license": "CC BY 4.0",
                    "privacy": "public",
                },
            },
            {
                "id": "2024_other_01",
                "properties": {"title": "Unrelated collection", "country": "Kenya"},
            },
        ]
    }

    matches = _matching_records(payload)

    assert len(matches) == 1
    assert "egypt" in matches[0]["matched_terms"]
    assert matches[0]["record"]["properties"]["license"] == "CC BY 4.0"


def test_worldcereal_xlsx_metadata_scan_finds_egypt_and_license_row() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <si><t>Collection ID</t></si>
              <si><t>Country</t></si>
              <si><t>License</t></si>
              <si><t>egypt_mallawi_2024</t></si>
              <si><t>Egypt</t></si>
              <si><t>CC BY 4.0</t></si>
            </sst>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="s"><v>0</v></c>
                  <c r="B1" t="s"><v>1</v></c>
                  <c r="C1" t="s"><v>2</v></c>
                </row>
                <row r="2">
                  <c r="A2" t="s"><v>3</v></c>
                  <c r="B2" t="s"><v>4</v></c>
                  <c r="C2" t="s"><v>5</v></c>
                </row>
              </sheetData>
            </worksheet>""",
        )

    matches = _scan_xlsx_bytes(buffer.getvalue(), "metadata.xlsx")

    assert len(matches) == 1
    assert matches[0]["row"] == "2"
    assert "egypt" in matches[0]["matched_terms"]
    assert any("CC BY 4.0" in cell for cell in matches[0]["cells"])



def test_nested_worldcereal_collection_zip_detects_egypt_and_license(tmp_path) -> None:
    workbook = BytesIO()
    with ZipFile(workbook, "w", ZIP_DEFLATED) as book:
        book.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <si><t>Dataset Title</t></si>
              <si><t>License Type</t></si>
              <si><t>FAO WAPOR, Egypt, 2019</t></si>
              <si><t>CC_BY</t></si>
            </sst>""",
        )
        book.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1">
                <c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c>
              </row><row r="2">
                <c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c>
              </row></sheetData>
            </worksheet>""",
        )

    nested = BytesIO()
    with ZipFile(nested, "w", ZIP_DEFLATED) as collection:
        collection.writestr("metadata.xlsx", workbook.getvalue())
        collection.writestr("field_data.geoparquet", b"PAR1testPAR1")

    outer_path = tmp_path / "2019_Africa.zip"
    with ZipFile(outer_path, "w", ZIP_DEFLATED) as outer:
        outer.writestr("2019_egy_faowapor1_poly_111.zip", nested.getvalue())

    report = _scan_archive(outer_path)
    hits = report["matches"]

    assert any("_egy_" in hit["matched_terms"] for hit in hits)
    metadata_hit = next(hit for hit in hits if hit.get("source_file", "").endswith("metadata.xlsx"))
    assert "egypt" in metadata_hit["matched_terms"]
    assert any("CC_BY" in cell for cell in metadata_hit["cells"])



def test_egypt_candidate_manifest_excludes_generic_ewoc_codes() -> None:
    assert is_crop_specific_ewoc("1101080000")
    assert not is_crop_specific_ewoc("1000000000")
    assert not is_crop_specific_ewoc("1100000000")
    assert not is_crop_specific_ewoc("6000000000")
    assert not is_crop_specific_ewoc("7000000000")


def test_egypt_candidate_manifest_spatial_group_ids_are_stable() -> None:
    assert stable_group_id(["sample-b", "sample-a"]) == stable_group_id(["sample-a", "sample-b"])


def test_union_find_merges_connected_spatial_records() -> None:
    groups = UnionFind(5)
    groups.union(0, 1)
    groups.union(1, 3)
    groups.union(2, 4)

    assert groups.find(0) == groups.find(3)
    assert groups.find(2) == groups.find(4)
    assert groups.find(0) != groups.find(2)
