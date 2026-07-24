# TOOLS.md - Local Notes

Environment-specific details for the CMS Dashboard project.

## Python Environment

- **Venv:** `venv/Scripts/python.exe` (Windows)
- **System Python:** `python` (Miniconda)
- **Run tools:** `python tools/<tool_name>.py --args`

## Servers

| Service | Port | URL |
|---------|------|-----|
| Streamlit Dashboard | 8502 | `http://localhost:8502` |
| OpenClaw Gateway | 18789 | `http://localhost:18789` |
| Nginx Proxy | 8501 | `http://localhost:8501/home/` (dashboard), `/oclaw/` (OpenClaw) |
| OpenClaw Proxy | 8503 | `http://localhost:8503` |

## Data Files

| File | Size | Notes |
|------|------|-------|
| `data/df_cleaned.csv` | ~309k rows | Outage records, columns: latitude, longitude, district_name, duration-hours, year, season, direct_cause_category |
| `data/all_charging_sites.csv` | 236 rows | CMS chargepoints, columns: charge_point_location, site_category, latitude, longitude |
| `data/uk_ceremonial_counties.geojson` | ~117MB | 91 UK ceremonial counties, field: NAME |
| `data/borderlands_community_sites.csv` | Variable | Borderlands community sites |
| `data/flexibility_tenders.geojson` | Variable | Flexibility tender polygons |

## API Endpoints

| API | URL | Key |
|-----|-----|-----|
| ENW Outages | `https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/catalog/datasets/unplanned-outages/exports/csv` | `ENW_API_KEY` |
| ENW Live Incidents | `https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/catalog/datasets/live_incidents/exports/json` | `ENW_API_KEY` |
| Nominatim Geocoding | `https://nominatim.openstreetmap.org/search` | No key (rate limited) |
| OS BoundaryLine | `https://services.arcgis.com/qHLhLQrcvEnxjtPr/arcgis/rest/services/OS_Boundaryline/FeatureServer/12/query` | No key |

## Common Commands

```bash
# Run dashboard
python enhanced_app.py

# Fetch latest outages
python data/fetch_outages.py

# Run a single tool
python tools/query_outages.py --district Lancaster --year 2025
python tools/count_outages_near_chargepoints.py --top 10
python tools/forecast_outages_by_season.py --season Winter

# Run all tests
pytest tests/ -v

# Run specific tool tests
pytest tests/test_tag_counties.py -v
pytest tests/test_forecast_outages_by_season.py -v
pytest tests/test_count_outages_near_chargepoints.py -v

# Rebuild OpenClaw plugin
cd openclaw-plugin && npm run build

# Download county boundaries (run once)
python data/download_counties.py
```

## Environment Variables (.env)

- `ENW_API_KEY` — Electricity North West API key
- `XIAOMI_API_KEY` — Xiaomi LLM API key (optional)
- `OPENAI_API_KEY` — OpenAI API key (optional)
- `ANTHROPIC_API_KEY` — Anthropic API key (optional)

## County Names (OS BoundaryLine)

The ceremonial county names from the downloaded GeoJSON:
- Cumbria (covers Cumberland + Westmorland and Furness area)
- Lancashire
- Northumberland
- Tyne & Wear (covers Newcastle area)
- Greater Manchester
- Merseyside
- etc.

**Note:** These are traditional ceremonial county names, not 2023 local authority names.

## OpenClaw Tool Registration

To add a new tool:
1. Create `tools/<tool_name>.py` (argparse + JSON stdout)
2. Add tool definition in `openclaw-plugin/index.ts` (TypeBox schema + execute function)
3. Add usage examples to the system prompt in `hooks.gateway_start`
4. Write tests in `tests/test_<tool_name>.py`
5. `cd openclaw-plugin && npm run build`

---

Add whatever helps you do your job. This is your cheat sheet.
