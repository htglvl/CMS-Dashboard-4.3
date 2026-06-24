import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Longridge, Lancashire: approx 53.83, -2.50
target_lat, target_lon = 53.83, -2.50

# Predictions
p = pd.read_csv('models/predictions_randomforest.csv')
p = p.dropna(subset=['lat','lon'])
p['dist'] = np.sqrt((p['lat'] - target_lat)**2 + (p['lon'] - target_lon)**2)
p['dist_km'] = p['dist'] * 111
nearest = p.sort_values('dist').head(5)

print('=== Nearest grid cells to Longridge (53.83, -2.50) ===')
for _, r in nearest.iterrows():
    print(f"  ({r['lat']}, {r['lon']}) - {r['dist_km']:.1f}km")
    print(f"    Risk: {r['risk_level']} | Prob High: {r['prob_high']*100:.1f}% | Confidence: {r['confidence']*100:.1f}%")

# Outages
print()
o = pd.read_csv('data/df_cleaned.csv', low_memory=False)
o = o.dropna(subset=['latitude','longitude'])
o['dist'] = np.sqrt((o['latitude'] - target_lat)**2 + (o['longitude'] - target_lon))
for r_km in [5, 10, 20]:
    r_deg = r_km / 111
    count = len(o[o['dist'] < r_deg])
    print(f'Outages within {r_km}km: {count}')

near = o[o['dist'] < 0.05]
if len(near) > 0:
    print(f"Districts (5.5km): {near['district_name'].value_counts().head(5).to_dict()}")
    print(f"Avg duration (hrs): {near['duration-hours'].mean():.1f}")
    print(f"Avg customers affected: {near['customer_affected'].mean():.0f}")

# Charging
print()
c = pd.read_csv('data/all_charging_sites.csv')
c = c.dropna(subset=['latitude','longitude'])
c['dist'] = np.sqrt((c['latitude'] - target_lat)**2 + (c['longitude'] - target_lon))
c['dist_km'] = c['dist'] * 111
nc = c.sort_values('dist').head(5)
print('=== Nearest chargepoints ===')
for _, r in nc.iterrows():
    print(f"  {r['charge_point_location']} ({r['dist_km']:.1f}km) - {r['site_category']}")
