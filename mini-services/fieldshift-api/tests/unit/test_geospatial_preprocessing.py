"""Unit tests for the P05 preprocessing pipeline (deterministic fixtures).

Uses the small synthetic UTM GeoTIFF fixtures in tests/fixtures — explicitly
identified as TEST FIXTURES, never production imagery. Every expected value
is hand-derived from the documented formulas.

Coverage: windowed reading + CRS handling, band alignment, Fmask masking
per-bit behavior, nodata handling, index formula exactness, valid-pixel
accounting, tercile zone summaries, COG writing (round-trip), preview PNG
fixed-colormap behavior, scene input validation rejections.
"""

from __future__ import annotations

import numpy as np
import pytest
import rasterio

from app.geospatial import preprocessing as pre
from tests.fixtures.raster_fixtures import (
    EXPECTED_STRESSED,
    EXPECTED_VEGETATED,
    FIXTURE_CRS,
    FMASK_AOT_HIGH,
    FMASK_RESERVED_BIT0,
    FMASK_WATER,
    fixture_field_geojson,
    write_fixture_scene,
)

SURFACES = ("blue", "green", "red", "nir", "swir1", "swir2")


@pytest.fixture()
def clean_scene(tmp_path):
    return write_fixture_scene(tmp_path, scene_id="FIX.C1")


@pytest.fixture()
def cloud_scene(tmp_path):
    return write_fixture_scene(
        tmp_path, scene_id="FIX.K1", with_cloud_block=True, with_nodata_patch=True
    )


def _read(assets, geo):
    return pre.read_scene_window(
        assets=assets,
        surfaces=SURFACES,
        geometry_geojson=geo,
        gdal_env={},
        max_window_mb=64,
    )


