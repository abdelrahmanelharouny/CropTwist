"""Read-only FAO WaPOR v3 catalogue and bounded tiled GeoTIFF field-window access.

The FAO v3 API is public and does not require a token. Raw raster statistics
are always retained; scaled summaries are added only when unit and scale are
supported by API metadata, GeoTIFF tags or the cited WaPOR product specification.
This module never invents canonical CropTwist variables.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.data_platform.providers.wapor_v3_catalog import get_product

API_ROOT = "https://data.apps.fao.org/gismgr/api/v2/catalog/workspaces/WAPOR-3/mapsets"
API_HOST = "data.apps.fao.org"
RASTER_HOSTS = frozenset({"storage.googleapis.com"})
_MAX_PAGES = 50
_MAX_RESPONSE_BYTES = 8_000_000
_CODE_RE = re.compile(r"^L[12]-[A-Z0-9-]{2,40}$")


class WaPORProviderError(RuntimeError):
    """Normalized provider failure without upstream response bodies."""


@dataclass(frozen=True)
class WaPORRasterWindow:
    mapset_code: str
    raster_code: str
    array: Any
    valid_pixel_count: int
    nodata_pixel_count: int
    raw_mean: float | None
    raw_median: float | None
    unit: str | None
    scale_factor: float | None
    offset: float | None
    scaled_mean: float | None
    scaled_median: float | None
    period_code: str | None
    metadata_reference: str
    license: str
    asset_layout: str | None
    overview_levels: tuple[int, ...]
    resolution_m: int
    crs: str
    source_url: str
    provider: str = "FAO WaPOR v3"


def _read_raster_metadata(url: str) -> dict[str, Any]:
    """Read lightweight GeoTIFF metadata without downloading the full raster."""
    import rasterio

    with rasterio.open(url) as dataset:
        tags = {key.casefold(): value for key, value in dataset.tags(1).items()}
        unit = dataset.units[0] if dataset.units else None
        if not unit or str(unit).strip().casefold() in {"1", "unitless", "unknown"}:
            unit = tags.get("unit") or tags.get("units")
        if isinstance(unit, str) and unit.strip().casefold() in {"1", "unitless", "unknown"}:
            unit = None
        scale_raw = tags.get("scale_factor") or tags.get("scale")
        offset_raw = tags.get("offset")
        try:
            scale = float(scale_raw) if scale_raw is not None else None
        except (TypeError, ValueError):
            scale = None
        try:
            offset = float(offset_raw) if offset_raw is not None else None
        except (TypeError, ValueError):
            offset = None
        image_structure = dataset.tags(ns="IMAGE_STRUCTURE")
        return {
            "unit": unit,
            "scale_factor": scale,
            "offset": offset,
            "nodata": dataset.nodata,
            "is_tiled": bool(dataset.is_tiled),
            "overview_levels": dataset.overviews(1),
            "layout": image_structure.get("LAYOUT"),
        }


class WaPORV3Client:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        client_factory: Any | None = None,
    ) -> None:
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))
        self._client_factory = client_factory or self._default_client

    @staticmethod
    def _default_client(timeout: httpx.Timeout) -> httpx.Client:
        return httpx.Client(timeout=timeout, follow_redirects=False)

    @staticmethod
    def _safe_api_url(url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != API_HOST or parsed.port not in (None, 443) or parsed.username or parsed.password:
            raise WaPORProviderError("FAO API pagination returned an untrusted URL")
        if not parsed.path.startswith("/gismgr/api/v2/catalog/workspaces/WAPOR-3/"):
            raise WaPORProviderError("FAO API pagination escaped the WaPOR v3 catalogue")
        return url

    @staticmethod
    def _response_items(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("response"), dict):
            raise WaPORProviderError("FAO API returned an invalid catalogue response")
        response = payload["response"]
        items = response.get("items")
        links = response.get("links") or []
        if not isinstance(items, list) or not isinstance(links, list):
            raise WaPORProviderError("FAO API returned an invalid catalogue page")
        if any(not isinstance(item, dict) for item in items):
            raise WaPORProviderError("FAO API returned an invalid catalogue item")
        return items, links

    def _collect(self, start_url: str) -> list[dict[str, Any]]:
        next_url: str | None = self._safe_api_url(start_url)
        collected: list[dict[str, Any]] = []
        visited: set[str] = set()
        with self._client_factory(self._timeout) as client:
            for _ in range(_MAX_PAGES):
                if next_url is None:
                    return collected
                next_url = self._safe_api_url(next_url)
                if next_url in visited:
                    raise WaPORProviderError("FAO API pagination loop detected")
                visited.add(next_url)
                try:
                    response = client.get(next_url)
                    response.raise_for_status()
                    if len(response.content) > _MAX_RESPONSE_BYTES:
                        raise WaPORProviderError("FAO API response exceeded the size limit")
                    payload = response.json()
                except WaPORProviderError:
                    raise
                except Exception:
                    raise WaPORProviderError("FAO API request failed") from None
                items, links = self._response_items(payload)
                collected.extend(items)
                if len(collected) > 100_000:
                    raise WaPORProviderError("FAO API catalogue exceeded the item limit")
                next_links = [link for link in links if isinstance(link, dict) and link.get("rel") == "next"]
                if not next_links:
                    return collected
                href = next_links[0].get("href")
                if not isinstance(href, str) or not href:
                    raise WaPORProviderError("FAO API returned an invalid next-page link")
                next_url = urljoin(next_url, href)
        raise WaPORProviderError("FAO API pagination exceeded the page limit")

    def list_mapsets(self) -> list[dict[str, Any]]:
        items = self._collect(API_ROOT)
        return [
            {"code": item.get("code"), "caption": item.get("caption")}
            for item in items
            if isinstance(item.get("code"), str)
        ]

    def list_rasters(self, mapset_code: str) -> list[dict[str, Any]]:
        code = mapset_code.strip().upper() if isinstance(mapset_code, str) else ""
        if not _CODE_RE.fullmatch(code):
            raise ValueError("mapset code is invalid")
        # Reject unknown products before constructing a provider URL.
        product = get_product(code)
        items = self._collect(f"{API_ROOT}/{code}/rasters")
        result: list[dict[str, Any]] = []
        for item in items:
            raster_code = item.get("code")
            download_url = item.get("downloadUrl")
            if not isinstance(raster_code, str) or not isinstance(download_url, str):
                continue
            parsed = urlsplit(download_url)
            if parsed.scheme != "https" or parsed.hostname not in RASTER_HOSTS or parsed.port not in (None, 443) or parsed.username or parsed.password:
                continue
            period_code = raster_code.split(".", 2)[-1]
            if not re.fullmatch(r"\d{4}-\d{2}-D[1-3]", period_code):
                continue
            if not raster_code.startswith(f"WAPOR-3.{code}."):
                continue
            result.append({
                "code": raster_code,
                "download_url": download_url,
                "unit": item.get("unit") if isinstance(item.get("unit"), str) else product.unit,
                "scale_factor": item.get("scale") if isinstance(item.get("scale"), (int, float)) else product.scale_factor,
                "offset": item.get("offset") if isinstance(item.get("offset"), (int, float)) else None,
                "period_code": period_code,
                "raw_metadata": {key: item[key] for key in ("unit", "scale", "offset", "startDate", "endDate") if key in item},
            })
        return result

    def read_field_window(
        self,
        *,
        mapset_code: str,
        raster: dict[str, Any],
        geometry_geojson: dict[str, Any],
        max_window_mb: float = 128.0,
    ) -> WaPORRasterWindow:
        """Read only the requested field window from an official FAO COG URL."""
        import numpy as np

        from app.geospatial.preprocessing import field_mask_for_window, read_scene_window

        code = mapset_code.strip().upper()
        product = get_product(code)
        download_url = raster.get("download_url") if isinstance(raster, dict) else None
        raster_code = raster.get("code") if isinstance(raster, dict) else None
        parsed = urlsplit(download_url) if isinstance(download_url, str) else None
        if (
            not isinstance(raster_code, str)
            or not re.fullmatch(r"WAPOR-3\." + re.escape(code) + r"\.\d{4}-\d{2}-D[1-3]", raster_code)
            or parsed is None
            or parsed.scheme != "https"
            or parsed.hostname not in RASTER_HOSTS
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
        ):
            raise ValueError("raster must be a catalogue record with a trusted FAO COG URL")
        try:
            raster_metadata = _read_raster_metadata(download_url)
            if not raster_metadata.get("is_tiled"):
                raise WaPORProviderError("FAO raster is not tiled; refusing an unbounded whole-scene read")
            reading = read_scene_window(
                assets={"wapor": download_url},
                surfaces=("wapor",),
                geometry_geojson=geometry_geojson,
                max_window_mb=max_window_mb,
            )
            field_mask = field_mask_for_window(
                geometry_geojson=geometry_geojson,
                crs_string=reading.crs,
                transform=reading.transform,
                width=reading.width,
                height=reading.height,
            )
            raw = np.asarray(reading.arrays["wapor"], dtype="float64")
            valid = field_mask & np.isfinite(raw)
            values = raw[valid]
        except WaPORProviderError:
            raise
        except Exception:
            raise WaPORProviderError("FAO raster could not be read for the requested field") from None
        if values.size:
            mean = float(np.mean(values))
            median = float(np.median(values))
        else:
            mean = median = None
        import math

        def finite_number(value: Any) -> bool:
            return (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
            )

        # Ignore malformed upstream metadata and fall back only to independently
        # documented raster tags or the versioned product catalogue.
        scale_candidates = (
            raster.get("scale_factor"),
            raster_metadata.get("scale_factor"),
            product.scale_factor,
        )
        scale = next(
            (float(value) for value in scale_candidates if finite_number(value) and float(value) > 0),
            None,
        )
        offset_candidates = (raster.get("offset"), raster_metadata.get("offset"))
        offset = next(
            (float(value) for value in offset_candidates if finite_number(value)),
            None,
        )
        unit_candidates = (raster.get("unit"), raster_metadata.get("unit"), product.unit)
        unit = next(
            (
                value.strip()
                for value in unit_candidates
                if isinstance(value, str)
                and value.strip()
                and value.strip().casefold() not in {"1", "unitless", "unknown"}
            ),
            None,
        )
        # WaPOR's product registry publishes multiplicative scale factors and
        # no additive offset; absent offset therefore means the documented 0.
        if scale is not None and offset is None and unit is not None:
            offset = 0.0
        scaled_mean = mean * scale + offset if mean is not None and scale is not None and offset is not None and unit is not None else None
        scaled_median = median * scale + offset if median is not None and scale is not None and offset is not None and unit is not None else None
        return WaPORRasterWindow(
            mapset_code=code,
            raster_code=raster_code,
            array=np.where(field_mask, raw, np.nan),
            valid_pixel_count=int(values.size),
            nodata_pixel_count=int(field_mask.sum() - values.size),
            raw_mean=mean,
            raw_median=median,
            unit=unit,
            scale_factor=scale,
            offset=offset,
            scaled_mean=scaled_mean,
            scaled_median=scaled_median,
            period_code=raster.get("period_code") if isinstance(raster.get("period_code"), str) else None,
            resolution_m=product.resolution_m,
            crs=reading.crs,
            source_url=download_url,
            metadata_reference=product.metadata_reference,
            license=product.license,
            asset_layout=raster_metadata.get("layout") if isinstance(raster_metadata.get("layout"), str) else None,
            overview_levels=tuple(raster_metadata.get("overview_levels") or ()),
        )
