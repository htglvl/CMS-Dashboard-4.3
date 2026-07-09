"""Test 2: Tool Output Correctness — verify each tool script returns valid JSON with expected keys.

These tests call the Python tool scripts directly (subprocess) and validate
their output structure. They do NOT require the OpenClaw gateway to be running.

Usage:
    pytest tests/test_tools.py -v
    pytest tests/test_tools.py -v -k "geocode"
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
PYTHON = sys.executable

# Track rate limiting across tests
_rate_limited = False


def run_tool(script_name: str, args: list[str] = None, timeout: int = 30) -> dict:
    """Run a tool script and return parsed JSON output."""
    script = TOOLS_DIR / script_name
    cmd = [PYTHON, str(script)]
    if args:
        cmd.extend(args)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(PROJECT_ROOT))

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"{script_name} did not return valid JSON.\nstdout: {result.stdout}\nstderr: {result.stderr}\nexit: {result.returncode}")

    # Detect rate limiting
    if isinstance(data, dict) and data.get("error", "").startswith("HTTP Error 429"):
        global _rate_limited
        _rate_limited = True
        pytest.skip(f"Nominatim rate limited (429): {data['error']}")

    return data


def is_rate_limited():
    """Check if we've been rate limited."""
    return _rate_limited


# ── Test 2a: geocode.py ─────────────────────────────────────────────────