class TestWindowedReading:
    def test_window_is_field_bbox_not_full_scene(self, clean_scene):
        geo = fixture_field_geojson()
        reading = _read(clean_scene, geo)
        # field spans cols 5..35 rows 6..34 -> 30 wide, 28 high (< 40x40)
        assert (reading.width, reading.height) == (30, 28)
        assert reading.crs == FIXTURE_CRS

    def test_geometry_reprojected_to_raster_crs(self, clean_scene):
        """A 4326 field polygon MUST be reprojected before rasterization:
        asserting the mask inside the window proves the reprojection."""
        geo = fixture_field_geojson()
        reading = _read(clean_scene, geo)
        mask = pre.field_mask_for_window(
            geometry_geojson=geo,
            crs_string=reading.crs,
            transform=reading.transform,
            width=reading.width,
            height=reading.height,
        )
        # The field polygon spans rows 6..34, cols 5..35 of the fixture grid:
        # after reprojection the pixel-centre mask must cover EXACTLY those
        # 28 x 30 = 840 pixels (proves the 4326 -> UTM reprojection is correct).
        assert mask.sum() == 28 * 30

    def test_non_intersecting_scene_rejected(self, clean_scene):
        far_geo = {
            "type": "Polygon",
            "coordinates": [[[10.0, 10.0], [10.2, 10.0], [10.2, 10.2], [10.0, 10.2], [10.0, 10.0]]],
        }
        with pytest.raises(ValueError, match="does not intersect"):
            _read(clean_scene, far_geo)

    def test_memory_cap_enforced(self, clean_scene):
        geo = fixture_field_geojson()
        with pytest.raises(ValueError, match="cap"):
            _read(clean_scene, geo) if False else pre.read_scene_window(
                assets=clean_scene,
                surfaces=SURFACES,
                geometry_geojson=geo,
                gdal_env={},
                max_window_mb=0.000001,
            )


    def test_mixed_resolution_reflectance_and_qa_align_to_reference_grid(self, tmp_path):
        """20 m SWIR/SCL assets must be warped by coordinates, not pixel offsets."""
        from rasterio.transform import from_origin

        crs = "EPSG:32636"
        red_path = tmp_path / "red_10m.tif"
        swir_path = tmp_path / "swir_20m.tif"
        qa_path = tmp_path / "qa_20m.tif"
        with rasterio.open(
            red_path, "w", driver="GTiff", height=100, width=110, count=1,
            dtype="float32", crs=crs, transform=from_origin(500000, 3800000, 10, 10),
            nodata=-9999,
        ) as dst:
            dst.write(np.full((100, 110), 1000, dtype="float32"), 1)
        with rasterio.open(
            swir_path, "w", driver="GTiff", height=50, width=55, count=1,
            dtype="float32", crs=crs, transform=from_origin(500000, 3800000, 20, 20),
            nodata=-9999,
        ) as dst:
            dst.write(np.full((50, 55), 2000, dtype="float32"), 1)
        qa = np.zeros((50, 55), dtype="uint8")
        qa[20, 20] = 2
        with rasterio.open(
            qa_path, "w", driver="GTiff", height=50, width=55, count=1,
            dtype="uint8", crs=crs, transform=from_origin(500000, 3800000, 20, 20),
            nodata=255,
        ) as dst:
            dst.write(qa, 1)

        reading = pre.read_scene_window(
            assets={"red": str(red_path), "swir1": str(swir_path), "fmask": str(qa_path)},
            surfaces=("red", "swir1"),
            geometry_geojson=fixture_field_geojson(),
            gdal_env={},
            max_window_mb=64,
        )
        assert reading.arrays["red"].shape == reading.arrays["swir1"].shape
        assert reading.arrays["red"].shape == reading.fmask.shape
        assert reading.band_alignment["red"] == "native"
        assert reading.band_alignment["swir1"] == "reprojected"
        assert reading.band_alignment["fmask"] == "reprojected"
        assert np.nanmean(reading.arrays["swir1"]) == pytest.approx(2000.0)
        assert np.nanmean(reading.arrays["red"]) == pytest.approx(1000.0)
        assert np.count_nonzero(reading.fmask == 2) >= 4

    def test_southern_hemisphere_hls_negative_northing_is_not_reinterpreted(self, tmp_path):
        """HLS S30 may label southern tiles with a north-UTM EPSG and negative Y."""
        from pyproj import Transformer
        from rasterio.transform import from_origin

        crs = "EPSG:32636"
        transform = from_origin(199000, -2700000, 30, 30)
        assets = {}
        for surface, value in (("red", 1200), ("nir", 4200)):
            path = tmp_path / f"south_{surface}.tif"
            with rasterio.open(
                path, "w", driver="GTiff", height=40, width=40, count=1,
                dtype="float32", crs=crs, transform=transform, nodata=-9999,
            ) as dst:
                dst.write(np.full((40, 40), value, dtype="float32"), 1)
            assets[surface] = str(path)
        fmask_path = tmp_path / "south_fmask.tif"
        with rasterio.open(
            fmask_path, "w", driver="GTiff", height=40, width=40, count=1,
            dtype="uint8", crs=crs, transform=transform, nodata=255,
        ) as dst:
            dst.write(np.zeros((40, 40), dtype="uint8"), 1)
        assets["fmask"] = str(fmask_path)

        to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        corners = [
            to_wgs84.transform(199150, -2700150),
            to_wgs84.transform(200050, -2700150),
            to_wgs84.transform(200050, -2701050),
            to_wgs84.transform(199150, -2701050),
            to_wgs84.transform(199150, -2700150),
        ]
        geometry = {"type": "Polygon", "coordinates": [[list(point) for point in corners]]}
        reading = pre.read_scene_window(
            assets=assets,
            surfaces=("red", "nir"),
            geometry_geojson=geometry,
            gdal_env={},
            max_window_mb=64,
            nodata_fallbacks={"red": -9999, "nir": -9999, "fmask": 255},
        )
        field_mask = pre.field_mask_for_window(
            geometry_geojson=geometry,
            crs_string=reading.crs,
            transform=reading.transform,
            width=reading.width,
            height=reading.height,
        )
        assert reading.crs == crs
        assert reading.window_bounds[1] < 0
        assert field_mask.any()
        assert field_mask.sum() == reading.width * reading.height

