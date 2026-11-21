"""NASA HLS provider (P04) — real satellite acquisition adapter.

Implements the platform provider contract (EnvironmentalDataProvider) against
NASA HLS v2.0 (Harmonized Landsat Sentinel-2, LP DAAC):

- Catalog: NASA CMR STAC (`cmr.earthdata.nasa.gov/stac/LPCLOUD`) — public,
  unauthenticated metadata search (see catalog.py).
- Assets: LP DAAC cloud-optimized GeoTIFFs. Reads use rasterio/GDAL HTTP
  range reads for the field-sized window only (no full-raster downloads,
  no binaries persisted) with
  NASA Earthdata Login credentials from settings
  (`CROPTWIST_EARTHDATA_USERNAME` / `CROPTWIST_EARTHDATA_PASSWORD` or a
  pre-minted `CROPTWIST_EARTHDATA_BEARER_TOKEN`). Credentials are never
  hardcoded. Without credentials, protected asset reads fail loudly
  (ProviderUnavailable) — never fabricated.
- Processing: per-pixel vegetation indices via the shared, documented index
  math (`app.vegetation.raster_indices` / `app.vegetation.indices`), CRS-safe
  field-window reads, HLS v2 Fmask cloud/adjacency/shadow/snow/high-AOT masking
  (water and all AOT levels recorded separately), and zonal field statistics.
  HLS band scaling
  (DN * 0.0001) and band naming follow the HLS v2.0 user guide.
- Ingestion flow: `scene_ids` + `scene_records` (from a discovery step) pin
  the exact scenes to acquire — bounded, retryable, idempotent. Without
  scene_records the provider performs its own bounded discovery and caps the
  number of processed scenes (`nasa_hls_max_scenes_per_job`).

Honesty properties:
- No scene, observation, resolution or quality value is ever invented.
- One ingestion job targets exactly one HLS collection (HLSL30 OR HLSS30) so
  result-level provenance is unambiguous.
- Per-scene failures degrade to warnings and surface as failed scene status —
  they never abort the remaining scenes.
- is_synthetic=False, evidence_class=satellite_derived_estimate, full
  SourceProvenance (license/attribution/limitations) on every result.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import ProviderRequestError, ProviderUnavailable, UnsupportedVariable
from app.data_platform.contracts.observations import (
    AreaOfInterest,
    CanonicalObservation,
    EvidenceClass,
    ProviderFetchResult,
    QualityStatus,
    SourceProvenance,
    TimeSupport,
)
from app.data_platform.providers.nasa_hls import catalog as hls_catalog
from app.data_platform.providers.nasa_hls.registry_info import (
    ATTRIBUTION_TEXT,
    DOCUMENTATION_URL,
    FMASK_AOT_HIGH,
    FMASK_AOT_MASK,
    FMASK_EXCLUDE_MASK,
    HLS_REFLECTANCE_SCALE,
    HLS_SPATIAL_RESOLUTION_M,
    KNOWN_LIMITATIONS,
    LICENSE_NAME,
    LICENSE_URL,
    PRODUCT_CODE_L30,
    PRODUCT_CODE_S30,
    PRODUCT_VERSION,
    PROVIDER_CODE,
    PROVIDER_NAME,
)

logger = logging.getLogger("croptwist.providers.nasa_hls")

SUPPORTED_VARIABLES = ("ndvi", "evi", "savi", "ndmi", "ndwi")

SEARCH_TIMEOUT_SECONDS = 30.0


class NasaHlsProvider:
    """NASA HLS acquisition provider (CMR STAC discovery + LP DAAC assets)."""

    provider_code = PROVIDER_CODE

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    # ------------------------------------------------------------- metadata
    def supported_variables(self) -> list[str]:
        return list(SUPPORTED_VARIABLES)

    def collections(self) -> list[str]:
        return [PRODUCT_CODE_L30, PRODUCT_CODE_S30]

    def validate_request(
        self, *, variables: list[str], options: dict[str, Any] | None = None
    ) -> None:
        """Fail fast before a job row is created (data_platform route hook)."""
        options = options or {}
        unknown = sorted(set(variables) - set(SUPPORTED_VARIABLES))
        if unknown:
            raise UnsupportedVariable(
                f"Variables not produced by this provider: {', '.join(unknown)}.",
                details=[{"field": "variables", "reason": "nasa_hls produces vegetation indices only"}],
            )
        scene_ids = options.get("scene_ids")
        if scene_ids is not None:
            if (
                not isinstance(scene_ids, list)
                or not scene_ids
                or any(
                    not isinstance(scene_id, str)
                    or not scene_id.strip()
                    or len(scene_id) > 256
                    for scene_id in scene_ids
                )
            ):
                raise ProviderRequestError(
                    "scene_ids must be a non-empty list of bounded scene identifiers.",
                    details=[{"field": "scene_ids", "reason": "invalid shape or identifier"}],
                )
            if len(scene_ids) != len(set(scene_ids)):
                raise ProviderRequestError(
                    "scene_ids must not contain duplicate identifiers.",
                    details=[{"field": "scene_ids", "reason": "duplicate scene id"}],
                )
            if len(scene_ids) > settings.nasa_hls_max_scenes_per_job:
                raise ProviderRequestError(
                    f"Too many scenes requested (limit {settings.nasa_hls_max_scenes_per_job}).",
                    details=[{"field": "scene_ids", "reason": "nasa_hls_max_scenes_per_job exceeded"}],
                )

    # ------------------------------------------------------------ provenance
    def _provenance(self, collection: str) -> SourceProvenance:
        return SourceProvenance(
            provider_code=PROVIDER_CODE,
            provider_name=PROVIDER_NAME,
            product_code=collection,
            product_version=PRODUCT_VERSION,
            license_name=LICENSE_NAME,
            license_url=LICENSE_URL,
            attribution_text=ATTRIBUTION_TEXT,
            documentation_url=DOCUMENTATION_URL,
            known_limitations=KNOWN_LIMITATIONS,
            retrieval_method="cmr_stac_cog_http_range",
        )

    # ------------------------------------------------------------ discovery
    def search_scenes(
        self,
        *,
        geometry_geojson: dict[str, Any],
        start: datetime,
        end: datetime,
        max_cloud_cover: float | None = None,
        page_size: int | None = None,
        max_pages: int | None = None,
    ) -> tuple[list[hls_catalog.HlsSceneRecord], list[str]]:
        """Public catalog discovery (metadata only, unauthenticated)."""
        return hls_catalog.search_scenes(
            geometry_geojson=geometry_geojson,
            start=start,
            end=end,
            collections=[
                settings.nasa_hls_l30_collection_id,
                settings.nasa_hls_s30_collection_id,
            ],
            max_cloud_cover=(
                settings.nasa_hls_default_max_cloud_cover
                if max_cloud_cover is None
                else max_cloud_cover
            ),
            page_size=page_size,
            max_pages=max_pages,
            client=self._client,
        )

    # ----------------------------------------------------------- ingestion
    def fetch_observations(
        self,
        *,
        area_of_interest: AreaOfInterest,
        variables: list[str],
        start: datetime,
        end: datetime,
        options: dict[str, Any] | None = None,
    ) -> ProviderFetchResult:
        options = options or {}
        unknown = sorted(set(variables) - set(SUPPORTED_VARIABLES))
        if unknown:
            raise UnsupportedVariable(
                f"Variables not produced by this provider: {', '.join(unknown)}.",
                details=[{"field": "variables", "reason": "nasa_hls produces vegetation indices only"}],
            )

        scene_records = self._resolve_targets(
            options, start, end, area_of_interest.geometry_geojson
        )
        collections = {record["collection"] for record in scene_records.values()}
        if not scene_records:
            return ProviderFetchResult(
                provider_code=PROVIDER_CODE,
                provenance=self._provenance(PRODUCT_CODE_L30),
                observations=[],
                warnings=[
                    "No NASA HLS scenes were available for the requested range. "
                    "This is a data-availability gap, not an error."
                ],
                coverage={
                    "scenes_requested": 0,
                    "scenes_processed": 0,
                    "start": start.astimezone(UTC).isoformat(),
                    "end": end.astimezone(UTC).isoformat(),
                },
                provider_request_id=None,
                raw_reference=hls_catalog_url(),
                input_record_count=0,
            )
        if len(collections) > 1:
            raise ProviderRequestError(
                "One NASA HLS ingestion job must target a single collection "
                "(group HLSL30 and HLSS30 scenes into separate jobs).",
                details=[{"field": "scene_records", "reason": f"collections: {sorted(collections)}"}],
            )
        collection = collections.pop()

        ordered_ids = sorted(scene_records.keys())
        provider_request_id = f"nasa_hls:{_stable_id(ordered_ids)[:16]}"

        observations: list[CanonicalObservation] = []
        warnings: list[str] = []
        scenes_processed = 0
        gdal_env = _gdal_env_options(self._earthdata_auth())
        for scene_id in ordered_ids:
            record = scene_records[scene_id]
            try:
                scene_obs, scene_warnings = _scene_observations(
                    record=record,
                    variables=sorted(set(variables)),
                    geometry_geojson=area_of_interest.geometry_geojson,
                    gdal_env=gdal_env,
                )
            except ProviderUnavailable as exc:
                warnings.append(f"Scene {scene_id}: {exc}")
                logger.warning("nasa_hls scene degraded", extra={"scene_id": scene_id})
                continue
            observations.extend(scene_obs)
            warnings.extend(scene_warnings)
            if scene_obs:
                scenes_processed += 1

        return ProviderFetchResult(
            provider_code=PROVIDER_CODE,
            provenance=self._provenance(collection),
            observations=observations,
            warnings=warnings,
            coverage={
                "scenes_requested": len(scene_records),
                "scenes_processed": scenes_processed,
                "start": start.astimezone(UTC).isoformat(),
                "end": end.astimezone(UTC).isoformat(),
            },
            provider_request_id=provider_request_id,
            raw_reference=hls_catalog_url(),
            input_record_count=len(observations),
        )

    # ------------------------------------------------------------- targets
    def _resolve_targets(
        self,
        options: dict[str, Any],
        start: datetime,
        end: datetime,
        geometry_geojson: dict[str, Any] | None,
    ) -> dict[str, dict[str, Any]]:
        """Resolve which scenes to acquire.

        Two supported modes:
        - Explicit: `scene_ids` + `scene_records` (from the discovery step /
          acquisition API) — the deterministic, bounded acquisition mode.
        - Bounded auto-discovery: no scene_records -> CMR STAC search for the
          range, processing at most `nasa_hls_max_scenes_per_job` scenes
          (clearest first). Used for direct data-jobs; the cap is recorded in
          coverage and warnings.
        """
        scene_ids = options.get("scene_ids")
        scene_records = options.get("scene_records")
        # Explicit selectors must never be silently ignored. In particular,
        # malformed or empty scene_ids previously fell through to "all
        # records", which could acquire more imagery than the caller asked for.
        if scene_ids is not None:
            if (
                not isinstance(scene_ids, list)
                or not scene_ids
                or any(
                    not isinstance(scene_id, str)
                    or not scene_id.strip()
                    or len(scene_id) > 256
                    for scene_id in scene_ids
                )
            ):
                raise ProviderRequestError(
                    "scene_ids must be a non-empty list of bounded scene identifiers.",
                    details=[{"field": "scene_ids", "reason": "invalid shape or identifier"}],
                )
            if len(scene_ids) != len(set(scene_ids)):
                raise ProviderRequestError(
                    "scene_ids must not contain duplicate identifiers.",
                    details=[{"field": "scene_ids", "reason": "duplicate scene id"}],
                )
        if scene_records is not None:
            if not isinstance(scene_records, dict) or not scene_records:
                raise ProviderRequestError(
                    "scene_records must be a non-empty object keyed by scene id "
                    "(obtained from satellite discovery).",
                    details=[{"field": "scene_records", "reason": "invalid shape"}],
                )
            # Validate keys and metadata before sorting or indexing untrusted
            # caller-supplied dictionaries.
            for key, record in scene_records.items():
                _validate_scene_record(key, record)
                acquired_at = datetime.fromisoformat(
                    record["acquired_at"].replace("Z", "+00:00")
                ).astimezone(UTC)
                if not start.astimezone(UTC) <= acquired_at <= end.astimezone(UTC):
                    raise ProviderRequestError(
                        f"Scene record '{key}' is outside the requested time range.",
                        details=[{"field": "scene_records", "reason": "acquired_at outside requested range"}],
                    )
            if scene_ids is not None:
                missing = [scene_id for scene_id in scene_ids if scene_id not in scene_records]
                if missing:
                    raise ProviderRequestError(
                        "scene_ids reference scenes without discovery metadata.",
                        details=[{"field": "scene_ids", "reason": f"missing records: {missing[:5]}"}],
                    )
                ordered = scene_ids
            else:
                ordered = sorted(scene_records.keys())
            return {k: scene_records[k] for k in ordered}

        if scene_ids is None:
            # Bounded auto-discovery mode.
            if geometry_geojson is None:
                raise ProviderRequestError(
                    "Field geometry is required for NASA HLS discovery.",
                    details=[{"field": "geometry", "reason": "missing"}],
                )
            records, _warnings = self.search_scenes(
                geometry_geojson=geometry_geojson,
                start=start,
                end=end,
            )
            records.sort(
                key=lambda r: (
                    r.cloud_cover_pct if r.cloud_cover_pct is not None else 999.0,
                    -r.acquired_at.timestamp(),
                )
            )
            cap = settings.nasa_hls_max_scenes_per_job
            capped = records[:cap]
            scene_records = {r.scene_id: _record_to_scene_record(r) for r in capped}
            if len(records) > cap:
                logger.warning(
                    "nasa_hls auto-discovery capped", extra={"found": len(records), "cap": cap}
                )
            return scene_records
        raise ProviderRequestError(
            "scene_ids provided without scene_records metadata.",
            details=[{"field": "scene_records", "reason": "run discovery first"}],
        )

    # ----------------------------------------------------------------- auth
    def _earthdata_auth(self) -> dict[str, str]:
        """NASA Earthdata Login credential resolution (settings only)."""
        token = settings.earthdata_bearer_token
        if token:
            return {"bearer_token": token}
        if settings.earthdata_username and settings.earthdata_password:
            minted = self._mint_earthdata_token()
            if minted:
                return {"bearer_token": minted}
            return {
                "basic_user": settings.earthdata_username,
                "basic_password": settings.earthdata_password,
            }
        return {}

    def _mint_earthdata_token(self) -> str | None:
        """POST the EDL token endpoint with basic auth (best-effort).

        EDL tokens are the documented bearer mechanism for LP DAAC cloud
        assets. Failure falls back to basic-auth GDAL handling; nothing is
        fabricated and no credential is ever logged.
        """
        http = self._client or httpx
        try:
            response = http.post(
                settings.earthdata_token_url,
                auth=(settings.earthdata_username, settings.earthdata_password),
                timeout=SEARCH_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            token = data.get("token") or data.get("access_token")
            return token if isinstance(token, str) and token else None
        except Exception as exc:  # noqa: BLE001 — auth is best-effort
            logger.warning("Earthdata token mint failed (%s); using basic-auth GDAL path", type(exc).__name__)
            return None


# ------------------------------------------------------------------ helpers
def hls_catalog_url() -> str | None:
    return settings.nasa_hls_stac_base_url.rstrip("/") + hls_catalog.STAC_SEARCH_PATH


def _stable_id(scene_ids: list[str]) -> str:
    import hashlib

    return hashlib.sha256("|".join(scene_ids).encode("utf-8")).hexdigest()


def _record_to_scene_record(record: hls_catalog.HlsSceneRecord) -> dict[str, Any]:
    return {
        "scene_id": record.scene_id,
        "collection": record.collection,
        "collection_id": record.collection_id,
        "acquired_at": record.acquired_at.isoformat(),
        "cloud_cover_pct": record.cloud_cover_pct,
        "platform": record.platform,
        "assets": dict(record.asset_refs),
        "band_mapping": dict(record.band_mapping),
        "processing_version": record.processing_version,
    }


def _validate_scene_record(scene_id: str, record: Any) -> None:
    """Validate caller-supplied discovery records before GDAL can open assets."""
    from urllib.parse import urlsplit

    if not isinstance(scene_id, str) or not scene_id.strip() or len(scene_id) > 256:
        raise ProviderRequestError(
            "Scene record key must be a non-empty bounded identifier.",
            details=[{"field": "scene_records", "reason": "invalid scene id"}],
        )
    if not isinstance(record, dict):
        raise ProviderRequestError(
            f"Scene record '{scene_id}' must be an object.",
            details=[{"field": "scene_records", "reason": "invalid shape"}],
        )
    if record.get("scene_id") != scene_id:
        raise ProviderRequestError(
            f"Scene record '{scene_id}' has a mismatched scene identifier.",
            details=[{"field": "scene_records", "reason": "scene_id mismatch"}],
        )
    if record.get("collection") not in (PRODUCT_CODE_L30, PRODUCT_CODE_S30):
        raise ProviderRequestError(
            f"Scene record '{scene_id}' has an unknown collection.",
            details=[{"field": "scene_records", "reason": "expected HLSL30 or HLSS30"}],
        )
    acquired_at = record.get("acquired_at")
    if not isinstance(acquired_at, str) or not acquired_at:
        raise ProviderRequestError(
            f"Scene record '{scene_id}' has no acquisition timestamp.",
            details=[{"field": "scene_records", "reason": "acquired_at required"}],
        )
    try:
        timestamp = datetime.fromisoformat(acquired_at.replace("Z", "+00:00"))
    except ValueError:
        raise ProviderRequestError(
            f"Scene record '{scene_id}' has an invalid acquisition timestamp.",
            details=[{"field": "scene_records", "reason": "invalid acquired_at"}],
        ) from None
    if timestamp.tzinfo is None:
        raise ProviderRequestError(
            f"Scene record '{scene_id}' acquisition timestamp must include a timezone.",
            details=[{"field": "scene_records", "reason": "timezone required"}],
        )

    cloud_cover = record.get("cloud_cover_pct")
    if cloud_cover is not None:
        try:
            valid_cloud_cover = (
                not isinstance(cloud_cover, bool)
                and isinstance(cloud_cover, (int, float))
                and math.isfinite(float(cloud_cover))
                and 0.0 <= float(cloud_cover) <= 100.0
            )
        except (OverflowError, ValueError):
            valid_cloud_cover = False
        if not valid_cloud_cover:
            raise ProviderRequestError(
                f"Scene record '{scene_id}' has invalid cloud-cover metadata.",
                details=[{"field": "scene_records", "reason": "cloud_cover_pct must be between 0 and 100"}],
            )

    assets = record.get("assets")
    if assets is None:
        assets = {}
    allowed_surfaces = {"red", "nir", "blue", "green", "swir1", "swir2", "fmask"}
    if not isinstance(assets, dict) or any(key not in allowed_surfaces for key in assets):
        raise ProviderRequestError(
            f"Scene record '{scene_id}' has invalid asset metadata.",
            details=[{"field": "scene_records", "reason": "unsupported asset key"}],
        )
    for surface, href in assets.items():
        try:
            parsed = urlsplit(href) if isinstance(href, str) else None
            valid_url = bool(
                parsed
                and parsed.scheme.lower() == "https"
                and parsed.hostname
                and parsed.hostname.lower() in {
                    "data.lpdaac.earthdatacloud.nasa.gov",
                    "data.lpdaac.earthdata.nasa.gov",
                }
                and parsed.port in (None, 443)
                and not parsed.username
                and not parsed.password
                and not parsed.query
                and not parsed.fragment
                and (
                    parsed.path.startswith("/lp-prod-protected/")
                    or parsed.path.startswith("/lp-prod-public/")
                )
            )
        except ValueError:
            valid_url = False
        if not valid_url:
            raise ProviderRequestError(
                f"Scene record '{scene_id}' contains an untrusted {surface} asset URL.",
                details=[{"field": "scene_records", "reason": "asset URL must be an unsigned HTTPS LP DAAC URL"}],
            )


def _gdal_env_options(auth: dict[str, str]) -> dict[str, str]:
    """GDAL config options for authenticated /vsicurl/ reads of LP DAAC COGs.

    - Bearer token path (preferred): `GDAL_HTTP_HEADERS` (GDAL >= 3.6).
    - Fallback: HTTP basic auth over the URS redirect challenge plus a
      cookie jar (documented EDL access pattern for GDAL).
    - No credentials -> anonymous read attempt (public assets only); the
      protected LP DAAC buckets will fail loudly downstream.
    """
    opts = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "VSI_CACHE": "TRUE",
        "GDAL_HTTP_TIMEOUT": str(int(settings.nasa_hls_timeout_seconds)),
    }
    token = auth.get("bearer_token")
    if token:
        opts["GDAL_HTTP_HEADERS"] = f"Authorization: Bearer {token}"
    elif auth.get("basic_user") and auth.get("basic_password"):
        opts["GDAL_HTTP_AUTH"] = "BASIC"
        opts["GDAL_USERPWD"] = f"{auth['basic_user']}:{auth['basic_password']}"
        opts["GDAL_HTTP_COOKIEFILE"] = "/vsimem/edl_cookies.txt"
        opts["GDAL_HTTP_COOKIEJAR"] = "/vsimem/edl_cookies.txt"
    return opts


def _load_scene_arrays(
    assets: dict[str, str],
    surfaces: list[str],
    gdal_env: dict[str, str],
    geometry_geojson: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a bounded field window through the shared CRS-safe COG reader."""
    from app.geospatial import preprocessing as pre

    reading = pre.read_scene_window(
        assets=assets,
        surfaces=tuple(surfaces),
        geometry_geojson=geometry_geojson,
        gdal_env=gdal_env,
        max_window_mb=settings.raster_max_field_window_mb,
        nodata_fallbacks={**{surface: -9999 for surface in surfaces}, "fmask": 255},
    )
    arrays = {
        surface: {"data": data, "transform": reading.transform}
        for surface, data in reading.arrays.items()
    }
    context = {
        "fmask": reading.fmask,
        "shape": (reading.height, reading.width),
        "transform": reading.transform,
        "crs": reading.crs,
        "band_alignment": reading.band_alignment,
        "window_bounds": reading.window_bounds,
        "read_bytes_estimate": reading.read_bytes_estimate,
    }
    return arrays, context


