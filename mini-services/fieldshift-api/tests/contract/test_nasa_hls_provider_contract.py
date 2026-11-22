"""Contract tests: NASA HLS provider (P04).

Deterministic via ``httpx.MockTransport`` and a monkeypatched raster seam.
The STAC fixtures mirror the documented CMR STAC / HLS v2.0 shapes and are
TEST-ONLY — they never represent live provider data.
"""

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.core.errors import ProviderRequestError, ProviderUnavailable, UnsupportedVariable
from app.data_platform.contracts.observations import (
    AreaOfInterest,
    EnvironmentalDataProvider,
)
from app.data_platform.providers.nasa_hls import catalog as hls_catalog
from app.data_platform.providers.nasa_hls import provider as hls_provider_module
from app.data_platform.providers.nasa_hls.provider import NasaHlsProvider

FIELD_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[31.40, 31.10], [31.42, 31.10], [31.42, 31.12], [31.40, 31.12], [31.40, 31.10]]],
}

LP = "https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected"


def _l30_item(scene_id="HLS.L30.T16SDC.2024189T164537.v2.0", cloud=12.5):
    return {
        "id": scene_id,
        "collection": "HLSL30_2.0",
        "bbox": [31.4, 31.1, 31.42, 31.12],
        "geometry": FIELD_GEOMETRY,
        "properties": {
            "datetime": "2024-07-07T16:45:37Z",
            "eo:cloud_cover": cloud,
            "platform": ["LANDSAT-8"],
        },
        "assets": {
            key: {"href": f"{LP}/{scene_id}.{key}.tif"}
            for key in ("B02", "B03", "B04", "B05", "B06", "B07", "Fmask")
        },
    }


def _s30_item(scene_id="HLS.S30.T16SDC.2024191T160801.v2.0", cloud=41.2):
    return {
        "id": scene_id,
        "collection": "HLSS30_2.0",
        "bbox": [31.4, 31.1, 31.42, 31.12],
        "geometry": FIELD_GEOMETRY,
        "properties": {
            "datetime": "2024-07-09T16:08:01Z",
            "eo:cloud_cover": cloud,
            "platform": ["SENTINEL-2B"],
        },
        "assets": {
            key: {"href": f"{LP}/{scene_id}.{key}.tif"}
            for key in ("B02", "B03", "B04", "B08", "B11", "B12", "Fmask")
        },
    }


def _search_body(features, next_after=None):
    body = {"features": features, "links": [{"rel": "self"}]}
    if next_after is not None:
        body["links"].append({"rel": "next", "method": "POST", "body": {"searchAfter": next_after}})
    return body


