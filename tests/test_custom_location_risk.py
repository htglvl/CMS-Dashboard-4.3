import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from advanced_charts import DynamicChartGenerator
from advanced_charts import data


@pytest.fixture
def generator(monkeypatch):
    monkeypatch.setattr(data, "load_cache", lambda: None)
    outages = pd.DataFrame({
        "latitude": [54.0, 54.001, 55.0],
        "longitude": [-2.0, -2.001, -3.0],
        "duration-hours": [1.0, 3.0, 2.0],
        "Total Customer Minutes Lost": [60.0, 180.0, 120.0],
    })
    sites = pd.DataFrame({
        "charge_point_location": ["Site A", "Site B"],
        "latitude": [54.0, 55.0], "longitude": [-2.0, -3.0],
    })
    return DynamicChartGenerator(outages, sites)


def test_custom_point_matches_existing_site_at_same_coordinates(generator):
    nearby = data.outages_within_radius(generator._data.outages, 54.0, -2.0)
    assert len(nearby) == 2
    custom = generator.get_risk_scores("📍 Location (54,-2)", site_outages=nearby)
    assert custom == generator.get_risk_scores("Site A")
    assert all(0 <= value <= 100 for value in custom.values())


def test_radar_updates_for_changed_filters_with_same_location_label(generator):
    outages = generator._data.outages
    first = generator.create_risk_assessment_chart("📍 Location", site_outages=outages.iloc[:2])
    second = generator.create_risk_assessment_chart("📍 Location", site_outages=outages.iloc[:1])
    assert list(first.data[0].r) != list(second.data[0].r)
    empty = generator.create_risk_assessment_chart("📍 Location", site_outages=outages.iloc[:0])
    assert not empty.data
    assert generator.get_risk_scores("📍 Location", site_outages=outages.iloc[:0]) == {}


def test_outside_reference_range_stays_on_radar_scale():
    assert data._scale(-1, 0, 10) == 0
    assert data._scale(11, 0, 10) == 100
    assert data._scale(5, 0, 10) == 50


@pytest.mark.parametrize("empty", [False, True])
def test_custom_location_risk_tab_renders(empty):
    app = AppTest.from_string('''
import pandas as pd
from unittest.mock import patch
from advanced_charts import DynamicChartGenerator
from dashboard.charts.risk_assessment import render_risk_assessment
outages = pd.DataFrame({"latitude": [54.,54.001], "longitude": [-2.,-2.001],
    "duration-hours": [1.,3.], "Total Customer Minutes Lost": [60.,180.]})
sites = pd.DataFrame({"charge_point_location": ["A"], "latitude": [54.], "longitude": [-2.]})
with patch("advanced_charts.data.load_cache", return_value=None):
    generator = DynamicChartGenerator(outages, sites)
render_risk_assessment(generator, "📍 Location (54,-2)", site_outages=outages''' +
        (".iloc[:0]" if empty else "") + ")")
    app.run(timeout=20)
    assert not app.exception
    assert not app.warning
    if empty:
        assert "No recorded outages" in app.info[0].value
        assert not app.get("plotly_chart")
    else:
        assert len(app.get("plotly_chart")) == 1
        assert any("Overall Vulnerability Score" in item.value for item in app.markdown)
        assert "2 miles" in app.caption[0].value
