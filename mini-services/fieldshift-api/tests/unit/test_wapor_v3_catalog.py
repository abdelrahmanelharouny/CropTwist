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
