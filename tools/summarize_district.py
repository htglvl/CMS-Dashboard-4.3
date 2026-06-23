"""Full district summary combining risk, outages, charging sites.

Usage:
    python tools/summarize_district.py --district Lancaster
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
CHARGING_SITES_FILE = PROJECT_ROOT / "data" / "all_charging_sites.csv"


def haversine_km(lat1, lon1, lat2_arr, lon2_arr):
    R = 6371.0
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2_arr), np.radians(lon2_arr)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def load_predictions():
    dfs = []
    for path in [PREDICTIONS_RF, PREDICTIONS_XGB]:
        if path.exists():
            dfs.append(pd.read_csv(path))
    if not dfs:
        raise FileNotFoundError("No prediction files found in models/")
    combined = pd.concat(dfs, ignore_index=True)
    return combined.groupby(["lat", "lon"]).agg(
        risk_level=("risk_level", "first"),
        confidence=("confidence", "mean"),
        prob_high=("prob_high", "mean"),
        prob_medium=("prob_medium", "mean"),
        prob_low=("prob_low", "mean"),
    ).reset_index()


def assign_districts(predictions, outages):
    if outages.empty or "district_name" not in outages.columns:
        predictions["district_name"] = "Unknown"
        return predictions
    valid = outages.dropna(subset=["latitude", "longitude", "district_name"])
    out_lat, out_lon, out_district = valid["latitude"].values, valid["longitude"].values, valid["district_name"].values
    districts = []
    for _, row in predictions.iterrows():
        dists = haversine_km(row["lat"], row["lon"], out_lat, out_lon)
        districts.append(out_district[np.argmin(dists)])
    predictions["district_name"] = districts
    return predictions


def get_risk_summary(predictions, district):
    mask = predictions["district_name"].str.lower() == district.lower()
    cells = predictions[mask]
    if cells.empty:
        mask = predictions["district_name"].str.lower().str.contains(district.lower(), na=False)
        cells = predictions[mask]
    total = len(cells)
    high_count = len(cells[cells["risk_level"] == "High"])
    return {
        "total_cells": total,
        "high_risk_cells": high_count,
        "avg_confidence": round(float(cells["confidence"].mean()), 4) if total > 0 else 0.0,
        "high_risk_pct": round(high_count / total * 100, 1) if total > 0 else 0.0,
    }


def get_outage_summary(outages, district):
    mask = outages["district_name"].str.lower() == district.lower()
    df = outages[mask]
    if df.empty:
        mask = outages["district_name"].str.lower().str.contains(district.lower(), na=False)
        df = outages[mask]
    total = len(df)
    if total == 0:
        return {"total": 0, "avg_duration": 0.0, "total_customer_hours": 0.0, "top_causes": []}
    df = df.copy()
    df["duration-hours"] = pd.to_numeric(df["duration-hours"], errors="coerce").fillna(0)
    df["customer_affected"] = pd.to_numeric(df["customer_affected"], errors="coerce").fillna(0)
    cause_counts = df["direct_cause_category"].value_counts().head(5)
    return {
        "total": total,
        "avg_duration": round(float(df["duration-hours"].mean()), 2),
        "total_customer_hours": round(float((df["customer_affected"] * df["duration-hours"]).sum()), 1),
        "top_causes": [{"cause": str(c), "count": int(n)} for c, n in cause_counts.items()],
    }


def get_charging_sites_summary(charging_sites, outages, district, radius_km=15.0):
    if charging_sites.empty:
        return {"total": 0, "v2x": 0, "building_supplied": 0, "other": 0, "sites": []}
    mask = outages["district_name"].str.lower() == district.lower()
    district_outages = outages[mask]
    if district_outages.empty:
        mask = outages["district_name"].str.lower().str.contains(district.lower(), na=False)
        district_outages = outages[mask]
    if district_outages.empty:
        return {"total": 0, "v2x": 0, "building_supplied": 0, "other": 0, "sites": []}
    centroid_lat = float(district_outages["latitude"].mean())
    centroid_lon = float(district_outages["longitude"].mean())
    dists = haversine_km(centroid_lat, centroid_lon, charging_sites["latitude"].values, charging_sites["longitude"].values)
    nearby = charging_sites[dists <= radius_km].copy()
    nearby["distance_km"] = dists[dists <= radius_km]
    return {
        "total": len(nearby),
        "v2x": len(nearby[nearby["site_category"] == "V2X Chargepoint"]),
        "building_supplied": len(nearby[nearby["site_category"] == "Building-supplied Charger"]),
        "other": len(nearby[nearby["site_category"] == "Other Chargepoint"]),
        "sites": [{"charge_point_location": str(r.get("charge_point_location", "")),
                   "site_category": str(r.get("site_category", "")),
                   "distance_km": round(float(r["distance_km"]), 2)}
                  for _, r in nearby.sort_values("distance_km").iterrows()],
    }


def main():
    parser = argparse.ArgumentParser(description="Full district summary.")
    parser.add_argument("--district", type=str, required=True)
    args = parser.parse_args()

    try:
        predictions = load_predictions()
        outages = pd.read_csv(OUTAGES_FILE, low_memory=False) if OUTAGES_FILE.exists() else pd.DataFrame()
        charging_sites = pd.read_csv(CHARGING_SITES_FILE) if CHARGING_SITES_FILE.exists() else pd.DataFrame()
        predictions = assign_districts(predictions, outages)

        risk = get_risk_summary(predictions, args.district)
        outage_summary = get_outage_summary(outages, args.district)
        charging_summary = get_charging_sites_summary(charging_sites, outages, args.district)

        parts = [f"{args.district} has {risk['high_risk_cells']} high-risk grid cells out of {risk['total_cells']} ({risk['high_risk_pct']}%)."]
        if outage_summary["total"] > 0:
            parts.append(f"Historically {outage_summary['total']} outages, avg {outage_summary['avg_duration']:.1f}h, {outage_summary['total_customer_hours']:.0f} customer-hours lost.")
        if charging_summary["total"] > 0:
            parts.append(f"{charging_summary['total']} charging sites nearby ({charging_summary['v2x']} V2X).")

        output = {
            "district": args.district,
            "risk": risk,
            "outages": outage_summary,
            "charging_sites": charging_summary,
            "summary_text": " ".join(parts),
        }
        print(json.dumps(output, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
