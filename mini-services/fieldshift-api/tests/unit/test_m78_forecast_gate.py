from types import SimpleNamespace

import pytest

from app.core.errors import Conflict
from app.scenario_execution.service import _require_executable


@pytest.mark.parametrize("scenario_type", ["climate_projection", "weather_forecast"])
def test_m78_forecast_and_projection_scenarios_remain_non_executable(scenario_type):
    scenario = SimpleNamespace(
        scenario_status="finalized",
        scenario_type=scenario_type,
    )
    with pytest.raises(Conflict, match="has no executable transformation"):
        _require_executable(scenario)
