"""Check for new incidents since last check and return risk context.

Usage:
    python tools/check_new_incidents.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import numpy as np
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = PROJECT_ROOT / "data" / ".last_incidents_state"
PREDICTIONS_RF = PROJECT_ROOT / "models" / "predictions_randomforest.csv"
CHARGING_SITES_FILE = PROJECT_ROOT / "data" / "all_charging_sites.csv"
OUTAGES_FILE = PROJECT_ROOT / "data" / "df_cleaned.csv"


def haversine_km(lat1, lon1, lat2_arr, lon2_arr):
    R = 6371.0
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2_arr), np.radians(lon2_arr)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"known_incident_ids": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_risk_at_location(lat, lon, predictions):
    dists = haversine_km(lat, lon, predictions["lat"].values, predictions["lon"].values)
    nearest_idx = np.argmin(dists)
    row = predictions.iloc[nearest_idx]
    return {
        "risk_level": str(row["risk_level"]),
        "confidence": round(float(row["confidence"]), 4),
        "prob_high": round(float(row["prob_high"]), 4),
        "distance_km": round(float(dists[nearest_idx]), 3),
    }


def get_nearest_chargepoints(lat, lon, charging_sites, top=3):
    if charging_sites.empty:
        return []
    dists = haversine_km(lat, lon, charging_sites["latitude"].values, charging_sites["longitude"].values)
    nearest = charging_sites.iloc[np.argsort(dists)[:top]]
    results = []
    for i, (_, row) in enumerate(nearest.iterrows()):
        results.append({
            "name": str(row.get("charge_point_location", "")),
            "category": str(row.get("site_category", "")),
            "distance_km": round(float(dists[np.argsort(dists)[i]]), 2),
        })
    return results


def get_historic_context(lat, lon, outages, radius_km=5.0):
    if outages.empty:
        return {"count": 0}
    outages = outages.copy()
    outages["duration-hours"] = pd.to_numeric(outages["duration-hours"], errors="coerce").fillna(0)
    dists = haversine_km(lat, lon, outages["latitude"].values, outages["longitude"].values)
    nearby = outages[dists <= radius_km]
    if nearby.empty:
        return {"count": 0}
    return {
        "count": len(nearby),
        "avg_duration": round(float(nearby["duration-hours"].mean()), 2),
        "total_customer_hours": round(float((pd.to_numeric(nearby["customer_affected"], errors="coerce").fillna(0) * nearby["duration-hours"]).sum()), 1),
    }


def main():
    try:
        from data.fetch_live_incidents import fetch_live_incidents

        df = fetch_live_incidents()
        state = load_state()
        known_ids = set(state.get("known_incident_ids", []))

        if df.empty:
            if known_ids:
                save_state({"known_incident_ids": []})
            print(json.dumps({"new_incidents": [], "count": 0, "message": "No active incidents"}, indent=2))
            return

        current_ids = set(df["incident_num"].dropna().astype(str).tolist())
        new_ids = current_ids - known_ids

        if not new_ids:
            print(json.dumps({"new_incidents": [], "count": 0, "message": "No new incidents since last check"}, indent=2))
            return

        # Load data for context
        predictions = pd.read_csv(PREDICTIONS_RF) if PREDICTIONS_RF.exists() else pd.DataFrame()
        charging_sites = pd.read_csv(CHARGING_SITES_FILE) if CHARGING_SITES_FILE.exists() else pd.DataFrame()
        outages = pd.read_csv(OUTAGES_FILE, low_memory=False) if OUTAGES_FILE.exists() else pd.DataFrame()

        new_incidents = []
        for _, row in df[df["incident_num"].astype(str).isin(new_ids)].iterrows():
            lat = row.get("latitude")
            lon = row.get("longitude")
            incident = {
                "incident_num": str(row.get("incident_num", "")),
                "incident_type": str(row.get("incident_type", "")),
                "outage_time": str(row.get("outage_time", "")),
                "customers_affected": int(row.get("customers_affected", 0)) if pd.notna(row.get("customers_affected")) else 0,
                "customers_off_supply": int(row.get("customers_off_supply", 0)) if pd.notna(row.get("customers_off_supply")) else 0,
                "incident_status": str(row.get("incident_status", "")),
                "estimated_restoration": str(row.get("estimated_restoration_time", "")),
                "lat": float(lat) if pd.notna(lat) else None,
                "lon": float(lon) if pd.notna(lon) else None,
            }

            if pd.notna(lat) and pd.notna(lon) and not predictions.empty:
                incident["risk_context"] = get_risk_at_location(lat, lon, predictions)
                incident["nearest_chargepoints"] = get_nearest_chargepoints(lat, lon, charging_sites)
                incident["historic_outages"] = get_historic_context(lat, lon, outages)

            new_incidents.append(incident)

        # Update state
        save_state({"known_incident_ids": list(current_ids)})

        output = {"new_incidents": new_incidents, "count": len(new_incidents)}
        print(json.dumps(output, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
