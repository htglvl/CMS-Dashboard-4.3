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
- **OpenClaw integration** — AI-powered chat interface for querying dashboard data

---

## Quick Start

### First Time Setup

1. **Double-click `setup.bat`** — This will:
   - Create a Python virtual environment
   - Install all dependencies
   - Prompt for API keys
   - Fetch initial data
   - Train the ML model
   - Build OpenClaw plugin
   - **Auto-configure OpenClaw** (gateway, auth, plugin paths)
   - Download nginx (for proxy)

2. **Edit `.env`** with your API keys:
   ```
   ENW_API_KEY=your_api_key_here
   XIAOMI_API_KEY=your_api_key_here
   ```

3. **Run the dashboard:**
   ```bash
   run_dashboard.bat
   ```

### OpenClaw (Optional)

If you want AI chat integration:

1. Install OpenClaw: `npm install -g openclaw@latest`
2. Run `setup.bat` — it will auto-configure everything
3. Start with `run_dashboard.bat`
4. Open **http://127.0.0.1:18789/** for WebChat

See [README_OPENCLAW.md](README_OPENCLAW.md) for details.

### Manual Setup (Developers)

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API keys
copy .env.example .env
# Edit .env with your keys

# 4. Fetch data and train model
python data/fetch_outages.py
python advanced_charts/risk_model.py

# 5. Launch dashboard
streamlit run enhanced_app.py
```

---

## Project Structure

```
CMS Dashboard 4.3/
│
├── enhanced_app.py              # Main entry point
├── setup.bat                    # First-time setup script
├── run_dashboard.bat            # Launch dashboard
├── run_cleaning_dashboard.bat   # Launch chargepoint cleaning utility
├── requirements.txt             # Python dependencies
├── .env.example                 # API key template (copy to .env)
├── .gitignore                   # Git ignore rules
│
├── advanced_charts/             # LOGIC: analysis + ML + recommendations
│   ├── data.py                  # SiteData (Haversine, risk scoring)
│   ├── charts.py                # Plotly chart factories
│   ├── cache_utils.py           # Caching utilities
│   ├── recommendations.py       # AIRecommendationEngine (rule-based)
│   ├── risk_model.py            # ML model (Random Forest + XGBoost)
│   └── recommendation_engine.py # Business recommendations + NL interface
│
├── dashboard/                   # UI: Streamlit rendering
│   ├── app_logic.py             # Data loading, risk computation
│   ├── chart_display.py         # Tab orchestrator
│   ├── click_processor.py       # Map click event handling
│   ├── floating_chat.py         # Floating AI chat interface
│   ├── charts/                  # One file per analysis tab
│   ├── map.py, sidebar.py, metrics.py, live_incidents.py, theme.py
│
├── data/                        # DATA: fetching + storage
│   ├── fetch_outages.py         # Historic outage fetcher
│   ├── fetch_live_incidents.py  # Live incidents fetcher
│   ├── fetch_flexibility_tenders.py  # Flexibility tender fetcher
│   ├── df_cleaned.csv           # Cleaned outage data
│   ├── all_charging_sites.csv   # Cleaned charging site data
│   └── flexibility_tenders.geojson   # Flexibility tender locations
│
├── charge_point_cleaning/       # Standalone cleaning utility
│
├── tools/                       # CLI tools for OpenClaw integration
│   └── README.md                # Tool documentation
│
├── openclaw-plugin/             # OpenClaw AI chat integration
│   ├── index.ts                 # Plugin entry point
│   ├── skills/                  # AI workflow skills
│   └── package.json             # Node.js dependencies
│
├── models/                      # Trained ML models (auto-generated)
├── logs/                        # Fetch logs (not tracked by git)
└── wiki/                        # Full documentation
```

---

## Documentation

| Document | Contents |
|---|---|
| [README_OPENCLAW.md](README_OPENCLAW.md) | OpenClaw AI chat setup and usage |
| [wiki/Home.md](wiki/Home.md) | Overview, tech stack, project structure |
| [wiki/Dashboard-Guide.md](wiki/Dashboard-Guide.md) | Filters, map interaction, analysis tabs |
| [wiki/Data-Cleaning.md](wiki/Data-Cleaning.md) | How to clean raw chargepoint exports |
| [wiki/API-Reference.md](wiki/API-Reference.md) | Outage fetcher and live incidents setup |
| [wiki/Risk-Assessment.md](wiki/Risk-Assessment.md) | Vulnerability scoring and ML predictions |
| [wiki/Spatial-Analysis.md](wiki/Spatial-Analysis.md) | Haversine distances, buffer zones |
| [tools/README.md](tools/README.md) | CLI tools for OpenClaw integration |

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
| AI integration | OpenClaw (Node.js) |
| Environment | Python 3.12+ |
