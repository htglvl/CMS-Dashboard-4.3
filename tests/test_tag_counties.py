"""Test: tag_counties.py — verify single-point and bulk county lookups.

These tests call the tag_counties tool directly (subprocess) and validate
its output structure. They do NOT require the OpenClaw gateway to be running.

Usage:
    pytest tests/test_tag_counties.py -v
    pytest tests/test_tag_counties.py -v -k "single"
    pytest tests/test_tag_counties.py -v -k "bulk"
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
DATA_DIR = PROJECT_ROOT / "data"
PYTHON = sys.executable

# Skip all tests if county boundary GeoJSON doesn't exist
GEOJSON_PATH = DATA_DIR / "uk_ceremonial_counties.geojson"
pytestmark = pytest.mark.skipif(
    not GEOJSON_PATH.exists(),
    reason="County boundary GeoJSON not found. Run: python data/download_counties.py"
)


def run_tool(args: list[str], timeout: int = 120) -> dict:
    """Run tag_counties.py and return parsed JSON output."""
    script = TOOLS_DIR / "tag_counties.py"
    cmd = [PYTHON, str(script)] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(PROJECT_ROOT))

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(
            f"tag_counties.py did not return valid JSON.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}\nexit: {result.returncode}"
        )
    return data


# ── Single-point lookup tests ───────────────────────────────────────────

class TestTagCountiesSingleLookup:
    """Verify single-point county lookup returns correct results."""

    def test_cumbria(self):
        """Carlisle (54.89, -2.93) should be in Cumbria."""
        out = run_tool(["--lat", "54.89", "--lon", "-2.93"])
        assert out["found"] is True
        assert out["ceremonial_county"] == "Cumbria"
        assert out["lat"] == 54.89
        assert out["lon"] == -2.93

    def test_tyne_and_wear(self):
        """Newcastle (54.97, -1.61) should be in Tyne & Wear."""
        out = run_tool(["--lat", "54.97", "--lon", "-1.61"])
        assert out["found"] is True
        assert out["ceremonial_county"] == "Tyne & Wear"

    def test_cumbria_kendal(self):
        """Kendal (54.33, -2.74) should be in Cumbria."""
        out = run_tool(["--lat", "54.33", "--lon", "-2.74"])
        assert out["found"] is True
        assert out["ceremonial_county"] == "Cumbria"

    def test_lancashire(self):
        """Lancaster (54.05, -2.80) should be in Lancashire."""
        out = run_tool(["--lat", "54.05", "--lon", "-2.80"])
        assert out["found"] is True
        assert out["ceremonial_county"] == "Lancashire"

    def test_outside_gb_returns_not_found(self):
        """Paris (48.86, 2.35) should not be in any GB county."""
        out = run_tool(["--lat", "48.86", "--lon", "2.35"])
        assert out["found"] is False
        assert out["ceremonial_county"] is None

    def test_output_has_required_keys(self):
        """Output must contain lat, lon, ceremonial_county, found."""
        out = run_tool(["--lat", "54.05", "--lon", "-2.80"])
        assert "lat" in out
        assert "lon" in out
        assert "ceremonial_county" in out
        assert "found" in out

    def test_no_args_returns_error(self):
        """Running without --lat/--lon or --bulk should return an error."""
        script = TOOLS_DIR / "tag_counties.py"
        result = subprocess.run(
            [PYTHON, str(script)],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT)
        )
        out = json.loads(result.stdout)
        assert "error" in out


# ── Bulk tagging tests ──────────────────────────────────────────────────

class TestTagCountiesBulk:
    """Verify bulk CSV tagging with ceremonial counties."""

    def _make_temp_csv(self, rows: list[dict]) -> Path:
        """Create a temporary CSV file with latitude/longitude columns."""
        df = pd.DataFrame(rows)
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w")
        df.to_csv(tmp.name, index=False)
        return Path(tmp.name)

    def test_bulk_tags_all_rows(self):
        """All rows with valid coordinates should get a county."""
        csv_path = self._make_temp_csv([
            {"name": "A", "latitude": 54.89, "longitude": -2.93},
            {"name": "B", "latitude": 54.97, "longitude": -1.61},
            {"name": "C", "latitude": 54.05, "longitude": -2.80},
        ])
        out = run_tool(["--bulk", str(csv_path)])
        assert out["processed"] == 3
        assert out["tagged"] == 3
        assert out["untagged"] == 0
        assert len(out["counties_found"]) >= 2  # At least Cumbria + Lancashire/Tyne & Wear

    def test_bulk_output_csv_has_county_column(self):
        """The output CSV should have a 'ceremonial_county' column."""
        csv_path = self._make_temp_csv([
            {"name": "A", "latitude": 54.89, "longitude": -2.93},
        ])
        out_path = csv_path.with_suffix(".tagged.csv")
        out = run_tool(["--bulk", str(csv_path), "--output", str(out_path)])

        result_df = pd.read_csv(out_path)
        assert "ceremonial_county" in result_df.columns
        assert result_df["ceremonial_county"].iloc[0] == "Cumbria"

    def test_bulk_handles_missing_coordinates(self):
        """Rows with missing lat/lon should be skipped (not crash)."""
        csv_path = self._make_temp_csv([
            {"name": "A", "latitude": 54.89, "longitude": -2.93},
            {"name": "B", "latitude": None, "longitude": None},
            {"name": "C", "latitude": 54.05, "longitude": -2.80},
        ])
        out = run_tool(["--bulk", str(csv_path)])
        assert out["processed"] == 3
        assert out["valid_coordinates"] == 2
        assert out["tagged"] == 2

    def test_bulk_no_lat_lon_columns_returns_error(self):
        """CSV without latitude/longitude columns should return an error."""
        csv_path = self._make_temp_csv([
            {"name": "A", "x": 54.89, "y": -2.93},
        ])
        out = run_tool(["--bulk", str(csv_path)])
        assert "error" in out

    def test_bulk_output_has_required_keys(self):
        """Bulk output must contain processed, tagged, untagged, output_path, counties_found."""
        csv_path = self._make_temp_csv([
            {"name": "A", "latitude": 54.89, "longitude": -2.93},
        ])
        out = run_tool(["--bulk", str(csv_path)])
        assert "processed" in out
        assert "tagged" in out
        assert "untagged" in out
        assert "output_path" in out
        assert "counties_found" in out
