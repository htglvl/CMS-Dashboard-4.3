"""Test 4: Pipeline Integrity — verify data flows correctly through the full stack.

These tests check that data files exist, have expected schemas, and that
tool outputs can be consumed by downstream components (e.g. recommendation
engine reads the same columns the risk model produces).

Usage:
    pytest tests/test_pipeline.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"
TOOLS_DIR = PROJECT_ROOT / "tools"
PYTHON = sys.executable


# ── Data File Existence ─────────────────────────────────────────────────

class TestDataFilesExist:
    """Verify required data files are present."""

    def test_outage_data_exists(self):
        f = DATA_DIR / "df_cleaned.csv"
        assert f.exists(), f"Missing: {f}"

    def test_charging_sites_exists(self):
        f = DATA_DIR / "all_charging_sites.csv"
        assert f.exists(), f"Missing: {f}"

    def test_borderlands_excel_exists(self):
        f = DATA_DIR / "Borderlands Long List Sites Apr 26.xlsx"
        assert f.exists(), f"Missing: {f}"


# ── Data Schema Validation ──────────────────────────────────────────────

class TestDataSchemas:
    """Verify data files have expected columns."""

    def test_outage_data_columns(self):
        df = pd.read_csv(DATA_DIR / "df_cleaned.csv", nrows=5, low_memory=False)
        expected = {"latitude", "longitude", "incident_date_time"}
        assert expected.issubset(set(df.columns)), f"Missing columns: {expected - set(df.columns)}"

    def test_charging_sites_columns(self):
        df = pd.read_csv(DATA_DIR / "all_charging_sites.csv", nrows=5)
        expected = {"charge_point_location", "site_category", "latitude", "longitude"}
        assert expected.issubset(set(df.columns)), f"Missing columns: {expected - set(df.columns)}"

    def test_charging_sites_have_coordinates(self):
        df = pd.read_csv(DATA_DIR / "all_charging_sites.csv")
        assert df["latitude"].notna().sum() > 0, "No lat values in charging sites"
        assert df["longitude"].notna().sum() > 0, "No lon values in charging sites"
        # UK bounds check
        valid = df.dropna(subset=["latitude", "longitude"])
        assert (valid["latitude"] > 49).all(), "Some lat values outside UK"
        assert (valid["latitude"] < 61).all(), "Some lat values outside UK"

    def test_borderlands_excel_columns(self):
        df = pd.read_excel(DATA_DIR / "Borderlands Long List Sites Apr 26.xlsx", engine="openpyxl", header=1, nrows=5)
        df.columns = df.columns.str.strip()
        expected = {"Town/ Village", "Potential Sites", "Brief Description", "Local Authority Area"}
        assert expected.issubset(set(df.columns)), f"Missing columns: {expected - set(df.columns)}"

    def test_borderlands_has_data(self):
        df = pd.read_excel(DATA_DIR / "Borderlands Long List Sites Apr 26.xlsx", engine="openpyxl", header=1)
        assert len(df) > 50, f"Expected 100+ rows, got {len(df)}"


# ── Model Predictions Schema ────────────────────────────────────────────

class TestModelPredictions:
    """Verify model prediction files have expected schema (if they exist)."""

    @pytest.fixture
    def predictions(self):
        for name in ["predictions_randomforest.csv", "predictions_xgboost.csv"]:
            f = MODELS_DIR / name
            if f.exists():
                return pd.read_csv(f)
        pytest.skip("No prediction files found")

    def test_predictions_have_lat_lon(self, predictions):
        assert "lat" in predictions.columns
        assert "lon" in predictions.columns

    def test_predictions_have_risk_level(self, predictions):
        assert "risk_level" in predictions.columns or "prob_high" in predictions.columns

    def test_predictions_in_uk_bounds(self, predictions):
        assert (predictions["lat"] > 49).all()
        assert (predictions["lat"] < 61).all()

    def test_predictions_have_confidence(self, predictions):
        assert "confidence" in predictions.columns


# ── Tool Chain Consistency ───────────────────────────────────────────────

class TestToolChainConsistency:
    """Verify tools can be chained: output of one feeds into another."""

    def test_geocode_to_risk(self):
        """Geocode output lat/lon should work as query_risk input."""
        geo = subprocess.run(
            [PYTHON, str(TOOLS_DIR / "geocode.py"), "--query", "Lancaster", "--limit", "1"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT)
        )
        geo_data = json.loads(geo.stdout)
        if not geo_data.get("results"):
            pytest.skip("Geocode returned no results")

        lat = geo_data["results"][0]["lat"]
        lon = geo_data["results"][0]["lon"]

        risk = subprocess.run(
            [PYTHON, str(TOOLS_DIR / "query_risk.py"), "--lat", str(lat), "--lon", str(lon), "--top", "1"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT)
        )
        risk_data = json.loads(risk.stdout)
        # Should not error — even if no results, structure should be valid
        assert "results" in risk_data or "error" in risk_data

    def test_geocode_to_charging_sites(self):
        """Geocode output lat/lon should work as query_charging_sites input."""
        geo = subprocess.run(
            [PYTHON, str(TOOLS_DIR / "geocode.py"), "--query", "Kendal", "--limit", "1"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT)
        )
        geo_data = json.loads(geo.stdout)
        if not geo_data.get("results"):
            pytest.skip("Geocode returned no results")

        lat = geo_data["results"][0]["lat"]
        lon = geo_data["results"][0]["lon"]

        sites = subprocess.run(
            [PYTHON, str(TOOLS_DIR / "query_charging_sites.py"), "--near-lat", str(lat), "--near-lon", str(lon), "--radius", "20"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT)
        )
        sites_data = json.loads(sites.stdout)
        assert "results" in sites_data

    def test_geocode_to_outages(self):
        """Geocode output lat/lon should work as query_outages input."""
        geo = subprocess.run(
            [PYTHON, str(TOOLS_DIR / "geocode.py"), "--query", "Carlisle", "--limit", "1"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT)
        )
        geo_data = json.loads(geo.stdout)
        if not geo_data.get("results"):
            pytest.skip("Geocode returned no results")

        lat = geo_data["results"][0]["lat"]
        lon = geo_data["results"][0]["lon"]

        outages = subprocess.run(
            [PYTHON, str(TOOLS_DIR / "query_outages.py"), "--lat", str(lat), "--lon", str(lon), "--radius", "15", "--top", "3"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT)
        )
        outages_data = json.loads(outages.stdout)
        assert "results" in outages_data or "error" in outages_data

    def test_borderlands_cross_ref_chain(self):
        """clean_borderlands --cross-ref should return risk + charging data."""
        out = subprocess.run(
            [PYTHON, str(TOOLS_DIR / "clean_borderlands.py"), "--top", "2", "--cross-ref"],
            capture_output=True, text=True, timeout=180, cwd=str(PROJECT_ROOT)
        )
        data = json.loads(out.stdout)
        assert "sites" in data
        assert "summary" in data
        # Cross-ref summary should be present
        if data["summary"].get("geocoded", 0) > 0:
            assert "cross_ref" in data["summary"]


# ── Recommendation Engine Integration ───────────────────────────────────

class TestRecommendationEngineIntegration:
    """Verify recommendation engine can read the data it needs."""

    def test_engine_importable(self):
        """RecommendationEngine should be importable."""
        sys.path.insert(0, str(PROJECT_ROOT))
        try:
            from advanced_charts.recommendation_engine import RecommendationEngine
        except (ImportError, ModuleNotFoundError):
            pytest.skip("streamlit not available in test environment")
        assert RecommendationEngine is not None

    def test_engine_can_load_data(self):
        """Engine should be able to load predictions and outages."""
        sys.path.insert(0, str(PROJECT_ROOT))
        try:
            from advanced_charts.recommendation_engine import RecommendationEngine
        except (ImportError, ModuleNotFoundError):
            pytest.skip("streamlit not available in test environment")

        predictions = None
        for name in ["predictions_randomforest.csv", "predictions_xgboost.csv"]:
            f = MODELS_DIR / name
            if f.exists():
                predictions = pd.read_csv(f)
                break

        if predictions is None:
            pytest.skip("No prediction files")

        outages = pd.read_csv(DATA_DIR / "df_cleaned.csv", low_memory=False, parse_dates=["incident_date_time"])
        charging = pd.read_csv(DATA_DIR / "all_charging_sites.csv") if (DATA_DIR / "all_charging_sites.csv").exists() else None

        engine = RecommendationEngine(predictions, outages, charging)
        assert engine is not None
