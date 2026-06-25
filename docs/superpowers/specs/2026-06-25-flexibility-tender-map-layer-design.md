# Flexibility Tender Map Layer — Design Spec

**Date**: 2026-06-25
**Status**: Approved
**Branch**: flex

## Overview

Add an interactive "Flexibility Tenders" layer to the existing CMS dashboard map. Polygons represent Electricity North West flexibility tender site requirements. Clicking a polygon shows a fixed-size scrollable info panel with site details, with arrow pagination to navigate between delivery periods for the same substation.

## Data Source

- **File**: `data/flexibility_tenders.geojson` (558 features, 4 MB)
- **Format**: GeoJSON FeatureCollection with MultiPolygon geometries
- **Fields**: substation_name, post_codes, voltage_of_connection_kv, maximum_requirement_mva, need_type, delivery_start_date, months_required, times_required, days_required, maximum_utilisation_price_mw, estimated_availability_hours, estimated_utilisation_hours, easting, northing, lat, long, period, site_number, ceiling_price_period
- **No API call needed** — the file is already downloaded and matches the live dataset

## Architecture

### Data Layer (`dashboard/app_logic.py`)

Add `load_flexibility_tenders()` function:

```
@st.cache_data
def load_flexibility_tenders(geojson_path: str, file_mtime: float) -> tuple:
    """Load flexibility tender data from GeoJSON.

    Returns
    -------
    tuple
        (gdf, grouped_dict) where:
        - gdf: GeoDataFrame with one row per unique substation (dissolved geometry)
        - grouped_dict: {substation_name: [list of record dicts sorted by delivery_start_date]}
    """
```

- Read GeoJSON with GeoPandas
- Group records by `substation_name`
- For map rendering: dissolve geometries by substation (one polygon per substation)
- For info panel: keep all records per substation, sorted by `delivery_start_date`
- Cache with `@st.cache_data` using file mtime as part of the key

### Map Layer (`dashboard/map.py`)

Extend `create_advanced_map()` with new parameter:

```python
def create_advanced_map(
    ...,
    flexibility_tenders=None,  # GeoDataFrame with dissolved geometries
):
```

- Add `folium.GeoJson` layer named "Flexibility Tenders"
- Color polygons by `need_type`:
  - "Variable Availability" → blue (#0066CC)
  - "Variable Availability + Operational Utilisation" → purple (#7B2D8E)
  - Other → grey (#6C757D)
- Fill opacity: 0.3, border: 1px darker shade
- Tooltip: substation_name
- Each feature gets an `id` property set to the substation_name for click identification

### Click Handling (`enhanced_app.py`)

Session state additions:
- `flex_selected_substation` — name of clicked substation (or None)
- `flex_page_index` — current delivery period page (0-based)

Click detection flow:
1. `st_folium` returns `last_object_clicked` when a polygon is clicked
2. The GeoJson feature includes a `substation_name` property set via `folium.GeoJsonTooltip`/`fields` — `st_folium` returns this in `last_object_clicked_popup` or the feature properties
3. Parse the substation_name from the returned data, set session state, and `st.rerun()`
4. If the user clicks the map but NOT on a polygon: clear `flex_selected_substation` (set to None)

### Info Panel (`enhanced_app.py`)

Rendered below the map in `col1` when a flexibility tender is selected.

Layout:
- Header: "< Substation Name (1/6) >" with Streamlit `<` `>` buttons
- Fixed-height scrollable container (max-height: 400px, overflow-y: auto)
- Fields displayed as key-value pairs matching the user's specified format
- Pagination updates `flex_page_index` in session state

### Sidebar Toggle

Add a checkbox in the sidebar to show/hide the Flexibility Tenders layer:
- `filters["show_flexibility_tenders"]` — default True
- Follows the same pattern as `show_heatmap`, `show_risk_heatmap`, etc.

## Files to Modify

1. **`dashboard/app_logic.py`** — add `load_flexibility_tenders()` function
2. **`dashboard/map.py`** — add `flexibility_tenders` parameter and GeoJson layer rendering
3. **`enhanced_app.py`** — load data, pass to map, handle clicks, render info panel with pagination
4. **`dashboard/sidebar.py`** — add "Flexibility Tenders" toggle checkbox

## Polygon Coloring

| Need Type | Fill Color | Border Color |
|-----------|-----------|--------------|
| Variable Availability | #0066CC (blue) | #004C99 |
| Variable Availability + Operational Utilisation | #7B2D8E (purple) | #5A1F68 |
| Other | #6C757D (grey) | #4E555B |

## Info Panel Fields

All fields from the GeoJSON properties, displayed in the order specified by the user:

1. Substation Name
2. Post Codes
3. Voltage of connection (kV)
4. Maximum requirement (MVA)
5. Need Type
6. Delivery start date
7. Months Required
8. Times required
9. Days required
10. Maximum Utilisation Price (£/MWh)
11. Estimated availability hours
12. Estimated utilisation hours
13. Easting
14. Northing
15. Lat
16. Long
17. Period
18. Site Number
19. Ceiling Price (£/Period)

## Pagination Behavior

- Each substation can have N delivery periods (1 to ~6)
- Arrow buttons `<` `>` cycle through periods
- Header shows "Substation Name (current/total)" e.g. "Bolton By Bowland (1/6)"
- Index wraps around: pressing `>` on the last page goes to page 1
- Page resets to 1 when clicking a different substation

## Non-Goals

- No API fetching — use the existing local GeoJSON file
- No new dependencies — GeoPandas and Folium are already installed
- No separate page — this is a layer on the existing map
- No filtering by delivery date in the sidebar (YAGNI — can add later)

## Error Handling

- If `flexibility_tenders.geojson` is missing: log warning, skip layer (no crash)
- If GeoJSON is malformed: catch exception in `load_flexibility_tenders()`, return None
- If click can't be matched to a substation: ignore (no error shown to user)
