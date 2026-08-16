## Plan: Add Monthly Tender Data + Rename Layers

### 1. New fetch script: `data/fetch_monthly_tenders.py`
- Mirror `fetch_flexibility_tenders.py` structure
- API: `https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/catalog/datasets/sp-enw-flexibility-monthly-tender-site-requirements/exports/geojson?limit=-1`
- Output: `data/monthly_tenders.geojson`
- State file: `data/.last_fetch_monthly_tenders`
- `run_monthly_tenders_fetch()` function

### 2. `dashboard/app_logic.py` — add `load_monthly_tenders()`
- Same pattern as `load_flexibility_tenders()` — reads GeoJSON, returns `(dissolved_gdf, grouped_dict)`

### 3. `enhanced_app.py` — fetch + load + click detection
- Fetch monthly tenders (same `is_cache_stale` pattern)
- Load with `load_monthly_tenders()` → `monthly_gdf`, `monthly_grouped`
- **Click detection checks BOTH independently**: biannual hit? show Biannual Region Info. Monthly hit? show Monthly Region Info. Both can be true simultaneously.
- Pass `monthly_tenders=monthly_gdf` to map
- Pass `monthly_selected_substation` + `monthly_grouped` to chart_display

### 4. `dashboard/sidebar.py` — rename + add layer
- `"Flexibility Tenders"` → `"Biannual Tenders"`
- Add `"Monthly Tenders"`

### 5. `dashboard/map.py` — rename + add monthly layer
- Rename `name="Flexibility Tenders"` → `name="Biannual Tenders"`
- Add new FeatureGroup `name="Monthly Tenders"` with same rendering logic
- Accept `monthly_tenders` parameter

### 6. `dashboard/chart_display.py` — region info tabs
- Accept `monthly_selected_substation` + `monthly_grouped` params
- `"Region Info"` → `"Biannual Region Info"` (when biannual match)
- Add `"Monthly Region Info"` tab (when monthly match)
- Both tabs can appear simultaneously, each with shared region info + contract sub-tabs

### Files
1. **Create** `data/fetch_monthly_tenders.py`
2. **Edit** `dashboard/app_logic.py`
3. **Edit** `enhanced_app.py`
4. **Edit** `dashboard/sidebar.py`
5. **Edit** `dashboard/map.py`
6. **Edit** `dashboard/chart_display.py`