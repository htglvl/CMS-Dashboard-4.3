"""Query historic outage data with filters.

Usage:
    python tools/query_outages.py --district Lancaster --year 2023
    python tools/query_outages.py --cause Weather --min-duration 2.0
    python tools/query_outages.py --top 5 --sort customers
    python tools/query_outages.py --lat 54.05 --lon -2.80 --radius 15
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
OUTAGES_FILE = PROJECT_ROOT / "data" / "df_cleaned.csv"


def haversine_km(lat1, lon1, lat2_arr, lon2_arr):
    """Calculate haversine distance in km."""
    R = 6371.0
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2_arr), np.radians(lon2_arr)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

RESULT_FIELDS = [
    "incident_date_time", "district_name", "primary_substation",
    "duration-hours", "customer_affected", "direct_cause_category",
    "latitude", "longitude",
]

SORT_MAP = {"duration": "duration-hours", "customers": "customer_affected", "date": "incident_date_time"}


def main():
    parser = argparse.ArgumentParser(description="Query historic outage data.")
    parser.add_argument("--district", type=str, help="Filter by district name")
    parser.add_argument("--lat", type=float, help="Latitude for proximity search")
    parser.add_argument("--lon", type=float, help="Longitude for proximity search")
    parser.add_argument("--radius", type=float, default=15.0, help="Radius in km (default: 15)")
    parser.add_argument("--year", type=int, help="Filter by year")
    parser.add_argument("--cause", type=str, help="Filter by direct cause category")
    parser.add_argument("--min-duration", type=float, help="Minimum duration in hours")
    parser.add_argument("--top", type=int, default=10, help="Number of results")
    parser.add_argument("--sort", type=str, default="duration", choices=["duration", "customers", "date"])
    args = parser.parse_args()

    try:
        if not OUTAGES_FILE.exists():
            raise FileNotFoundError(f"Outage data not found: {OUTAGES_FILE}")

        df = pd.read_csv(OUTAGES_FILE, low_memory=False)
        if not pd.api.types.is_datetime64_any_dtype(df["incident_date_time"]):
            df["incident_date_time"] = pd.to_datetime(df["incident_date_time"], errors="coerce", utc=True)
        df["duration-hours"] = pd.to_numeric(df["duration-hours"], errors="coerce").fillna(0)
        df["customer_affected"] = pd.to_numeric(df["customer_affected"], errors="coerce").fillna(0)

        if args.district:
            df = df[df["district_name"].str.lower().str.contains(args.district.lower(), na=False)]

        # Proximity filter: lat/lon/radius
        if args.lat is not None and args.lon is not None:
            if "latitude" in df.columns and "longitude" in df.columns:
                dists = haversine_km(args.lat, args.lon, df["latitude"].values, df["longitude"].values)
                df = df[dists <= args.radius].copy()
                df["distance_km"] = dists[dists <= args.radius]
            else:
                # No lat/lon columns - can't do proximity search
                pass

        if args.year:
            df = df[df["year"] == args.year]
        if args.cause:
            df = df[df["direct_cause_category"].str.lower().str.contains(args.cause.lower(), na=False)]
        if args.min_duration is not None:
            df = df[df["duration-hours"] >= args.min_duration]

        sort_col = SORT_MAP[args.sort]
        df = df.sort_values(sort_col, ascending=False, na_position="last")

        total_count = len(df)
        avg_duration = float(df["duration-hours"].mean()) if total_count > 0 else 0.0
        total_customer_hours = float((df["customer_affected"] * df["duration-hours"]).sum()) if total_count > 0 else 0.0

        results = []
        for _, row in df.head(args.top).iterrows():
            entry = {}
            for field in RESULT_FIELDS:
                val = row.get(field)
                if pd.isna(val):
                    entry[field] = None
                elif field == "incident_date_time":
                    entry[field] = str(val)
                else:
                    entry[field] = val
            # Include distance if proximity search was used
            if "distance_km" in row.index:
                entry["distance_km"] = round(float(row["distance_km"]), 3)
            results.append(entry)

        output = {
            "count": total_count,
            "filters": {"district": args.district, "lat": args.lat, "lon": args.lon,
                        "radius_km": args.radius, "year": args.year, "cause": args.cause,
                        "min_duration": args.min_duration, "sort": args.sort},
            "results": results,
            "summary": {"avg_duration": round(avg_duration, 2), "total_customer_hours": round(total_customer_hours, 1)},
        }
        print(json.dumps(output, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
