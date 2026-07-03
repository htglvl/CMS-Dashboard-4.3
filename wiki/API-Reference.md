# API Reference — Daily Outage Fetcher

The `data/fetch_outages.py` script automatically downloads unplanned outage records from Electricity North West's OpenDataSoft API.

---

## Auto-Fetch on Dashboard Launch

When you run `streamlit run enhanced_app.py`, the dashboard automatically checks if a fetch is needed (once per day, after 20+ hours since the last run). If so, it:

1. Shows a spinner: *"Fetching latest outage data from ENW (once daily)..."*
2. Runs an incremental fetch (only new records since the last fetch)
3. Reloads the dataset from disk (cache invalidates on file change)

This means **no manual intervention is needed** — just launch the dashboard and it stays up to date.

The state file `.last_fetch_outages` tracks when the last fetch occurred. Delete it to force a full re-download on next launch.

---

## Dataset

| Property | Value |
|---|---|
| Dataset ID | `unplanned-outages` |
| Title | SP ENW - Operational Data - Historic Unplanned Outages |
| Records | ~309,000 (dating back to 2000) |
| Update frequency | Daily |
| API base URL | `https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/` |

---

## Setup

### 1. Get an API Key

Register at [Electricity North West Open Data](https://electricitynorthwest.opendatasoft.com/) to obtain an API key.

### 2. Configure

Create a `.env` file in the project root:

```
ENW_API_KEY=your_api_key_here
```

### 3. Install dependencies

```bash
conda activate cms
pip install requests python-dotenv
```

---

## Usage

### Incremental fetch (default)
```bash
python data/fetch_outages.py
```
Downloads only records newer than the last successful fetch. The timestamp is stored in `.last_fetch_outages`.

### Full re-download
```bash
python data/fetch_outages.py --full
```
Downloads all ~309,000 records. Use this for the initial setup.

### Fetch since a specific date
```bash
python data/fetch_outages.py --since 2024-01-01
```

### Custom output file
```bash
python data/fetch_outages.py --output df_cleaned.parquet
```

---

## How It Works

1. **Reads the API key** from `.env` (or environment variable `ENW_API_KEY`)
2. **Queries the API** for records matching the date filter
3. **Paginates** through results (100 records per page, API maximum)
4. **Flattens** the `geometry` field into `latitude`/`longitude` columns
5. **Derives dashboard fields**: `duration-hours`, `duration_category`, `year`, `month_name`, `hour`, `season`, `is_exceptional_event`
6. **Deduplicates** against existing data using `incident_reference_number`
7. **Saves** to CSV or Parquet
8. **Updates** the state file with the latest record timestamp

---

## API Fields Retrieved

| Field | Type | Description |
|---|---|---|
| `incident_date_time` | datetime | When the outage started |
| `restoration_date_time` | datetime | When power was restored |
| `incident_duration` | int | Duration in minutes |
| `customer_affected` | int | Number of customers affected |
| `total_customer_minutes_lost` | int | Total customer-minutes lost |
| `direct_cause_category` | text | e.g. "Companies", "Third Party", "Weather" |
| `direct_cause` | text | Specific cause description |
| `network_type` | text | LV, HV, etc. |
| `voltage` | text | Voltage level |
| `district_code` | int | District identifier |
| `district_name` | text | e.g. "Kendal", "Preston" |
| `primary_substation` | text | Substation identifier |
| `incident_reference_number` | text | Unique reference |
| `main_equipment_involved_1` - `_6` | text | Equipment involved |
| `exceptional_event_id` | text | Non-null if part of a major event |
| `local_authority` | text | Local authority area |
| `geometry` | geo_point_2d | Lat/lon of incident location |

---

## Scheduling

### Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task → "Daily Outage Fetch"
3. Trigger: Daily at a quiet time (e.g. 06:00)
4. Action: Start a program
   - Program: `<project_root>\run_daily_fetch.bat`
   - Start in: `<project_root>\`

Replace `<project_root>` with the actual path where you installed the CMS Dashboard.

### Manual run
Double-click `run_daily_fetch.bat` or run:
```bash
conda activate cms
python data/fetch_outages.py
```

---

## Live Incidents

The `fetch_live_incidents()` function fetches **current active power cuts** from a separate ENW dataset.

### Dataset

| Property | Value |
|---|---|
| Dataset ID | `live_incidents` |
| Title | SP ENW - Operational Data - Live Incidents |
| API endpoint | `https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/catalog/datasets/live_incidents/exports/json` |
| Authentication | Requires `ENW_API_KEY` (same as historic outages) |

### Fields Retrieved

| Field | Type | Description |
|---|---|---|
| `incident_num` | text | Incident reference (e.g. "INC 125344361") |
| `incident_type` | text | e.g. "Underground Main", "High Voltage Fault" |
| `outage_time` | datetime | When the outage started |
| `customers_affected` | int | Number of customers affected |
| `customers_off_supply` | int | Currently without power |
| `incident_status` | text | e.g. "Dispatched", "Restored" |
| `estimated_restoration_time` | datetime | Estimated time power will be restored |
| `geo_point_2d` | lat/lon | Incident location |

### Dashboard Integration

- **Map**: Red pulsing circle markers with popup details
- **Right panel**: Status indicator (green = no incidents, red = active) with expandable incident cards
- **Auto-refresh**: Configurable interval (15 min / 30 min / 1 hour / 2 hours / Disabled)
- **Layer control**: "Live Incidents" layer can be toggled on/off on the map

### Usage

```python
from data.fetch_live_incidents import fetch_live_incidents

df = fetch_live_incidents()
# Returns DataFrame with active incidents, or empty DataFrame if none
```

---

## Flexibility Tenders

The `fetch_flexibility_tenders.py` script downloads flexibility tender data from the ENW API.

### Dataset

| Property | Value |
|---|---|
| Dataset ID | `flexibility-tenders` |
| Title | SP ENW - Flexibility Tender Opportunities |
| Output | `flexibility_tenders.geojson` |
| State file | `.last_fetch_flexibility` |

### Usage

```bash
python data/fetch_flexibility_tenders.py
```

### Dashboard Integration

Flexibility tender locations are displayed on the dashboard map as a separate layer, showing areas where grid flexibility services are being procured.

---

## Logs

Logs are written to `logs/fetch_outages.log` and also printed to the console. The log includes:
- Timestamp of each run
- Number of records fetched
- Any API errors or retries
- Deduplication statistics

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `ENW_API_KEY not found` | Check `.env` file exists and contains the key |
| `ForbiddenAccess` error | API key is invalid or expired |
| `Timeout` error | Check internet connection; the script retries once automatically |
| No new records | Normal if the fetcher ran recently; check `.last_fetch_outages` |
| Parquet write fails | Script falls back to CSV automatically |
