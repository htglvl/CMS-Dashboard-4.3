"""Exploratory Data Analysis for dissertation."""

import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

df = pd.read_csv(DATA_DIR / "df_cleaned.csv")
df["incident_date_time"] = pd.to_datetime(df["incident_date_time"], errors="coerce", utc=True)

print("=" * 70)
print("EXPLORATORY DATA ANALYSIS")
print("=" * 70)

# 1. Basic stats
print("\n--- 1. DATASET OVERVIEW ---")
print(f"Total records: {len(df):,}")
print(f"Date range: {df['incident_date_time'].min()} to {df['incident_date_time'].max()}")
print(f"Latitude range: {df['latitude'].min():.2f} to {df['latitude'].max():.2f}")
print(f"Longitude range: {df['longitude'].min():.2f} to {df['longitude'].max():.2f}")

# 2. Missing values
print("\n--- 2. MISSING VALUES ---")
missing = df.isnull().sum()
missing_pct = (missing / len(df) * 100).round(1)
for col in df.columns:
    if missing[col] > 0:
        print(f"  {col}: {missing[col]:,} ({missing_pct[col]}%)")

# 3. Duration statistics
print("\n--- 3. DURATION STATISTICS ---")
dur = df["duration-hours"].dropna()
print(f"  Count: {len(dur):,}")
print(f"  Mean: {dur.mean():.2f} hours")
print(f"  Median: {dur.median():.2f} hours")
print(f"  Std: {dur.std():.2f} hours")
print(f"  Min: {dur.min():.2f} hours")
print(f"  Max: {dur.max():.2f} hours")
print(f"  25th percentile: {dur.quantile(0.25):.2f} hours")
print(f"  75th percentile: {dur.quantile(0.75):.2f} hours")
print(f"  95th percentile: {dur.quantile(0.95):.2f} hours")
print(f"  99th percentile: {dur.quantile(0.99):.2f} hours")

# 4. Temporal distribution
print("\n--- 4. TEMPORAL DISTRIBUTION ---")
print("\nOutages by year:")
year_counts = df["year"].value_counts().sort_index()
for year, count in year_counts.items():
    print(f"  {int(year)}: {count:,}")

print("\nOutages by season:")
season_counts = df["season"].value_counts()
for season, count in season_counts.items():
    print(f"  {season}: {count:,} ({count/len(df)*100:.1f}%)")

print("\nOutages by month:")
month_counts = df["month_name"].value_counts()
for month, count in month_counts.items():
    print(f"  {month}: {count:,} ({count/len(df)*100:.1f}%)")

# 5. Cause analysis
print("\n--- 5. DIRECT CAUSE ANALYSIS ---")
cause_counts = df["direct_cause_category"].value_counts()
for cause, count in cause_counts.items():
    print(f"  {cause}: {count:,} ({count/len(df)*100:.1f}%)")

# 6. Network type
print("\n--- 6. NETWORK TYPE ---")
net_counts = df["network_type"].value_counts()
for net, count in net_counts.items():
    print(f"  {net}: {count:,} ({count/len(df)*100:.1f}%)")

# 7. Voltage
print("\n--- 7. VOLTAGE ---")
volt_counts = df["voltage"].value_counts()
for volt, count in volt_counts.items():
    print(f"  {volt}: {count:,} ({count/len(df)*100:.1f}%)")

# 8. Duration category
print("\n--- 8. DURATION CATEGORY ---")
dur_cat = df["duration_category"].value_counts()
for cat, count in dur_cat.items():
    print(f"  {cat}: {count:,} ({count/len(df)*100:.1f}%)")

# 9. Exceptional events
print("\n--- 9. EXCEPTIONAL EVENTS ---")
exc_counts = df["is_exceptional_event"].value_counts()
for val, count in exc_counts.items():
    print(f"  {val}: {count:,} ({count/len(df)*100:.1f}%)")

# 10. Top districts
print("\n--- 10. TOP DISTRICTS ---")
dist_counts = df["district_name"].value_counts().head(10)
for dist, count in dist_counts.items():
    print(f"  {dist}: {count:,} ({count/len(df)*100:.1f}%)")

# 11. Customer impact
print("\n--- 11. CUSTOMER IMPACT ---")
cust = df["total_customer_minutes_lost"].dropna()
print(f"  Total customer minutes lost: {cust.sum():,.0f}")
print(f"  Mean: {cust.mean():,.0f}")
print(f"  Median: {cust.median():,.0f}")
print(f"  Max: {cust.max():,.0f}")

# 12. Charging sites
print("\n--- 12. CHARGING SITES ---")
cs = pd.read_csv(DATA_DIR / "all_charging_sites.csv")
print(f"Total sites: {len(cs)}")
print("\nBy category:")
for cat, count in cs["site_category"].value_counts().items():
    print(f"  {cat}: {count}")

# 13. Flexibility tenders
print("\n--- 13. FLEXIBILITY TENDERS ---")
import json
with open(DATA_DIR / "flexibility_tenders.geojson", "r") as f:
    data = json.load(f)
features = data["features"]
props = [f["properties"] for f in features]
ft = pd.DataFrame(props)
print(f"Total polygons: {len(features)}")
print(f"Unique substations: {ft['substation_name'].nunique()}")
print("\nBy need type:")
for nt, count in ft["need_type"].value_counts().items():
    print(f"  {nt}: {count}")
