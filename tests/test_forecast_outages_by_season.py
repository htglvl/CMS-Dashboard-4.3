"""Test: forecast_outages_by_season.py — verify seasonal outage forecasts.

These tests call the tool directly (subprocess) and validate its output structure.
They do NOT require the OpenClaw gateway to be running.

Usage:
    pytest tests/test_forecast_outages_by_season.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
DATA_DIR = PROJECT_ROOT / "data"
PYTHON = sys.executable

# Skip if outage data doesn't exist
pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "df_cleaned.csv").exists(),
    reason="Outage data not found"
)


def run_tool(args: list[str] = None, timeout: int = 60) -> dict:
    """Run forecast_outages_by_season.py and return parsed JSON output."""
    script = TOOLS_DIR / "forecast_outages_by_season.py"
    cmd = [PYTHON, str(script)]
    if args:
        cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(PROJECT_ROOT))

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(
            f"Tool did not return valid JSON.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}\nexit: {result.returncode}"
        )
    return data


# ── Output structure tests ──────────────────────────────────────────────

class TestOutputStructure:
    """Verify the tool returns valid JSON with expected keys."""

    def test_has_summary_and_forecasts(self):
        """Output should have summary and forecasts keys."""
        out = run_tool()
        assert "summary" in out
        assert "forecasts" in out

    def test_summary_has_required_keys(self):
        """Summary should contain total_outages_in_dataset and reliable_years_used."""
        out = run_tool()
        summary = out["summary"]
        assert "total_outages_in_dataset" in summary
        assert "reliable_years_used" in summary
        assert "min_outages_per_year_threshold" in summary

    def test_all_four_seasons_present(self):
        """Default run should return forecasts for all 4 seasons."""
        out = run_tool()
        assert "Winter" in out["forecasts"]
        assert "Spring" in out["forecasts"]
        assert "Summer" in out["forecasts"]
        assert "Autumn" in out["forecasts"]

    def test_forecast_entry_has_required_keys(self):
        """Each season forecast should have mean, median, std, min, max, forecast fields."""
        out = run_tool()
        winter = out["forecasts"]["Winter"]
        assert "historical_mean" in winter
        assert "historical_median" in winter
        assert "historical_std" in winter
        assert "historical_min" in winter
        assert "historical_max" in winter
        assert "forecast_low" in winter
        assert "forecast_expected" in winter
        assert "forecast_high" in winter
        assert "years_of_data" in winter


# ── Forecast value tests ────────────────────────────────────────────────

class TestForecastValues:
    """Verify forecast values are sensible."""

    def test_winter_has_highest_mean(self):
        """Winter should have the highest historical mean (most outages)."""
        out = run_tool()
        means = {s: out["forecasts"][s]["historical_mean"] for s in out["forecasts"]}
        assert means["Winter"] == max(means.values())

    def test_forecast_range_is_valid(self):
        """forecast_low <= forecast_expected <= forecast_high for each season."""
        out = run_tool()
        for season, data in out["forecasts"].items():
            assert data["forecast_low"] <= data["forecast_expected"], f"{season}: low > expected"
            assert data["forecast_expected"] <= data["forecast_high"], f"{season}: expected > high"

    def test_forecast_low_is_non_negative(self):
        """forecast_low should be >= 0 for all seasons."""
        out = run_tool()
        for season, data in out["forecasts"].items():
            assert data["forecast_low"] >= 0, f"{season}: negative forecast_low"

    def test_years_of_data_is_positive(self):
        """Each season should have at least 1 year of data."""
        out = run_tool()
        for season, data in out["forecasts"].items():
            assert data["years_of_data"] >= 1

    def test_historical_min_le_mean_le_max(self):
        """min <= mean <= max for each season."""
        out = run_tool()
        for season, data in out["forecasts"].items():
            assert data["historical_min"] <= data["historical_mean"], f"{season}: min > mean"
            assert data["historical_mean"] <= data["historical_max"], f"{season}: mean > max"


# ── Filter tests ────────────────────────────────────────────────────────

class TestFilters:
    """Verify season, district, and cause filters work."""

    def test_single_season_filter(self):
        """--season Winter should return only Winter forecast."""
        out = run_tool(["--season", "Winter"])
        assert "Winter" in out["forecasts"]
        assert len(out["forecasts"]) == 1

    def test_single_season_has_correct_keys(self):
        """Single season filter should still have all required keys."""
        out = run_tool(["--season", "Summer"])
        summer = out["forecasts"]["Summer"]
        assert "historical_mean" in summer
        assert "forecast_expected" in summer

    def test_year_in_summary(self):
        """--year should appear in summary."""
        out = run_tool(["--year", "2027"])
        assert out["summary"]["target_year"] == 2027

    def test_district_filter_reduces_total(self):
        """District filter should reduce total_outages_in_dataset."""
        out_all = run_tool()
        out_district = run_tool(["--district", "Carlisle"])
        if "error" in out_district:
            pytest.skip("District filter returned no data")
        assert out_district["summary"]["total_outages_in_dataset"] < out_all["summary"]["total_outages_in_dataset"]


# ── Optional sections tests ─────────────────────────────────────────────

class TestOptionalSections:
    """Verify --include-duration and --include-causes flags work."""

    def test_include_duration(self):
        """--include-duration should add duration_stats to output."""
        out = run_tool(["--include-duration"])
        assert "duration_stats" in out
        assert "Winter" in out["duration_stats"]
        assert "median_duration_hours" in out["duration_stats"]["Winter"]

    def test_include_causes(self):
        """--include-causes should add top_causes to output."""
        out = run_tool(["--include-causes"])
        assert "top_causes" in out
        assert "Winter" in out["top_causes"]
        # Should be a dict of cause -> count
        winter_causes = out["top_causes"]["Winter"]
        assert isinstance(winter_causes, dict)
        assert len(winter_causes) > 0

    def test_duration_not_present_by_default(self):
        """duration_stats should not be in output without --include-duration."""
        out = run_tool()
        assert "duration_stats" not in out

    def test_causes_not_present_by_default(self):
        """top_causes should not be in output without --include-causes."""
        out = run_tool()
        assert "top_causes" not in out
