"""Count unplanned outages within 2-mile radius of each Charge My Street chargepoint.

Usage:
    python tools/count_outages_near_chargepoints.py
    python tools/count_outages_near_chargepoints.py --top 10
    python tools/count_outages_near_chargepoints.py --category V2X
    python tools/count_outages_near_chargepoints.py --radius 5
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import numpy as np
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHARGING_SITES_FILE = PROJECT_ROOT / "data" / "all_charging_sites.csv"
OUTAGES_FILE = PROJECT_ROOT / "data" / "df_cleaned.csv"

# 2 miles in km
TWO_MILES_KM = 3.218688

CATEGORY_MAP = {
    "v2x": "V2X Chargepoint",
    "building-supplied": "Building-supplied Charger",
    "other": "Other Chargepoint",
}


def haversine_km(lat1, lon1, lat2_arr, lon2_arr):
    """Calculate haversine distance in km."""
    R = 6371.0
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2_arr), np.radians(lon2_arr)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def main():
    parser = argparse.ArgumentParser(
        description="Count outages near Charge My Street chargepoints."
    )
    parser.add_argument("--radius", type=float, default=TWO_MILES_KM,
                        help="Radius in km (default: 3.218688 = 2 miles)")
    parser.add_argument("--category", type=str, default=None,
                        help="Filter sites by category: V2X, Building-supplied, Other")
    parser.add_argument("--top", type=int, default=0,
                        help="Show top N sites by outage count (0 = summary only)")
    args = parser.parse_args()

    try:
        # Load data
        if not CHARGING_SITES_FILE.exists():
            raise FileNotFoundError(f"Charging sites not found: {CHARGING_SITES_FILE}")
        if not OUTAGES_FILE.exists():
            raise FileNotFoundError(f"Outage data not found: {OUTAGES_FILE}")

        sites_df = pd.read_csv(CHARGING_SITES_FILE)
        outages_df = pd.read_csv(OUTAGES_FILE, low_memory=False)

        # Filter sites by category if specified
        if args.category:
            cat_lower = args.category.lower()
            if cat_lower in CATEGORY_MAP:
                sites_df = sites_df[sites_df["site_category"] == CATEGORY_MAP[cat_lower]]
            else:
                sites_df = sites_df[sites_df["site_category"].str.lower().str.contains(cat_lower, na=False)]

        if sites_df.empty:
            print(json.dumps({"error": "No charging sites found matching filter"}, indent=2))
            sys.exit(1)

        # Ensure outages have valid coordinates
        outages_df = outages_df.dropna(subset=["latitude", "longitude"])

        outage_lats = outages_df["latitude"].values
        outage_lons = outages_df["longitude"].values

        # Count outages within radius for each site
        site_results = []
        total_outages_near_sites = 0
        sites_with_outages = 0

        for _, site in sites_df.iterrows():
            site_lat = site["latitude"]
            site_lon = site["longitude"]
            site_name = str(site.get("charge_point_location", "Unknown"))

            dists = haversine_km(site_lat, site_lon, outage_lats, outage_lons)
            outage_count = int(np.sum(dists <= args.radius))

            if outage_count > 0:
                sites_with_outages += 1
                total_outages_near_sites += outage_count

            site_results.append({
                "site_name": site_name,
                "site_category": str(site.get("site_category", "")),
                "latitude": round(float(site_lat), 6),
                "longitude": round(float(site_lon), 6),
                "outages_within_radius": outage_count,
            })

        # Sort by outage count descending
        site_results.sort(key=lambda x: x["outages_within_radius"], reverse=True)

        # Summary
        output = {
            "summary": {
                "total_sites": len(sites_df),
                "sites_with_outages": sites_with_outages,
                "sites_without_outages": len(sites_df) - sites_with_outages,
                "total_outages_near_sites": total_outages_near_sites,
                "avg_outages_per_site": round(total_outages_near_sites / len(sites_df), 2) if len(sites_df) > 0 else 0,
                "radius_km": round(args.radius, 3),
                "radius_miles": round(args.radius / 1.609344, 2),
            },
            "results": site_results[:args.top] if args.top > 0 else site_results,
        }

        print(json.dumps(output, indent=2, default=str))

    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