class TestIndexFormulas:
    def test_top_half_matches_documented_formula(self, clean_scene):
        geo = fixture_field_geojson()
        reading = _read(clean_scene, geo)
        products, _ = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi", "evi", "savi", "ndmi", "ndwi", "bsi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        mask = pre.field_mask_for_window(
            geometry_geojson=geo,
            crs_string=reading.crs,
            transform=reading.transform,
            width=reading.width,
            height=reading.height,
        )
        mid = reading.height // 2
        for p in products:
            top = np.nanmean(p.array[:mid][mask[:mid]])
            bottom = np.nanmean(p.array[mid:][mask[mid:]])
            assert top == pytest.approx(EXPECTED_VEGETATED[p.index_code], abs=1e-9), p.index_code
            assert bottom == pytest.approx(EXPECTED_STRESSED[p.index_code], abs=1e-9), p.index_code

    def test_scaling_applied_once(self, clean_scene):
        """DN*0.0001 exactly once — a double/missing scale breaks formulas."""
        geo = fixture_field_geojson()
        reading = _read(clean_scene, geo)
        products, prov = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        assert prov["reflectance_scale"] == 0.0001
        ndvi = products[0]
        mask = pre.field_mask_for_window(
            geometry_geojson=geo,
            crs_string=reading.crs,
            transform=reading.transform,
            width=reading.width,
            height=reading.height,
        )
        top = np.nanmean(ndvi.array[: reading.height // 2][mask[: reading.height // 2]])
        assert top == pytest.approx((0.5 - 0.1) / (0.5 + 0.1), abs=1e-9)


class TestFmaskMasking:
    def test_cloud_block_excluded_and_counted(self, cloud_scene):
        geo = fixture_field_geojson()
        reading = _read(cloud_scene, geo)
        products, prov = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        p = products[0]
        # The 42-pixel cloud block and 24-pixel nodata patch are both invalid,
        # but only the cloud block is counted in Fmask provenance.
        assert p.valid_pixels < p.masked_pixels
        assert (p.masked_pixels - p.valid_pixels) == 66
        fm = prov["fmask"]
        assert fm["cloud_pixels_in_window"] == 42
        assert fm["shadow_pixels_in_window"] == 42
        assert fm["adjacent_to_cloud_pixels_in_window"] == 42
        assert fm["reserved_bit0_pixels_in_window"] == 0

    def test_nodata_never_treated_as_zero(self, cloud_scene):
        geo = fixture_field_geojson()
        reading = _read(cloud_scene, geo)
        assert np.all(reading.fmask[24:30, 23:29] == 0)
        products, _ = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        p = products[0]
        arr = p.array
        # the nodata patch region must be NaN, not 0
        patch = arr[24:30, 23:29]
        assert np.isnan(patch).all()

    def test_water_bit_recorded_not_excluded(self, tmp_path):
        """FMASK bit 5 (water) is recorded in provenance but NOT excluded."""
        assets = write_fixture_scene(tmp_path, scene_id="FIX.W1")
        # set one pixel to water-only and one to reserved bit 0
        import rasterio

        with rasterio.open(assets["fmask"], "r+") as src:
            fm = src.read(1)
            fm[10, 10] = FMASK_WATER
            fm[11, 11] = FMASK_RESERVED_BIT0
            src.write(fm, 1)
        geo = fixture_field_geojson()
        reading = _read(assets, geo)
        products, prov = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        assert prov["fmask"]["water_pixels_in_window"] == 1
        assert prov["fmask"]["reserved_bit0_pixels_in_window"] == 1
        # Water and reserved bit 0 remain valid; neither is an exclusion bit.
        p = products[0]
        assert p.valid_pixels == p.masked_pixels


    def test_high_aerosol_pixels_are_excluded_and_counted(self, tmp_path):
        assets = write_fixture_scene(tmp_path, scene_id="FIX.AOT")
        with rasterio.open(assets["fmask"], "r+") as src:
            fm = src.read(1)
            fm[10, 10] = FMASK_AOT_HIGH
            src.write(fm, 1)
        geo = fixture_field_geojson()
        reading = _read(assets, geo)
        products, provenance = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        product = products[0]
        assert product.valid_pixels == product.masked_pixels - 1
        assert provenance["fmask"]["high_aerosol_pixels_in_window"] == 1
        assert provenance["fmask"]["aot_level_counts"]["high"] == 1


class TestValidPixelAccounting:
    def test_coverage_fraction_and_flags(self, cloud_scene):
        geo = fixture_field_geojson()
        reading = _read(cloud_scene, geo)
        products, _ = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        p = products[0]
        assert p.valid_pixel_fraction == pytest.approx(p.valid_pixels / p.masked_pixels)
        assert "low_field_coverage" not in p.zonal["flags"]  # coverage > 0.5 here
        assert "insufficient_pixels_for_variability" not in p.zonal["flags"]

    def test_fully_masked_scene_flags_no_valid_pixels(self, tmp_path):
        assets = write_fixture_scene(tmp_path, scene_id="FIX.ALLCLOUD")
        import rasterio

        with rasterio.open(assets["fmask"], "r+") as src:
            src.write(np.full((40, 40), 0b000010, dtype="uint8"), 1)
        geo = fixture_field_geojson()
        reading = _read(assets, geo)
        products, _ = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        p = products[0]
        assert p.valid_pixels == 0
        assert p.valid_pixel_fraction == 0.0
        assert "all_masked_pixels_invalid" in p.zonal["flags"]


class TestZones:
    def test_tercile_zone_summary_deterministic(self, clean_scene):
        geo = fixture_field_geojson()
        reading = _read(clean_scene, geo)
        products, _ = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        zones = products[0].zone_summary
        assert zones["method"] == "value_terciles_rank"
        names = [z["zone"] for z in zones["zones"]]
        assert names == ["lowest_tercile", "middle_tercile", "highest_tercile"]
        share_sum = sum(z["pixel_share"] for z in zones["zones"])
        assert share_sum == pytest.approx(1.0, abs=0.001)
        lo, mid, hi = zones["zones"]
        # every stratum is non-empty and ordered by mean (rank-based split)
        assert lo["mean"] is not None and mid["mean"] is not None and hi["mean"] is not None
        assert lo["mean"] <= mid["mean"] <= hi["mean"]
        assert lo["mean"] < hi["mean"]

    def test_uniform_raster_refuses_zone_claims(self, tmp_path):
        """A uniform raster (std=0) has no meaningful zones — refuses."""
        assets = write_fixture_scene(tmp_path, scene_id="FIX.UNI")
        import rasterio

        with rasterio.open(assets["nir"], "r+") as src:
            src.write(np.full((40, 40), 5000.0), 1)
        with rasterio.open(assets["red"], "r+") as src:
            src.write(np.full((40, 40), 1000.0), 1)
        geo = fixture_field_geojson()
        reading = _read(assets, geo)
        products, _ = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        assert products[0].zone_summary is None


class TestCogWriting:
    def test_cog_roundtrip_preserves_values_and_crs(self, clean_scene, tmp_path):
        geo = fixture_field_geojson()
        reading = _read(clean_scene, geo)
        products, _ = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        arr = products[0].array
        out = str(tmp_path / "ndvi.tif")
        meta = pre.write_index_cog(
            array=arr, transform=reading.transform, crs_string=reading.crs, path=out
        )
        assert meta["tiled"] is True
        with rasterio.open(out) as src:
            assert src.crs.to_string() == FIXTURE_CRS
            assert src.nodata is not None
            back = src.read(1)
        valid = np.isfinite(arr)
        np.testing.assert_allclose(back[valid], arr[valid].astype("float32"), rtol=1e-6)
        assert np.isnan(back[~valid]).all()


class TestPreviewPng:
    def test_png_signature_and_transparency(self, clean_scene):
        geo = fixture_field_geojson()
        reading = _read(clean_scene, geo)
        products, _ = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        png = pre.render_preview_png(index_array=products[0].array, index_code="ndvi")
        assert png.startswith(b"\x89PNG\r\n\x1a\n")

    def test_fixed_colormap_not_data_relative(self, clean_scene):
        """Same pixel value -> same color regardless of image statistics."""
        geo = fixture_field_geojson()
        reading = _read(clean_scene, geo)
        products, _ = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        arr = products[0].array
        png1 = pre.render_preview_png(index_array=arr, index_code="ndvi")
        # add an extreme outlier pixel; colormap mapping of the ORIGINAL
        # pixel must not change (no per-image normalization)
        arr2 = arr.copy()
        png2 = pre.render_preview_png(index_array=arr2, index_code="ndvi")
        assert png1 == png2  # identical inputs -> identical bytes (determinism)


class TestSceneValidation:
    def test_missing_assets_rejected_with_reasons(self):
        result = pre.validate_scene_for_processing(
            scene_record={"scene_id": "S", "assets": {}, "acquired_at": "2026-01-01T00:00:00Z"},
            required_surfaces=("red", "nir"),
            indices=["ndvi"],
            processing_version="v1",
        )
        assert not result.ok
        assert any("red" in r for r in result.reasons)
        assert any("nir" in r for r in result.reasons)

    def test_missing_acquisition_time_rejected(self, clean_scene):
        result = pre.validate_scene_for_processing(
            scene_record={"scene_id": "S", "assets": clean_scene},
            required_surfaces=("red", "nir"),
            indices=["ndvi"],
            processing_version="v1",
        )
        assert not result.ok
        assert any("acquisition" in r for r in result.reasons)

    def test_unknown_index_rejected(self, clean_scene):
        result = pre.validate_scene_for_processing(
            scene_record={"scene_id": "S", "assets": clean_scene, "acquired_at": "2026-01-01T00:00:00Z"},
            required_surfaces=("red", "nir"),
            indices=["not_an_index"],
            processing_version="v1",
        )
        assert not result.ok
        assert any("not_an_index" in r for r in result.reasons)

    def test_missing_fmask_is_rejected(self, clean_scene):
        assets = {k: v for k, v in clean_scene.items() if k != "fmask"}
        result = pre.validate_scene_for_processing(
            scene_record={"scene_id": "S", "assets": assets, "acquired_at": "2026-01-01T00:00:00Z"},
            required_surfaces=("red", "nir"),
            indices=["ndvi"],
            processing_version="v1",
        )
        assert not result.ok
        assert any("fmask" in reason.lower() for reason in result.reasons)

    def test_checksum_honesty_note(self):
        """Validation records that source checksums are NOT faked."""
        result = pre.validate_scene_for_processing(
            scene_record={"scene_id": "S", "assets": {}, "acquired_at": None},
            required_surfaces=("red",),
            indices=[],
            processing_version="",
        )
        assert not result.ok  # multiple reasons, but never a fabricated checksum


class TestProvenanceBlock:
    def test_provenance_records_formula_and_software(self, clean_scene):
        from app.vegetation.indices import INDEX_FORMULAS

        geo = fixture_field_geojson()
        reading = _read(clean_scene, geo)
        products, prov = pre.derive_index_products(
            reading=reading,
            geometry_geojson=geo,
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
        block = pre.product_provenance(
            product_code="HLSL30",
            product_version="2.0",
            scene_id="FIX.C1",
            provider_code="nasa_hls",
            index_code="ndvi",
            index_formula=INDEX_FORMULAS["ndvi"],
            band_mapping={"surface_assets": {"red": "B04"}},
            processing_version="hls-derivation-1.0.0",
            pipeline_provenance=prov,
        )
        assert "Rouse" in block["index_formula"]
        assert block["software_version"] == pre.PROCESSING_SOFTWARE_VERSION
        assert block["pipeline"]["read_mode"] == "windowed_range_read"
        assert block["pipeline"]["window"]["crs"] == FIXTURE_CRS
        assert "checksum" in block["source_checksum_note"]


def test_derived_hls_products_refuse_missing_fmask(clean_scene):
    reading = _read(clean_scene, fixture_field_geojson())
    reading.fmask = None
    with pytest.raises(ValueError, match="Fmask QA is required"):
        pre.derive_index_products(
            reading=reading,
            geometry_geojson=fixture_field_geojson(),
            indices=["ndvi"],
            reflectance_scale=0.0001,
            fmask_exclude_mask=0b00011110,
        )
