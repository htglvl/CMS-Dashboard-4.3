# CMS Grid Resilience Dashboard 4.3

An interactive dashboard for analysing unplanned power outages across the Electricity North West (ENW) network and mapping them against EV charging sites. The goal is to identify locations most vulnerable to grid disruption and prioritise **V2X (Vehicle-to-Everything)** upgrades.

---

## Features

- **Interactive map** with colour-coded charging sites, 2-mile buffer zones, outage heatmap, and risk heatmap
- **Live incidents** — real-time power cut monitoring from the ENW API
- **Statistical filtering** — IQR outlier removal, significance thresholds
- **Per-site analysis** — frequency timelines, customer impact, risk radar charts
- **ML risk prediction** — Random Forest and XGBoost models predicting outage risk per grid cell
- **Business recommendations** — charging station placement, grid resilience priorities, community impact
- **Natural language interface** — ask questions about risk, charger placement, and investment priorities
- **Automated data fetching** — daily pull of outage records from the ENW API

---

## Quick Start

### 1. Set up the environment

```bash
pip install -r requirements.txt
```

### 2. Configure your API key

Create a `.env` file in the project root:

```
ENW_API_KEY=your_api_key_here
```

### 3. Launch the dashboard

```bash
streamlit run enhanced_app.py
```

Or double-click `run_dashboard.bat`.

### 4. Train the risk model (first time only)

```bash
python advanced_charts/risk_model.py
```

---

## Project Structure

```
CMS Dashboard 4.3/
│
├── enhanced_app.py              # Main entry point
├── run_dashboard.bat            # Launch dashboard
├── run_cleaning_dashboard.bat   # Launch chargepoint cleaning utility
├── requirements.txt             # Python dependencies
├── .env                         # API key (not tracked by git)
│
├── advanced_charts/             # LOGIC: analysis + ML + recommendations
│   ├── data.py                  # SiteData (Haversine, risk scoring)
│   ├── charts.py                # Plotly chart factories
│   ├── recommendations.py       # AIRecommendationEngine (rule-based)
│   ├── risk_model.py            # ML model (Random Forest + XGBoost)
│   └── recommendation_engine.py # Business recommendations + NL interface
│
├── dashboard/                   # UI: Streamlit rendering
│   ├── app_logic.py             # Data loading, risk computation
│   ├── chart_display.py         # Tab orchestrator
│   ├── charts/                  # One file per analysis tab
│   ├── map.py, sidebar.py, metrics.py, live_incidents.py, theme.py
│
├── data/                        # DATA: fetching + storage
│   ├── fetch_outages.py         # Historic outage fetcher
│   ├── fetch_live_incidents.py  # Live incidents fetcher
│   ├── df_cleaned.csv           # Cleaned outage data
│   └── all_charging_sites.csv   # Cleaned charging site data
│
├── charge_point_cleaning/       # Standalone cleaning utility
├── models/                      # Trained ML models (auto-generated)
├── logs/                        # Fetch logs
└── wiki/                        # Full documentation
```

---

## Documentation

Full documentation is in the [`wiki/`](wiki/) folder:

| Page | Contents |
|---|---|
| [Home](wiki/Home.md) | Overview, tech stack, project structure |
| [Dashboard Guide](wiki/Dashboard-Guide.md) | Filters, map interaction, analysis tabs |
| [Data Cleaning](wiki/Data-Cleaning.md) | How to clean raw chargepoint exports |
| [API Reference](wiki/API-Reference.md) | Outage fetcher and live incidents setup |
| [Risk Assessment](wiki/Risk-Assessment.md) | Vulnerability scoring and ML predictions |
| [Spatial Analysis](wiki/Spatial-Analysis.md) | Haversine distances, buffer zones |

---

## Tech Stack

| Component | Technology |
|---|---|
| Web framework | Streamlit |
| Interactive maps | Folium + streamlit-folium |
| Charts | Plotly (line, pie, radar, bar) |
| Data processing | Pandas, NumPy |
| ML models | scikit-learn, XGBoost |
| API client | Requests |
| Environment | Python 3.12+ |
