"""Contract tests for Sentinel-2 field-window alignment and radiometry."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import rasterio
import pytest
from rasterio.transform import from_origin

from app.core.config import Settings

from app.data_platform.providers.sentinel2.provider import (
    Sentinel2StacProvider,
    _gdal_env_options,
    _observations_from_item,
    _safe_asset_href_for_metadata,
)
from tests.fixtures.raster_fixtures import fixture_field_geojson


def _write_sentinel2_item(tmp_path, *, baseline="05.11", stac_radiometry=True, include_scl=True):
    crs = "EPSG:32636"
    transform_10m = from_origin(500000, 3800000, 10, 10)
    transform_20m = from_origin(500000, 3800000, 20, 20)
    spectral = {
        "B02_10m": (1000, 10, 110, transform_10m),
        "B03_10m": (2000, 10, 110, transform_10m),
        "B04_10m": (3000, 10, 110, transform_10m),
        "B08_10m": (7000, 10, 110, transform_10m),
        "B11_20m": (5000, 20, 55, transform_20m),
    }
    assets = {}
    for key, (value, resolution, width, transform) in spectral.items():
        height = 100 if resolution == 10 else 50
        path = tmp_path / f"{key}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="uint16",
            crs=crs,
            transform=transform,
            nodata=0,
        ) as dst:
            dst.write(np.full((height, width), value, dtype="uint16"), 1)
        asset = {"href": str(path)}
        if stac_radiometry:
            asset["raster:bands"] = [{"scale": 0.0001, "offset": -0.1, "nodata": 0}]
        assets[key] = asset

    if include_scl:
        scl_path = tmp_path / "SCL_20m.tif"
        scl = np.full((50, 55), 4, dtype="uint8")
        scl[20, 20] = 9  # high-probability cloud; nearest-neighbour to 10 m
        scl[21, 21] = 7  # unclassified
        scl[22, 22] = 11  # snow/ice
        with rasterio.open(
            scl_path,
            "w",
            driver="GTiff",
            height=50,
            width=55,
            count=1,
            dtype="uint8",
            crs=crs,
            transform=transform_20m,
            nodata=0,
        ) as dst:
            dst.write(scl, 1)
        assets["SCL_20m"] = {"href": str(scl_path)}

    return {
        "id": "S2A_TEST_FIELD_20240707",
        "properties": {
            "platform": "sentinel-2a",
            "datetime": "2024-07-07T10:00:00Z",
            "s2:processing_baseline": baseline,
        },
        "assets": assets,
    }


def _observations(item, variables=("ndvi", "ndmi")):
    return _observations_from_item(
        item=item,
        scene_id=item["id"],
        acquired_at=datetime(2024, 7, 7, 10, 0, tzinfo=UTC),
        cloud_cover=12.5,
        variables=list(variables),
        geometry_geojson=fixture_field_geojson(),
        options={},
        gdal_env={},
    )


def test_mixed_resolution_sentinel2_scene_is_aligned_and_baseline_scaled(tmp_path):
    item = _write_sentinel2_item(tmp_path, baseline="03.01")
    observations, warnings = _observations(item)

    assert warnings == []
    by_index = {obs.variable_code: obs for obs in observations}
    assert by_index["ndvi"].value == pytest.approx(0.5, abs=1e-6)
    assert by_index["ndmi"].value == pytest.approx(0.2, abs=1e-6)
    assert by_index["ndvi"].spatial_resolution_m == 10.0
    assert by_index["ndmi"].spatial_resolution_m == 20.0

    ndmi_meta = by_index["ndmi"].metadata
    assert ndmi_meta["raster_window"]["reference_grid"] == "red_10m"
    assert ndmi_meta["raster_window"]["band_alignment"]["swir1"] == "reprojected"
    assert ndmi_meta["raster_window"]["band_alignment"]["fmask"] == "reprojected"
    assert ndmi_meta["radiometry"]["red"]["offset"] == -0.1
    assert ndmi_meta["radiometry"]["red"]["offset_source"] == "stac_raster_bands"
    assert ndmi_meta["zonal"]["valid_pixels"] < ndmi_meta["zonal"]["masked_pixels"]


def test_processing_baseline_supplies_offset_when_asset_tags_are_absent(tmp_path):
    item = _write_sentinel2_item(tmp_path, stac_radiometry=False, baseline="05.11")
    observations, warnings = _observations(item, variables=("ndvi",))

    assert warnings == []
    ndvi = observations[0]
    assert ndvi.value == pytest.approx(0.5, abs=1e-6)
    assert ndvi.metadata["radiometry"]["red"]["offset"] == -0.1
    assert ndvi.metadata["radiometry"]["red"]["offset_source"] == "processing_baseline"


def test_legacy_processing_baseline_uses_zero_offset(tmp_path):
    item = _write_sentinel2_item(tmp_path, stac_radiometry=False, baseline="03.01")
    observations, warnings = _observations(item, variables=("ndvi",))

    assert warnings == []
    ndvi = observations[0]
    assert ndvi.value == pytest.approx(0.4, abs=1e-6)
    assert ndvi.metadata["radiometry"]["red"]["offset"] == 0.0


def test_missing_offset_and_baseline_fails_closed(tmp_path):
    from app.core.errors import ProviderUnavailable

    item = _write_sentinel2_item(tmp_path, stac_radiometry=False)
    item["properties"].pop("s2:processing_baseline")
    with pytest.raises(ProviderUnavailable, match="no Sentinel-2 processing baseline"):
        _observations(item, variables=("ndvi",))


def test_scene_without_scl_is_skipped_instead_of_claiming_cloud_masking(tmp_path):
    item = _write_sentinel2_item(tmp_path, include_scl=False)
    observations, warnings = _observations(item, variables=("ndvi",))

    assert observations == []
    assert any("SCL quality asset missing" in warning for warning in warnings)


def test_gdal_auth_header_is_scoped_to_cdse_asset_hosts():
    headers = {"Authorization": "Bearer token"}
    cdse_asset = "https://eodata.dataspace.copernicus.eu/path/band.tif"
    external_asset = "https://planetarycomputer.microsoft.com/path/band.tif?sig=secret"

    assert _gdal_env_options({}) == {}
    assert _gdal_env_options(headers) == {}
    assert _gdal_env_options(headers, [cdse_asset]) == {
        "GDAL_HTTP_HEADERS": "Authorization: Bearer token\r\n"
    }
    assert _gdal_env_options(headers, [external_asset]) == {}
    assert _gdal_env_options(headers, [cdse_asset, external_asset]) == {}


def test_alternate_stac_provider_never_receives_cdse_credentials(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "sentinel2_stac_base_url", "https://planetarycomputer.microsoft.com/api/stac/v1")
    monkeypatch.setattr(settings, "cdse_username", "user")
    monkeypatch.setattr(settings, "cdse_password", "password")

    class ForbiddenClient:
        def post(self, *args, **kwargs):
            raise AssertionError("CDSE credentials must not be requested for an alternate STAC host")

    provider = Sentinel2StacProvider(client=ForbiddenClient())
    assert provider._auth_headers() == {}


def test_signed_asset_query_is_removed_before_metadata_persistence():
    href = "https://example.com/band.tif?sig=secret&token=private#fragment"
    assert _safe_asset_href_for_metadata(href) == "https://example.com/band.tif"
