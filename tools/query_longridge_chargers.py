import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)

target_lat, target_lon = 53.83, -2.50

c = pd.read_csv('data/all_charging_sites.csv')
c = c.dropna(subset=['latitude','longitude'])
c['dist'] = np.sqrt((c['latitude'] - target_lat)**2 + (c['longitude'] - target_lon))
c['dist_km'] = c['dist'] * 111
nc = c.sort_values('dist').head(5)
print('=== Nearest chargepoints to Longridge (53.83, -2.50) ===')
for _, r in nc.iterrows():
    print(f"  {r['charge_point_location']} ({r['dist_km']:.1f}km) - {r['site_category']}")
    print(f"    Lat: {r['latitude']:.6f}, Lon: {r['longitude']:.6f}")
