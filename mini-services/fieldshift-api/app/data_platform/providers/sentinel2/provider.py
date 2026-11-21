"""Sentinel-2 L2A STAC provider (P2.A) — Copernicus Data Space / STAC.

Implements the platform provider contract against STAC APIs that publish
Sentinel-2 L2A (surface reflectance) products:

- Primary target: the current Copernicus Data Space Ecosystem (CDSE) STAC v1
  catalogue. Discovery is public. Current item assets use `s3://eodata/...`
  URIs and require separate S3 access/secret keys generated in the CDSE
  account; these are NOT the account username/password. Keys are read from
  the secret-backed settings `CROPTWIST_CDSE_S3_ACCESS_KEY` and
  `CROPTWIST_CDSE_S3_SECRET_KEY`, never hardcoded.
- Alternate STAC endpoints can be configured, but the provider currently
  supports only directly accessible HTTPS assets. It does not yet implement
  provider-specific signing (for example, Microsoft Planetary Computer SAS
  signing). CDSE credentials are never forwarded to alternate hosts.

Processing pipeline per scene (when network access exists):
1. STAC search: bbox of field geometry, datetime range, collection
   `sentinel-2-l2a`, cloud-cover filter (`options.max_cloud_cover`, default 80).
2. The shared geospatial reader opens bounded GDAL VSI windows. CDSE S3 URIs
   are mapped to `/vsis3/` and read through the official S3 endpoint; other
   HTTPS assets are read through their native GDAL virtual filesystem.
   Reflectance bands are aligned to the red reference grid (bilinear), while
   categorical SCL is aligned with nearest-neighbour resampling.
3. Reflectance conversion uses STAC/GeoTIFF scale-offset metadata first, then
   `processing:version` (or legacy `s2:processing_baseline`); PB >= 04.00
   applies the -0.1 reflectance offset. SCL cloud/shadow/snow/unclassified
   classes are excluded before zonal statistics.
4. CDSE S3 keys are passed to GDAL only for `s3://eodata` assets. Signed
   third-party URLs and credentials are not persisted in the Data Passport.

Honesty properties:
- No scene is ever fabricated when the network is unreachable — failures
  raise `ProviderUnavailable` and the ingestion job records them.
- Sub-field spatial-variability claims below the zonal pixel threshold are
  flagged (`insufficient_pixels_for_variability`), never asserted.
- Live availability in the current sandbox: BLOCKED (no external network and
  no CDSE S3 keys). Contract tests use mocked STAC/HTTP and in-memory rasters;
  live use still requires network access and separately generated S3 keys.
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

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
from app.vegetation.indices import (
    SENTINEL2_BAND_RESOLUTION_M,
    SENTINEL2_L2A,
    supported_indices,
)

logger = logging.getLogger("croptwist.providers.sentinel2")

PROVIDER_CODE = "sentinel2"
PROVIDER_NAME = "Copernicus Sentinel-2 L2A (STAC)"
PRODUCT_CODE = "sentinel-2-l2a"
PRODUCT_VERSION = "stac-1.1.0"
STAC_SEARCH_PATH = "/search"

DEFAULT_COLLECTION = "sentinel-2-l2a"
DEFAULT_MAX_CLOUD = 80.0
SEARCH_TIMEOUT_SECONDS = 30.0

SUPPORTED_VARIABLES = supported_indices()

_CDSE_STAC_HOSTS = {
    "stac.dataspace.copernicus.eu",
    "catalogue.dataspace.copernicus.eu",  # legacy endpoint; explicit migration only
}
_CDSE_IDENTITY_HOST = "identity.dataspace.copernicus.eu"


def _https_host(url: str) -> str | None:
    try:
        parsed = urlsplit(str(url))
        if parsed.scheme.lower() != "https":
            return None
        return (parsed.hostname or "").lower() or None
    except ValueError:
        return None


def _is_cdse_asset_url(url: str) -> bool:
    host = _https_host(url)
    return bool(host and (host == "dataspace.copernicus.eu" or host.endswith(".dataspace.copernicus.eu")))


def _rasterio_asset_href(href: str) -> str:
    """Translate CDSE S3 URIs to GDAL's /vsis3/ virtual filesystem path."""
    parsed = urlsplit(str(href))
    if parsed.scheme.lower() != "s3":
        return str(href)
    if parsed.netloc.lower() != "eodata" or not parsed.path or parsed.query or parsed.fragment:
        raise ValueError("unsupported or malformed CDSE S3 asset URI")
    return f"/vsis3/{parsed.netloc}{parsed.path}"


