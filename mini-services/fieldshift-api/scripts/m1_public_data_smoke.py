"""Live, public-only M1 metadata and WaPOR raster-window acceptance probe.

Uses a small non-sensitive public AOI near Mallawi, Egypt. NASA HLS and CDSE
checks are metadata discovery only; protected asset reads are a separate gate.
WaPOR is public and is checked through one bounded COG window. No secrets,
farmer data, or production database are used.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.data_platform.contracts.observations import AreaOfInterest
from app.data_platform.providers.nasa_hls.catalog import search_scenes
from app.data_platform.providers.nasa_hls.provider import NasaHlsProvider, _record_to_scene_record
from app.data_platform.providers.sentinel2.provider import Sentinel2StacProvider
from app.data_platform.providers.wapor_v3 import WaPORV3Client
from app.intelligence.config import ai_settings
from app.intelligence.orchestration.provider_diagnostics import probe_provider
from pyproj import Geod

AOI = {
    "type": "Polygon",
    "coordinates": [[
        [30.8000, 27.7000],
        [30.8400, 27.7000],
        [30.8400, 27.7400],
        [30.8000, 27.7400],
        [30.8000, 27.7000],
    ]],
}
START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)



_SAFE_PROVIDER_REASON_CODES = {
    "unsupported_s3_asset_host",
    "cdse_s3_credentials_missing",
    "missing_sentinel2_radiometric_offset",
    "RasterioIOError",
    "CRSError",
    "ValueError",
    "HTTPStatusError",
    "ConnectError",
    "ReadTimeout",
    "TimeoutException",
    "CPLE_OpenFailedError",
    "CPLE_AppDefinedError",
    "KeyError",
    "RuntimeError",
}


def _safe_provider_failure(exc: Exception) -> dict[str, str]:
    """Return allowlisted failure identifiers only; never serialize messages/details."""
    result = {"error_type": type(exc).__name__}
    details = getattr(exc, "details", None)
    if isinstance(details, list):
        for item in details[:5]:
            if not isinstance(item, dict):
                continue
            reason = item.get("reason")
            if isinstance(reason, str) and reason in _SAFE_PROVIDER_REASON_CODES:
                result["reason_code"] = reason
                break
    return result


def _safe_warning_reason_codes(warnings: list[str]) -> list[str]:
    """Extract only allowlisted exception class names from provider warning strings."""
    found: set[str] = set()
    for warning in warnings[:20]:
        if not isinstance(warning, str):
            continue
        for reason in _SAFE_PROVIDER_REASON_CODES:
            if re.search(r"\\(" + re.escape(reason) + r"\\)", warning):
                found.add(reason)
    return sorted(found)


def main() -> int:
    evidence: dict[str, object] = {
        "test": "m1_public_data_smoke",
        "aoi": "public_mallawi_egypt_test_polygon",
        "date_range": [START.isoformat(), END.isoformat()],
        "secrets_used": bool(
            settings.earthdata_bearer_token
            or (settings.cdse_s3_access_key and settings.cdse_s3_secret_key)
            or ai_settings.gemini_api_key.get_secret_value()
        ),
    }
    failures: list[str] = []

    try:
        scenes, warnings = search_scenes(
            geometry_geojson=AOI,
            start=START,
            end=END,
            collections=["HLSL30_2.0", "HLSS30_2.0"],
            max_cloud_cover=100.0,
            page_size=10,
            max_pages=1,
        )
        evidence["nasa_hls"] = {
            "status": "metadata_verified" if scenes else "no_items",
            "scene_count": len(scenes),
            "collections": sorted({scene.collection_id for scene in scenes}),
            "sample_scene_id": scenes[0].scene_id,
            "sample_collection": scenes[0].collection,
            "latest_acquisition": max(
                (scene.acquired_at.isoformat() for scene in scenes), default=None
            ),
            "warning_count": len(warnings),
            "warning_reason_codes": _safe_warning_reason_codes(warnings),
            "protected_asset_read": "not_attempted_no_earthdata_secret",
        }
        if not scenes:
            failures.append("NASA HLS public metadata discovery returned no scenes")
        if settings.earthdata_bearer_token and scenes:
            try:
                best_scene = min(
                    scenes,
                    key=lambda scene: scene.cloud_cover_pct if scene.cloud_cover_pct is not None else 101.0,
                )
                scene_record = _record_to_scene_record(best_scene)
                acquired = best_scene.acquired_at
                result = NasaHlsProvider().fetch_observations(
                    area_of_interest=AreaOfInterest(geometry_geojson=AOI),
                    variables=["ndvi"],
                    start=acquired - timedelta(seconds=1),
                    end=acquired + timedelta(seconds=1),
                    options={
                        "scene_ids": [best_scene.scene_id],
                        "scene_records": {best_scene.scene_id: scene_record},
                    },
                )
                evidence["nasa_hls"]["protected_asset_read"] = {
                    "status": "asset_window_verified" if result.observations else "no_valid_observations",
                    "scene_id": best_scene.scene_id,
                    "observation_count": len(result.observations),
                    "warning_count": len(result.warnings),
                    "coverage": result.coverage,
                }
                if not result.observations:
                    failures.append("NASA HLS protected asset read returned no valid observations")
            except Exception as exc:
                evidence["nasa_hls"]["protected_asset_read"] = {
                    "status": "failed",
                    **_safe_provider_failure(exc),
                }
                failures.append("NASA HLS protected asset-window read failed")
        else:
            evidence["nasa_hls"]["protected_asset_read"] = "blocked_missing_earthdata_bearer_token"
    except Exception as exc:
        evidence["nasa_hls"] = {"status": "failed", "error_type": type(exc).__name__}
        failures.append("NASA HLS metadata discovery failed")

    try:
        items = Sentinel2StacProvider().search_items(
            geometry_geojson=AOI,
            start=START,
            end=END,
            max_cloud_cover=100.0,
            limit=10,
        )
        evidence["copernicus_sentinel2"] = {
            "status": "metadata_verified" if items else "no_items",
            "item_count": len(items),
            "sample_item_id": str(items[0].get("id")) if items else None,
            "collections": sorted({
                str(item.get("collection"))
                for item in items
                if isinstance(item, dict) and item.get("collection")
            }),
            "latest_acquisition": max(
                (
                    str((item.get("properties") or {}).get("datetime"))
                    for item in items
                    if isinstance(item, dict)
                    and isinstance(item.get("properties"), dict)
                    and (item.get("properties") or {}).get("datetime")
                ),
                default=None,
            ),
            "protected_asset_read": "not_attempted_no_cdse_s3_keys",
        }
        if not items:
            failures.append("CDSE Sentinel-2 public metadata discovery returned no items")
        if settings.cdse_s3_access_key and settings.cdse_s3_secret_key:
            try:
                result = Sentinel2StacProvider().fetch_observations(
                    area_of_interest=AreaOfInterest(geometry_geojson=AOI),
                    variables=["ndvi"],
                    start=datetime(2025, 12, 28, 0, 0, tzinfo=UTC),
                    end=datetime(2025, 12, 29, 0, 0, tzinfo=UTC),
                    options={"max_cloud_cover": 100.0},
                )
                evidence["copernicus_sentinel2"]["protected_asset_read"] = {
                    "status": "asset_window_verified" if result.observations else "no_valid_observations",
                    "observation_count": len(result.observations),
                    "warning_count": len(result.warnings),
                    "coverage": result.coverage,
                }
                if not result.observations:
                    failures.append("CDSE protected asset read returned no valid observations")
            except Exception as exc:
                evidence["copernicus_sentinel2"]["protected_asset_read"] = {
                    "status": "failed",
                    **_safe_provider_failure(exc),
                }
                failures.append("CDSE protected S3 asset-window read failed")
        else:
            evidence["copernicus_sentinel2"]["protected_asset_read"] = "blocked_missing_cdse_s3_keys"
    except Exception as exc:
        evidence["copernicus_sentinel2"] = {
            "status": "failed",
            "error_type": type(exc).__name__,
        }
        failures.append("CDSE Sentinel-2 metadata discovery failed")

    try:
        client = WaPORV3Client(timeout_seconds=30)
        mapsets = client.list_mapsets()
        mapset_codes = {
            str(item.get("code")) for item in mapsets if isinstance(item, dict)
        }
        if "L2-AETI-D" not in mapset_codes:
            raise RuntimeError("expected Egypt L2-AETI-D mapset is absent")
        rasters = client.list_rasters("L2-AETI-D")
        if not rasters:
            raise RuntimeError("no Egypt L2-AETI-D rasters are available")
        selected = max(rasters, key=lambda item: str(item.get("period_code", "")))
        window = client.read_field_window(
            mapset_code="L2-AETI-D",
            raster=selected,
            geometry_geojson=AOI,
            max_window_mb=32,
        )
        import rasterio

        with rasterio.open(selected["download_url"]) as dataset:
            if dataset.crs is None:
                raise RuntimeError("WaPOR COG has no CRS")
            if not dataset.is_tiled:
                raise RuntimeError("WaPOR raster is not internally tiled")
            x_resolution, y_resolution = dataset.res
            if dataset.crs.is_geographic:
                geod = Geod(ellps="WGS84")
                lon0 = (30.8000 + 30.8400) / 2
                lat0 = (27.7000 + 27.7400) / 2
                _, _, x_metres = geod.inv(lon0, lat0, lon0 + x_resolution, lat0)
                _, _, y_metres = geod.inv(lon0, lat0, lon0, lat0 + y_resolution)
            elif dataset.crs.is_projected:
                factor = dataset.crs.axis_info[0].unit_conversion_factor or 1.0
                x_metres = x_resolution * factor
                y_metres = y_resolution * factor
            else:
                raise RuntimeError("WaPOR COG CRS units cannot be converted to metres")
            actual_resolution_m_xy = [abs(float(x_metres)), abs(float(y_metres))]
            actual_crs = dataset.crs.to_string()
            raster_nodata = dataset.nodata
            raster_is_tiled = dataset.is_tiled
            raster_overviews = dataset.overviews(1)
        evidence["wapor_egypt_l2_aeti"] = {
            "status": "asset_window_verified",
            "mapset_count": len(mapset_codes),
            "available_raster_count": len(rasters),
            "period_code": window.period_code,
            "crs": window.crs,
            "actual_raster_crs": actual_crs,
            "catalogue_resolution_m": window.resolution_m,
            "actual_resolution_m_xy": actual_resolution_m_xy,
            "raster_nodata_value": raster_nodata,
            "raster_overview_levels": raster_overviews,
            "unit": window.unit,
            "scale_factor": window.scale_factor,
            "offset": window.offset,
            "valid_pixel_count": window.valid_pixel_count,
            "nodata_pixel_count": window.nodata_pixel_count,
            "raw_mean": window.raw_mean,
            "scaled_mean": window.scaled_mean,
            "tiled": raster_is_tiled,
            "overview_levels": list(window.overview_levels),
            "license": window.license,
        }
        if window.valid_pixel_count < 1:
            failures.append("WaPOR raster window contained no valid pixels")
        if not window.crs:
            failures.append("WaPOR raster CRS metadata is missing")
        if actual_crs != window.crs:
            failures.append("WaPOR provider CRS differs from the source GeoTIFF CRS")
        if not all(80.0 <= value <= 120.0 for value in actual_resolution_m_xy):
            failures.append("WaPOR source GeoTIFF pixel size is inconsistent with the 100 m L2 product spec")
        if window.unit != "mm/day" or window.scale_factor != 0.1 or window.offset not in (0.0, None):
            failures.append("WaPOR AETI unit/scale/offset did not match the versioned product spec")
        if window.scaled_mean is None:
            failures.append("WaPOR scaled physical summary was withheld by metadata validation")
    except Exception as exc:
        evidence["wapor_egypt_l2_aeti"] = {
            "status": "failed",
            "error_type": type(exc).__name__,
        }
        failures.append("WaPOR Egypt L2 COG-window validation failed")

    if ai_settings.gemini_api_key.get_secret_value():
        try:
            gemini = asyncio.run(probe_provider("gemini"))
            evidence["gemini_primary_probe"] = gemini
            if gemini.get("status") != "live_verified":
                failures.append("Gemini primary provider live probe did not return live_verified")
        except Exception as exc:
            evidence["gemini_primary_probe"] = {"status": "failed", "error_type": type(exc).__name__}
            failures.append("Gemini primary provider live probe failed")
    else:
        evidence["gemini_primary_probe"] = "blocked_missing_gemini_api_key"

    evidence["failures"] = failures
    evidence["overall_status"] = "public_checks_passed" if not failures else "failed"
    evidence["m1_acceptance_status"] = "not_closed"
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
