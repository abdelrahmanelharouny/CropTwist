import pytest

from app.data_platform.providers.wapor_v3_catalog import (
    WAPOR_V3_PRODUCTS,
    get_product,
    products_for_country,
)


def test_egypt_has_global_and_national_wapor_v3_products():
    products = products_for_country("egy", level=2)
    assert {item.code for item in products} == {
        "L2-AETI-D", "L2-E-D", "L2-I-D", "L2-T-D", "L2-NPP-D", "L2-RSM-D"
    }
    assert all(item.resolution_m == 100 for item in products)


def test_global_products_are_available_for_all_countries():
    assert any(item.level == 1 for item in products_for_country("EGY", level=1))
    assert any(item.level == 1 for item in products_for_country("KEN", level=1))


def test_catalog_rejects_unknown_product_and_invalid_country():
    with pytest.raises(KeyError):
        get_product("L3-ZAN-AETI-D")
    with pytest.raises(ValueError):
        products_for_country("EG")


def test_catalog_collection_ids_are_unique():
    codes = [item.code for item in WAPOR_V3_PRODUCTS]
    assert len(codes) == len(set(codes))

def test_ret_resolution_and_product_units_are_not_misrepresented():
    ret = get_product("L1-RET-D")
    aeti = get_product("L2-AETI-D")
    rsm = get_product("L2-RSM-D")
    assert ret.resolution_m == 30000
    assert ret.unit == "mm/day"
    assert aeti.resolution_m == 100
    assert aeti.scale_factor == 0.1
    assert rsm.unit == "%"
    assert rsm.scale_factor == 0.001

def test_wapor_canonical_variables_keep_distinct_physical_meanings_and_units():
    from app.data_platform.contracts.variables import VARIABLE_CATALOG

    assert VARIABLE_CATALOG["actual_evapotranspiration_interception"].unit == "mm/day"
    assert VARIABLE_CATALOG["actual_evapotranspiration_interception"].typical_time_support == "dekadal"
    assert VARIABLE_CATALOG["relative_soil_moisture"].unit == "%"
    assert VARIABLE_CATALOG["relative_soil_moisture"].code != "soil_moisture_surface"
    assert VARIABLE_CATALOG["net_primary_productivity"].unit == "gC/m2/day"


def test_wapor_provider_variables_are_registered_as_distinct_canonical_codes():
    from app.data_platform.contracts.variables import VARIABLE_CATALOG
    from app.data_platform.providers.wapor_v3 import WAPOR_EGYPT_L2_VARIABLE_MAP, WaPORV3Provider

    assert set(WaPORV3Provider.supported_variables()) == set(WAPOR_EGYPT_L2_VARIABLE_MAP)
    for variable in WaPORV3Provider.supported_variables():
        definition = VARIABLE_CATALOG[variable]
        assert definition.typical_time_support == "dekadal"
        assert definition.evidence_class_hint == "satellite_derived_estimate"

    assert VARIABLE_CATALOG["actual_evapotranspiration_interception"].unit == "mm/day"
    assert VARIABLE_CATALOG["relative_soil_moisture"].unit == "%"
    assert VARIABLE_CATALOG["net_primary_productivity"].unit == "gC/m2/day"


def test_wapor_provider_is_registered_for_environmental_ingestion():
    from app.data_platform.registry.provider_registry import get_provider_registry
    from app.data_platform.providers.wapor_v3 import WaPORV3Provider

    provider = get_provider_registry().get("fao_wapor_v3")
    assert isinstance(provider, WaPORV3Provider)

def test_l1_interception_unit_conflict_withholds_canonical_physical_unit():
    # DE Africa's current specification lists mm/year for L1-I-D, while the
    # FAO GEE collection describes average daily interception over a dekad.
    # Keep the product discoverable but do not publish a guessed canonical unit.
    product = get_product("L1-I-D")
    assert product.temporal_support == "dekadal"
    assert product.unit is None
    assert product.scale_factor == 0.1


def test_wapor_raster_catalog_requires_exact_product_period_and_deduplicates(monkeypatch):
    from app.data_platform.providers.wapor_v3 import WaPORProviderError, WaPORV3Client

    items = [
        {
            "code": "WAPOR-3.L2-AETI-D.2025-01-D1",
            "downloadUrl": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/a.tif",
        },
        {
            "code": "WAPOR-3.L2-E-D.2025-01-D1",
            "downloadUrl": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/wrong-product.tif",
        },
        {
            "code": "WAPOR-3.L2-AETI-D.2025-01-D2.extra",
            "downloadUrl": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/malformed.tif",
        },
        {
            "code": "WAPOR-3.L2-AETI-D.2025-13-D1",
            "downloadUrl": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/invalid-month.tif",
        },
    ]
    client = WaPORV3Client()
    monkeypatch.setattr(client, "_collect", lambda _: items)
    rasters = client.list_rasters("L2-AETI-D")
    assert [item["period_code"] for item in rasters] == ["2025-01-D1"]

    monkeypatch.setattr(client, "_collect", lambda _: [items[0], items[0]])
    with pytest.raises(WaPORProviderError, match="duplicate raster identifier"):
        client.list_rasters("L2-AETI-D")


@pytest.mark.parametrize(
    "url",
    [
        "https://storage.googleapis.com/fao-gismgr-wapor-3-data/a.tif",
        "https://storage.googleapis.com.evil.example/fao-gismgr-wapor-3-data/a.tif",
        "https://storage.googleapis.com/attacker-bucket/a.tif",
        "http://storage.googleapis.com/fao-gismgr-wapor-3-data/a.tif",
        "https://user@storage.googleapis.com/fao-gismgr-wapor-3-data/a.tif",
        "https://storage.googleapis.com:444/fao-gismgr-wapor-3-data/a.tif",
        "https://storage.googleapis.com:invalid/fao-gismgr-wapor-3-data/a.tif",
        "https://storage.googleapis.com/fao-gismgr-wapor-3-data/",
    ],
)
def test_wapor_raster_url_is_restricted_to_official_bucket(url):
    from app.data_platform.providers.wapor_v3 import _safe_raster_url

    assert _safe_raster_url(url) is (url == "https://storage.googleapis.com/fao-gismgr-wapor-3-data/a.tif")


def test_wapor_field_window_rejects_catalogue_record_with_mismatched_period():
    from app.data_platform.providers.wapor_v3 import WaPORV3Client

    client = WaPORV3Client()
    with pytest.raises(ValueError, match="matching period"):
        client.read_field_window(
            mapset_code="L2-AETI-D",
            raster={
                "code": "WAPOR-3.L2-AETI-D.2025-01-D1",
                "period_code": "2025-01-D2",
                "download_url": "https://storage.googleapis.com/fao-gismgr-wapor-3-data/a.tif",
            },
            geometry_geojson={"type": "Polygon", "coordinates": []},
        )
