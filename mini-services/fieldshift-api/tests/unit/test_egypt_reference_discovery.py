from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from scripts.discover_egypt_reference_data import _matching_records, _scan_xlsx_bytes


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
