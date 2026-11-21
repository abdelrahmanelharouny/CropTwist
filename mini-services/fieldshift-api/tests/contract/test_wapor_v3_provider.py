import numpy as np
import httpx
import pytest

from app.data_platform.providers import wapor_v3


def _client_factory(handler):
    def factory(timeout):
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
            follow_redirects=False,
        )
    return factory


def test_catalog_client_follows_only_fao_pagination():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(200, json={
                "response": {
                    "items": [{"code": "L2-T-D", "caption": "Transpiration"}],
                    "links": [{"rel": "next", "href": "https://data.apps.fao.org/gismgr/api/v2/catalog/workspaces/WAPOR-3/mapsets?page=2"}],
                }
            })
        return httpx.Response(200, json={
            "response": {"items": [{"code": "L2-AETI-D", "caption": "AETI"}], "links": []}
        })

    client = wapor_v3.WaPORV3Client(client_factory=_client_factory(handler))
    assert [item["code"] for item in client.list_mapsets()] == ["L2-T-D", "L2-AETI-D"]
    assert len(calls) == 2


def test_catalog_client_rejects_untrusted_pagination_url():
    def handler(request):
        return httpx.Response(200, json={
            "response": {
                "items": [],
                "links": [{"rel": "next", "href": "https://evil.example/steal"}],
            }
        })

    client = wapor_v3.WaPORV3Client(client_factory=_client_factory(handler))
    with pytest.raises(wapor_v3.WaPORProviderError, match="untrusted URL"):
        client.list_mapsets()


def test_list_rasters_validates_mapset_and_trusted_cog_url():
    def handler(request):
        return httpx.Response(200, json={
            "response": {
                "items": [
                    {
                        "code": "WAPOR-3.L2-T-D.2025-01-D1",
                        "downloadUrl": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/sample.tif",
                        "unit": "mm/dekad",
                        "scale": 1.0,
                    },
                    {
                        "code": "untrusted",
                        "downloadUrl": "https://evil.example/sample.tif",
                    },
                ],
                "links": [],
            }
        })

    client = wapor_v3.WaPORV3Client(client_factory=_client_factory(handler))
    rasters = client.list_rasters("L2-T-D")
    assert len(rasters) == 1
    assert rasters[0]["unit"] == "mm/dekad"
    assert rasters[0]["period_code"] == "2025-01-D1"
    with pytest.raises(ValueError, match="mapset code"):
        client.list_rasters("../secrets")


def test_field_window_masks_outside_field_and_preserves_raw_units(monkeypatch):
    class Reading:
        arrays = {"wapor": np.array([[1.0, 2.0], [3.0, np.nan]])}
        crs = "EPSG:32636"
        transform = object()
        width = 2
        height = 2

    monkeypatch.setattr(
        wapor_v3,
        "get_product",
        lambda code: type("Product", (), {"resolution_m": 100, "unit": "mm/day", "scale_factor": 0.1, "metadata_reference": "https://example.org/spec", "license": "CC BY-SA 4.0"})(),
    )
    monkeypatch.setattr(
        wapor_v3,
        "_read_raster_metadata",
        lambda url: {"unit": "mm/dekad", "scale_factor": 0.1, "offset": 0.0, "nodata": -9999, "is_tiled": True},
    )
    monkeypatch.setattr(
        "app.geospatial.preprocessing.read_scene_window",
        lambda **kwargs: Reading(),
    )
    monkeypatch.setattr(
        "app.geospatial.preprocessing.field_mask_for_window",
        lambda **kwargs: np.array([[True, False], [True, True]]),
    )
    client = wapor_v3.WaPORV3Client()
    result = client.read_field_window(
        mapset_code="L2-T-D",
        raster={
            "code": "WAPOR-3.L2-T-D.2025-01-D1",
            "download_url": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/sample.tif",
            "unit": None,
            "scale_factor": None,
        },
        geometry_geojson={"type": "Polygon", "coordinates": []},
    )
    assert result.valid_pixel_count == 2
    assert result.raw_mean == 2.0
    assert result.unit == "mm/dekad"
    assert result.scale_factor == 0.1
    assert result.offset == 0.0
    assert result.scaled_mean == pytest.approx(0.2)
    assert result.scaled_median == pytest.approx(0.2)
    assert result.metadata_reference == "https://example.org/spec"
    assert result.license == "CC BY-SA 4.0"
    assert np.isnan(result.array[0, 1])

def test_field_window_refuses_non_tiled_asset(monkeypatch):
    monkeypatch.setattr(
        wapor_v3,
        "get_product",
        lambda code: type("Product", (), {"resolution_m": 100, "unit": "mm/day", "scale_factor": 0.1, "metadata_reference": "https://example.org/spec"})(),
    )
    monkeypatch.setattr(
        wapor_v3,
        "_read_raster_metadata",
        lambda url: {"unit": None, "scale_factor": None, "offset": None, "nodata": None, "is_tiled": False},
    )
    client = wapor_v3.WaPORV3Client()
    with pytest.raises(wapor_v3.WaPORProviderError, match="not tiled"):
        client.read_field_window(
            mapset_code="L2-T-D",
            raster={
                "code": "WAPOR-3.L2-T-D.2025-01-D1",
                "download_url": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/sample.tif",
            },
            geometry_geojson={"type": "Polygon", "coordinates": []},
        )
