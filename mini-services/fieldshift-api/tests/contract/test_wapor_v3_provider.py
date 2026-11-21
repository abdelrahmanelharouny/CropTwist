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
        lambda code: wapor_v3.WaPORProduct("L2-T-D", "id", 2, "transpiration", "dekadal", 100, "Africa", ("EGY",)),
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
    assert result.unit is None
    assert result.scale_factor is None
    assert np.isnan(result.array[0, 1])
