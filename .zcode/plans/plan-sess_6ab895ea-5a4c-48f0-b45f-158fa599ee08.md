## Plan: Add Flexibility Region Info Tab

### Goal
When clicking a flexibility tender polygon, a **"Region Info" tab** appears as the first tab showing the region's overall info with contract pagination arrows. When clicking outside a flex region, no extra tab appears and Frequency Timeline stays first.

### Changes

#### 1. `enhanced_app.py`
- **Remove** the standalone flex detail panel (lines 378-442) — it moves into the tab
- **Pass** `flex_selected_substation` and `flex_grouped` to `display_dynamic_charts()`

#### 2. `dashboard/chart_display.py`
- **Accept** `flex_selected_substation=None` and `flex_grouped=None` parameters
- **Conditionally build tab list**: if a flex region is selected, prepend `"Region Info"` as the first tab
- **Render** the flex detail content (overall region info + pagination arrows) inside the Region Info tab using the same logic currently in `enhanced_app.py`

### Files to Edit
1. `enhanced_app.py` — remove flex panel, update `display_dynamic_charts` call
2. `dashboard/chart_display.py` — accept new params, conditional tab, render flex content