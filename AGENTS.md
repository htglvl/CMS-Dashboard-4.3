# AGENTS.md — CMS Dashboard Workspace

## Project Overview

**CMS Dashboard** (Charge My Street Grid Resilience Dashboard) analyses unplanned power outages across the Electricity North West (ENW) network and maps them against EV charging sites to identify locations vulnerable to grid disruption and prioritise V2X upgrades.

**Tech Stack:** Python, Streamlit, GeoPandas, Shapely, Pandas, Folium, Plotly, scikit-learn, XGBoost, TypeScript (OpenClaw plugin)

## Architecture

```
User (WebChat) → OpenClaw Gateway (port 18789) → Plugin Tools → Python CLI Scripts → Data/Model
User (Browser) → nginx (port 8501) → Streamlit (port 8502) → Dashboard
```

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `tools/` | CLI tool scripts for OpenClaw (argparse, JSON stdout) |
| `openclaw-plugin/` | TypeScript plugin registering tools with OpenClaw |
| `data/` | CSV/GeoJSON data files and fetch scripts |
| `models/` | Trained ML models (Random Forest, XGBoost) |
| `advanced_charts/` | Risk model, recommendation engine, chart factories |
| `dashboard/` | Streamlit UI components (map, sidebar, metrics) |
| `tests/` | pytest test files |
| `wiki/` | Documentation markdown |
| `docs/` | Design specs and implementation plans |

## Tools Convention

All OpenClaw tools follow this pattern:

```python
"""Brief description.

Usage:
    python tools/tool_name.py --arg1 value1
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--arg", type=str, help="...")
    args = parser.parse_args()
    try:
        result = do_work(args)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}))
        sys.exit(1)

if __name__ == "__main__":
    main()
```

**Rules:**
- JSON output to stdout, progress/errors to stderr
- `sys.path.insert` at top for project imports
- `argparse` for CLI, `json.dumps` for output
- Try/except with JSON error output
- Register in `openclaw-plugin/index.ts` with TypeBox schema
- Add usage examples to the system prompt in `hooks.gateway_start`
- Write tests in `tests/test_<tool_name>.py` (subprocess-based, pytest)

## Data Files

| File | Content |
|------|---------|
| `data/df_cleaned.csv` | 309k+ outage records (lat/lon, district, duration, cause, year, season) |
| `data/all_charging_sites.csv` | 236 CMS chargepoints (lat/lon, category) |
| `data/uk_ceremonial_counties.geojson` | UK ceremonial county boundaries (91 features) |
| `data/borderlands_community_sites.csv` | Borderlands community sites |
| `data/flexibility_tenders.geojson` | Flexibility tender polygons |

**Key columns in df_cleaned.csv:** `latitude`, `longitude`, `district_name`, `duration-hours`, `customer_affected`, `direct_cause_category`, `year`, `season`, `incident_date_time`

**Key columns in all_charging_sites.csv:** `latitude`, `longitude`, `charge_point_location`, `site_category`

## Available OpenClaw Tools

| Tool | Purpose |
|------|---------|
| `geocode` | Place name → lat/lon (Nominatim) |
| `query_risk` | ML risk predictions for a location |
| `query_outages` | Historic outage records with filters |
| `query_charging_sites` | EV charging sites lookup |
| `get_recommendations` | V2X/chargepoint placement recommendations |
| `get_live_incidents` | Current ENW live incidents |
| `summarize_district` | Full district analysis |
| `get_wiki` | Dashboard documentation |
| `check_new_incidents` | New incidents since last check |
| `clean_borderlands` | Borderlands site cleaning/geocoding |
| `tag_counties` | UK ceremonial county lookup (single or bulk) |
| `count_outages_near_chargepoints` | Outages within 2-mile radius of CMS sites |
| `forecast_outages_by_season` | Seasonal outage forecasting |

## Testing

**Framework:** pytest
**Pattern:** Subprocess-based (call tools as CLI, parse JSON output)

```bash
# Run all tests
pytest tests/ -v

# Run specific tool tests
pytest tests/test_tag_counties.py -v
pytest tests/test_forecast_outages_by_season.py -v

# Run specific test class
pytest tests/test_tools.py::TestGeocodeTool -v
```

Tests skip gracefully when data files are missing or external services are unavailable.

## Anti-Hallucination Rules

When working with OpenClaw tools:
1. **Never make up data.** Every fact must come from a tool call.
2. **Report errors honestly.** If a tool fails, say so.
3. **Admit limitations.** "I don't have a tool for that" is better than guessing.
4. **Cite sources.** "According to query_outages..." not "There are approximately..."
5. **Present forecasts as estimates** with confidence ranges, not certainties.

## Common Workflows

### County-level analysis
```
1. tag_counties(bulk="data/df_cleaned.csv") → adds ceremonial_county column
2. Read tagged CSV, filter by county, aggregate
```

### Outage-chargepoint proximity
```
1. count_outages_near_chargepoints() → per-site outage counts
2. tag_counties(bulk="data/all_charging_sites.csv") → tag sites with counties
3. Filter by county, combine with forecast
```

### Seasonal forecasting
```
1. forecast_outages_by_season(include_duration=true, include_causes=true)
2. For specific county: forecast_outages_by_season(district="Carlisle")
```

## Red Lines

- Don't modify `df_cleaned.csv` without explicit approval
- Don't make external API calls without checking rate limits
- Don't commit data files (`.gitignore` excludes `data/*`)
- Before deleting anything, check what it contains first
- When in doubt, ask

## Related Docs

- `README.md` — Project overview
- `README_OPENCLAW.md` — OpenClaw integration guide
- `wiki/` — Dashboard documentation
- `docs/superpowers/specs/` — Design specs
- `docs/superpowers/plans/` — Implementation plans
