"""Read-only FAO WaPOR v3 catalogue and bounded tiled GeoTIFF field-window access.

The FAO v3 API is public and does not require a token. Raw raster statistics
are always retained; scaled summaries are added only when unit and scale are
supported by API metadata, GeoTIFF tags or the cited WaPOR product specification.
This module never invents canonical CropTwist variables.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from calendar import monthrange
from time import monotonic
from uuid import uuid4
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.errors import InvalidDateRange, ProviderUnavailable, UnsupportedVariable, ValidationFailed
from app.data_platform.contracts.observations import (
    AreaOfInterest,
    CanonicalObservation,
    EvidenceClass,
    ProviderFetchResult,
    QualityStatus,
    SourceProvenance,
    SpatialSupportType,
    TimeSupport,
    validate_provider_request,
)
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
                # Preserve explicitly reported values, including malformed ones,
                # so the raster reader can fail closed instead of silently replacing
                # an invalid API claim with catalogue defaults.
                "unit": item.get("unit") if "unit" in item else product.unit,
                "scale_factor": item.get("scale") if "scale" in item else product.scale_factor,
                "offset": item.get("offset") if "offset" in item else None,
                "period_code": period_code,
                "resolution_m": product.resolution_m,
                "license": product.license,
                "metadata_reference": product.metadata_reference,
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
        """Read only the requested field window from an official FAO tiled GeoTIFF URL."""
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
            raise ValueError("raster must be a catalogue record with a trusted FAO GeoTIFF URL")
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
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False
            try:
                return math.isfinite(float(value))
            except (OverflowError, ValueError):
                return False

        # Ignore malformed upstream metadata and fall back only to independently
        # documented raster tags or the versioned product catalogue.
        scale_candidates = (raster.get("scale_factor"), raster_metadata.get("scale_factor"))
        present_scales = [value for value in scale_candidates if value is not None]
        valid_scales = [
            float(value) for value in present_scales
            if finite_number(value) and float(value) > 0
        ]
        scales_consistent = (
            len(valid_scales) == len(present_scales)
            and all(
                math.isclose(value, product.scale_factor, rel_tol=1e-9, abs_tol=1e-12)
                for value in valid_scales
            )
        )
        # Every available API/GeoTIFF scale must agree with the versioned
        # product specification. A valid first value cannot mask a conflict
        # in a second metadata source.
        scale = (
            product.scale_factor
            if product.scale_factor is not None and scales_consistent
            else None
        )
        offset_candidates = (raster.get("offset"), raster_metadata.get("offset"))
        present_offsets = [value for value in offset_candidates if value is not None]
        valid_offsets = [float(value) for value in present_offsets if finite_number(value)]
        # The published WaPOR product registry specifies multiplicative scaling
        # only. Missing offsets imply zero; malformed or non-zero metadata is a
        # conflict and withholds scaled physical values.
        offset = (
            0.0
            if not present_offsets
            else 0.0
            if len(valid_offsets) == len(present_offsets) and all(value == 0.0 for value in valid_offsets)
            else None
        )
        unit_candidates = (raster.get("unit"), raster_metadata.get("unit"))
        present_units = [value for value in unit_candidates if value is not None]
        meaningful_units = [
            value.strip()
            for value in present_units
            if isinstance(value, str)
            and value.strip()
            and value.strip().casefold() not in {"1", "unitless", "unknown"}
        ]
        invalid_unit_metadata = any(not isinstance(value, str) for value in present_units)
        units_consistent = (
            not invalid_unit_metadata
            and all(value.casefold() == (product.unit or "").casefold() for value in meaningful_units)
        )
        # Check all metadata sources, not just the first non-empty unit. A
        # malformed or conflicting unit withholds canonical scaled values.
        unit = product.unit if product.unit is not None and units_consistent else None
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


# Canonical variables exposed by the Egypt Level-2 dekadal products. These
# mappings are deliberately explicit: AETI is not reference ET0, and relative
# soil moisture is not volumetric soil_moisture_surface.
WAPOR_EGYPT_L2_VARIABLE_MAP = {
    "actual_evapotranspiration_interception": "L2-AETI-D",
    "evaporation": "L2-E-D",
    "interception": "L2-I-D",
    "transpiration": "L2-T-D",
    "relative_soil_moisture": "L2-RSM-D",
    "net_primary_productivity": "L2-NPP-D",
}


def _dekad_period(period_code: str) -> tuple[datetime, datetime]:
    match = re.fullmatch(r"(\d{4})-(\d{2})-D([1-3])", period_code)
    if not match:
        raise ValueError("invalid WaPOR dekadal period code")
    year, month, dekad = (int(value) for value in match.groups())
    if not 1 <= month <= 12:
        raise ValueError("invalid WaPOR month")
    if dekad == 1:
        first, last = 1, 10
    elif dekad == 2:
        first, last = 11, 20
    else:
        first, last = 21, monthrange(year, month)[1]
    return (
        datetime(year, month, first, tzinfo=UTC),
        datetime(year, month, last, 23, 59, 59, 999999, tzinfo=UTC),
    )


class WaPORV3Provider:
    """EnvironmentalDataProvider adapter for Egypt's WaPOR v3 L2 dekadal products."""

    provider_code = "fao_wapor_v3"

    def __init__(self, client: WaPORV3Client | None = None) -> None:
        self.client = client or WaPORV3Client()

    @staticmethod
    def supported_variables() -> list[str]:
        return sorted(WAPOR_EGYPT_L2_VARIABLE_MAP)

    def fetch_observations(
        self,
        *,
        area_of_interest: AreaOfInterest,
        variables: list[str],
        start: datetime,
        end: datetime,
        options: dict[str, Any] | None = None,
    ) -> ProviderFetchResult:
        if start.tzinfo is None or end.tzinfo is None:
            raise InvalidDateRange("WaPOR requests require timezone-aware start/end timestamps.")
        validate_provider_request(variables, start, end)
        start_utc, end_utc = start.astimezone(UTC), end.astimezone(UTC)
        if options is None:
            options = {}
        if not isinstance(options, dict):
            raise ValidationFailed("WaPOR provider options must be an object.")
        raw_country_code = options.get("country_code", "EGY")
        raw_level = options.get("level", 2)
        if not isinstance(raw_country_code, str) or isinstance(raw_level, bool) or not isinstance(raw_level, int):
            raise ValidationFailed("WaPOR country_code and level options have invalid types.")
        country_code = raw_country_code.strip().upper()
        level = raw_level
        if country_code != "EGY" or level != 2:
            raise UnsupportedVariable(
                "The canonical WaPOR provider currently exposes only Egypt Level-2 dekadal products."
            )
        unknown = sorted(set(variables) - set(WAPOR_EGYPT_L2_VARIABLE_MAP))
        if unknown:
            raise UnsupportedVariable(
                "Requested variables have no verified WaPOR Level-2 mapping.",
                details=[{"field": "variables", "reason": ", ".join(unknown)}],
            )

        observations: list[CanonicalObservation] = []
        warnings: list[str] = []
        rasters_seen = 0
        products_used: list[str] = []
        missing_count = 0
        for variable in variables:
            mapset_code = WAPOR_EGYPT_L2_VARIABLE_MAP[variable]
            products_used.append(mapset_code)
            try:
                rasters = self.client.list_rasters(mapset_code)
            except Exception as exc:  # noqa: BLE001 — never leak upstream URLs or response bodies
                raise ProviderUnavailable(
                    f"WaPOR catalogue discovery failed for product {mapset_code} ({type(exc).__name__}).",
                    details=[{"product_code": mapset_code, "reason": type(exc).__name__}],
                ) from exc
            selected = []
            for raster in rasters:
                try:
                    period_start, period_end = _dekad_period(raster["period_code"])
                except (KeyError, ValueError):
                    continue
                if period_end < start_utc or period_start > end_utc:
                    continue
                partial_period = period_start.date() < start_utc.date() or period_end.date() > end_utc.date()
                if partial_period:
                    warnings.append(
                        f"Requested range intersects a partial dekad for {variable}; full dekadal observation returned."
                    )
                selected.append((raster, period_start, period_end, partial_period))
            if not selected:
                warnings.append(f"No WaPOR rasters found for {variable} in the requested date range.")
                continue
            for raster, period_start, period_end, partial_period in selected:
                rasters_seen += 1
                raw_window_limit = options.get("max_window_mb", 128.0)
                try:
                    if isinstance(raw_window_limit, bool):
                        raise ValueError
                    window_limit = float(raw_window_limit)
                except (TypeError, ValueError):
                    raise ValidationFailed("WaPOR max_window_mb must be a finite number between 1 and 256.") from None
                import math
                if not math.isfinite(window_limit) or not 1.0 <= window_limit <= 256.0:
                    raise ValidationFailed("WaPOR max_window_mb must be a finite number between 1 and 256.")
                try:
                    window = self.client.read_field_window(
                        mapset_code=mapset_code,
                        raster=raster,
                        geometry_geojson=area_of_interest.geometry_geojson,
                        max_window_mb=window_limit,
                    )
                except Exception as exc:  # noqa: BLE001
                    raise ProviderUnavailable(
                        f"WaPOR field-window extraction failed for product {mapset_code} ({type(exc).__name__}).",
                        details=[{"product_code": mapset_code, "raster_code": raster["code"], "reason": type(exc).__name__}],
                    ) from exc
                if window.valid_pixel_count > 0 and window.scaled_mean is None:
                    raise ProviderUnavailable(
                        f"WaPOR product {mapset_code} has no verified physical unit/scale metadata.",
                        details=[{"product_code": mapset_code, "raster_code": raster["code"], "reason": "unresolved_unit_scale"}],
                    )
                is_missing = window.valid_pixel_count == 0
                missing_count += int(is_missing)
                value = None if is_missing else float(window.scaled_mean)
                unit = window.unit
                if not unit:
                    raise ProviderUnavailable(
                        f"WaPOR product {mapset_code} has no verified canonical unit.",
                        details=[{"product_code": mapset_code, "raster_code": raster["code"], "reason": "missing_unit"}],
                    )
                total_pixels = window.valid_pixel_count + window.nodata_pixel_count
                observations.append(CanonicalObservation(
                    variable_code=variable,
                    value=value,
                    unit=unit,
                    observed_at=period_end,
                    period_start=period_start,
                    period_end=period_end,
                    time_support=TimeSupport.dekadal,
                    spatial_support_type=SpatialSupportType.field_intersection,
                    spatial_resolution_m=float(window.resolution_m),
                    quality_status=QualityStatus.missing if is_missing else QualityStatus.valid,
                    evidence_class=EvidenceClass.satellite_derived_estimate,
                    is_synthetic=False,
                    processing_version="wapor-v3",
                    metadata={
                        "mapset_code": mapset_code,
                        "raster_code": window.raster_code,
                        "raw_mean": window.raw_mean,
                        "raw_median": window.raw_median,
                        "scaled_mean": window.scaled_mean,
                        "scaled_median": window.scaled_median,
                        "scale_factor": window.scale_factor,
                        "offset": window.offset,
                        "crs": window.crs,
                        "valid_pixel_count": window.valid_pixel_count,
                        "nodata_pixel_count": window.nodata_pixel_count,
                        "valid_pixel_fraction": (window.valid_pixel_count / total_pixels) if total_pixels else 0.0,
                        "asset_layout": window.asset_layout,
                        "overview_levels": list(window.overview_levels),
                        "license": window.license,
                        "metadata_reference": window.metadata_reference,
                        "requested_range_partial_period": partial_period,
                    },
                    quality_flags=([{"code": "no_valid_pixels", "message": "No valid WaPOR pixels intersect the field."}] if is_missing else []),
                ))

        provenance = SourceProvenance(
            provider_code=self.provider_code,
            provider_name="FAO WaPOR v3",
            product_code="WaPOR v3 Level-2 dekadal water-productivity products",
            product_version="3",
            license_name="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
            attribution_text="FAO WaPOR v3 data, licensed under CC BY-SA 4.0.",
            documentation_url="https://www.fao.org/in-action/remote-sensing-for-water-productivity/wapor/en",
            known_limitations=(
                "Egypt Level-2 dekadal products at nominal 100 m resolution; satellite/model estimates, "
                "not field measurements. Level-3 pilot products and Level-1 coarse products are not "
                "included in this canonical adapter."
            ),
            retrieval_method="FAO GISMGR catalogue API + tiled GeoTIFF field-window read",
        )
        return ProviderFetchResult(
            provider_code=self.provider_code,
            provenance=provenance,
            observations=observations,
            warnings=warnings,
            coverage={
                "country_code": country_code,
                "level": level,
                "products": sorted(set(products_used)),
                "rasters_seen": rasters_seen,
                "observations": len(observations),
                "missing_observations": missing_count,
            },
            provider_request_id=uuid4().hex,
            raw_reference=API_ROOT,
            input_record_count=rasters_seen,
        )


def wapor_v3_health_probe() -> dict[str, Any]:
    """Short, best-effort public catalogue probe for the provider registry."""
    started = monotonic()
    try:
        mapsets = WaPORV3Client(timeout_seconds=5.0).list_mapsets()
        return {
            "status": "ok" if mapsets else "degraded",
            "latency_ms": int((monotonic() - started) * 1000),
            "detail": f"FAO WaPOR v3 catalogue returned {len(mapsets)} mapsets",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unreachable",
            "latency_ms": int((monotonic() - started) * 1000),
            "detail": f"FAO WaPOR v3 catalogue unavailable ({type(exc).__name__})",
        }
