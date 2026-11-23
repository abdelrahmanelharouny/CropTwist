"""Regression tests for authenticated NASA HLS COG access."""

from app.data_platform.providers.nasa_hls.provider import _gdal_env_options


def test_bearer_auth_uses_range_get_instead_of_head():
    options = _gdal_env_options({"bearer_token": "test-token"})

    assert options["GDAL_HTTP_HEADERS"] == "Authorization: Bearer test-token"
    assert options["CPL_VSIL_CURL_USE_HEAD"] == "NO"
    assert options["GDAL_HTTP_MAX_RETRY"] == "3"
    assert options["GDAL_HTTP_RETRY_DELAY"] == "1"


def test_basic_auth_uses_range_get_instead_of_head():
    options = _gdal_env_options(
        {"basic_user": "test-user", "basic_password": "test-password"}
    )

    assert options["GDAL_HTTP_AUTH"] == "BASIC"
    assert options["GDAL_USERPWD"] == "test-user:test-password"
    assert options["CPL_VSIL_CURL_USE_HEAD"] == "NO"
    assert options["GDAL_HTTP_MAX_RETRY"] == "3"
    assert options["GDAL_HTTP_RETRY_DELAY"] == "1"
