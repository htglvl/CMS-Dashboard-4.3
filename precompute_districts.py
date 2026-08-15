"""Pre-compute district assignments for prediction cells.
Run once, then query_risk.py will load the cached results.

Usage: python precompute_districts.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PREDICTIONS_RF = PROJECT_ROOT / "models" / "predictions_randomforest.csv"
PREDICTIONS_XGB = PROJECT_ROOT / "models" / "predictions_xgboost.csv"
OUTAGES_FILE = PROJECT_ROOT / "data" / "df_cleaned.csv"


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2), np.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def main():
    print("Loading data...")
    outages = pd.read_csv(OUTAGES_FILE, low_memory=False)
    valid = outages.dropna(subset=["latitude", "longitude", "district_name"])
    out_lat = valid["latitude"].values
    out_lon = valid["longitude"].values
    out_district = valid["district_name"].values

    for pred_file in [PREDICTIONS_RF, PREDICTIONS_XGB]:
        if not pred_file.exists():
            print(f"Skipping {pred_file} (not found)")
            continue

        print(f"\nProcessing {pred_file.name}...")
        preds = pd.read_csv(pred_file)
        print(f"  {len(preds)} cells")

        districts = []
        for i, row in preds.iterrows():
            dists = haversine_km(row["lat"], row["lon"], out_lat, out_lon)
            districts.append(out_district[np.argmin(dists)])
            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(preds)} cells processed...")

        preds["district_name"] = districts

        # Save
        preds.to_csv(pred_file, index=False)
        print(f"  Saved to {pred_file}")

        # Show distribution
        print(f"  District distribution:")
        for d, count in preds["district_name"].value_counts().items():
            print(f"    {d}: {count}")

    print("\nDone! query_risk.py will now use cached district assignments.")


if __name__ == "__main__":
    main()
