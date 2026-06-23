"""Query charging site data.

Usage:
    python tools/query_charging_sites.py --category V2X
    python tools/query_charging_sites.py --near-lat 54.05 --near-lon -2.80 --radius 10
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

CATEGORY_MAP = {
    "v2x": "V2X Chargepoint",
    "building-supplied": "Building-supplied Charger",
    "other": "Other Chargepoint",
}


def haversine_km(lat1, lon1, lat2_arr, lon2_arr):
    R = 6371.0
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2_arr), np.radians(lon2_arr)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def main():
    parser = argparse.ArgumentParser(description="Query charging site data.")
    parser.add_argument("--category", type=str, help="Filter: V2X, Building-supplied, Other")
    parser.add_argument("--near-lat", type=float, help="Latitude for proximity search")
    parser.add_argument("--near-lon", type=float, help="Longitude for proximity search")
    parser.add_argument("--radius", type=float, default=5.0, help="Radius in km")
    parser.add_argument("--top", type=int, default=10, help="Number of results")
    args = parser.parse_args()

    if args.near_lat is not None and args.near_lon is None:
        parser.error("--near-lon required with --near-lat")
    if args.near_lon is not None and args.near_lat is None:
        parser.error("--near-lat required with --near-lon")

    try:
        if not CHARGING_SITES_FILE.exists():
            raise FileNotFoundError(f"Charging sites not found: {CHARGING_SITES_FILE}")

        df = pd.read_csv(CHARGING_SITES_FILE)

        if args.category:
            cat_lower = args.category.lower()
            if cat_lower in CATEGORY_MAP:
                df = df[df["site_category"] == CATEGORY_MAP[cat_lower]]
            else:
                df = df[df["site_category"].str.lower().str.contains(cat_lower, na=False)]

        if df.empty:
            print(json.dumps({"count": 0, "results": []}, indent=2))
            return

        if args.near_lat is not None:
            dists = haversine_km(args.near_lat, args.near_lon, df["latitude"].values, df["longitude"].values)
            df = df.copy()
            df["distance_km"] = dists
            df = df[df["distance_km"] <= args.radius].sort_values("distance_km")

        results = []
        for _, row in df.head(args.top).iterrows():
            entry = {
                "charge_point_location": str(row.get("charge_point_location", "")),
                "site_category": str(row.get("site_category", "")),
                "latitude": round(float(row["latitude"]), 6),
                "longitude": round(float(row["longitude"]), 6),
            }
            if "distance_km" in row.index:
                entry["distance_km"] = round(float(row["distance_km"]), 3)
            results.append(entry)

        output = {
            "count": len(df),
            "filters": {"category": args.category, "near_lat": args.near_lat,
                        "near_lon": args.near_lon, "radius_km": args.radius},
            "results": results,
        }
        print(json.dumps(output, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
