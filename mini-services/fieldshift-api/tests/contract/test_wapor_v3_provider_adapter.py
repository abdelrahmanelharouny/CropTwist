from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.errors import ProviderUnavailable, UnsupportedVariable
from app.data_platform.contracts.observations import AreaOfInterest, QualityStatus, TimeSupport
from app.data_platform.providers.wapor_v3 import (
    WAPOR_EGYPT_L2_VARIABLE_MAP,
    WaPORV3Provider,
    _dekad_period,
)

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[31.0, 30.0], [31.1, 30.0], [31.1, 30.1], [31.0, 30.1], [31.0, 30.0]]],
}


def _window(**overrides):
    values = {
        "raster_code": "WAPOR-3.L2-AETI-D.2025-01-D1",
        "valid_pixel_count": 12,
        "nodata_pixel_count": 3,
        "raw_mean": 25.0,
        "raw_median": 24.0,
        "scaled_mean": 2.5,
        "scaled_median": 2.4,
        "scale_factor": 0.1,
        "offset": 0.0,
        "unit": "mm/day",
        "resolution_m": 100,
        "asset_layout": "COG",
        "overview_levels": (2, 4, 8),
        "license": "CC BY-SA 4.0",
        "metadata_reference": "https://docs.digitalearthafrica.org/en/latest/data_specs/WaPOR_specs.html",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeClient:
    def __init__(self, rasters=None, window=None):
        self.rasters = rasters if rasters is not None else [
            {"code": "WAPOR-3.L2-AETI-D.2025-01-D1", "period_code": "2025-01-D1"},
            {"code": "WAPOR-3.L2-AETI-D.2025-01-D2", "period_code": "2025-01-D2"},
        ]
        self.window = window or _window()
        self.calls = []

    def list_rasters(self, mapset_code):
        self.calls.append(("list", mapset_code))
        return self.rasters

    def read_field_window(self, **kwargs):
        self.calls.append(("read", kwargs["mapset_code"], kwargs["raster"]["code"]))
        return self.window


def test_wapor_adapter_maps_only_verified_egypt_l2_variables():
    assert WAPOR_EGYPT_L2_VARIABLE_MAP["actual_evapotranspiration_interception"] == "L2-AETI-D"
    assert "relative_soil_moisture" in WaPORV3Provider.supported_variables()
    assert "reference_et0" not in WaPORV3Provider.supported_variables()


def test_wapor_fetch_returns_canonical_dekadal_observation_with_provenance():
    client = FakeClient()
    result = WaPORV3Provider(client).fetch_observations(
        area_of_interest=AreaOfInterest(field_id="field-1", geometry_geojson=GEOMETRY),
        variables=["actual_evapotranspiration_interception"],
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 10, 23, 59, tzinfo=UTC),
    )
    assert len(result.observations) == 1
    observation = result.observations[0]
    assert observation.variable_code == "actual_evapotranspiration_interception"
    assert observation.value == pytest.approx(2.5)
    assert observation.unit == "mm/day"
    assert observation.time_support == TimeSupport.dekadal
    assert observation.quality_status == QualityStatus.valid
    assert observation.period_start == datetime(2025, 1, 1, tzinfo=UTC)
    assert observation.period_end.day == 10
    assert observation.evidence_class.value == "satellite_derived_estimate"
    assert observation.metadata["valid_pixel_fraction"] == pytest.approx(0.8)
    assert result.provenance.license_name == "CC BY-SA 4.0"
    assert result.coverage["rasters_seen"] == 1
    assert client.calls[-1][2].endswith("2025-01-D1")


def test_wapor_fetch_represents_no_valid_pixels_as_missing_not_zero():
    client = FakeClient(window=_window(valid_pixel_count=0, nodata_pixel_count=15, raw_mean=None, raw_median=None, scaled_mean=None, scaled_median=None))
    result = WaPORV3Provider(client).fetch_observations(
        area_of_interest=AreaOfInterest(geometry_geojson=GEOMETRY),
        variables=["actual_evapotranspiration_interception"],
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 10, tzinfo=UTC),
    )
    assert result.observations[0].value is None
    assert result.observations[0].quality_status == QualityStatus.missing
    assert result.observations[0].quality_flags[0]["code"] == "no_valid_pixels"


def test_wapor_fetch_fails_closed_when_physical_scale_is_unresolved():
    client = FakeClient(window=_window(scaled_mean=None, scaled_median=None, scale_factor=None))
    with pytest.raises(ProviderUnavailable, match="unit/scale metadata"):
        WaPORV3Provider(client).fetch_observations(
            area_of_interest=AreaOfInterest(geometry_geojson=GEOMETRY),
            variables=["actual_evapotranspiration_interception"],
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 10, tzinfo=UTC),
        )


def test_wapor_fetch_rejects_unmapped_variable_and_non_egypt_level():
    provider = WaPORV3Provider(FakeClient())
    args = {
        "area_of_interest": AreaOfInterest(geometry_geojson=GEOMETRY),
        "start": datetime(2025, 1, 1, tzinfo=UTC),
        "end": datetime(2025, 1, 10, tzinfo=UTC),
    }
    with pytest.raises(UnsupportedVariable):
        provider.fetch_observations(variables=["reference_et0"], **args)
    with pytest.raises(UnsupportedVariable):
        provider.fetch_observations(
            variables=["actual_evapotranspiration_interception"],
            options={"country_code": "KEN"},
            **args,
        )


def test_wapor_fetch_normalizes_naive_datetimes_as_utc():
    result = WaPORV3Provider(FakeClient()).fetch_observations(
        area_of_interest=AreaOfInterest(geometry_geojson=GEOMETRY),
        variables=["actual_evapotranspiration_interception"],
        start=datetime(2025, 1, 1),
        end=datetime(2025, 1, 10),
    )
    assert result.observations[0].period_start.tzinfo == UTC


def test_wapor_period_parser_handles_last_dekad_of_february():
    start, end = _dekad_period("2024-02-D3")
    assert start == datetime(2024, 2, 21, tzinfo=UTC)
    assert end == datetime(2024, 2, 29, 23, 59, 59, 999999, tzinfo=UTC)