def _scene_observations(
    *,
    record: dict[str, Any],
    variables: list[str],
    geometry_geojson: dict[str, Any],
    gdal_env: dict[str, str],
) -> tuple[list[CanonicalObservation], list[str]]:
    """Acquire one scene: read assets, mask, compute indices, zonal stats.

    Mirrors the Sentinel-2 provider's scientifically-correct order (index
    first, statistics second) with HLS-specific band naming and Fmask QA.
    """
    import numpy as np

    from app.geospatial import preprocessing as pre
    from app.vegetation.raster_indices import compute_index_arrays
    from app.vegetation.zonal import ZonalResult, subfield_statistics_ok

    warnings: list[str] = []
    scene_id = record["scene_id"]
    collection = record["collection"]
    assets = dict(record.get("assets") or {})
    missing = [s for s in ("red", "nir", "fmask") if not assets.get(s)]
    if missing:
        warnings.append(
            f"Scene {scene_id}: required band assets missing ({', '.join(missing)}); scene skipped."
        )
        return [], warnings

    acquired_at = datetime.fromisoformat(str(record["acquired_at"]).replace("Z", "+00:00"))
    if acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=UTC)
    cloud_cover = record.get("cloud_cover_pct")
    platform = record.get("platform")
    processing_version = str(record.get("processing_version") or PRODUCT_VERSION)
    metadata_common: dict[str, Any] = {
        "scene_id": scene_id,
        "granule_id": scene_id,
        "platform": platform,
        "collection": collection,
        "collection_id": record.get("collection_id"),
        "processing_baseline": processing_version,
        "cloud_cover_pct": cloud_cover,
        "spatial_resolution_m": HLS_SPATIAL_RESOLUTION_M,
        "asset_refs": assets,
        "raster_url": assets.get("nir"),
        "provider_code": PROVIDER_CODE,
    }

    try:
        surfaces = [s for s in ("red", "nir", "blue", "green", "swir1", "swir2") if s in assets]
        band_arrays, context = _load_scene_arrays(assets, surfaces, gdal_env, geometry_geojson)
        fmask = context["fmask"]
        shape = context["shape"]
        transform = context["transform"]
        if fmask is None or fmask.shape != shape:
            raise ValueError("HLS Fmask QA asset is missing or not aligned to the field window")
        field_mask = pre.field_mask_for_window(
            geometry_geojson=geometry_geojson,
            crs_string=context["crs"],
            transform=transform,
            width=shape[1],
            height=shape[0],
        )
        metadata_common["raster_window"] = {
            "crs": context["crs"],
            "bounds": list(context["window_bounds"]),
            "width_px": shape[1],
            "height_px": shape[0],
            "read_bytes_estimate": context["read_bytes_estimate"],
            "read_mode": "windowed_range_read",
            "band_alignment": context["band_alignment"],
        }
        field_fmask = fmask[field_mask].astype(np.uint8)
        valid_qa = field_fmask != 255
        aot_level = (field_fmask & FMASK_AOT_MASK) >> 6
        metadata_common["fmask_qa"] = {
            "cloud_pixels": int((((field_fmask & 0b00000010) != 0) & valid_qa).sum()),
            "adjacent_to_cloud_pixels": int((((field_fmask & 0b00000100) != 0) & valid_qa).sum()),
            "shadow_pixels": int((((field_fmask & 0b00001000) != 0) & valid_qa).sum()),
            "snow_pixels": int((((field_fmask & 0b00010000) != 0) & valid_qa).sum()),
            "water_pixels": int((((field_fmask & 0b00100000) != 0) & valid_qa).sum()),
            "reserved_bit0_pixels": int((((field_fmask & 0b00000001) != 0) & valid_qa).sum()),
            "high_aerosol_pixels": int(((aot_level == 3) & valid_qa).sum()),
            "qa_nodata_pixels": int((~valid_qa).sum()),
            "aot_level_counts": {
                "climatology": int(((aot_level == 0) & valid_qa).sum()),
                # HLS v2 guide expresses the pair in bit-7/bit-6 order:
                # 10 = low (raw byte bits 7:6 -> shifted value 2),
                # 01 = medium (shifted value 1).
                "low": int(((aot_level == 2) & valid_qa).sum()),
                "medium": int(((aot_level == 1) & valid_qa).sum()),
                "high": int(((aot_level == 3) & valid_qa).sum()),
            },
        }
        # DN -> surface reflectance (HLS v2.0 documented scale factor).
        reflectances = {
            surface: arr["data"] * HLS_REFLECTANCE_SCALE for surface, arr in band_arrays.items()
        }
        index_arrays = compute_index_arrays(reflectances=reflectances, indices=variables)
        fmask_uint8 = fmask.astype(np.uint8)
        high_aerosol_mask = (fmask_uint8 & FMASK_AOT_MASK) == FMASK_AOT_HIGH
        cloud_mask = ((fmask_uint8 & FMASK_EXCLUDE_MASK) != 0) | high_aerosol_mask
    except Exception as exc:  # noqa: BLE001 — raster errors can contain signed asset URLs
        reason = type(exc).__name__
        raise ProviderUnavailable(
            f"Scene {scene_id} could not be read or validated ({reason}); "
            "verify Earthdata credentials, COG availability, CRS metadata and QA assets.",
            details=[{"scene_id": scene_id, "reason": reason}],
        ) from exc

    observations: list[CanonicalObservation] = []
    for vcode in variables:
        index_array = index_arrays.get(vcode)
        stats = ZonalResult(index=vcode)
        if index_array is None or not bool(np.any(np.isfinite(index_array))):
            stats.flags.append("no_valid_pixels")
        else:
            inside = field_mask & np.isfinite(index_array)
            inside = inside & ~cloud_mask
            values = index_array[inside].astype("float64")
            masked_pixels = int(field_mask.sum())
            stats.masked_pixels = masked_pixels
            stats.valid_pixels = int(values.size)
            if masked_pixels > 0:
                stats.coverage_fraction = values.size / masked_pixels
            if values.size:
                stats.mean = float(np.mean(values))
                stats.median = float(np.median(values))
                stats.p5 = float(np.percentile(values, 5))
                stats.p25 = float(np.percentile(values, 25))
                stats.p75 = float(np.percentile(values, 75))
                stats.p95 = float(np.percentile(values, 95))
                stats.std = float(np.std(values, ddof=0)) if values.size > 1 else 0.0
            else:
                stats.flags.append("all_masked_pixels_invalid")
            if values.size < 5:
                stats.flags.append("insufficient_pixels_for_variability")
            if stats.coverage_fraction is not None and stats.coverage_fraction < 0.5:
                stats.flags.append("low_field_coverage")

        value = stats.mean if stats.valid_pixels > 0 else None
        quality = QualityStatus.valid if value is not None else QualityStatus.missing
        obs_metadata = dict(metadata_common)
        obs_metadata["zonal"] = stats.as_dict()
        obs_metadata["subfield_statistics_ok"] = subfield_statistics_ok(stats.valid_pixels)
        if value is None:
            obs_metadata["quality_flags"] = [
                {
                    "flag_code": "CLOUD_OCCLUDED_OR_NO_COVERAGE",
                    "severity": "warning",
                    "message": "No usable field pixels after Fmask/nodata masking.",
                }
            ]
        else:
            obs_metadata["quality_flags"] = [
                {
                    "flag_code": "NASA_HLS_ZONAL",
                    "severity": "info",
                    "message": (
                        f"Per-pixel {vcode.upper()} over field mask "
                        f"({stats.valid_pixels} valid pixels, HLS v2 Fmask "
                        "cloud/adjacency/shadow/snow/high-AOT masked; water retained)."
                    ),
                }
            ]
        observations.append(
            CanonicalObservation(
                variable_code=vcode,
                value=value,
                unit="index",
                observed_at=acquired_at,
                period_start=acquired_at,
                period_end=acquired_at,
                time_support=TimeSupport.instant,
                spatial_support_type="polygon_average",
                spatial_resolution_m=HLS_SPATIAL_RESOLUTION_M,
                quality_status=quality,
                uncertainty_value=None,
                uncertainty_type="not_quantified",
                evidence_class=EvidenceClass.satellite_derived_estimate,
                is_synthetic=False,
                processing_version=f"{PRODUCT_VERSION}+veg-raster",
                metadata=obs_metadata,
                quality_flags=obs_metadata["quality_flags"],
            )
        )
    return observations, warnings
