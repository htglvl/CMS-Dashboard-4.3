# Spatial Analysis

This page explains how the dashboard determines which outages affect which charging sites.

---

## Buffer Zones

Each charging site has a **2-mile (3.218 km) circular buffer** drawn around it on the map. Outages that fall within this buffer are considered to affect that site.

---

## Haversine Distance

The dashboard uses the **Haversine formula** to calculate the great-circle distance between two points on the Earth's surface. This is more accurate than the previous rectangular approximation (latitude/longitude difference), which created a bounding box rather than a true circle.

### The Formula

```python
a = sin²(Δlat/2) + cos(lat1) × cos(lat2) × sin²(Δlon/2)
c = 2 × arcsin(√a)
distance = R × c
```

Where:
- `R` = 6371 km (Earth's radius)
- `lat1, lon1` = site coordinates (in radians)
- `lat2, lon2` = outage coordinates (in radians)

### Vectorised Implementation

For performance, the dashboard precomputes outage coordinates in radians and uses NumPy array operations to calculate distances to all outages simultaneously:

```python
lat0 = np.radians(site['latitude'])
lon0 = np.radians(site['longitude'])
outages_lat_rad = np.radians(outages['latitude'].values)
outages_lon_rad = np.radians(outages['longitude'].values)

dlat = outages_lat_rad - lat0
dlon = outages_lon_rad - lon0
a = np.sin(dlat / 2) ** 2 + np.cos(lat0) * np.cos(outages_lat_rad) * np.sin(dlon / 2) ** 2
c = 2 * np.arcsin(np.sqrt(a))
distances_km = 6371.0 * c

mask = distances_km <= 3.218  # 2 miles in km
nearby_outages = outages[mask]
```

This avoids slow Python loops over individual outage records.

---

## GeoPandas Spatial Analysis

The `spatial_analysis.py` module provides more advanced spatial operations using GeoPandas and Shapely:

### Multi-Radius Overlaps

Finds outages that fall within the buffer zones of **multiple** charging sites. This identifies areas where grid disruption affects several EV charging locations simultaneously.

### Site Vulnerability Analysis

For each site, the module:
1. Creates a Shapely Point geometry for the site
2. Projects to British National Grid (EPSG:27700) for accurate buffer creation
3. Creates a 3.218 km buffer polygon
4. Checks which outage points fall within the buffer
5. Computes vulnerability metrics

### Investment Priority Ranking

Generates a prioritised list of sites for V2X investment based on:
- Vulnerability score (weighted: frequency 30%, duration 25%, impact 35%, consistency 10%)
- Existing V2X capability (non-V2X sites get a 1.2× boost)
- Data confidence (sites with >5 outages get a 1.1× boost)

---

## Coordinate Systems

| CRS | Code | Usage |
|---|---|---|
| WGS 84 | EPSG:4326 | Default lat/lon coordinates |
| British National Grid | EPSG:27700 | Used for accurate buffer calculations in the UK |

The spatial analysis module converts between these coordinate systems to ensure buffer distances are measured accurately in metres, not degrees.

---

## Heatmap

When enabled, the dashboard overlays a Folium HeatMap showing the density of outage locations. The heatmap uses:
- `radius=15` — pixel radius of each point
- `blur=10` — blur factor
- `min_opacity=0.2` — minimum opacity

The intensity of each point is weighted by the outage duration in hours.

---

## Performance Considerations

- Haversine calculations are vectorised using NumPy for speed
- The dashboard precomputes radian coordinates once and reuses them
- GeoPandas spatial joins in `spatial_analysis.py` are slower but more flexible for complex queries
- For the main dashboard, the vectorised Haversine approach is used (faster for interactive use)
