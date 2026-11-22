from app.data_platform.registry.provider_registry import get_provider_registry


def test_wapor_provider_is_registered_as_optional_real_data_source():
    registry = get_provider_registry()
    provider = registry.get("fao_wapor_v3")
    assert provider.supported_variables() == [
        "actual_evapotranspiration_interception",
        "evaporation",
        "interception",
        "net_primary_productivity",
        "relative_soil_moisture",
        "transpiration",
    ]
    entry = next(item for item in registry.health(with_probes=False) if item["provider_code"] == "fao_wapor_v3")
    assert entry["kind"] == "api_raster"
    assert entry["status"] == ("optional" if entry["details"]["rasterio_available"] else "degraded")
    assert entry["details"]["is_synthetic"] is False
    assert entry["details"]["country_codes"] == ["EGY"]
    assert entry["details"]["native_resolution_m"] == 100
