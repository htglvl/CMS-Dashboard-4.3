"""Test: count_outages_near_chargepoints.py — verify outage counts near CMS chargepoints.

These tests call the tool directly (subprocess) and validate its output structure.
They do NOT require the OpenClaw gateway to be running.

Usage:
    pytest tests/test_count_outages_near_chargepoints.py -v
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

# Skip if data files don't exist
pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "all_charging_sites.csv").exists() or not (DATA_DIR / "df_cleaned.csv").exists(),
    reason="Data files not found"
)


def run_tool(args: list[str] = None, timeout: int = 120) -> dict:
    """Run count_outages_near_chargepoints.py and return parsed JSON output."""
    script = TOOLS_DIR / "count_outages_near_chargepoints.py"
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

    def test_summary_has_required_keys(self):
        """Summary should contain total_sites, sites_with_outages, etc."""
        out = run_tool()
        assert "summary" in out
        summary = out["summary"]
        assert "total_sites" in summary
        assert "sites_with_outages" in summary
        assert "sites_without_outages" in summary
        assert "total_outages_near_sites" in summary
        assert "avg_outages_per_site" in summary
        assert "radius_km" in summary
        assert "radius_miles" in summary

    def test_results_is_list(self):
        """Results should be a list of site objects."""
        out = run_tool()
        assert "results" in out
        assert isinstance(out["results"], list)
        assert len(out["results"]) > 0

    def test_result_entry_has_required_keys(self):
        """Each result entry should have site_name, outages_within_radius, etc."""
        out = run_tool()
        first = out["results"][0]
        assert "site_name" in first
        assert "site_category" in first
        assert "latitude" in first
        assert "longitude" in first
        assert "outages_within_radius" in first


# ── Summary value tests ─────────────────────────────────────────────────

class TestSummaryValues:
    """Verify summary values are sensible."""

    def test_total_sites_matches_csv(self):
        """Total sites should match the CSV row count."""
        out = run_tool()
        assert out["summary"]["total_sites"] == 236

    def test_sites_with_outages_plus_without_equals_total(self):
        """sites_with_outages + sites_without_outages should equal total_sites."""
        out = run_tool()
        s = out["summary"]
        assert s["sites_with_outages"] + s["sites_without_outages"] == s["total_sites"]

    def test_radius_defaults_to_2_miles(self):
        """Default radius should be 2 miles (3.219 km)."""
        out = run_tool()
        assert abs(out["summary"]["radius_km"] - 3.219) < 0.01
        assert abs(out["summary"]["radius_miles"] - 2.0) < 0.01

    def test_outage_counts_are_non_negative(self):
        """All outage counts should be >= 0."""
        out = run_tool()
        for site in out["results"]:
            assert site["outages_within_radius"] >= 0

    def test_total_outages_near_sites_is_sum(self):
        """Total outages should equal sum of per-site counts."""
        out = run_tool()
        total_from_sites = sum(s["outages_within_radius"] for s in out["results"])
        assert out["summary"]["total_outages_near_sites"] == total_from_sites


# ── Filter tests ────────────────────────────────────────────────────────

class TestFilters:
    """Verify category and radius filters work."""

    def test_category_v2x(self):
        """V2X filter should return only V2X sites."""
        out = run_tool(["--category", "V2X"])
        for site in out["results"]:
            assert site["site_category"] == "V2X Chargepoint"

    def test_category_building_supplied(self):
        """Building-supplied filter should return only that category."""
        out = run_tool(["--category", "Building-supplied"])
        for site in out["results"]:
            assert site["site_category"] == "Building-supplied Charger"

    def test_category_limits_total_sites(self):
        """Category filter should reduce total_sites."""
        out_all = run_tool()
        out_v2x = run_tool(["--category", "V2X"])
        assert out_v2x["summary"]["total_sites"] < out_all["summary"]["total_sites"]

    def test_custom_radius(self):
        """Custom radius should be reflected in summary."""
        out = run_tool(["--radius", "5"])
        assert abs(out["summary"]["radius_km"] - 5.0) < 0.01

    def test_larger_radius_finds_more_outages(self):
        """5km radius should find same or more outages than 2-mile radius."""
        out_2mi = run_tool(["--radius", "3.219"])
        out_5km = run_tool(["--radius", "5"])
        assert out_5km["summary"]["total_outages_near_sites"] >= out_2mi["summary"]["total_outages_near_sites"]


# ── Top N tests ─────────────────────────────────────────────────────────

class TestTopN:
    """Verify --top parameter limits results."""

    def test_top_limits_results(self):
        """--top 5 should return at most 5 results."""
        out = run_tool(["--top", "5"])
        assert len(out["results"]) <= 5

    def test_top_returns_sorted_descending(self):
        """Results should be sorted by outage count descending."""
        out = run_tool(["--top", "10"])
        counts = [s["outages_within_radius"] for s in out["results"]]
        assert counts == sorted(counts, reverse=True)

    def test_top_1_returns_highest(self):
        """--top 1 should return the site with most outages."""
        out = run_tool(["--top", "1"])
        assert len(out["results"]) == 1
        # Should be one of the Carlisle sites (91 outages)
        assert out["results"][0]["outages_within_radius"] >= 50
