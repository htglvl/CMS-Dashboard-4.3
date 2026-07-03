# CMS Grid Resilience Dashboard — Wiki

Welcome to the documentation for the **Charge My Street (CMS) Grid Resilience Dashboard**.

This project analyses unplanned power outages across the Electricity North West (ENW) network and maps them against EV charging sites to identify locations most vulnerable to grid disruption. The goal is to prioritise **V2X (Vehicle-to-Everything)** upgrades where they will have the greatest impact.

---

## Quick Links

| Topic | Description |
|---|---|
| [Dashboard Guide](Dashboard-Guide.md) | How to launch, configure, and interpret the dashboard |
| [Data Cleaning](Data-Cleaning.md) | How to clean raw CSV exports for use with the dashboard |
| [API Reference](API-Reference.md) | How the daily ENW outage fetcher and live incidents work |
| [Risk Assessment](Risk-Assessment.md) | How vulnerability scores, radar charts, and ML predictions work |
| [Spatial Analysis](Spatial-Analysis.md) | How buffer zones and Haversine distances work |

---

## Project Structure

```
CMS Dashboard 4.3/
│
├── enhanced_app.py              # Main entry point (slim orchestrator)
├── setup.bat                    # First-time setup script
├── run_dashboard.bat            # Launch dashboard
├── run_cleaning_dashboard.bat   # Launch chargepoint cleaning utility
├── requirements.txt             # Python dependencies
├── .env.example                 # API key template (copy to .env)
├── .gitignore                   # Git ignore rules
│
├── advanced_charts/             # LOGIC: analysis + ML + recommendations
│   ├── __init__.py              # DynamicChartGenerator wrapper
│   ├── data.py                  # SiteData (Haversine, risk scoring)
│   ├── charts.py                # Plotly chart factories
│   ├── cache_utils.py           # Caching utilities for performance
│   ├── recommendations.py       # AIRecommendationEngine (rule-based)
│   ├── risk_model.py            # ML model (Random Forest + XGBoost)
│   └── recommendation_engine.py # Business recommendations + NL interface
│
├── dashboard/                   # UI: Streamlit rendering
│   ├── __init__.py
│   ├── app_logic.py             # Data loading, risk computation, caching
│   ├── chart_display.py         # Tab orchestrator
│   ├── click_processor.py       # Map click event handling
│   ├── floating_chat.py         # Floating AI chat interface
│   ├── charts/                  # One file per analysis tab
│   │   ├── __init__.py
│   │   ├── site_summary.py      # Basic site info metrics row
│   │   ├── frequency_timeline.py# Tab 1: outage frequency over time
│   │   ├── customer_impact.py   # Tab 2: pie charts by duration
│   │   ├── risk_assessment.py   # Tab 3: radar chart + vulnerability score
│   │   ├── rule_insights.py     # Tab 4: rule-based risk classification
│   │   └── risk_prediction.py   # Tab 5: ML risk prediction
│   ├── map.py                   # Folium map creation
│   ├── sidebar.py               # Sidebar filters, controls, auto-refresh
│   ├── metrics.py               # Right panel metrics + AI recommendations
│   ├── live_incidents.py        # Live incidents panel
│   └── theme.py                 # Dark mode detection
│
├── data/                        # DATA: fetching + storage
│   ├── fetch_outages.py         # Historic outage fetcher (ENW API)
│   ├── fetch_live_incidents.py  # Live incidents fetcher (ENW API)
│   ├── fetch_flexibility_tenders.py  # Flexibility tender fetcher
│   ├── df_cleaned.csv           # Cleaned outage data
│   ├── all_charging_sites.csv   # Cleaned charging site data
│   ├── flexibility_tenders.geojson  # Flexibility tender locations
│   └── .last_fetch_outages      # Fetch state file
│
├── charge_point_cleaning/       # Standalone cleaning utility
│   ├── clean_datasets.py        # Core cleaning function
│   ├── clean_chargepoint_dts_dashboard_logic.py  # Orchestration logic
│   └── data_cleaning_dashboard.py                # Streamlit UI
│
├── tools/                       # CLI tools for OpenClaw integration
│   ├── README.md                # Tool documentation
│   ├── geocode.py               # Place name to coordinates
│   ├── query_risk.py            # Risk predictions
│   ├── query_outages.py         # Historic outage queries
│   └── ...                      # See tools/README.md for full list
│
├── openclaw-plugin/             # OpenClaw AI chat integration
│   ├── index.ts                 # Plugin entry point
│   ├── skills/                  # AI workflow skills
│   └── package.json             # Node.js dependencies
│
├── models/                      # Trained ML models (.pkl, auto-generated)
├── logs/                        # Fetch logs (not tracked by git)
└── wiki/                        # This documentation
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Web framework | Streamlit |
| Interactive maps | Folium + streamlit-folium |
| Charts | Plotly (line, pie, radar, bar) |
| Data processing | Pandas, NumPy |
| Spatial operations | Haversine (vectorised NumPy) |
| ML models | scikit-learn (Random Forest), XGBoost |
| Model persistence | joblib |
| File formats | CSV, Parquet (PyArrow) |
| API client | Requests |
| AI integration | OpenClaw (Node.js) |
| Environment | Python 3.12+ |

---

## Getting Started

### Quick Setup (End Users)

1. **Double-click `setup.bat`** — handles everything automatically
2. **Edit `.env`** with your API keys when prompted
3. **Run `run_dashboard.bat`** to start

### Manual Setup (Developers)

1. **Set up the environment:**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure your API key** (for data fetching and live incidents):
   ```bash
   copy .env.example .env
   # Edit .env with your keys
   ```

3. **Launch the dashboard:**
   ```bash
   streamlit run enhanced_app.py
   ```
   Or double-click `run_dashboard.bat`.

4. **Fetch latest outage data** (optional — dashboard auto-fetches):
   ```bash
   python data/fetch_outages.py
   ```

5. **Train the risk model** (first time only):
   ```bash
   python advanced_charts/risk_model.py
   ```
   This creates `models/` with trained classifiers and grid cell predictions.
