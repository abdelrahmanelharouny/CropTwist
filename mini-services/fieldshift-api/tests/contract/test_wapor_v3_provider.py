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
    assert rasters[0]["resolution_m"] == 100
    assert rasters[0]["license"] == "CC BY-SA 4.0"
    assert rasters[0]["metadata_reference"].endswith("WaPOR_specs.html")
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
        lambda url: {"unit": "mm/day", "scale_factor": 0.1, "offset": 0.0, "nodata": -9999, "is_tiled": True},
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
    assert result.unit == "mm/day"
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
        lambda code: type("Product", (), {"resolution_m": 100, "unit": "mm/day", "scale_factor": 0.1, "metadata_reference": "https://example.org/spec", "license": "CC BY-SA 4.0"})(),
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


@pytest.mark.parametrize(
    "url",
    [
        "https://storage.googleapis.com:444/fao-gismgr-wapor-3-data/sample.tif",
        "https://user:secret@storage.googleapis.com/fao-gismgr-wapor-3-data/sample.tif",
    ],
)
def test_field_window_rejects_untrusted_raster_authority_before_io(monkeypatch, url):
    monkeypatch.setattr(
        wapor_v3,
        "_read_raster_metadata",
        lambda _: (_ for _ in ()).throw(AssertionError("untrusted URL reached rasterio")),
    )
    with pytest.raises(ValueError, match="trusted FAO COG URL"):
        wapor_v3.WaPORV3Client().read_field_window(
            mapset_code="L2-T-D",
            raster={
                "code": "WAPOR-3.L2-T-D.2025-01-D1",
                "download_url": url,
            },
            geometry_geojson={"type": "Polygon", "coordinates": []},
        )


def test_conflicting_scale_unit_and_offset_withhold_scaled_values(monkeypatch):
    class Reading:
        arrays = {"wapor": np.array([[2.0]])}
        crs = "EPSG:32636"
        transform = object()
        width = 1
        height = 1

    monkeypatch.setattr(
        wapor_v3,
        "get_product",
        lambda code: type("Product", (), {
            "resolution_m": 100, "unit": "mm/day", "scale_factor": 0.1,
            "metadata_reference": "https://example.org/spec", "license": "CC BY-SA 4.0",
        })(),
    )
    monkeypatch.setattr(
        wapor_v3,
        "_read_raster_metadata",
        lambda url: {"unit": "mm/dekad", "scale_factor": 0.2, "offset": 0.0, "is_tiled": True},
    )
    monkeypatch.setattr("app.geospatial.preprocessing.read_scene_window", lambda **kwargs: Reading())
    monkeypatch.setattr(
        "app.geospatial.preprocessing.field_mask_for_window",
        lambda **kwargs: np.array([[True]]),
    )
    result = wapor_v3.WaPORV3Client().read_field_window(
        mapset_code="L2-T-D",
        raster={
            "code": "WAPOR-3.L2-T-D.2025-01-D1",
            "download_url": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/sample.tif",
            "scale_factor": float("nan"),
            "offset": True,
            "unit": "unknown",
        },
        geometry_geojson={"type": "Polygon", "coordinates": []},
    )
    # Conflicting upstream scale/unit metadata is not promoted to canonical
    # physical values; only the raw raster statistics remain trustworthy.
    assert result.scale_factor is None
    assert result.offset is None
    assert result.unit is None
    assert result.scaled_mean is None


def test_wapor_provider_rejects_naive_datetimes_before_provider_io():
    from datetime import datetime
    from app.core.errors import InvalidDateRange
    from app.data_platform.contracts.observations import AreaOfInterest
    from app.data_platform.providers.wapor_v3 import WaPORV3Provider

    class NoIoClient:
        def list_rasters(self, mapset_code):
            raise AssertionError("invalid time range reached provider I/O")

    with pytest.raises(InvalidDateRange, match="timezone-aware"):
        WaPORV3Provider(client=NoIoClient()).fetch_observations(
            area_of_interest=AreaOfInterest(
                geometry_geojson={"type": "Polygon", "coordinates": [[[31, 30], [32, 30], [32, 31], [31, 31], [31, 30]]]}
            ),
            variables=["actual_evapotranspiration_interception"],
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 10),
        )


def test_wapor_provider_bounds_raster_window_before_reading():
    from datetime import UTC, datetime
    from app.core.errors import ValidationFailed
    from app.data_platform.contracts.observations import AreaOfInterest
    from app.data_platform.providers.wapor_v3 import WaPORV3Provider

    class FakeClient:
        def list_rasters(self, mapset_code):
            return [{
                "code": f"WAPOR-3.{mapset_code}.2025-01-D1",
                "period_code": "2025-01-D1",
            }]

        def read_field_window(self, **kwargs):
            raise AssertionError("out-of-bounds window reached raster read")

    with pytest.raises(ValidationFailed, match="between 1 and 256"):
        WaPORV3Provider(client=FakeClient()).fetch_observations(
            area_of_interest=AreaOfInterest(
                geometry_geojson={"type": "Polygon", "coordinates": [[[31, 30], [32, 30], [32, 31], [31, 31], [31, 30]]]}
            ),
            variables=["actual_evapotranspiration_interception"],
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 10, tzinfo=UTC),
            options={"max_window_mb": 1024},
        )