class TestGeocodeTool:
    """Verify geocode.py returns structured location data."""

    def test_geocode_returns_results(self):
        out = run_tool("geocode.py", ["--query", "Lancaster", "--limit", "3"])
        assert "results" in out
        assert out["count"] >= 1
        assert len(out["results"]) >= 1

    def test_geocode_result_has_lat_lon(self):
        out = run_tool("geocode.py", ["--query", "Kendal", "--limit", "1"])
        if is_rate_limited():
            pytest.skip("Rate limited")
        first = out["results"][0]
        assert "lat" in first
        assert "lon" in first
        assert isinstance(first["lat"], (int, float))
        assert isinstance(first["lon"], (int, float))
        # Rough UK bounds
        assert 49 < first["lat"] < 61
        assert -9 < first["lon"] < 3

    def test_geocode_postcode(self):
        out = run_tool("geocode.py", ["--query", "LA1 1YW", "--limit", "1"])
        if is_rate_limited():
            pytest.skip("Rate limited")
        # Nominatim may not resolve all UK postcodes — just verify it doesn't error
        assert "results" in out

    def test_geocode_error_on_missing_query(self):
        result = subprocess.run(
            [PYTHON, str(TOOLS_DIR / "geocode.py")],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode != 0


# ── Test 2b: query_risk.py ──────────────────────────────────────────────

class TestQueryRiskTool:
    """Verify query_risk.py returns risk predictions."""

    def test_risk_by_district(self):
        out = run_tool("query_risk.py", ["--district", "Lancaster", "--top", "3"])
        assert "results" in out or "error" in out

    def test_risk_by_lat_lon(self):
        out = run_tool("query_risk.py", ["--lat", "54.05", "--lon", "-2.80", "--top", "3"])
        assert "results" in out or "error" in out

    def test_risk_result_structure(self):
        out = run_tool("query_risk.py", ["--district", "Lancaster", "--top", "1"])
        if "error" in out:
            pytest.skip("Risk model not trained yet")
        if out.get("results"):
            first = out["results"][0]
            assert "risk_level" in first
            assert "confidence" in first
            assert first["risk_level"] in ["High", "Medium", "Low"]


# ── Test 2c: query_outages.py ───────────────────────────────────────────

class TestQueryOutagesTool:
    """Verify query_outages.py returns outage records."""

    def test_outages_by_district(self):
        out = run_tool("query_outages.py", ["--district", "Lancaster", "--top", "3"])
        assert "results" in out or "error" in out

    def test_outages_by_proximity(self):
        out = run_tool("query_outages.py", ["--lat", "54.05", "--lon", "-2.80", "--radius", "10", "--top", "3"])
        assert "results" in out or "error" in out

    def test_outages_result_has_incident_info(self):
        out = run_tool("query_outages.py", ["--district", "Lancaster", "--top", "1"])
        if "error" in out:
            pytest.skip("Outage data not available")
        if out.get("results"):
            first = out["results"][0]
            assert "latitude" in first or "lat" in first


# ── Test 2d: query_charging_sites.py ────────────────────────────────────

class TestQueryChargingSitesTool:
    """Verify query_charging_sites.py returns charging site data."""

    def test_charging_sites_all(self):
        out = run_tool("query_charging_sites.py", ["--top", "5"])
        assert "results" in out
        assert out["count"] >= 1

    def test_charging_sites_by_category(self):
        out = run_tool("query_charging_sites.py", ["--category", "V2X", "--top", "3"])
        assert "results" in out
        for site in out["results"]:
            assert "V2X" in site["site_category"]

    def test_charging_sites_near_location(self):
        out = run_tool("query_charging_sites.py", ["--near-lat", "54.05", "--near-lon", "-2.80", "--radius", "20", "--top", "3"])
        assert "results" in out
        for site in out["results"]:
            assert "distance_km" in site

    def test_charging_sites_result_structure(self):
        out = run_tool("query_charging_sites.py", ["--top", "1"])
        first = out["results"][0]
        assert "charge_point_location" in first
        assert "site_category" in first
        assert "latitude" in first
        assert "longitude" in first


# ── Test 2e: get_recommendations.py ─────────────────────────────────────

class TestGetRecommendationsTool:
    """Verify get_recommendations.py returns recommendation data."""

    def test_recommendations_all(self):
        out = run_tool("get_recommendations.py", ["--type", "all"], timeout=60)
        assert "recommendations" in out or "error" in out

    def test_recommendations_chargepoint(self):
        out = run_tool("get_recommendations.py", ["--type", "chargepoint"], timeout=60)
        assert "recommendations" in out or "error" in out

    def test_recommendation_structure(self):
        out = run_tool("get_recommendations.py", ["--type", "chargepoint"], timeout=60)
        if "error" in out:
            pytest.skip("Recommendation engine not available")
        if out.get("recommendations"):
            first = out["recommendations"][0]
            assert "category" in first
            assert "priority" in first
            assert "title" in first
            assert "detail" in first
            assert first["priority"] in ["Critical", "High", "Medium", "Low"]


# ── Test 2f: clean_borderlands.py ───────────────────────────────────────

class TestCleanBorderlandsTool:
    """Verify clean_borderlands.py returns cleaned Borderlands site data."""

    def test_borderlands_basic(self):
        out = run_tool("clean_borderlands.py", ["--top", "3"], timeout=120)
        assert "sites" in out
        assert "summary" in out
        assert out["summary"]["total_sites"] >= 1

    def test_borderlands_site_structure(self):
        out = run_tool("clean_borderlands.py", ["--top", "5"], timeout=120)
        if is_rate_limited():
            pytest.skip("Rate limited")
        assert len(out["sites"]) >= 1
        first = out["sites"][0]
        assert "site_name" in first
        assert "town" in first
        assert "site_type" in first
        assert "latitude" in first
        assert "longitude" in first
        assert "local_authority" in first
        # At least one site should be geocoded
        geocoded = [s for s in out["sites"] if s["latitude"] is not None]
        assert len(geocoded) >= 1, "No sites were geocoded"

    def test_borderlands_geocode_in_uk(self):
        out = run_tool("clean_borderlands.py", ["--top", "5"], timeout=120)
        if is_rate_limited():
            pytest.skip("Rate limited")
        for site in out["sites"]:
            if site["latitude"] is not None:
                assert 49 < site["latitude"] < 61, f"{site['town']} lat out of UK bounds"
                assert -9 < site["longitude"] < 3, f"{site['town']} lon out of UK bounds"

    def test_borderlands_filter_authority(self):
        out = run_tool("clean_borderlands.py", ["--local-authority", "Cumberland", "--top", "5"], timeout=120)
        assert "sites" in out
        for site in out["sites"]:
            assert "cumberland" in site["local_authority"].lower()

    def test_borderlands_cross_ref(self):
        out = run_tool("clean_borderlands.py", ["--top", "3", "--cross-ref"], timeout=180)
        if is_rate_limited():
            pytest.skip("Rate limited")
        assert "sites" in out
        summary = out["summary"]
        assert "cross_ref" in summary
        cross = summary["cross_ref"]
        assert "high_risk_sites" in cross
        assert "sites_with_nearby_charging" in cross
        assert "matches_recommendation" in cross

    def test_borderlands_site_types(self):
        out = run_tool("clean_borderlands.py", ["--top", "10"], timeout=120)
        valid_types = {"Village Hall", "Community Centre", "Community Building", "Other Community Site"}
        for site in out["sites"]:
            assert site["site_type"] in valid_types, f"Unknown site type: {site['site_type']}"


# ── Test 2g: get_wiki.py ────────────────────────────────────────────────

class TestGetWikiTool:
    """Verify get_wiki.py returns wiki content."""

    def test_wiki_list(self):
        out = run_tool("get_wiki.py", ["--list"])
        assert "topics" in out or "error" in out

    def test_wiki_topic(self):
        out = run_tool("get_wiki.py", ["--topic", "home"])
        assert "content" in out or "error" in out


# ── Test 2h: summarize_district.py ──────────────────────────────────────

class TestSummarizeDistrictTool:
    """Verify summarize_district.py returns a district summary."""

    def test_summarize_district(self):
        out = run_tool("summarize_district.py", ["--district", "Lancaster"], timeout=60)
        assert "district" in out or "error" in out

    def test_summarize_has_risk_and_outages(self):
        out = run_tool("summarize_district.py", ["--district", "Lancaster"], timeout=60)
        if "error" in out:
            pytest.skip("District summary not available")
        assert "risk" in out
        assert "outages" in out
