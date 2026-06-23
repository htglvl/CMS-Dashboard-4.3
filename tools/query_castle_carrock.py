import pandas as pd
import numpy as np

target_lat, target_lon = 54.84, -2.71

predictions = pd.read_csv('models/predictions_randomforest.csv')
predictions['dist'] = np.sqrt((predictions['lat'] - target_lat)**2 + (predictions['lon'] - target_lon)**2)

nearest = predictions.sort_values('dist').head(5)
print('=== Nearest grid cells to Castle Carrock (54.84, -2.71) ===')
for _, row in nearest.iterrows():
    km = row['dist'] * 111
    print(f"  ({row['lat']}, {row['lon']}) - {km:.1f}km away")
    print(f"    Risk: {row['risk_level']} | Probability: {row['prob_high']*100:.1f}% | Confidence: {row['confidence']*100:.1f}%")

print()
outages = pd.read_csv('data/df_cleaned.csv', low_memory=False)
outages['dist'] = np.sqrt((outages['latitude'] - target_lat)**2 + (outages['longitude'] - target_lon))
nearby = outages[outages['dist'] < 0.05]
print(f'=== Outages within ~5.5km of Castle Carrock ===')
print(f'Total outages: {len(nearby)}')
if len(nearby) > 0:
    print(f"Districts: {nearby['district_name'].value_counts().head(5).to_dict()}")
    print(f"Avg duration (hrs): {nearby['duration-hours'].mean():.1f}")
    print(f"Avg customers affected: {nearby['customer_affected'].mean():.0f}")

print()
charging = pd.read_csv('data/all_charging_sites.csv')
charging['dist'] = np.sqrt((charging['latitude'] - target_lat)**2 + (charging['longitude'] - target_lon))
nearest_chargers = charging.sort_values('dist').head(5)
print('=== Nearest chargepoints ===')
for _, row in nearest_chargers.iterrows():
    km = row['dist'] * 111
    print(f"  {row['charge_point_location']} ({km:.1f}km) - {row['site_category']}")