def _safe_asset_href_for_metadata(href: str | None) -> str | None:
    """Drop credentials, query signatures and fragments before persistence."""
    if not href:
        return None
    try:
        parsed = urlsplit(str(href))
        if not parsed.scheme and not parsed.netloc:
            return parsed.path
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except ValueError:
        return "[redacted-invalid-asset-url]"

# Sentinel-2 SCL classes excluded from vegetation statistics:
# 0 no-data, 1 saturated/defective, 3 cloud shadow, 7 unclassified,
# 8 medium-probability cloud, 9 high-probability cloud, 10 cirrus,
# 11 snow/ice, and 255 (reprojected no-data). Dark-area (2) and water (6)
# are retained and can be useful signals for agricultural monitoring.
SCL_EXCLUDED_CLASSES = (0, 1, 3, 7, 8, 9, 10, 11, 255)

_SURFACE_TO_BAND = {
    "blue": SENTINEL2_L2A.blue,
    "green": SENTINEL2_L2A.green,
    "red": SENTINEL2_L2A.red,
    "nir": SENTINEL2_L2A.nir,
    "swir1": SENTINEL2_L2A.swir1,
}


class Sentinel2StacProvider:
    """Sentinel-2 L2A provider implementing the platform provider contract.

    All HTTP happens through an injected `httpx.Client`-compatible transport
    (default: real network) so contract tests can mock deterministically.
    """

    provider_code = PROVIDER_CODE

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._last_auth_headers: dict[str, str] = {}

    # ------------------------------------------------------------- metadata
    def supported_variables(self) -> list[str]:
        return list(SUPPORTED_VARIABLES)

    def collections(self) -> list[str]:
        return [DEFAULT_COLLECTION]

    def _provenance(self) -> SourceProvenance:
        return SourceProvenance(
            provider_code=PROVIDER_CODE,
            provider_name=PROVIDER_NAME,
            product_code=PRODUCT_CODE,
            product_version=PRODUCT_VERSION,
            license_name="Copernicus (free, open licence)",
            license_url="https://space.copernicus.eu/legal-notices",
            attribution_text="Contains modified Copernicus Sentinel data.",
            documentation_url="https://documentation.dataspace.copernicus.eu/",
            known_limitations=(
                "10 m VNIR / 20 m SWIR grid: spatial-variability claims over "
                "small fields are refused below the zonal pixel threshold. "
                "Cloud/shadow contamination is masked per scene via SCL; "
                "heavily clouded scenes are excluded by the cloud filter. "
                "L2A surface reflectance is an atmospheric estimate, not a "
                "ground measurement."
            ),
            retrieval_method="stac_api_gdal_vsi_windowed_read",
        )

    def _stac_base_url(self) -> str:
        return settings.sentinel2_stac_base_url.rstrip("/")

    def _auth_headers(self) -> dict[str, str]:
        """Legacy CDSE OAuth path; current STAC v1 discovery is public."""
        if _https_host(self._stac_base_url()) == "stac.dataspace.copernicus.eu":
            self._last_auth_headers = {}
            return {}
        username = settings.cdse_username
        password = settings.cdse_password
        stac_host = _https_host(self._stac_base_url())
        token_host = _https_host(settings.cdse_token_url)
        # CDSE credentials must never be sent to an alternate STAC provider or
        # an operator-overridden token endpoint. Alternate catalogues use their
        # own signed asset URLs instead.
        if (
            not username
            or not password
            or stac_host not in _CDSE_STAC_HOSTS
            or token_host != _CDSE_IDENTITY_HOST
        ):
            self._last_auth_headers = {}
            return {}
        try:
            response = (self._client or httpx).post(
                settings.cdse_token_url,
                data={
                    "grant_type": "password",
                    "username": username,
                    "password": password,
                    "client_id": "cdse-public",
                },
                timeout=SEARCH_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            token = response.json().get("access_token")
            if token:
                self._last_auth_headers = {"Authorization": f"Bearer {token}"}
                return dict(self._last_auth_headers)
        except Exception as exc:  # noqa: BLE001
            logger.warning("CDSE authentication failed (%s); continuing anonymous", exc)
        self._last_auth_headers = {}
        return {}


    # -------------------------------------------------------------- search
    def search_items(
        self,
        *,
        geometry_geojson: dict[str, Any],
        start: datetime,
        end: datetime,
        max_cloud_cover: float = DEFAULT_MAX_CLOUD,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """STAC item search with bounded, same-origin pagination."""
        bbox = _bbox_of_geojson(geometry_geojson)
        if bbox is None:
            raise ProviderRequestError(
                "Field geometry could not be converted to a STAC bbox.",
                details=[{"field": "geometry", "reason": "unsupported or empty geometry"}],
            )
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ProviderRequestError(
                "Sentinel-2 STAC page size must be a positive integer.",
                details=[{"field": "limit", "reason": "expected a positive integer"}],
            )
        if isinstance(max_cloud_cover, bool):
            raise ProviderRequestError(
                "Sentinel-2 maximum cloud cover must be numeric.",
                details=[{"field": "max_cloud_cover", "reason": "boolean is not a valid number"}],
            )
        try:
            cloud_cover = float(max_cloud_cover)
        except (TypeError, ValueError) as exc:
            raise ProviderRequestError(
                "Sentinel-2 maximum cloud cover must be numeric.",
                details=[{"field": "max_cloud_cover", "reason": "expected a number"}],
            ) from exc
        if not 0.0 <= cloud_cover <= 100.0:
            raise ProviderRequestError(
                "Sentinel-2 maximum cloud cover must be between 0 and 100.",
                details=[{"field": "max_cloud_cover", "reason": "outside supported range"}],
            )
        page_size = min(limit, 200)
        max_items = 2000
        max_pages = 20
        payload: dict[str, Any] = {
            "collections": [DEFAULT_COLLECTION],
            "bbox": bbox,
            "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "limit": page_size,
            "query": {"eo:cloud_cover": {"lt": cloud_cover}},
        }
        base_url = self._stac_base_url()
        origin = urlsplit(base_url)
        if origin.scheme.lower() != "https" or not origin.hostname or origin.username or origin.password:
            raise ProviderRequestError(
                "Sentinel-2 STAC endpoint must use HTTPS.",
                details=[{"field": "stac_base_url", "reason": "HTTPS endpoint without embedded credentials required"}],
            )
        try:
            origin_port = origin.port or 443
        except ValueError as exc:
            raise ProviderRequestError(
                "Sentinel-2 STAC endpoint has an invalid port.",
                details=[{"field": "stac_base_url", "reason": "invalid HTTPS port"}],
            ) from exc
        headers = self._auth_headers()
        client = self._client or httpx
        next_request: tuple[str, str, dict[str, Any] | None] = (
            "POST", f"{base_url}{STAC_SEARCH_PATH}", payload
        )
        visited: set[tuple[str, str, str]] = set()
        collected: list[dict[str, Any]] = []
        for _ in range(max_pages):
            method, url, request_body = next_request
            parsed = urlsplit(url)
            try:
                parsed_port = parsed.port or 443
            except ValueError:
                parsed_port = None
            if (
                parsed.scheme.lower() != "https"
                or (parsed.hostname or "").lower() != (origin.hostname or "").lower()
                or parsed_port != origin_port
                or parsed.username
                or parsed.password
            ):
                raise ProviderRequestError(
                    "Sentinel-2 STAC pagination returned an untrusted URL.",
                    details=[{"reason": "pagination must remain on the configured HTTPS origin"}],
                )
            body_key = repr(sorted(request_body.items())) if request_body else ""
            visit_key = (method, url, body_key)
            if visit_key in visited:
                raise ProviderRequestError(
                    "Sentinel-2 STAC pagination loop detected.",
                    details=[{"reason": "repeated pagination request"}],
                )
            visited.add(visit_key)
            try:
                if method == "POST":
                    response = client.post(
                        url, json=request_body, headers=headers, timeout=SEARCH_TIMEOUT_SECONDS
                    )
                else:
                    response = client.get(
                        url, headers=headers, timeout=SEARCH_TIMEOUT_SECONDS
                    )
                response.raise_for_status()
                body = response.json()
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(
                    "Sentinel-2 STAC search failed (network or API error).",
                    details=[{"reason": str(exc)}],
                ) from exc
            except ValueError as exc:
                raise ProviderRequestError(
                    "Sentinel-2 STAC search returned a malformed response.",
                    details=[{"reason": str(exc)}],
                ) from exc
            if not isinstance(body, dict) or not isinstance(body.get("features"), list):
                raise ProviderRequestError(
                    "STAC response has no 'features' array.",
                    details=[{"reason": "unexpected STAC payload shape"}],
                )
            features = body["features"]
            if any(not isinstance(feature, dict) for feature in features):
                raise ProviderRequestError(
                    "STAC response contains an invalid feature.",
                    details=[{"reason": "features must be objects"}],
                )
            remaining = max_items - len(collected)
            collected.extend(features[:remaining])
            if len(collected) >= max_items:
                return collected
            links = body.get("links", [])
            if not isinstance(links, list):
                raise ProviderRequestError(
                    "STAC response has an invalid links array.",
                    details=[{"reason": "links must be an array"}],
                )
            next_links = [
                link for link in links
                if isinstance(link, dict) and link.get("rel") == "next"
            ]
            if not next_links:
                return collected
            link = next_links[0]
            href = link.get("href")
            if not isinstance(href, str) or not href.strip():
                raise ProviderRequestError(
                    "STAC next link is missing a valid href.",
                    details=[{"reason": "invalid pagination link"}],
                )
            method_value = link.get("method", "GET")
            if not isinstance(method_value, str) or method_value.upper() not in {"GET", "POST"}:
                raise ProviderRequestError(
                    "STAC next link uses an unsupported HTTP method.",
                    details=[{"reason": "only GET and POST pagination are supported"}],
                )
            next_body = link.get("body") if method_value.upper() == "POST" else None
            if next_body is not None and not isinstance(next_body, dict):
                raise ProviderRequestError(
                    "STAC next link contains an invalid POST body.",
                    details=[{"reason": "pagination body must be an object"}],
                )
            next_request = (
                method_value.upper(),
                urljoin(url, href),
                next_body,
            )
        raise ProviderUnavailable(
            "Sentinel-2 STAC pagination exceeded the safety page limit.",
            details=[{"max_pages": max_pages, "max_items": max_items}],
        )

    # ------------------------------------------------------- observations
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
                details=[{"field": "variables", "reason": "sentinel2 produces vegetation indices only"}],
            )
        max_cloud = float(options.get("max_cloud_cover", DEFAULT_MAX_CLOUD))
        items = self.search_items(
            geometry_geojson=area_of_interest.geometry_geojson,
            start=start.astimezone(UTC),
            end=end.astimezone(UTC),
            max_cloud_cover=max_cloud,
        )
        if not items:
            return ProviderFetchResult(
                provider_code=PROVIDER_CODE,
                provenance=self._provenance(),
                observations=[],
                warnings=[
                    "No Sentinel-2 L2A scenes matched the geometry/date/cloud "
                    "filters. This is a data-availability gap, not an error."
                ],
                coverage={"scenes": 0, "start": start.isoformat(), "end": end.isoformat()},
                provider_request_id=None,
                raw_reference=None,
                input_record_count=0,
            )

        observations: list[CanonicalObservation] = []
        warnings: list[str] = []
        scenes_processed = 0
        for item in items:
            scene_id = item.get("id")
            if not scene_id:
                continue
            properties = item.get("properties") or {}
            acquired_raw = properties.get("datetime")
            if not acquired_raw:
                warnings.append(f"Scene {scene_id} has no acquisition timestamp; skipped.")
                continue
            try:
                acquired_at = datetime.fromisoformat(
                    acquired_raw.replace("Z", "+00:00")
                ).astimezone(UTC)
            except ValueError:
                warnings.append(f"Scene {scene_id} has an unparseable timestamp; skipped.")
                continue
            cloud_cover = properties.get("eo:cloud_cover")
            scene_obs, scene_warnings = _observations_from_item(
                item=item,
                scene_id=scene_id,
                acquired_at=acquired_at,
                cloud_cover=cloud_cover,
                variables=sorted(set(variables)),
                geometry_geojson=area_of_interest.geometry_geojson,
                options=options,
                gdal_auth_headers=self._last_auth_headers,
            )
            observations.extend(scene_obs)
            warnings.extend(scene_warnings)
            scenes_processed += 1

        return ProviderFetchResult(
            provider_code=PROVIDER_CODE,
            provenance=self._provenance(),
            observations=observations,
            warnings=warnings,
            coverage={
                "scenes": scenes_processed,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "max_cloud_cover": max_cloud,
            },
            provider_request_id=None,
            raw_reference=None,
            input_record_count=len(observations),
        )


# --------------------------------------------------------------------- helpers
def _bbox_of_geojson(geometry_geojson: dict[str, Any]) -> list[float] | None:
    try:
        from shapely.geometry import shape

        geom = shape(geometry_geojson)
        if geom.is_empty:
            return None
        minx, miny, maxx, maxy = geom.bounds
        return [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)]
    except Exception:  # noqa: BLE001
        return None


