"""Clean Borderlands Long List sites, geocode, and cross-reference with risk/chargepoints.

Reads the Borderlands Long List Excel file, geocodes each site,
and cross-references with ML risk predictions, recommendation engine,
and existing chargepoint data.

Usage:
    python tools/clean_borderlands.py
    python tools/clean_borderlands.py --top 10
    python tools/clean_borderlands.py --local-authority Cumberland
    python tools/clean_borderlands.py --cross-ref
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BORDERLANDS_FILE = PROJECT_ROOT / "data" / "Borderlands Long List Sites Apr 26.xlsx"
CHARGING_SITES_FILE = PROJECT_ROOT / "data" / "all_charging_sites.csv"
PREDICTIONS_RF = PROJECT_ROOT / "models" / "predictions_randomforest.csv"
PREDICTIONS_XGB = PROJECT_ROOT / "models" / "predictions_xgboost.csv"
OUTPUT_CSV = PROJECT_ROOT / "data" / "borderlands_community_sites.csv"

# Site type classification keywords
SITE_TYPE_MAP = {
    "village hall": "Village Hall",
    "community centre": "Community Centre",
    "community center": "Community Centre",
    "church": "Community Building",
    "chapel": "Community Building",
    "memorial hall": "Community Building",
    "educational institute": "Community Building",
    "parish council": "Community Building",
}


def haversine_km(lat1, lon1, lat2_arr, lon2_arr):
    """Vectorised Haversine distance in km."""
    R = 6371.0
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2_arr), np.radians(lon2_arr)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def classify_site_type(potential_sites: str, brief_description: str) -> str:
    """Classify site type from Potential Sites and Brief Description fields."""
    text = f"{potential_sites} {brief_description}".lower()
    for key, site_type in SITE_TYPE_MAP.items():
        if key in text:
            return site_type
    return "Other Community Site"


def geocode_location(location_name: str, local_authority: str) -> tuple[float, float] | None:
    """Geocode a location using Nominatim (OpenStreetMap)."""
    try:
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="cms_dashboard_tool", timeout=10)

        # Try with local authority first for disambiguation
        query = f"{location_name}, {local_authority}, UK"
        location = geolocator.geocode(query)
        if location:
            return (round(location.latitude, 6), round(location.longitude, 6))

        # Fallback: place name + UK
        query = f"{location_name}, UK"
        location = geolocator.geocode(query)
        if location:
            return (round(location.latitude, 6), round(location.longitude, 6))

        return None
    except Exception:
        return None


def load_predictions() -> pd.DataFrame | None:
    """Load ML risk predictions."""
    for f in [PREDICTIONS_RF, PREDICTIONS_XGB]:
        if f.exists():
            return pd.read_csv(f)
    return None


def load_charging_sites() -> pd.DataFrame | None:
    """Load existing charging site data."""
    if CHARGING_SITES_FILE.exists():
        return pd.read_csv(CHARGING_SITES_FILE)
    return None


def cross_reference_risk(lat: float, lon: float, predictions: pd.DataFrame, radius_km: float = 10) -> dict | None:
    """Find risk data near a geocoded site."""
    if predictions is None or predictions.empty:
        return None

    dists = haversine_km(lat, lon, predictions["lat"].values, predictions["lon"].values)
    nearby = predictions[dists <= radius_km].copy()
    if nearby.empty:
        return None

    nearby["dist_km"] = dists[dists <= radius_km]
    nearest = nearby.sort_values("dist_km").iloc[0]

    result = {
        "nearest_risk_cell_km": round(float(nearest["dist_km"]), 2),
        "risk_level": str(nearest.get("risk_level", "unknown")),
        "confidence": round(float(nearest.get("confidence", 0)), 3),
    }
    if "prob_high" in nearest.index:
        result["prob_high"] = round(float(nearest["prob_high"]), 3)
    if "prob_medium" in nearest.index:
        result["prob_medium"] = round(float(nearest["prob_medium"]), 3)

    # Aggregate nearby risk
    if "prob_high" in nearby.columns:
        result["avg_prob_high_nearby"] = round(float(nearby["prob_high"].mean()), 3)
    high_count = len(nearby[nearby.get("risk_level", pd.Series()) == "High"]) if "risk_level" in nearby.columns else 0
    result["high_risk_cells_within_km"] = int(high_count)

    return result


def cross_reference_charging(lat: float, lon: float, charging_sites: pd.DataFrame, radius_km: float = 10) -> dict | None:
    """Find existing chargepoints near a geocoded site."""
    if charging_sites is None or charging_sites.empty:
        return None

    dists = haversine_km(lat, lon, charging_sites["latitude"].values, charging_sites["longitude"].values)
    nearby = charging_sites[dists <= radius_km].copy()
    if nearby.empty:
        return {"nearest_chargepoint_km": round(float(dists.min()), 2), "count_within_radius": 0, "chargepoints": []}

    nearby["dist_km"] = dists[dists <= radius_km]
    nearest = nearby.sort_values("dist_km").iloc[0]

    cp_list = []
    for _, row in nearby.sort_values("dist_km").head(5).iterrows():
        cp_list.append({
            "name": str(row.get("charge_point_location", "")),
            "category": str(row.get("site_category", "")),
            "distance_km": round(float(row["dist_km"]), 2),
        })

    return {
        "nearest_chargepoint_km": round(float(nearest["dist_km"]), 2),
        "nearest_chargepoint_name": str(nearest.get("charge_point_location", "")),
        "count_within_radius": len(nearby),
        "chargepoints": cp_list,
    }


def cross_reference_recommendations(lat: float, lon: float, predictions: pd.DataFrame,
                                     charging_sites: pd.DataFrame | None, radius_km: float = 5) -> dict | None:
    """Check if site overlaps with recommendation engine output."""
    if predictions is None:
        return None

    # Simple heuristic: check if high-risk and no/low chargepoint coverage
    dists = haversine_km(lat, lon, predictions["lat"].values, predictions["lon"].values)
    nearby = predictions[dists <= radius_km]
    if nearby.empty:
        return {"matches_recommendation": False, "reason": "No risk data nearby"}

    has_high_risk = (nearby.get("risk_level", pd.Series()) == "High").any() if "risk_level" in nearby.columns else False

    cp_gap = True
    if charging_sites is not None and not charging_sites.empty:
        cp_dists = haversine_km(lat, lon, charging_sites["latitude"].values, charging_sites["longitude"].values)
        cp_gap = cp_dists.min() > 3.0

    if has_high_risk and cp_gap:
        return {
            "matches_recommendation": True,
            "reason": "High-risk area with no chargepoints within 3km — recommended for new placement",
        }
    elif has_high_risk:
        return {
            "matches_recommendation": True,
            "reason": "High-risk area with existing chargepoints — may need V2X upgrade",
        }
    return {"matches_recommendation": False, "reason": "Not a priority recommendation area"}


def clean_borderlands(top: int | None = None, local_authority: str | None = None,
                       cross_ref: bool = False, radius_km: float = 10) -> dict:
    """Clean Borderlands data, geocode, and optionally cross-reference.

    Parameters
    ----------
    top : int or None
        Limit number of sites returned.
    local_authority : str or None
        Filter by local authority area.
    cross_ref : bool
        Whether to cross-reference with risk/charging/recommendations.
    radius_km : float
        Radius for cross-reference lookups.

    Returns
    -------
    dict
        JSON-serialisable result.
    """
    if not BORDERLANDS_FILE.exists():
        return {"error": f"Borderlands file not found: {BORDERLANDS_FILE}", "type": "FileNotFoundError"}

    try:
        df = pd.read_excel(BORDERLANDS_FILE, engine="openpyxl", header=1)
    except Exception as e:
        return {"error": f"Failed to read Excel: {e}", "type": type(e).__name__}

    df.columns = df.columns.str.strip()

    required_cols = ["Town/ Village", "Potential Sites", "Brief Description", "Local Authority Area"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        return {"error": f"Missing columns: {missing}", "type": "ValueError"}

    # Load cross-reference data if needed
    predictions = load_predictions() if cross_ref else None
    charging_sites = load_charging_sites() if cross_ref else None

    # Filter by local authority
    if local_authority:
        df = df[df["Local Authority Area"].str.contains(local_authority, case=False, na=False)]

    results = []
    geocoded_count = 0

    for _, row in df.iterrows():
        town = str(row["Town/ Village"]).strip()
        potential_sites = str(row["Potential Sites"]).strip()
        brief_desc = str(row["Brief Description"]).strip()
        authority = str(row["Local Authority Area"]).strip()
        contact = str(row.get("Contact", "")).strip()
        email = str(row.get("Email", "")).strip()

        # Skip empty rows
        if town == "nan" or potential_sites == "nan":
            continue

        site_type = classify_site_type(potential_sites, brief_desc)
        site_name = f"{town} - {potential_sites}"

        # Geocode
        coords = geocode_location(town, authority)
        lat, lon = (coords[0], coords[1]) if coords else (None, None)
        if coords:
            geocoded_count += 1

        entry = {
            "site_name": site_name,
            "town": town,
            "site_type": site_type,
            "latitude": lat,
            "longitude": lon,
            "local_authority": authority,
            "brief_description": brief_desc,
            "contact": contact if contact != "nan" else None,
            "email": email if email != "nan" else None,
        }

        # Cross-reference if enabled and we have coordinates
        if cross_ref and lat is not None and lon is not None:
            risk_info = cross_reference_risk(lat, lon, predictions, radius_km)
            if risk_info:
                entry["risk"] = risk_info

            charging_info = cross_reference_charging(lat, lon, charging_sites, radius_km)
            if charging_info:
                entry["charging"] = charging_info

            rec_info = cross_reference_recommendations(lat, lon, predictions, charging_sites, radius_km)
            if rec_info:
                entry["recommendation"] = rec_info

            time.sleep(1.1)  # Nominatim rate limit

        results.append(entry)

        if top and len(results) >= top:
            break

    # Save cleaned CSV
    if results:
        out_df = pd.DataFrame(results)
        out_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    # Summary stats
    summary = {
        "total_sites": len(results),
        "geocoded": geocoded_count,
        "failed_geocode": len(results) - geocoded_count,
        "output_csv": str(OUTPUT_CSV),
    }

    if cross_ref:
        risk_match = sum(1 for r in results if r.get("recommendation", {}).get("matches_recommendation"))
        with_charging = sum(1 for r in results if r.get("charging", {}).get("count_within_radius", 0) > 0)
        high_risk = sum(1 for r in results if r.get("risk", {}).get("risk_level") == "High")
        summary["cross_ref"] = {
            "high_risk_sites": high_risk,
            "sites_with_nearby_charging": with_charging,
            "matches_recommendation": risk_match,
        }

    if local_authority:
        summary["filtered_by_authority"] = local_authority

    return {"sites": results, "summary": summary}


def main():
    parser = argparse.ArgumentParser(description="Clean Borderlands Long List sites and geocode.")
    parser.add_argument("--top", type=int, default=None, help="Limit number of sites returned")
    parser.add_argument("--local-authority", type=str, default=None, help="Filter by local authority area")
    parser.add_argument("--cross-ref", action="store_true", help="Cross-reference with risk/charging/recommendations")
    parser.add_argument("--radius", type=float, default=10, help="Cross-reference radius in km")
    args = parser.parse_args()

    result = clean_borderlands(
        top=args.top,
        local_authority=args.local_authority,
        cross_ref=args.cross_ref,
        radius_km=args.radius,
    )

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
