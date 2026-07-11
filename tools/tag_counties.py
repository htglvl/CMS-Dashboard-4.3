"""Check which UK ceremonial county a lat/lon coordinate falls in.

Usage:
    python tools/tag_counties.py --lat 54.89 --lon -2.93
    python tools/tag_counties.py --lat 54.97 --lon -1.61
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import geopandas as gpd
from pathlib import Path
from shapely.geometry import Point

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GEOJSON = PROJECT_ROOT / "data" / "uk_ceremonial_counties.geojson"

# Try common field names for the county name in ONS GeoJSON
COUNTY_NAME_FIELDS = ["CTY23NM", "CTY22NM", "CTY21NM", "CTY20NM", "name", "NAME"]


def find_county_name_field(gdf: gpd.GeoDataFrame) -> str:
    """Find the column containing ceremonial county names."""
    for field in COUNTY_NAME_FIELDS:
        if field in gdf.columns:
            return field
    raise ValueError(
        f"Could not find county name field in GeoJSON columns: {list(gdf.columns)}"
    )


def load_counties(geojson_path: Path) -> tuple[gpd.GeoDataFrame, str]:
    """Load county boundaries and return (GeoDataFrame, name_column)."""
    if not geojson_path.exists():
        raise FileNotFoundError(
            f"County boundaries not found: {geojson_path}. "
            f"Run: python data/download_counties.py"
        )
    gdf = gpd.read_file(geojson_path)
    name_col = find_county_name_field(gdf)
    # Ensure WGS84
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf, name_col


def lookup_county(lat: float, lon: float, geojson_path: Path) -> dict:
    """Find which ceremonial county a point falls in."""
    counties_gdf, name_col = load_counties(geojson_path)
    point = Point(lon, lat)

    matches = counties_gdf[counties_gdf.contains(point)]

    if len(matches) > 0:
        return {
            "lat": lat,
            "lon": lon,
            "ceremonial_county": matches.iloc[0][name_col],
            "found": True,
        }
    else:
        return {
            "lat": lat,
            "lon": lon,
            "ceremonial_county": None,
            "found": False,
        }


def main():
    parser = argparse.ArgumentParser(description="Check UK ceremonial county for a lat/lon coordinate.")
    parser.add_argument("--lat", type=float, required=True, help="Latitude")
    parser.add_argument("--lon", type=float, required=True, help="Longitude")
    parser.add_argument("--geojson", type=str, default=str(DEFAULT_GEOJSON), help="Path to county GeoJSON")
    args = parser.parse_args()

    try:
        result = lookup_county(args.lat, args.lon, Path(args.geojson))
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}))
        sys.exit(1)


if __name__ == "__main__":
    main()
