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
