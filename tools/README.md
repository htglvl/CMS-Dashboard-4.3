# CMS Dashboard Tools

CLI tools for querying the CMS Grid Resilience Dashboard data, risk models, and documentation.

These tools are used by the OpenClaw plugin to provide AI-powered analysis of power grid data in North West England. They can also be used standalone from the command line.

## Available Tools

| # | Tool | Description | Usage |
|---|------|-------------|-------|
| 1 | `geocode.py` | Convert UK place names to lat/lon coordinates (Nominatim) | `--query "Lancaster" [--limit 3]` |
| 2 | `query_risk.py` | ML risk predictions by location or district | `--lat 54.05 --lon -2.80` or `--district Lancaster [--top 10]` |
| 3 | `query_outages.py` | Historic outage records with filters | `--district Lancaster` or `--lat 54.05 --lon -2.80 [--radius 15] [--year 2024] [--cause Weather] [--min-duration 6] [--sort duration\|customers\|date] [--top 10]` |
| 4 | `query_charging_sites.py` | EV charging site lookups by category or proximity | `--category V2X` or `--near-lat 54.05 --near-lon -2.80 [--radius 5] [--top 10]` |
| 5 | `get_recommendations.py` | V2X/chargepoint placement recommendations | `--type v2x\|chargepoint\|all` |
| 6 | `get_live_incidents.py` | Current ENW live power incidents | *(no arguments)* |
| 7 | `summarize_district.py` | Full district analysis (risk + outages + charging sites) | `--district Lancaster` |
| 8 | `get_wiki.py` | Dashboard documentation lookup | `--topic risk` or `--search V2X` or `--list` |
| 9 | `check_new_incidents.py` | New incidents since last check, with risk context | *(no arguments)* |
| 10 | `clean_borderlands.py` | Borderlands site cleaning, geocoding, and cross-reference | `[--top 10] [--local-authority Cumberland] [--cross-ref] [--radius 10]` |
| 11 | `count_outages_near_chargepoints.py` | Outages within radius of each CMS chargepoint | `[--radius 3.2] [--category V2X] [--top 10]` |
| 12 | `forecast_outages_by_season.py` | Seasonal outage forecasting from historical data | `[--season Winter] [--year 2027] [--district Lancaster] [--cause Weather] [--include-duration] [--include-causes]` |
| 13 | `tag_counties.py` | UK ceremonial county lookup (single point or bulk CSV) | `--lat 54.89 --lon -2.93` or `--bulk data/df_cleaned.csv [--output data/tagged.csv]` |

## Quick Scripts

These are ad-hoc analysis scripts (no argparse, no JSON output). Not registered with OpenClaw.

| Script | Purpose |
|--------|---------|
| `query_castle_carrock.py` | Nearest grid cells and outages to Castle Carrock |
| `query_longridge.py` | Nearest grid cells and outages to Longridge |
| `query_longridge_chargers.py` | Nearest chargepoints to Longridge |
| `recommendation_sites.py` | High-risk cells summary with nearby charging sites |

## Prerequisites

- Python 3.12+
- Dependencies installed: `pip install -r requirements.txt`
- `.env` file with `ENW_API_KEY` (for `get_live_incidents.py` and `check_new_incidents.py`)
- Trained ML models in `models/` (run `python advanced_charts/risk_model.py` if missing)

## Example Usage

```bash
# Get coordinates for a place
python tools/geocode.py --query "Lancaster"

# Query risk at coordinates
python tools/query_risk.py --lat 54.0466 --lon -2.7983 --top 5

# Query risk by district
python tools/query_risk.py --district Lancaster

# Find charging sites near a location
python tools/query_charging_sites.py --near-lat 54.0466 --near-lon -2.7983 --radius 10

# Filter charging sites by category
python tools/query_charging_sites.py --category V2X

# Get outage history for a district
python tools/query_outages.py --district Lancaster --top 10

# Get recent outages near coordinates
python tools/query_outages.py --lat 54.05 --lon -2.80 --radius 15 --year 2024

# Search wiki documentation
python tools/get_wiki.py --search V2X

# List all wiki topics
python tools/get_wiki.py --list

# Get V2X placement recommendations
python tools/get_recommendations.py --type v2x

# Clean and cross-reference Borderlands sites
python tools/clean_borderlands.py --local-authority Cumberland --cross-ref

# Count outages near chargepoints (2-mile radius)
python tools/count_outages_near_chargepoints.py --category V2X --top 10

# Forecast winter outages with causes
python tools/forecast_outages_by_season.py --season Winter --include-causes

# Bulk-tag outage records with ceremonial counties
python tools/tag_counties.py --bulk data/df_cleaned.csv
```

## Output Format

All tools output JSON to stdout for easy parsing by OpenClaw or other automation. Errors are also returned as JSON:

```json
{
  "error": "Description of what went wrong",
  "type": "ExceptionClassName"
}
```

Exit codes: `0` for success, `1` for error.

## Integration with OpenClaw

These tools are registered in the OpenClaw plugin (`openclaw-plugin/index.ts`). The plugin automatically discovers and exposes them as AI-callable functions.

See `README_OPENCLAW.md` in the project root for setup instructions.
