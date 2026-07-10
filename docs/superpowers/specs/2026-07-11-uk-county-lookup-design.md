# UK Ceremonial County Lookup Tool — Design Spec

**Date:** 2026-07-11  
**Author:** ZCode (AI-assisted)  
**Status:** Draft

---

## Problem

The dashboard tracks unplanned outages across the Electricity North West (ENW) network. Each outage has latitude/longitude coordinates, but there is no way to determine which UK ceremonial county (Cumberland, Northumberland, Westmorland and Furness, etc.) an outage belongs to. This prevents county-level analysis and filtering.

## Goal

Create an OpenClaw tool that can:
1. **Bulk-tag** all outages in `df_cleaned.csv` with their ceremonial county
2. **Single-point lookup** — given a lat/lon, return which county it falls in

## Approach

Use GeoPandas spatial join (`sjoin`) with bundled UK ceremonial county boundary GeoJSON data.

---

## Components

### 1. Boundary Data

**Source:** ONS Open Geography Portal — "Ceremonial Counties (GB) 2023"

**File:** `data/uk_ceremonial_counties.geojson`

**Download script:** `data/download_counties.py`
- Fetches from ONS API endpoint
- Saves as GeoJSON in WGS84 (EPSG:4326)
- Extracts county name field (`CTY23NM`)
- Run once during setup; bundled in repo after

### 2. Tool: `tools/tag_counties.py`

A CLI script following the existing tool pattern (argparse, JSON stdout, sys.path setup).

**CLI arguments:**

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--csv` | No | `data/df_cleaned.csv` | Path to outage CSV |
| `--geojson` | No | `data/uk_ceremonial_counties.geojson` | Path to county boundaries |
| `--output` | No | same as `--csv` (in-place) | Output CSV path |
| `--lat` | No | — | Latitude for single-point lookup |
| `--lon` | No | — | Longitude for single-point lookup |

**Processing flow (bulk mode):**

1. Load county GeoJSON into a `GeoDataFrame` (WGS84)
2. Load outage CSV into a `GeoDataFrame` using `latitude`/`longitude` columns
3. `geopandas.sjoin(outages_gdf, counties_gdf, predicate='within', how='left')`
4. Rename joined county column to `ceremonial_county`
5. Drop unnecessary join columns (`index_right`)
6. Save back to CSV

**Processing flow (single-point mode):**

1. Load county GeoJSON into a `GeoDataFrame`
2. Create a `shapely.geometry.Point(lon, lat)`
3. Use `county_gdf[county_gdf.contains(point)]` to find matching county
4. Return JSON with county name

**Output (bulk mode):**

```json
{
  "processed": 309000,
  "tagged": 308500,
  "untagged": 500,
  "output_path": "data/df_cleaned.csv",
  "counties_found": ["Cumberland", "Northumberland", "Westmorland and Furness", ...]
}
```

**Output (single-point mode):**

```json
{
  "lat": 54.89,
  "lon": -2.93,
  "ceremonial_county": "Cumberland",
  "found": true
}
```

**Error output:**

```json
{
  "error": "No county boundaries found at data/uk_ceremonial_counties.geojson",
  "type": "FileNotFoundError"
}
```

### 3. OpenClaw Tool Registration

Add to `openclaw-plugin/index.ts`:

```typescript
const tagCountiesParams = Type.Object({
  lat: Type.Optional(Type.Number({ description: "Latitude for single-point lookup" })),
  lon: Type.Optional(Type.Number({ description: "Longitude for single-point lookup" })),
  bulk: Type.Optional(Type.Boolean({ description: "Run bulk tagging on df_cleaned.csv", default: false })),
});

// In the plugin registration:
{
  name: "tag_counties",
  description: "Check which UK ceremonial county a lat/lon belongs to, or bulk-tag all outages with their county. Uses ONS ceremonial county boundaries.",
  parameters: tagCountiesParams,
  execute: async ({ lat, lon, bulk }) => {
    if (bulk) {
      // Run: python tools/tag_counties.py
    } else if (lat !== undefined && lon !== undefined) {
      // Run: python tools/tag_counties.py --lat {lat} --lon {lon}
    } else {
      // Return usage guidance
    }
  }
}
```

---

## Integration Points

### Dashboard (`enhanced_app.py`, `dashboard/sidebar.py`)

After bulk tagging, `df_cleaned.csv` gains a `ceremonial_county` column. Future enhancement:
- Add county filter dropdown to sidebar
- County-level aggregation charts
- County comparison views

### Existing Tools

- `query_outages.py` — could add `--county` filter parameter
- `summarize_district.py` — could include county context
- `check_new_incidents.py` — could tag live incidents with county

These are **out of scope** for the initial implementation but the `ceremonial_county` column enables them.

---

## Files

| File | Action | Description |
|------|--------|-------------|
| `data/download_counties.py` | Create | Download ONS ceremonial counties GeoJSON |
| `data/uk_ceremonial_counties.geojson` | Create | Bundled boundary data |
| `tools/tag_counties.py` | Create | New CLI tool for county lookup/tagging |
| `openclaw-plugin/index.ts` | Modify | Register `tag_counties` tool |

## Dependencies

All already in `requirements.txt`:
- `geopandas>=0.13.0`
- `shapely>=2.0.0`
- `pandas`

No new dependencies needed.

---

## Assumptions

1. ONS ceremonial county boundaries are stable enough to bundle as a static file
2. ~309k outages can be processed in memory (GeoPandas spatial join is efficient for this scale)
3. County names in the GeoJSON match standard UK ceremonial county names
4. Points that fall exactly on county boundaries may be assigned to either county (standard point-in-polygon behaviour)

## Out of Scope

- Dashboard UI changes (county filter, charts) — future enhancement
- Modifying existing tools to accept `--county` parameter — future enhancement
- Scottish/Welsh/Northern Irish administrative subdivisions (ceremonial counties cover GB)
- Incremental/cached bulk tagging — full re-process is fast enough
