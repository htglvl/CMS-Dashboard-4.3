import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Load data
predictions = pd.read_csv('models/predictions_randomforest.csv').dropna(subset=['lat','lon'])
outages = pd.read_csv('data/df_cleaned.csv', low_memory=False).dropna(subset=['latitude','longitude'])
charging = pd.read_csv('data/all_charging_sites.csv').dropna(subset=['latitude','longitude'])

# Find high-risk grid cells
high_risk = predictions[predictions['risk_level'] == 'High'].sort_values('prob_high', ascending=False)
medium_risk = predictions[predictions['risk_level'] == 'Medium'].sort_values('prob_high', ascending=False)

print("=" * 70)
print("RECOMMENDATION SITES: HIGH RISK (for new chargepoint placement)")
print("=" * 70)
for _, r in high_risk.head(10).iterrows():
    # Find nearby outages
    outages['dist'] = np.sqrt((outages['latitude'] - r['lat'])**2 + (outages['longitude'] - r['lon']))
    nearby = outages[outages['dist'] < 0.05]
    # Find nearby charging
    charging['dist'] = np.sqrt((charging['latitude'] - r['lat'])**2 + (charging['longitude'] - r['lon']))
    nearby_chargers = charging[charging['dist'] < 0.1]
    
    print(f"\n  Grid: ({r['lat']}, {r['lon']})")
    print(f"    Risk: {r['risk_level']} | Prob High: {r['prob_high']*100:.1f}% | Confidence: {r['confidence']*100:.1f}%")
    print(f"    Nearby outages (5.5km): {len(nearby)} | Nearby chargers (11km): {len(nearby_chargers)}")

print("\n" + "=" * 70)
print("RECOMMENDATION SITES: MEDIUM RISK")
print("=" * 70)
for _, r in medium_risk.head(10).iterrows():
    outages['dist'] = np.sqrt((outages['latitude'] - r['lat'])**2 + (outages['longitude'] - r['lon']))
    nearby = outages[outages['dist'] < 0.05]
    charging['dist'] = np.sqrt((charging['latitude'] - r['lat'])**2 + (charging['longitude'] - r['lon']))
    nearby_chargers = charging[charging['dist'] < 0.1]
    
    print(f"\n  Grid: ({r['lat']}, {r['lon']})")
    print(f"    Risk: {r['risk_level']} | Prob High: {r['prob_high']*100:.1f}% | Confidence: {r['confidence']*100:.1f}%")
    print(f"    Nearby outages (5.5km): {len(nearby)} | Nearby chargers (11km): {len(nearby_chargers)}")

print("\n" + "=" * 70)
print("V2X OPPORTUNITY SITES (High/Medium risk + few existing chargers)")
print("=" * 70)
candidates = predictions[predictions['risk_level'].isin(['High', 'Medium'])].copy()
candidates['dist'] = np.sqrt((candidates['lat'] - 54.5)**2 + (candidates['lon'] + 2.7)**2)

for _, r in candidates.sort_values('prob_high', ascending=False).head(10).iterrows():
    charging['dist2'] = np.sqrt((charging['latitude'] - r['lat'])**2 + (charging['longitude'] - r['lon']))
    nearby_ch = charging[charging['dist2'] < 0.1]
    if len(nearby_ch) < 3:  # underserved area
        print(f"\n  Grid: ({r['lat']}, {r['lon']})")
        print(f"    Risk: {r['risk_level']} | Prob High: {r['prob_high']*100:.1f}% | Confidence: {r['confidence']*100:.1f}%")
        print(f"    Existing chargers within 11km: {len(nearby_ch)}")
        print(f"    REASON: High risk + underserved = V2X opportunity")