def _assets_for_surfaces(item: dict[str, Any]) -> dict[str, str]:
    """Map reflectance surfaces -> asset hrefs for a STAC item.

    Uses documented Sentinel-2 band names (B02/B03/B04/B08/B11) tolerating
    suffixed asset keys ("B04_10m"). Missing surfaces are simply absent —
    index computation refuses them honestly.
    """
    surfaces = {
        "blue": SENTINEL2_L2A.blue,
        "green": SENTINEL2_L2A.green,
        "red": SENTINEL2_L2A.red,
        "nir": SENTINEL2_L2A.nir,
        "swir1": SENTINEL2_L2A.swir1,
    }
    assets = item.get("assets") or {}
    hrefs: dict[str, str] = {}
    for surface, band_name in surfaces.items():
        if band_name is None:
            continue
        asset = assets.get(band_name)
        if asset is None:
            for key, candidate in assets.items():
                if key.split("_")[0] == band_name and isinstance(candidate, dict) and candidate.get("href"):
                    asset = candidate
                    break
        if isinstance(asset, dict) and asset.get("href"):
            hrefs[surface] = asset["href"]
    return hrefs


def _scl_asset_href(item: dict[str, Any]) -> str | None:
    assets = item.get("assets") or {}
    for key, asset in assets.items():
        if (
            key.split("_")[0].lower() == "scl"
            and isinstance(asset, dict)
            and asset.get("href")
        ):
            return str(asset["href"])
    return None