def make_client(pages, calls=None):
    """MockTransport for CMR STAC: serves the given page payloads in order."""
    state = {"page": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append({"url": str(request.url), "body": json.loads(request.content)})
        page = pages[min(state["page"], len(pages) - 1)]
        state["page"] += 1
        if callable(page):
            return page()
        return httpx.Response(200, json=page)

    return httpx.Client(transport=httpx.MockTransport(handler))




def test_nasa_hls_extracts_only_numeric_http_status_from_gdal_error():
    assert hls_provider_module._safe_http_status_from_exception(
        RuntimeError("HTTP response code: 403 while reading a protected asset")
    ) == 403
    assert hls_provider_module._safe_http_status_from_exception(
        RuntimeError("HTTP status code 429; request failed")
    ) == 429
    assert hls_provider_module._safe_http_status_from_exception(
        RuntimeError("request failed with secret_token_123 and no status")
    ) is None




def test_hls_reads_only_surfaces_required_by_requested_indices():
    assert hls_provider_module._required_surfaces_for_indices(["ndvi"]) == ["red", "nir"]
    assert hls_provider_module._required_surfaces_for_indices(["ndmi", "evi"]) == [
        "red", "nir", "blue", "swir1"
    ]


def test_provider_satisfies_platform_contract():
    provider = NasaHlsProvider()
    assert isinstance(provider, EnvironmentalDataProvider)
    assert provider.provider_code == "nasa_hls"
    assert set(provider.supported_variables()) == {"ndvi", "evi", "savi", "ndmi", "ndwi"}
    assert provider.collections() == ["HLSL30", "HLSS30"]


def test_provenance_is_honest_and_per_collection():
    provider = NasaHlsProvider()
    for collection, expected_product in (("HLSL30", "HLSL30"), ("HLSS30", "HLSS30")):
        prov = provider._provenance(collection)
        assert prov.provider_code == "nasa_hls"
        assert prov.product_code == expected_product
        assert prov.product_version == "2.0"
        assert prov.license_name and "NASA" in prov.license_name
        assert prov.license_url and prov.documentation_url
        assert "LP DAAC" in prov.attribution_text
        # Sentinel-2 is ESA/Copernicus data ingested by HLS — never a NASA satellite.
        if collection == "HLSS30":
            assert "Sentinel-2" in prov.attribution_text and "ESA" in prov.attribution_text
        assert prov.known_limitations and "SMAP" in prov.known_limitations
        assert prov.retrieval_method == "cmr_stac_cog_http_range"


def test_search_parses_items_pagination_and_request_filters():
    calls = []
    client = make_client(
        [
            _search_body([_l30_item()], next_after=["token-1"]),
            _search_body([_s30_item()]),
        ],
        calls=calls,
    )
    provider = NasaHlsProvider(client=client)
    records, warnings = provider.search_scenes(
        geometry_geojson=FIELD_GEOMETRY,
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        max_cloud_cover=80.0,
    )
    assert warnings == []
    assert [r.collection for r in records] == ["HLSL30", "HLSS30"]
    assert records[0].scene_id == "HLS.L30.T16SDC.2024189T164537.v2.0"
    assert records[0].acquired_at == datetime(2024, 7, 7, 16, 45, 37, tzinfo=UTC)
    assert records[0].cloud_cover_pct == 12.5
    assert records[0].spatial_resolution_m == 30.0
    assert records[0].asset_refs["nir"].endswith("B05.tif")
    assert records[1].asset_refs["nir"].endswith("B08.tif")
    # Two pages were fetched (pagination followed), both with spatial + temporal filters.
    assert len(calls) == 2
    first = calls[0]["body"]
    assert first["bbox"] == [31.4, 31.1, 31.42, 31.12]
    assert first["datetime"].startswith("2024-07-01T00:00:00Z/")
    assert first["query"] == {"eo:cloud_cover": {"lte": 80.0}}
    assert calls[1]["body"]["searchAfter"] == ["token-1"]


def test_search_skips_non_hls_collections_with_warnings():
    foreign = {**_l30_item(), "collection": "VNP09GA.1"}
    client = make_client([_search_body([foreign, _l30_item("HLS.L30.T16SDC.2024190T164500.v2.0")])])
    provider = NasaHlsProvider(client=client)
    records, warnings = provider.search_scenes(
        geometry_geojson=FIELD_GEOMETRY,
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
    )
    assert len(records) == 1
    assert any("not an HLS product" in w for w in warnings)


def test_search_max_pages_caps_pagination():
    calls = []
    client = make_client([_search_body([_l30_item()], next_after=["again"])], calls=calls)
    provider = NasaHlsProvider(client=client)
    records, _ = provider.search_scenes(
        geometry_geojson=FIELD_GEOMETRY,
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        max_pages=3,
    )
    assert len(calls) == 3


def test_search_retries_5xx_then_raises_provider_unavailable(monkeypatch):
    import time as _time

    monkeypatch.setattr(hls_catalog.time, "sleep", lambda *_: None)
    monkeypatch.setattr(_time, "sleep", lambda *_: None)
    client = make_client([lambda: httpx.Response(503, json={"error": "cmr busy"})])
    provider = NasaHlsProvider(client=client)
    with pytest.raises(ProviderUnavailable):
        provider.search_scenes(
            geometry_geojson=FIELD_GEOMETRY,
            start=datetime(2024, 7, 1, tzinfo=UTC),
            end=datetime(2024, 7, 31, tzinfo=UTC),
        )


def test_search_4xx_raises_provider_request_error():
    client = make_client([lambda: httpx.Response(400, json={"error": "bad bbox"})])
    provider = NasaHlsProvider(client=client)
    with pytest.raises(ProviderRequestError):
        provider.search_scenes(
            geometry_geojson=FIELD_GEOMETRY,
            start=datetime(2024, 7, 1, tzinfo=UTC),
            end=datetime(2024, 7, 31, tzinfo=UTC),
        )


def test_fetch_rejects_unknown_variables():
    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    with pytest.raises(UnsupportedVariable):
        provider.fetch_observations(
            area_of_interest=aoi,
            variables=["soil_ph"],
            start=datetime(2024, 7, 1, tzinfo=UTC),
            end=datetime(2024, 7, 31, tzinfo=UTC),
            options={},
        )


def test_fetch_without_scenes_reports_honest_availability_gap():
    client = make_client([_search_body([])])
    provider = NasaHlsProvider(client=client)
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    result = provider.fetch_observations(
        area_of_interest=aoi,
        variables=["ndvi"],
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        options={},
    )
    assert result.observations == []
    assert result.coverage["scenes_requested"] == 0
    assert any("data-availability gap" in w for w in result.warnings)


def test_fetch_mixed_collections_rejected():
    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    records = {
        _l30_item()["id"]: {"scene_id": _l30_item()["id"], "collection": "HLSL30", "acquired_at": "2024-07-07T16:45:37+00:00", "assets": {}},
        _s30_item()["id"]: {"scene_id": _s30_item()["id"], "collection": "HLSS30", "acquired_at": "2024-07-09T16:08:01+00:00", "assets": {}},
    }
    with pytest.raises(ProviderRequestError):
        provider.fetch_observations(
            area_of_interest=aoi,
            variables=["ndvi"],
            start=datetime(2024, 7, 1, tzinfo=UTC),
            end=datetime(2024, 7, 31, tzinfo=UTC),
            options={"scene_ids": list(records), "scene_records": records},
        )


def _fake_raster_seam(monkeypatch, red, nir, blue=None, fmask=None, size=(12, 12)):
    """Replace the /vsicurl/ raster seam with deterministic in-memory arrays."""
    import numpy as np
    from rasterio.transform import from_bounds

    transform = from_bounds(31.40, 31.10, 31.42, 31.12, size[1], size[0])

    def fake_load(assets, surfaces, gdal_env, geometry_geojson):
        arrays = {}
        for surface in surfaces:
            data = {"red": red, "nir": nir, "blue": blue if blue is not None else red}.get(surface)
            if data is None:
                continue
            arrays[surface] = {"data": data.astype("float64"), "transform": transform}
        qa = fmask if fmask is not None else np.zeros(size, dtype="uint8")
        return arrays, {
            "fmask": qa,
            "shape": size,
            "transform": transform,
            "crs": "EPSG:4326",
            "band_alignment": {surface: "native" for surface in surfaces} | {"fmask": "native"},
            "window_bounds": (31.40, 31.10, 31.42, 31.12),
            "read_bytes_estimate": size[0] * size[1] * (len(surfaces) + 2) * 8,
        }

    monkeypatch.setattr(hls_provider_module, "_load_scene_arrays", fake_load)
    return transform


def test_fetch_scene_observations_computed_with_real_index_math(monkeypatch):
    import numpy as np

    dn_red = np.full((12, 12), 0.12 * 10000)  # DN -> reflectance scale 0.0001
    dn_nir = np.full((12, 12), 0.42 * 10000)
    _fake_raster_seam(monkeypatch, dn_red, dn_nir)

    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    scene_id = "HLS.L30.T16SDC.2024189T164537.v2.0"
    records = {
        scene_id: {
            "scene_id": scene_id,
            "collection": "HLSL30",
            "collection_id": "HLSL30_2.0",
            "acquired_at": "2024-07-07T16:45:37+00:00",
            "cloud_cover_pct": 12.5,
            "platform": "LANDSAT-8",
            "assets": {"red": f"{LP}/x.B04.tif", "nir": f"{LP}/x.B05.tif", "fmask": f"{LP}/x.Fmask.tif"},
        }
    }
    result = provider.fetch_observations(
        area_of_interest=aoi,
        variables=["ndvi", "evi"],
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        options={"scene_ids": [scene_id], "scene_records": records},
    )
    assert result.coverage["scenes_processed"] == 1
    assert result.provenance.product_code == "HLSL30"
    obs = {o.variable_code: o for o in result.observations}
    assert set(obs) == {"ndvi", "evi"}
    ndvi = obs["ndvi"]
    # Independent NDVI check: (0.42-0.12)/(0.42+0.12).
    assert ndvi.value == pytest.approx((0.42 - 0.12) / (0.42 + 0.12), abs=1e-6)
    assert ndvi.evidence_class == "satellite_derived_estimate"
    assert ndvi.is_synthetic is False
    assert ndvi.spatial_resolution_m == 30.0
    meta = ndvi.metadata
    assert meta["scene_id"] == scene_id
    assert meta["collection"] == "HLSL30"
    assert meta["platform"] == "LANDSAT-8"
    assert meta["cloud_cover_pct"] == 12.5
    assert meta["zonal"]["valid_pixels"] == 144
    assert meta["zonal"]["coverage_fraction"] == pytest.approx(1.0)
    assert meta["quality_flags"][0]["flag_code"] == "NASA_HLS_ZONAL"
    # Stable provider request id for the same scene set.
    id2 = provider.fetch_observations(
        area_of_interest=aoi,
        variables=["ndvi"],
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        options={"scene_ids": [scene_id], "scene_records": records},
    ).provider_request_id
    assert result.provider_request_id == id2
    assert result.provider_request_id.startswith("nasa_hls:")


def test_fmask_masks_cloud_pixels(monkeypatch):
    import numpy as np

    dn_red = np.full((12, 12), 0.12 * 10000)
    dn_nir = np.full((12, 12), 0.42 * 10000)
    fmask = np.zeros((12, 12), dtype="uint8")
    fmask[:, :6] = 0b000010  # cloud bit set on half the scene (bit 1 = 2)
    _fake_raster_seam(monkeypatch, dn_red, dn_nir, fmask=fmask)

    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    scene_id = "HLS.L30.T16SDC.2024189T164537.v2.0"
    records = {
        scene_id: {
            "scene_id": scene_id,
            "collection": "HLSL30",
            "acquired_at": "2024-07-07T16:45:37+00:00",
            "assets": {"red": f"{LP}/test.red.tif", "nir": f"{LP}/test.nir.tif", "fmask": f"{LP}/test.Fmask.tif"},
        }
    }
    result = provider.fetch_observations(
        area_of_interest=aoi,
        variables=["ndvi"],
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        options={"scene_ids": [scene_id], "scene_records": records},
    )
    ndvi = result.observations[0]
    assert ndvi.value is not None
    assert ndvi.metadata["zonal"]["valid_pixels"] == 72  # half the scene masked out


def test_all_cloud_scene_yields_missing_not_zero(monkeypatch):
    import numpy as np

    dn_red = np.full((12, 12), 0.12 * 10000)
    dn_nir = np.full((12, 12), 0.42 * 10000)
    fmask = np.full((12, 12), 0b000010, dtype="uint8")
    _fake_raster_seam(monkeypatch, dn_red, dn_nir, fmask=fmask)

    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    scene_id = "HLS.L30.T16SDC.2024189T164537.v2.0"
    records = {
        scene_id: {
            "scene_id": scene_id,
            "collection": "HLSL30",
            "acquired_at": "2024-07-07T16:45:37+00:00",
            "assets": {"red": f"{LP}/test.red.tif", "nir": f"{LP}/test.nir.tif", "fmask": f"{LP}/test.Fmask.tif"},
        }
    }
    result = provider.fetch_observations(
        area_of_interest=aoi,
        variables=["ndvi"],
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        options={"scene_ids": [scene_id], "scene_records": records},
    )
    ndvi = result.observations[0]
    assert ndvi.value is None
    assert ndvi.quality_status == "missing"
    assert any(
        f["flag_code"] == "CLOUD_OCCLUDED_OR_NO_COVERAGE" for f in ndvi.quality_flags
    )


def test_per_scene_degradation_degrades_only_that_scene(monkeypatch):
    import numpy as np

    dn_red = np.full((12, 12), 0.12 * 10000)
    dn_nir = np.full((12, 12), 0.42 * 10000)
    _fake_raster_seam(monkeypatch, dn_red, dn_nir)

    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    good = "HLS.L30.T16SDC.2024189T164537.v2.0"
    bad = "HLS.L30.T16SDC.2024191T164538.v2.0"
    records = {
        good: {
            "scene_id": good,
            "collection": "HLSL30",
            "acquired_at": "2024-07-07T16:45:37+00:00",
            "assets": {"red": f"{LP}/test.red.tif", "nir": f"{LP}/test.nir.tif", "fmask": f"{LP}/test.Fmask.tif"},
        },
        bad: {
            "scene_id": bad,
            "collection": "HLSL30",
            "acquired_at": "2024-07-09T16:45:38+00:00",
            "assets": {"blue": f"{LP}/test.blue.tif"},  # red+nir missing -> scene skipped
        },
    }
    result = provider.fetch_observations(
        area_of_interest=aoi,
        variables=["ndvi"],
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        options={"scene_ids": [good, bad], "scene_records": records},
    )
    assert result.coverage["scenes_processed"] == 1
    assert any(bad in w and "required band assets missing" in w for w in result.warnings)
    assert {o.metadata["scene_id"] for o in result.observations} == {good}


def test_fmask_masks_high_aerosol_pixels(monkeypatch):
    import numpy as np

    dn_red = np.full((12, 12), 0.12 * 10000)
    dn_nir = np.full((12, 12), 0.42 * 10000)
    fmask = np.zeros((12, 12), dtype="uint8")
    fmask[5, 5] = 0b11000000
    _fake_raster_seam(monkeypatch, dn_red, dn_nir, fmask=fmask)

    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    scene_id = "HLS.L30.T16SDC.2024189T164537.v2.0"
    records = {
        scene_id: {
            "scene_id": scene_id,
            "collection": "HLSL30",
            "acquired_at": "2024-07-07T16:45:37+00:00",
            "assets": {"red": f"{LP}/test.red.tif", "nir": f"{LP}/test.nir.tif", "fmask": f"{LP}/test.Fmask.tif"},
        }
    }
    result = provider.fetch_observations(
        area_of_interest=aoi,
        variables=["ndvi"],
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        options={"scene_ids": [scene_id], "scene_records": records},
    )
    observation = result.observations[0]
    assert observation.metadata["zonal"]["valid_pixels"] == 143
    assert observation.metadata["fmask_qa"]["high_aerosol_pixels"] == 1
    assert observation.metadata["fmask_qa"]["aot_level_counts"]["high"] == 1



def test_fmask_aerosol_low_and_medium_bit_patterns_are_not_swapped(monkeypatch):
    import numpy as np

    dn_red = np.full((12, 12), 0.12 * 10000)
    dn_nir = np.full((12, 12), 0.42 * 10000)
    fmask = np.zeros((12, 12), dtype="uint8")
    # HLS v2 bits 6-7: 10 = low, 01 = medium.
    fmask[5, 5] = 0b01000000
    fmask[6, 6] = 0b10000000
    _fake_raster_seam(monkeypatch, dn_red, dn_nir, fmask=fmask)

    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    scene_id = "HLS.L30.T16SDC.2024189T164537.v2.0"
    records = {
        scene_id: {
            "scene_id": scene_id,
            "collection": "HLSL30",
            "acquired_at": "2024-07-07T16:45:37+00:00",
            "assets": {"red": f"{LP}/test.red.tif", "nir": f"{LP}/test.nir.tif", "fmask": f"{LP}/test.Fmask.tif"},
        }
    }
    result = provider.fetch_observations(
        area_of_interest=aoi,
        variables=["ndvi"],
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        options={"scene_ids": [scene_id], "scene_records": records},
    )
    counts = result.observations[0].metadata["fmask_qa"]["aot_level_counts"]
    assert counts["low"] == 1
    assert counts["medium"] == 1
    assert counts["high"] == 0

def test_scene_without_fmask_is_skipped_instead_of_claiming_qa_masking(monkeypatch):
    import numpy as np

    dn_red = np.full((12, 12), 0.12 * 10000)
    dn_nir = np.full((12, 12), 0.42 * 10000)
    _fake_raster_seam(monkeypatch, dn_red, dn_nir)

    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    scene_id = "HLS.L30.T16SDC.2024189T164537.v2.0"
    records = {
        scene_id: {
            "scene_id": scene_id,
            "collection": "HLSL30",
            "acquired_at": "2024-07-07T16:45:37+00:00",
            "assets": {"red": f"{LP}/test.red.tif", "nir": f"{LP}/test.nir.tif"},
        }
    }
    result = provider.fetch_observations(
        area_of_interest=aoi,
        variables=["ndvi"],
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        options={"scene_ids": [scene_id], "scene_records": records},
    )
    assert result.observations == []
    assert result.coverage["scenes_processed"] == 0
    assert any("required band assets missing (fmask)" in warning for warning in result.warnings)


def test_scene_records_without_acquired_at_rejected():
    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    scene_id = "HLS.L30.T16SDC.2024189T164537.v2.0"
    with pytest.raises(ProviderRequestError):
        provider.fetch_observations(
            area_of_interest=aoi,
            variables=["ndvi"],
            start=datetime(2024, 7, 1, tzinfo=UTC),
            end=datetime(2024, 7, 31, tzinfo=UTC),
            options={"scene_ids": [scene_id], "scene_records": {scene_id: {"scene_id": scene_id, "collection": "HLSL30", "assets": {}}}},
        )


@pytest.mark.parametrize(
    "scene_ids",
    [
        [],
        "",
        [""],
        [True],
        ["scene-a", "scene-a"],
        ["x" * 257],
    ],
)
def test_resolve_targets_rejects_malformed_explicit_scene_selectors(scene_ids):
    provider = NasaHlsProvider()
    with pytest.raises(ProviderRequestError, match="scene_ids"):
        provider._resolve_targets(
            {"scene_ids": scene_ids, "scene_records": {}},
            start=datetime(2024, 7, 1, tzinfo=UTC),
            end=datetime(2024, 7, 31, tzinfo=UTC),
            geometry_geojson=FIELD_GEOMETRY,
        )


def test_validate_request_enforces_scene_cap():
    provider = NasaHlsProvider()
    from app.core.config import settings

    too_many = [f"scene-{i}" for i in range(settings.nasa_hls_max_scenes_per_job + 1)]
    with pytest.raises(ProviderRequestError):
        provider.validate_request(variables=["ndvi"], options={"scene_ids": too_many})
    provider.validate_request(
        variables=["ndvi"], options={"scene_ids": ["one-scene"]}
    )  # no raise
    with pytest.raises(UnsupportedVariable):
        provider.validate_request(variables=["chlorophyll"], options={})

@pytest.mark.parametrize(
    "scene_ids",
    [[], [""], [True], ["scene-1", "scene-1"], ["x" * 257]],
)
def test_validate_request_rejects_malformed_scene_selectors_before_job_creation(scene_ids):
    provider = NasaHlsProvider()
    with pytest.raises(ProviderRequestError, match="scene_ids"):
        provider.validate_request(variables=["ndvi"], options={"scene_ids": scene_ids})


def test_hls_raster_exception_does_not_leak_signed_asset_url(monkeypatch):
    secret_url = "https://example.test/asset.tif?token=do-not-leak"

    def fail_read(*args, **kwargs):
        raise RuntimeError(f"failed to read {secret_url}")

    monkeypatch.setattr(hls_provider_module, "_load_scene_arrays", fail_read)
    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    scene_id = "HLS.L30.T16SDC.2024189T164537.v2.0"
    records = {
        scene_id: {
            "scene_id": scene_id,
            "collection": "HLSL30",
            "acquired_at": "2024-07-07T16:45:37+00:00",
            "assets": {"red": f"{LP}/test.red.tif", "nir": f"{LP}/test.nir.tif", "fmask": f"{LP}/test.Fmask.tif"},
        }
    }
    result = provider.fetch_observations(
        area_of_interest=aoi,
        variables=["ndvi"],
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        options={"scene_ids": [scene_id], "scene_records": records},
    )
    assert result.observations == []
    assert any("RuntimeError" in warning for warning in result.warnings)
    assert secret_url not in str(result.warnings)
    assert "do-not-leak" not in str(result.warnings)

def test_hls_scene_record_rejects_untrusted_asset_urls():
    from app.core.errors import ProviderRequestError

    base = {
        "scene_id": "scene-1",
        "collection": "HLSL30",
        "acquired_at": "2024-07-07T16:45:37+00:00",
        "assets": {},
    }
    invalid_hrefs = [
        "http://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/a.tif",
        "https://evil.example/lp-prod-protected/a.tif",
        "https://user:password@data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/a.tif",
        "https://data.lpdaac.earthdatacloud.nasa.gov:8443/lp-prod-protected/a.tif",
        "https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/a.tif?token=secret",
        "https://data.lpdaac.earthdatacloud.nasa.gov/other-bucket/a.tif",
    ]
    for href in invalid_hrefs:
        record = {**base, "assets": {"red": href}}
        with pytest.raises(ProviderRequestError, match="untrusted red asset URL"):
            hls_provider_module._validate_scene_record("scene-1", record)


def test_hls_scene_record_rejects_mismatched_identity_and_invalid_cloud_cover():
    from app.core.errors import ProviderRequestError

    record = {
        "scene_id": "different-scene",
        "collection": "HLSL30",
        "acquired_at": "2024-07-07T16:45:37+00:00",
        "assets": {},
    }
    with pytest.raises(ProviderRequestError, match="mismatched scene identifier"):
        hls_provider_module._validate_scene_record("scene-1", record)

    record["scene_id"] = "scene-1"
    record["cloud_cover_pct"] = float("nan")
    with pytest.raises(ProviderRequestError, match="invalid cloud-cover"):
        hls_provider_module._validate_scene_record("scene-1", record)

def test_hls_explicit_scene_records_must_match_requested_date_range():
    from app.core.errors import ProviderRequestError

    provider = NasaHlsProvider()
    scene_id = "HLS.L30.T16SDC.2023189T164537.v2.0"
    record = {
        "scene_id": scene_id,
        "collection": "HLSL30",
        "acquired_at": "2023-07-08T16:45:37+00:00",
        "assets": {},
    }
    with pytest.raises(ProviderRequestError, match="outside the requested time range"):
        provider._resolve_targets(
            {"scene_ids": [scene_id], "scene_records": {scene_id: record}},
            datetime(2024, 7, 1, tzinfo=UTC),
            datetime(2024, 7, 31, tzinfo=UTC),
            FIELD_GEOMETRY,
        )


def test_hls_explicit_scene_records_validate_keys_before_sorting():
    from app.core.errors import ProviderRequestError

    provider = NasaHlsProvider()
    with pytest.raises(ProviderRequestError, match="bounded identifier"):
        provider._resolve_targets(
            {"scene_records": {1: {"scene_id": "scene-1"}}},
            datetime(2024, 7, 1, tzinfo=UTC),
            datetime(2024, 7, 31, tzinfo=UTC),
            FIELD_GEOMETRY,
        )


def test_fmask_aerosol_level_counts_follow_hls_bit_order(monkeypatch):
    import numpy as np

    dn_red = np.full((12, 12), 0.12 * 10000)
    dn_nir = np.full((12, 12), 0.42 * 10000)
    fmask = np.zeros((12, 12), dtype="uint8")
    # HLS QA documents bits 7:6 as 10=low and 01=medium.
    fmask.flat[:48] = 0b10000000
    fmask.flat[48:96] = 0b01000000
    _fake_raster_seam(monkeypatch, dn_red, dn_nir, fmask=fmask)

    provider = NasaHlsProvider(client=make_client([_search_body([])]))
    aoi = AreaOfInterest(field_id="f", geometry_geojson=FIELD_GEOMETRY)
    scene_id = "HLS.L30.T16SDC.2024189T164537.v2.0"
    records = {
        scene_id: {
            "scene_id": scene_id,
            "collection": "HLSL30",
            "acquired_at": "2024-07-07T16:45:37+00:00",
            "assets": {
                "red": f"{LP}/test.red.tif",
                "nir": f"{LP}/test.nir.tif",
                "fmask": f"{LP}/test.Fmask.tif",
            },
        }
    }
    result = provider.fetch_observations(
        area_of_interest=aoi,
        variables=["ndvi"],
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 31, tzinfo=UTC),
        options={"scene_ids": [scene_id], "scene_records": records},
    )
    qa = result.observations[0].metadata["fmask_qa"]
    assert qa["aot_level_counts"] == {
        "climatology": 48,
        "low": 48,
        "medium": 48,
        "high": 0,
    }
