## Plan: Add UK Boundary Overlay Layers

### 1. Create `data/download_local_authorities.py`
- Download from ONS GeoPortal ArcGIS FeatureServer
- Save to `data/uk_local_authorities.geojson`

### 2. Update `dashboard/sidebar.py`
- Add `"UK Counties"` and `"Local Authorities"` at the TOP of `_ALL_LAYERS` (so they render first/bottom)

### 3. Update `dashboard/map.py`
- Render county and local authority boundaries FIRST (before all other layers)
- Boundary-only styling: no fill, just borders with labels on hover

### 4. Update `enhanced_app.py`
- Load both GeoJSON files with `gpd.read_file()`
- Pass to `create_advanced_map()`

### 5. Verify compilation