def _load_scene_arrays(
    item: dict[str, Any],
    hrefs: dict[str, str],
    geometry_geojson: dict[str, Any],
    gdal_env: dict[str, str] | None = None,
):
    """Read a field window and align reflectance/SCL assets to the red 10 m grid."""
    from app.geospatial import preprocessing as pre

    scl_href = _scl_asset_href(item)
    if not scl_href:
        raise ValueError("Sentinel-2 scene has no SCL quality asset")
    assets = {
        **{surface: _rasterio_asset_href(href) for surface, href in hrefs.items()},
        "fmask": _rasterio_asset_href(scl_href),
    }
    return pre.read_scene_window(
        assets=assets,
        surfaces=tuple(
            surface
            for surface in ("red", "nir", "blue", "green", "swir1")
            if hrefs.get(surface)
        ),
        geometry_geojson=geometry_geojson,
        gdal_env=gdal_env or {},
        max_window_mb=settings.raster_max_field_window_mb,
        nodata_fallbacks={**{surface: 0 for surface in hrefs}, "fmask": 0},
    )


def _asset_for_band(item: dict[str, Any], band_name: str) -> dict[str, Any]:
    assets = item.get("assets") or {}
    for key, asset in assets.items():
        if key.split("_")[0].upper() == band_name.upper() and isinstance(asset, dict):
            return asset
    return {}


