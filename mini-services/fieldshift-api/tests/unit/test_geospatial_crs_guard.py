from __future__ import annotations

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.geospatial import preprocessing as pre


def test_raster_without_crs_is_rejected_instead_of_assuming_wgs84(tmp_path):
    path = tmp_path / "missing-crs.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=8,
        width=8,
        count=1,
        dtype="float32",
        transform=from_origin(0, 8, 1, 1),
    ) as dataset:
        dataset.write(np.ones((8, 8), dtype="float32"), 1)

    geometry = {
        "type": "Polygon",
        "coordinates": [[[1, 1], [7, 1], [7, 7], [1, 7], [1, 1]]],
    }
    with pytest.raises(ValueError, match="no CRS metadata"):
        pre.read_scene_window(
            assets={"red": str(path)},
            surfaces=("red",),
            geometry_geojson=geometry,
            gdal_env={},
            max_window_mb=1,
        )
