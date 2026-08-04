"""Print all columns from each dataset for dissertation appendix."""

import pandas as pd
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# 1. Unplanned Outages
print("=" * 60)
print("UNPLANNED OUTAGES (df_cleaned.csv)")
print("=" * 60)
df = pd.read_csv(DATA_DIR / "df_cleaned.csv", nrows=1)

for i, col in enumerate(df.columns, 1):
    print(f"{col} {df[col].dtype}")
print(f"\nTotal columns: {len(df.columns)}")

# 2. Charging Sites
print("\n" + "=" * 60)
print("CHARGING SITES (all_charging_sites.csv)")
print("=" * 60)
df = pd.read_csv(DATA_DIR / "all_charging_sites.csv", nrows=1)
for i, col in enumerate(df.columns, 1):
    print(f"  {i:2d}. {col:<35s} ({df[col].dtype})")
print(f"\nTotal columns: {len(df.columns)}")

# 3. Flexibility Tenders
print("\n" + "=" * 60)
print("FLEXIBILITY TENDERS (flexibility_tenders.geojson)")
print("=" * 60)
with open(DATA_DIR / "flexibility_tenders.geojson", "r") as f:
    data = json.load(f)
    props = data["features"][0]["properties"]
    for i, (k, v) in enumerate(props.items(), 1):
        print(f"{k}")
    print(f"\nTotal columns: {len(props)}")

# 4. Live Incidents
print("\n" + "=" * 60)
print("LIVE INCIDENTS (API fields)")
print("=" * 60)
live_cols = [
    "incident_num", "incident_type", "outage_time",
    "customers_affected", "customers_off_supply",
    "incident_status", "estimated_restoration_time",
    "latitude", "longitude",
]
for i, col in enumerate(live_cols, 1):
    print(f"  {i:2d}. {col}")
print(f"\nTotal columns: {len(live_cols)}")
