## Plan: Add Layer Visibility Multiselect + Move Live Incidents Toggle

### Goal
Add a **"Map Layers" multiselect** in the Advanced Filters sidebar to control which layers are visible on the map. All layers default to ON. Remove the separate `show_risk_heatmap` checkbox and the "Disabled" option from the live incidents refresh interval.

### Layers in the Multiselect (7 total, all default ON)
- Chargepoints
- Buffer Zones
- Outage Heatmap
- Risk Heatmap
- Flexibility Tenders
- AI Recommended Sites
- Live Incidents

### Changes by File

#### 1. `dashboard/sidebar.py`
- **Add** `"Map Layers"` multiselect after Chargepoint Categories, before Statistical Filters (around line 130)
- **Remove** the `show_risk_heatmap` checkbox (line 177) — now in multiselect
- **Remove** `"Disabled"` from `live_refresh_options` dict (line 161) — Live Incidents on/off is now in the multiselect
- **Derive** `show_live_incidents` from `"Live Incidents" in selected_layers` instead of `live_refresh_min is not None`
- **Update** return dict: replace `show_chargepoints`, `show_buffers`, `show_heatmap`, `show_risk_heatmap` with `"show_layers": selected_layers`; keep `show_live_incidents` derived from multiselect

#### 2. `dashboard/map.py`
- **Replace** parameters `show_chargepoints`, `show_buffers`, `show_heatmap`, `show_risk_heatmap` with single `show_layers: list = None` parameter
- **Default** `show_layers` to all 7 layer names if None
- **Update** each layer block to check `if "Layer Name" in show_layers:`
- Layers: Risk Heatmap (line 186), Buffer Zones + Chargepoints (line 288), Outage Heatmap (line 361)

#### 3. `enhanced_app.py`
- **Replace** the 4 separate boolean args in `create_advanced_map()` call (lines 281-287) with `show_layers=filters["show_layers"]`
- **Update** `setup_autorefresh()` call (line 248) — `show_live_incidents` now comes from multiselect
- **Update** `render_live_incidents()` call (line 475) — same

#### 4. `dashboard/app_logic.py`
- **Update** line 254: `show_live_incidents` now comes from the multiselect, no change needed to logic itself (still gates data fetch)

### Verification
- Run `streamlit run enhanced_app.py`
- All 7 layers visible by default
- Deselecting a layer hides it; re-selecting brings it back
- Live Incidents refresh interval no longer has "Disabled" option
- Old `show_risk_heatmap` checkbox is gone