def _radiometry_for_scene(
    item: dict[str, Any],
    reading: Any,
    hrefs: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """Resolve per-band scale/offset from STAC, GeoTIFF tags, then baseline."""
    properties = item.get("properties") or {}
    raw_baseline = properties.get("processing:version") or properties.get("s2:processing_baseline")
    baseline_offset: float | None = None
    if raw_baseline is not None:
        match = re.match(r"^\s*(\d+(?:\.\d+)?)", str(raw_baseline))
        if match:
            baseline_offset = -0.1 if float(match.group(1)) >= 4.0 else 0.0

    radiometry: dict[str, dict[str, Any]] = {}
    for surface in hrefs:
        band_name = _SURFACE_TO_BAND[surface]
        asset = _asset_for_band(item, band_name)
        bands = asset.get("raster:bands") or asset.get("bands") or []
        band_metadata = bands[0] if isinstance(bands, list) and bands else (
            bands if isinstance(bands, dict) else {}
        )
        stac_scale = band_metadata.get("scale")
        stac_offset = band_metadata.get("offset")
        file_scale = reading.scale_values.get(surface, 1.0)
        file_offset = reading.offset_values.get(surface, 0.0)

        if stac_scale is not None:
            scale, scale_source = float(stac_scale), "stac_raster_bands"
        elif file_scale not in (None, 1.0):
            scale, scale_source = float(file_scale), "geotiff_scale"
        else:
            scale, scale_source = SENTINEL2_L2A.scale, "sentinel2_default_scale"

        if stac_offset is not None:
            offset, offset_source = float(stac_offset), "stac_raster_bands"
        elif file_offset not in (None, 0.0):
            offset, offset_source = float(file_offset), "geotiff_offset"
        elif baseline_offset is not None:
            offset, offset_source = baseline_offset, "processing_baseline"
        else:
            raise ValueError(
                f"band {band_name} has no offset metadata and the scene has no "
                "Sentinel-2 processing baseline; refusing an unverified reflectance conversion"
            )

        radiometry[surface] = {
            "band": band_name,
            "scale": scale,
            "offset": offset,
            "scale_source": scale_source,
            "offset_source": offset_source,
        }
    return radiometry


def _gdal_env_options(
    headers: dict[str, str] | None,
    asset_hrefs: list[str | None] | None = None,
) -> dict[str, str]:
    """Build bounded GDAL options for CDSE S3 or trusted HTTPS assets.

    The current CDSE STAC API publishes s3://eodata asset URIs. Those require
    separate CDSE-generated S3 keys; the account password/OIDC bearer token is
    not an S3 credential. Third-party signed HTTPS assets never receive CDSE
    credentials through GDAL_HTTP_HEADERS.
    """
    env = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "VSI_CACHE": "TRUE",
        "GDAL_HTTP_TIMEOUT": str(int(settings.sentinel2_timeout_seconds)),
    }
    if not asset_hrefs:
        return env

    parsed = [urlsplit(str(href)) for href in asset_hrefs if href]
    if len(parsed) != len(asset_hrefs):
        return env

    if any(item.scheme.lower() == "s3" for item in parsed):
        if not all(item.scheme.lower() == "s3" and item.netloc.lower() == "eodata" and item.path for item in parsed):
            raise ProviderUnavailable(
                "Sentinel-2 STAC returned an unsupported S3 asset location.",
                details=[{"reason": "unsupported_s3_asset_host"}],
            )
        access_key = settings.cdse_s3_access_key
        secret_key = settings.cdse_s3_secret_key
        if not access_key or not secret_key:
            raise ProviderUnavailable(
                "CDSE S3 credentials are required to read Sentinel-2 assets. "
                "Generate S3 keys in your Copernicus Data Space account and "
                "configure CROPTWIST_CDSE_S3_ACCESS_KEY and CROPTWIST_CDSE_S3_SECRET_KEY.",
                details=[{"reason": "cdse_s3_credentials_missing"}],
            )
        env.update(
            {
                "AWS_ACCESS_KEY_ID": access_key,
                "AWS_SECRET_ACCESS_KEY": secret_key,
                "AWS_S3_ENDPOINT": "eodata.dataspace.copernicus.eu",
                "AWS_DEFAULT_REGION": "default",
                "AWS_VIRTUAL_HOSTING": "FALSE",
                "AWS_HTTPS": "YES",
            }
        )
        return env

    if headers and all(
        item.scheme.lower() == "https" and _is_cdse_asset_url(item.geturl())
        for item in parsed
    ):
        header_lines = [f"{key}: {value}" for key, value in headers.items()]
        env["GDAL_HTTP_HEADERS"] = "\r\n".join(header_lines) + "\r\n"
    return env