def test_all_reported_scale_and_unit_sources_must_agree(monkeypatch):
    class Reading:
        arrays = {"wapor": np.array([[2.0]])}
        crs = "EPSG:32636"
        transform = object()
        width = 1
        height = 1

    monkeypatch.setattr(
        wapor_v3,
        "get_product",
        lambda code: type("Product", (), {
            "resolution_m": 100, "unit": "mm/day", "scale_factor": 0.1,
            "metadata_reference": "https://example.org/spec", "license": "CC BY-SA 4.0",
        })(),
    )
    monkeypatch.setattr(
        wapor_v3,
        "_read_raster_metadata",
        lambda url: {"unit": "mm/dekad", "scale_factor": 0.2, "offset": 0.0, "is_tiled": True},
    )
    monkeypatch.setattr("app.geospatial.preprocessing.read_scene_window", lambda **kwargs: Reading())
    monkeypatch.setattr(
        "app.geospatial.preprocessing.field_mask_for_window",
        lambda **kwargs: np.array([[True]]),
    )
    result = wapor_v3.WaPORV3Client().read_field_window(
        mapset_code="L2-T-D",
        raster={
            "code": "WAPOR-3.L2-T-D.2025-01-D1",
            "download_url": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/sample.tif",
            "unit": "mm/day",
            "scale_factor": 0.1,
            "offset": 0.0,
        },
        geometry_geojson={"type": "Polygon", "coordinates": []},
    )
    # The API agrees with the catalogue, but the GeoTIFF disagrees. Do not
    # accept the first source and silently ignore the second.
    assert result.scale_factor is None
    assert result.unit is None
    assert result.scaled_mean is None


def test_malformed_catalogue_scale_and_unit_are_not_replaced_by_defaults(monkeypatch):
    class Reading:
        arrays = {"wapor": np.array([[2.0]])}
        crs = "EPSG:32636"
        transform = object()
        width = 1
        height = 1

    monkeypatch.setattr(
        wapor_v3,
        "get_product",
        lambda code: type("Product", (), {
            "resolution_m": 100, "unit": "mm/day", "scale_factor": 0.1,
            "metadata_reference": "https://example.org/spec", "license": "CC BY-SA 4.0",
        })(),
    )
    monkeypatch.setattr(
        wapor_v3,
        "_read_raster_metadata",
        lambda url: {"unit": None, "scale_factor": None, "offset": None, "is_tiled": True},
    )
    monkeypatch.setattr("app.geospatial.preprocessing.read_scene_window", lambda **kwargs: Reading())
    monkeypatch.setattr(
        "app.geospatial.preprocessing.field_mask_for_window",
        lambda **kwargs: np.array([[True]]),
    )
    result = wapor_v3.WaPORV3Client().read_field_window(
        mapset_code="L2-T-D",
        raster={
            "code": "WAPOR-3.L2-T-D.2025-01-D1",
            "download_url": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/sample.tif",
            "unit": 123,
            "scale_factor": "not-a-number",
            "offset": 0.0,
        },
        geometry_geojson={"type": "Polygon", "coordinates": []},
    )
    assert result.scale_factor is None
    assert result.unit is None
    assert result.scaled_mean is None


@pytest.mark.parametrize(
    "url",
    [
        "https://storage.googleapis.com/fao-gismgr-wapor-3-data/sample.tif?X-Goog-Signature=secret",
        "https://storage.googleapis.com/fao-gismgr-wapor-3-data/sample.tif#fragment",
    ],
)
def test_raster_url_rejects_signed_or_fragmented_asset_references(url):
    assert not wapor_v3._safe_raster_url(url)


def test_read_field_window_accepts_canonical_period_code(monkeypatch):
    class Reading:
        arrays = {"wapor": np.array([[1.0]])}
        crs = "EPSG:32636"
        transform = object()
        width = 1
        height = 1

    monkeypatch.setattr(
        wapor_v3,
        "get_product",
        lambda code: type("Product", (), {
            "resolution_m": 100, "unit": "mm/day", "scale_factor": 0.1,
            "metadata_reference": "https://example.org/spec", "license": "CC BY-SA 4.0",
        })(),
    )
    monkeypatch.setattr(
        wapor_v3,
        "_read_raster_metadata",
        lambda url: {"unit": "mm/day", "scale_factor": 0.1, "offset": 0.0, "nodata": None, "is_tiled": True},
    )
    monkeypatch.setattr("app.geospatial.preprocessing.read_scene_window", lambda **kwargs: Reading())
    monkeypatch.setattr(
        "app.geospatial.preprocessing.field_mask_for_window",
        lambda **kwargs: np.array([[True]]),
    )
    result = wapor_v3.WaPORV3Client().read_field_window(
        mapset_code="L2-T-D",
        raster={
            "code": "WAPOR-3.L2-T-D.2025-01-D1",
            "period_code": "2025-01-D1",
            "download_url": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/sample.tif",
        },
        geometry_geojson={"type": "Polygon", "coordinates": []},
    )
    assert result.valid_pixel_count == 1
    assert result.period_code == "2025-01-D1"
