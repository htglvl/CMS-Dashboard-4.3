"""Query risk predictions for a location or district.

Usage:
    python tools/query_risk.py --lat 54.05 --lon -2.80
    python tools/query_risk.py --district Lancaster
    python tools/query_risk.py --district Lancaster --top 20
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
PREDICTIONS_RF = PROJECT_ROOT / "models" / "predictions_randomforest.csv"
PREDICTIONS_XGB = PROJECT_ROOT / "models" / "predictions_xgboost.csv"
OUTAGES_FILE = PROJECT_ROOT / "data" / "df_cleaned.csv"
CELL_SIZE = 0.01


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2), np.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def load_predictions():
    dfs = []
    for path in [PREDICTIONS_RF, PREDICTIONS_XGB]:
        if path.exists():
            df = pd.read_csv(path)
            df["model"] = path.stem.replace("predictions_", "")
            dfs.append(df)
    if not dfs:
        raise FileNotFoundError("No prediction files found in models/")
    return pd.concat(dfs, ignore_index=True)


def assign_districts(predictions, outages):
    if outages.empty or "district_name" not in outages.columns:
        predictions["district_name"] = "Unknown"
        return predictions
    valid = outages.dropna(subset=["latitude", "longitude", "district_name"])
    out_lat = valid["latitude"].values
    out_lon = valid["longitude"].values
    out_district = valid["district_name"].values
    districts = []
    for _, row in predictions.iterrows():
        dists = haversine_km(row["lat"], row["lon"], out_lat, out_lon)
        districts.append(out_district[np.argmin(dists)])
    predictions["district_name"] = districts
    return predictions


def main():
    parser = argparse.ArgumentParser(description="Query risk predictions.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--lat", type=float, help="Latitude")
    group.add_argument("--district", type=str, help="District name")
    parser.add_argument("--lon", type=float, help="Longitude (required with --lat)")
    parser.add_argument("--top", type=int, default=10, help="Number of results")
    args = parser.parse_args()

    if args.lat is not None and args.lon is None:
        parser.error("--lon is required when --lat is provided")

    try:
        predictions = load_predictions()
        outages = pd.read_csv(OUTAGES_FILE, low_memory=False) if OUTAGES_FILE.exists() else pd.DataFrame()
        predictions = assign_districts(predictions, outages)

        # Merge both models into per-cell averages
        unique_cells = predictions.groupby(["lat", "lon"]).agg(
            risk_level=("risk_level", "first"),
            confidence=("confidence", "mean"),
            prob_high=("prob_high", "mean"),
            prob_medium=("prob_medium", "mean"),
            prob_low=("prob_low", "mean"),
            district_name=("district_name", "first"),
        ).reset_index()

        if args.lat is not None:
            dists = haversine_km(args.lat, args.lon, unique_cells["lat"].values, unique_cells["lon"].values)
            unique_cells = unique_cells.copy()
            unique_cells["distance_km"] = dists
            nearest = unique_cells.nsmallest(args.top, "distance_km")
            results = []
            for _, row in nearest.iterrows():
                results.append({
                    "lat": float(row["lat"]), "lon": float(row["lon"]),
                    "risk_level": str(row["risk_level"]),
                    "confidence": round(float(row["confidence"]), 4),
                    "prob_high": round(float(row["prob_high"]), 4),
                    "prob_medium": round(float(row["prob_medium"]), 4),
                    "prob_low": round(float(row["prob_low"]), 4),
                    "distance_km": round(float(row["distance_km"]), 3),
                    "district_name": str(row.get("district_name", "Unknown")),
                })
            output = {
                "query_type": "coordinates",
                "query_lat": args.lat, "query_lon": args.lon,
                "results": results,
                "summary": {
                    "count": len(results),
                    "nearest_risk_level": results[0]["risk_level"] if results else None,
                    "nearest_distance_km": results[0]["distance_km"] if results else None,
                },
            }
        else:
            mask = unique_cells["district_name"].str.lower() == args.district.lower()
            cells = unique_cells[mask]
            if cells.empty:
                mask = unique_cells["district_name"].str.lower().str.contains(args.district.lower(), na=False)
                cells = unique_cells[mask]
            high_count = len(cells[cells["risk_level"] == "High"])
            total = len(cells)
            results = []
            for _, row in cells.head(args.top).iterrows():
                results.append({
                    "lat": float(row["lat"]), "lon": float(row["lon"]),
                    "risk_level": str(row["risk_level"]),
                    "confidence": round(float(row["confidence"]), 4),
                    "prob_high": round(float(row["prob_high"]), 4),
                    "prob_medium": round(float(row["prob_medium"]), 4),
                    "prob_low": round(float(row["prob_low"]), 4),
                })
            output = {
                "query_type": "district",
                "query_district": args.district,
                "results": results,
                "summary": {
                    "total_cells": total,
                    "high_risk_cells": high_count,
                    "avg_confidence": round(float(cells["confidence"].mean()), 4) if total > 0 else 0.0,
                    "high_risk_pct": round(high_count / total * 100, 1) if total > 0 else 0.0,
                },
            }

        print(json.dumps(output, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
