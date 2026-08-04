"""Print basic statistics for each dataset."""

import pandas as pd
import json
from pathlib import Path
from collections import Counter

DATA_DIR = Path(__file__).parent / "data"

# 1. Unplanned Outages
print("=" * 60)
print("UNPLANNED OUTAGES (df_cleaned.csv)")
print("=" * 60)
df = pd.read_csv(DATA_DIR / "df_cleaned.csv")
print(f"Total records: {len(df):,}")
print(f"Columns: {len(df.columns)}")
print(f"Date range: {df['incident_date_time'].min()} to {df['incident_date_time'].max()}")
print(f"Latitude range: {df['latitude'].min():.2f} to {df['latitude'].max():.2f}")
print(f"Longitude range: {df['longitude'].min():.2f} to {df['longitude'].max():.2f}")
print(f"\nDuration (hours):")
print(f"  Mean: {df['duration-hours'].mean():.2f}")
print(f"  Median: {df['duration-hours'].median():.2f}")
print(f"  Max: {df['duration-hours'].max():.2f}")
print(f"\nDirect cause categories:")
for k, v in df['direct_cause_category'].value_counts().items():
    print(f"  {k}: {v} ({v/len(df)*100:.1f}%)")
print(f"\nNetwork types:")
for k, v in df['network_type'].value_counts().items():
    print(f"  {k}: {v}")
print(f"\nVoltage levels:")
for k, v in df['voltage'].value_counts().head(5).items():
    print(f"  {k}: {v}")

# 2. Charging Sites
print("\n" + "=" * 60)
print("CHARGING SITES (all_charging_sites.csv)")
print("=" * 60)
df = pd.read_csv(DATA_DIR / "all_charging_sites.csv")
print(f"Total sites: {len(df)}")
print(f"Columns: {len(df.columns)}")
print(f"\nSite categories:")
for k, v in df['site_category'].value_counts().items():
    print(f"  {k}: {v}")
print(f"\nLatitude range: {df['latitude'].min():.4f} to {df['latitude'].max():.4f}")
print(f"Longitude range: {df['longitude'].min():.4f} to {df['longitude'].max():.4f}")

# 3. Flexibility Tenders
print("\n" + "=" * 60)
print("FLEXIBILITY TENDERS (flexibility_tenders.geojson)")
print("=" * 60)
with open(DATA_DIR / "flexibility_tenders.geojson", "r") as f:
    data = json.load(f)
features = data["features"]
props = [f["properties"] for f in features]
df = pd.DataFrame(props)
print(f"Total polygons: {len(features)}")
print(f"Unique substations: {df['substation_name'].nunique()}")
print(f"Columns: {len(df.columns)}")
print(f"\nGeometry types:")
geom_types = [f["geometry"]["type"] for f in features]
for k, v in Counter(geom_types).items():
    print(f"  {k}: {v}")
print(f"\nNeed types:")
for k, v in df['need_type'].value_counts().items():
    print(f"  {k}: {v}")
print(f"\nVoltage levels:")
for k, v in df['voltage_of_connection_kv'].value_counts().items():
    print(f"  {k}: {v}")
print(f"\nSample substations: {list(df['substation_name'].unique()[:5])}")

# 4. Live Incidents
print("\n" + "=" * 60)
print("LIVE INCIDENTS (API fields)")
print("=" * 60)
print("Columns: incident_num, incident_type, outage_time,")
print("         customers_affected, customers_off_supply,")
print("         incident_status, estimated_restoration_time,")
print("         latitude, longitude")
print("Total columns: 9")