def _observations_from_item(
    *,
    item: dict[str, Any],
    scene_id: str,
    acquired_at: datetime,
    cloud_cover: float | None,
    variables: list[str],
    geometry_geojson: dict[str, Any],
    options: dict[str, Any],
    gdal_env: dict[str, str] | None = None,
    gdal_auth_headers: dict[str, str] | None = None,
) -> tuple[list[CanonicalObservation], list[str]]:
    """Compute indices on one CRS-correct, aligned, quality-masked field window."""
    import numpy as np

    from app.geospatial import preprocessing as pre
    from app.vegetation.raster_indices import compute_index_arrays
    from app.vegetation.zonal import ZonalResult, subfield_statistics_ok

    warnings: list[str] = []
    hrefs = _assets_for_surfaces(item)
    missing = [s for s in ("red", "nir") if s not in hrefs]
    if missing:
        warnings.append(
            f"Scene {scene_id}: required band assets missing ({', '.join(missing)}); scene skipped."
        )
        return [], warnings
    scl_href = _scl_asset_href(item)
    if not scl_href:
        warnings.append(f"Scene {scene_id}: SCL quality asset missing; scene skipped.")
        return [], warnings

    properties = item.get("properties") or {}
    platform = properties.get("platform") or "Sentinel-2"
    processing_baseline = properties.get("processing:version") or properties.get("s2:processing_baseline")
    metadata_common: dict[str, Any] = {
        "scene_id": scene_id,
        "granule_id": scene_id,
        "platform": platform,
        "processing_baseline": processing_baseline,
        "cloud_cover_pct": cloud_cover,
        "spatial_resolution_m": SENTINEL2_L2A.spatial_resolution_m,
        "asset_refs": {
            **{key: _safe_asset_href_for_metadata(value) for key, value in hrefs.items()},
            "scl": _safe_asset_href_for_metadata(scl_href),
        },
        "raster_url": _safe_asset_href_for_metadata(hrefs.get("nir")),
        "collection": DEFAULT_COLLECTION,
        "provider_code": PROVIDER_CODE,
    }

    try:
        safe_gdal_env = _gdal_env_options(
            gdal_auth_headers or {}, [*hrefs.values(), scl_href]
        )
        if gdal_env:
            safe_gdal_env.update(gdal_env)
        reading = _load_scene_arrays(item, hrefs, geometry_geojson, safe_gdal_env)
        scl = reading.fmask
        shape = (reading.height, reading.width)
        if scl is None or scl.shape != shape:
            raise ValueError("SCL QA asset is missing or not aligned to the field window")
        field_mask = pre.field_mask_for_window(
            geometry_geojson=geometry_geojson,
            crs_string=reading.crs,
            transform=reading.transform,
            width=reading.width,
            height=reading.height,
        )
        radiometry = _radiometry_for_scene(item, reading, hrefs)
        reflectances = {
            surface: data * radiometry[surface]["scale"] + radiometry[surface]["offset"]
            for surface, data in reading.arrays.items()
        }
        index_arrays = compute_index_arrays(reflectances=reflectances, indices=variables)
        cloud_mask = np.isin(scl, SCL_EXCLUDED_CLASSES)
        metadata_common["radiometry"] = radiometry
        metadata_common["scl_excluded_classes"] = list(SCL_EXCLUDED_CLASSES)
        metadata_common["raster_window"] = {
            "crs": reading.crs,
            "bounds": list(reading.window_bounds),
            "width_px": reading.width,
            "height_px": reading.height,
            "read_bytes_estimate": reading.read_bytes_estimate,
            "read_mode": "windowed_range_read",
            "band_alignment": reading.band_alignment,
            "reference_grid": "red_10m",
        }
    except ProviderUnavailable:
        raise
    except ValueError as exc:
        # Preserve the actionable radiometry failure without exposing asset URLs
        # or any signed credentials that may appear in lower-level exceptions.
        if "has no offset metadata and the scene has no Sentinel-2 processing baseline" in str(exc):
            raise ProviderUnavailable(
                f"Scene {scene_id} has no Sentinel-2 processing baseline or per-band offset metadata; "
                "refusing an unverified reflectance conversion.",
                details=[{"scene_id": scene_id, "reason": "missing_sentinel2_radiometric_offset"}],
            ) from exc
        raise ProviderUnavailable(
            f"Scene {scene_id} could not be read or validated (ValueError); verify provider access, "
            "raster CRS, QA assets and radiometric metadata.",
            details=[{"scene_id": scene_id, "reason": "ValueError"}],
        ) from exc
    except Exception as exc:  # noqa: BLE001 — network/raster failures degrade per scene
        # Raster/GDAL errors can echo signed asset URLs. Keep secrets out of
        # API responses, persisted job details and logs.
        reason = type(exc).__name__
        raise ProviderUnavailable(
            f"Scene {scene_id} could not be read or validated ({reason}); verify "
            "provider access, raster CRS, QA assets and radiometric metadata.",
            details=[{"scene_id": scene_id, "reason": reason}],
        ) from exc

    observations: list[CanonicalObservation] = []
    for vcode in variables:
        index_array = index_arrays.get(vcode)
        stats = ZonalResult(index=vcode)
        if index_array is None or not bool(np.any(np.isfinite(index_array))):
            stats.flags.append("no_valid_pixels")
        else:
            inside = field_mask & np.isfinite(index_array) & ~cloud_mask
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
        required_surfaces = pre.required_surfaces_for_indices([vcode])
        surface_resolution = {
            surface: SENTINEL2_BAND_RESOLUTION_M.get(_SURFACE_TO_BAND[surface], 10.0)
            for surface in required_surfaces
        }
        effective_resolution = max(surface_resolution.values(), default=10.0)
        obs_metadata = dict(metadata_common)
        obs_metadata["spatial_resolution_m"] = effective_resolution
        obs_metadata["zonal"] = stats.as_dict()
        obs_metadata["subfield_statistics_ok"] = subfield_statistics_ok(stats.valid_pixels)
        if value is None:
            obs_metadata["quality_flags"] = [
                {
                    "flag_code": "CLOUD_OCCLUDED_OR_NO_COVERAGE",
                    "severity": "warning",
                    "message": "No usable field pixels after SCL/nodata masking.",
                }
            ]
        else:
            obs_metadata["quality_flags"] = [
                {
                    "flag_code": "SENTINEL2_L2A_ZONAL",
                    "severity": "info",
                    "message": (
                        f"Per-pixel {vcode.upper()} over field mask "
                        f"({stats.valid_pixels} valid pixels; SCL cloud/shadow/"
                        f"unclassified/cirrus/snow mask applied; effective input "
                        f"resolution {effective_resolution:g} m)."
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
                spatial_resolution_m=effective_resolution,
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


