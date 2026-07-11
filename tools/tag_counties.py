"""Check which UK ceremonial county a lat/lon coordinate falls in.

Usage:
    # Single-point lookup
    python tools/tag_counties.py --lat 54.89 --lon -2.93
    python tools/tag_counties.py --lat 54.97 --lon -1.61

    # Bulk lookup: tag all rows in a CSV that have latitude/longitude columns
    python tools/tag_counties.py --bulk data/df_cleaned.csv
    python tools/tag_counties.py --bulk data/all_charging_sites.csv --output data/sites_tagged.csv
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import geopandas as gpd
import pandas as pd
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


def bulk_tag(csv_path: Path, geojson_path: Path, output_path: Path) -> dict:
    """Tag all rows in a CSV with their ceremonial county using spatial join."""
    counties_gdf, name_col = load_counties(geojson_path)

    df = pd.read_csv(csv_path, low_memory=False)
    if "latitude" not in df.columns or "longitude" not in df.columns:
        raise ValueError("CSV must have 'latitude' and 'longitude' columns")

    # Drop rows with missing coordinates for the join
    valid_mask = df["latitude"].notna() & df["longitude"].notna()
    df_valid = df[valid_mask].copy()

    # Build GeoDataFrame from points
    geometry = [Point(lon, lat) for lon, lat in zip(df_valid["longitude"], df_valid["latitude"])]
    points_gdf = gpd.GeoDataFrame(df_valid, geometry=geometry, crs="EPSG:4326")

    # Spatial join
    joined = gpd.sjoin(points_gdf, counties_gdf[[name_col, "geometry"]], predicate="within", how="left")

    # Map results back to original DataFrame
    df["ceremonial_county"] = None
    df.loc[joined.index, "ceremonial_county"] = joined[name_col].values

    # Save
    df.to_csv(output_path, index=False)

    tagged_count = int(df["ceremonial_county"].notna().sum())
    untagged_count = int(valid_mask.sum()) - tagged_count
    counties_found = sorted(df["ceremonial_county"].dropna().unique().tolist())

    return {
        "processed": len(df),
        "valid_coordinates": int(valid_mask.sum()),
        "tagged": tagged_count,
        "untagged": untagged_count,
        "output_path": str(output_path),
        "counties_found": counties_found,
    }


def main():
    parser = argparse.ArgumentParser(description="Check UK ceremonial county for a lat/lon coordinate.")
    parser.add_argument("--lat", type=float, default=None, help="Latitude for single-point lookup")
    parser.add_argument("--lon", type=float, default=None, help="Longitude for single-point lookup")
    parser.add_argument("--bulk", type=str, default=None, help="CSV path for bulk tagging (must have latitude/longitude columns)")
    parser.add_argument("--output", type=str, default=None, help="Output CSV path for bulk mode (default: overwrite input)")
    parser.add_argument("--geojson", type=str, default=str(DEFAULT_GEOJSON), help="Path to county GeoJSON")
    args = parser.parse_args()

    try:
        geojson_path = Path(args.geojson)

        # Bulk mode
        if args.bulk:
            csv_path = Path(args.bulk)
            output_path = Path(args.output) if args.output else csv_path
            result = bulk_tag(csv_path, geojson_path, output_path)
            print(json.dumps(result, indent=2))
            return

        # Single-point mode
        if args.lat is not None and args.lon is not None:
            result = lookup_county(args.lat, args.lon, geojson_path)
            print(json.dumps(result, indent=2))
            return

        # No valid arguments
        print(json.dumps({
            "error": "Provide --lat and --lon for single lookup, or --bulk <csv_path> for bulk tagging"
        }, indent=2))
        sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}))
        sys.exit(1)


if __name__ == "__main__":
    main()
