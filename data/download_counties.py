"""Download UK ceremonial county boundaries from OS BoundaryLine.

Usage:
    python data/download_counties.py
    python data/download_counties.py --output data/uk_ceremonial_counties.geojson
"""

import argparse
import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

# OS BoundaryLine FeatureServer endpoint for UK ceremonial counties (England, Scotland, Wales)
# Source: Ordnance Survey BoundaryLine via ArcGIS
# If this URL stops working, find the updated URL at:
# https://geoportal.statistics.gov.uk/search?q=ceremonial%20counties
OS_BOUNDARYLINE_URL = (
    "https://services.arcgis.com/qHLhLQrcvEnxjtPr/arcgis/rest/services/"
    "OS_Boundaryline/FeatureServer/12/query"
)

USER_AGENT = "CMS-Dashboard/1.0"


def fetch_all_features(base_url: str) -> list[dict]:
    """Fetch all features from an ArcGIS FeatureServer, handling pagination."""
    all_features = []
    offset = 0
    page_size = 20  # Small page size: each feature has complex geometries (~500KB each)

    while True:
        params = urllib.parse.urlencode({
            "where": "1=1",
            "outFields": "*",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        })
        url = f"{base_url}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())

        features = data.get("features", [])
        all_features.extend(features)

        if len(features) < page_size:
            break
        offset += page_size

    return all_features


def main():
    parser = argparse.ArgumentParser(description="Download UK ceremonial county boundaries.")
    parser.add_argument(
        "--output", type=str,
        default=str(Path(__file__).resolve().parent / "uk_ceremonial_counties.geojson"),
        help="Output GeoJSON file path",
    )
    parser.add_argument(
        "--url", type=str, default=OS_BOUNDARYLINE_URL,
        help="ArcGIS FeatureServer query URL",
    )
    args = parser.parse_args()

    try:
        print("Fetching ceremonial county boundaries from OS BoundaryLine...", file=sys.stderr)
        features = fetch_all_features(args.url)

        if not features:
            print(json.dumps({"error": "No features returned from OS BoundaryLine API", "features": 0}), file=sys.stderr)
            sys.exit(1)

        # Build GeoJSON FeatureCollection
        geojson = {
            "type": "FeatureCollection",
            "features": features,
        }

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f)

        # Extract county names for verification
        county_names = []
        for feat in features:
            props = feat.get("properties", {})
            name = (props.get("NAME") or props.get("CTY23NM") or
                    props.get("CTY22NM") or props.get("County") or "").strip()
            if name:
                county_names.append(name)

        result = {
            "status": "success",
            "output_path": str(output_path),
            "feature_count": len(features),
            "counties": sorted(county_names),
        }
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}))
        sys.exit(1)


if __name__ == "__main__":
    main()
