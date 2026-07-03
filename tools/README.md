# CMS Dashboard Tools

CLI tools for querying the CMS Grid Resilience Dashboard data, risk models, and documentation.

These tools are used by the OpenClaw plugin to provide AI-powered analysis of power grid data in North West England.

## Available Tools

| Tool | Description | Usage |
|------|-------------|-------|
| `geocode.py` | Convert place names to lat/lon coordinates | `python tools/geocode.py --query "Lancaster"` |
| `query_risk.py` | ML risk predictions by location or district | `python tools/query_risk.py --lat 54.05 --lon -2.80` |
| `query_outages.py` | Historic outage records (309k+) | `python tools/query_outages.py --district Lancaster` |
| `get_live_incidents.py` | Current active power incidents | `python tools/get_live_incidents.py` |
| `get_recommendations.py` | V2X/chargepoint placement recommendations | `python tools/get_recommendations.py --type all` |
| `query_charging_sites.py` | EV charging site lookups | `python tools/query_charging_sites.py --category V2X` |
| `get_wiki.py` | Dashboard documentation | `python tools/get_wiki.py --topic risk` |
| `summarize_district.py` | Full district analysis | `python tools/summarize_district.py --district Lancaster` |
| `check_new_incidents.py` | New incident detection with risk context | `python tools/check_new_incidents.py` |

## Prerequisites

- Python 3.12+
- Dependencies installed: `pip install -r requirements.txt`
- `.env` file with `ENW_API_KEY` (for data fetching tools)
- Trained ML models in `models/` (run `python advanced_charts/risk_model.py` first)

## Example Usage

```bash
# Get coordinates for a place
python tools/geocode.py --query "Lancaster"

# Query risk at coordinates
python tools/query_risk.py --lat 54.0466 --lon -2.7983 --top 5

# Find charging sites near a location
python tools/query_charging_sites.py --near-lat 54.0466 --near-lon -2.7983 --radius 10

# Get outage history for a district
python tools/query_outages.py --district Lancaster --top 10

# Search wiki documentation
python tools/get_wiki.py --search V2X

# List all wiki topics
python tools/get_wiki.py --list
```

## Output Format

All tools output JSON to stdout for easy parsing by OpenClaw or other automation.

## Integration with OpenClaw

These tools are registered in the OpenClaw plugin (`openclaw-plugin/`). The plugin automatically discovers and exposes them as AI-callable functions.

See `README_OPENCLAW.md` in the project root for setup instructions.
