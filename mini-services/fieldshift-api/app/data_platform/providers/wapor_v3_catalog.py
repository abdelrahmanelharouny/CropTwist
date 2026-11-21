"""Verified FAO WaPOR v3 product metadata.

This registry describes published product coverage and identifiers only. It
does not manufacture observations or infer that an area has a downloadable
Level-3 product. Runtime retrieval is intentionally a separate provider step.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class WaPORProduct:
    code: str
    gee_collection: str
    level: Literal[1, 2, 3]
    variable: Literal["aeti", "evaporation", "transpiration", "interception", "npp", "ret", "soil_moisture"]
    temporal_support: Literal["daily", "dekadal"]
    resolution_m: int
    coverage: str
    country_codes: tuple[str, ...]
    is_currently_produced: bool = True
    unit: str | None = None
    scale_factor: float | None = None
    metadata_reference: str = "https://docs.digitalearthafrica.org/en/latest/data_specs/WaPOR_specs.html"
    license: str = "CC BY-SA 4.0"


# FAO's published v3 catalogue lists these Level 1 and Level 2 collections.
# Level 1 is global (300 m); Level 2 covers Africa and the Near East (100 m).
WAPOR_V3_PRODUCTS: tuple[WaPORProduct, ...] = (
    WaPORProduct("L1-AETI-D", "projects/UNFAO/wapor/v3/L1-AETI-D", 1, "aeti", "dekadal", 300, "global", (), unit="mm/day", scale_factor=0.1),
    WaPORProduct("L1-E-D", "projects/UNFAO/wapor/v3/L1-E-D", 1, "evaporation", "dekadal", 300, "global", (), unit="mm/day", scale_factor=0.1),
    WaPORProduct("L1-I-D", "projects/UNFAO/wapor/v3/L1-I-D", 1, "interception", "dekadal", 300, "global", (), unit="mm/year", scale_factor=0.1),
    WaPORProduct("L1-T-D", "projects/UNFAO/wapor/v3/L1-T-D", 1, "transpiration", "dekadal", 300, "global", (), unit="mm/day", scale_factor=0.1),
    WaPORProduct("L1-NPP-D", "projects/UNFAO/wapor/v3/L1-NPP-D", 1, "npp", "dekadal", 300, "global", (), unit="gC/m2/day", scale_factor=0.001),
    WaPORProduct("L1-RET-D", "projects/UNFAO/wapor/v3/L1-RET-D", 1, "ret", "dekadal", 30000, "global", (), unit="mm/day", scale_factor=0.1),
    WaPORProduct("L1-RSM-D", "projects/UNFAO/wapor/v3/L1-RSM-D", 1, "soil_moisture", "dekadal", 300, "global", (), unit="%", scale_factor=0.001),
    WaPORProduct("L2-AETI-D", "projects/UNFAO/wapor/v3/L2-AETI-D", 2, "aeti", "dekadal", 100, "Africa and Near East", ("EGY",), unit="mm/day", scale_factor=0.1),
    WaPORProduct("L2-E-D", "projects/UNFAO/wapor/v3/L2-E-D", 2, "evaporation", "dekadal", 100, "Africa and Near East", ("EGY",), unit="mm/day", scale_factor=0.1),
    WaPORProduct("L2-I-D", "projects/UNFAO/wapor/v3/L2-I-D", 2, "interception", "dekadal", 100, "Africa and Near East", ("EGY",), unit="mm/day", scale_factor=0.1),
    WaPORProduct("L2-T-D", "projects/UNFAO/wapor/v3/L2-T-D", 2, "transpiration", "dekadal", 100, "Africa and Near East", ("EGY",), unit="mm/day", scale_factor=0.1),
    WaPORProduct("L2-NPP-D", "projects/UNFAO/wapor/v3/L2-NPP-D", 2, "npp", "dekadal", 100, "Africa and Near East", ("EGY",), unit="gC/m2/day", scale_factor=0.001),
    WaPORProduct("L2-RSM-D", "projects/UNFAO/wapor/v3/L2-RSM-D", 2, "soil_moisture", "dekadal", 100, "Africa and Near East", ("EGY",), unit="%", scale_factor=0.001),
)


def products_for_country(country_code: str, *, level: int | None = None) -> tuple[WaPORProduct, ...]:
    code = country_code.strip().upper()
    if len(code) != 3:
        raise ValueError("country_code must be an ISO alpha-3 code")
    return tuple(
        product for product in WAPOR_V3_PRODUCTS
        if (level is None or product.level == level)
        and (not product.country_codes or code in product.country_codes)
    )


def get_product(code: str) -> WaPORProduct:
    for product in WAPOR_V3_PRODUCTS:
        if product.code == code.strip().upper():
            return product
    raise KeyError("unsupported WaPOR v3 product code")
