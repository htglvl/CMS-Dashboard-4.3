# Data Cleaning

The dashboard requires data in specific formats. This page explains how to clean raw CSV exports.

---

## Quick Start

```bash
# Activate virtual environment
venv\Scripts\activate

# Run cleaning dashboard
streamlit run charge_point_cleaning/data_cleaning_dashboard.py --server.port 8502
```

Or double-click `run_cleaning_dashboard.bat`.

---

## What the Cleaning Utility Does

The Streamlit app (`charge_point_cleaning/data_cleaning_dashboard.py`) provides an interactive interface for:

1. Uploading a raw CSV export
2. Selecting the dataset type (chargepoints or outages)
3. Cleaning and downloading the result

It calls functions from `charge_point_cleaning/clean_datasets.py`, which can also be used from the command line.

---

## Chargepoints Cleaning

**Input:** Raw charging site export from CMS
**Output:** `all_charging_sites.csv`

### Fields produced:
| Column | Description |
|---|---|
| `charge_point_location` | Human-readable site name |
| `site_category` | One of: V2X Chargepoint, Building-supplied Charger, Other Chargepoint |
| `latitude` | WGS84 latitude |
| `longitude` | WGS84 longitude |

### Classification logic:
1. If `vx_flag = 1` and status is `open` or `cwys` → **V2X Chargepoint**
2. Else if site name is in the building-sites list → **Building-supplied Charger**
3. Else if status is `open` and not V2X → **Other Chargepoint**
4. Otherwise → excluded

### Command line:
```bash
python charge_point_cleaning/clean_datasets.py --input raw_sites.csv --type chargepoints --output all_charging_sites.csv
```

---

## Outages Cleaning

**Input:** Raw unplanned outages export from ENW
**Output:** `df_cleaned.csv` or `df_cleaned.parquet`

### Fields produced:
| Column | Description |
|---|---|
| `latitude` | WGS84 latitude (parsed from geometry if needed) |
| `longitude` | WGS84 longitude |
| `duration-hours` | Outage duration in hours |
| `Total Customer Minutes Lost` | Customer impact metric |
| `year` | Year of incident |
| `month_name` | Month name (e.g. "January") |
| `hour` | Hour of day (0-23) |
| `season` | Season (Winter/Spring/Summer/Autumn) |
| `duration_category` | Duration bucket (< 3h, 3-6h, 6-12h, > 12h) |
| `Incident Date-time` | Original timestamp (for dashboard compatibility) |

### Command line:
```bash
python charge_point_cleaning/clean_datasets.py --input raw_outages.csv --type outages --output df_cleaned.parquet
```

---

## Using the Fetcher Instead

If you have an ENW API key, you can skip manual cleaning and use the automated fetcher:

```bash
python data/fetch_outages.py
```

This downloads records directly from the ENW API, derives all dashboard-ready fields, and saves to `df_cleaned.csv`. See [API Reference](API-Reference.md) for details.

---

## Replacing Data Files

After cleaning:
1. Place the cleaned file in the project root
2. Restart the dashboard if it was already running
3. Select the new file from the sidebar dropdown
