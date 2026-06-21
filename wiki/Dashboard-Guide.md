# Dashboard Guide

This guide explains how to launch, configure, and interpret the CMS Grid Resilience Dashboard.

---

## Launching

```bash
streamlit run enhanced_app.py
```

Or double-click `run_dashboard.bat`. The first launch may take a moment while packages load.

---

## Choosing Data Sources

After launch, use the sidebar to select your datasets:

| Dataset | Default File | Description |
|---|---|---|
| Outages | `df_cleaned.csv` or `df_cleaned.parquet` | Historic unplanned outage records |
| Chargepoints | `all_charging_sites.csv` | EV charging site locations |

The dashboard scans the current directory for compatible files and lists them in dropdown menus.

---

## Sidebar Controls

### General Filters

- **Year Filter** — Select one or more years to analyse.
- **Daytime Only (9 AM-9PM)** — Exclude outages that occurred outside daytime hours.
- **Exclude Exceptional Events** — Remove unusually long or large outages caused by major incidents (e.g. storms).

### Chargepoint Categories

Toggle visibility of:
- V2X Chargepoint
- Building-supplied Charger
- Other Chargepoint

### Statistical Filters

#### IQR Multiplier
- Range: `0-4`
- Controls how aggressively outlier outages are removed.
- Higher values retain more data; lower values remove more extreme durations.
- Default: `1.5`

#### Significance Threshold (Quantile)
- Range: `0-1`
- Filters for high-impact outages based on customer-minutes-lost per minute of outage.
- Higher values keep only the most impactful events.
- Default: `0.5` (median)

### Map View

| Toggle | Default | Description |
|--------|---------|-------------|
| Show chargepoint markers | On | Site markers with popups |
| Show 2-mile buffer zones | On | Dashed circles around each site |
| Show outage heatmap | On | Heatmap weighted by outage duration |
| Show risk heatmap on map | On | ML-predicted risk cells (red/amber/green) |

### Auto-Refresh

| Setting | Options | Default |
|---------|---------|---------|
| Data refresh interval | 30 seconds, Hourly, Daily, Weekly, Monthly | Hourly |
| Live incidents refresh | 15 min, 30 min, 1 hour, 2 hours, Disabled | 30 minutes |

### Risk Prediction

| Setting | Options | Default |
|---------|---------|---------|
| Prediction model | Random Forest, XGBoost | Random Forest |

---

## Interacting with the Map

The interactive Folium map displays multiple toggleable layers (use the layer control in the top-right):

- **OpenStreetMap** — Base map tiles
- **Chargepoints** — Colour-coded site markers (pink = V2X, blue = Building-supplied, green = Other)
- **Outage Heatmap** — Density of outage locations weighted by duration
- **Risk Heatmap** — ML-predicted risk cells (red = High, amber = Medium, green = Low)
- **Live Incidents** — Red pulsing markers for active power cuts

**Click a marker** to select that site. The dashboard will:
1. Highlight the selected site in a banner
2. Display detailed analysis tabs below the map

---

## Detailed Analysis Tabs

When a site is selected, five tabs appear:

### 1. Frequency Timeline
- Monthly outage counts grouped by duration category (< 3h, 3-6h, 6-12h, > 12h)
- Customer-hours lost trend over time
- Hover over the `?` icons for chart explanations

### 2. Customer Impact
- Pie charts showing impact and frequency by duration category
- Reveals whether long outages drive most of the impact

### 3. Risk Assessment
- Radar/spider chart with four normalised axes:
  - **Frequency** — Number of outages
  - **Duration** — Average outage length
  - **Impact** — Total customer hours lost
  - **Consistency** — Predictability of outage patterns
- Overall Vulnerability Score (0-100) displayed below
- Theme-aware: adapts colours to light/dark mode

### 4. Rule-based Insights
- Risk classification (Critical / High / Medium / Low)
- Recommendations for V2X deployment, backup power, or monitoring
- Key metrics summary

### 5. Risk Prediction
- ML-predicted risk level with confidence score
- Class probability bar chart (Low / Medium / High)
- Top 3 contributing features from the model

---

## Right-Hand Panel (AI Dashboard)

### Live Incidents
When enabled, shows active power cuts from the ENW API:
- Red pulsing indicator with incident count
- Expandable cards with: reported time, customers off supply, customers affected, estimated restoration

### Metric Cards
Four year-over-year metrics:
- **Customers Affected** — total with % delta vs previous year
- **Customer Hours Lost** — total supply-hours lost
- **Median Outage Duration** — robust to outliers
- **Top Cause** — most frequent direct cause category

### Site Distribution
Pie chart showing charging sites by category.

### Quick Insights
- Winter outage percentage
- Long outage (>12h) percentage
- V2X site count

### AI Recommendations
Top 3 actionable recommendations from the ML risk model:
- Charging station placement suggestions
- Grid resilience priorities
- Community impact assessments

### Ask the AI
Natural language interface for asking questions about:
- Highest risk areas
- Charger placement recommendations
- Winter risk assessment
- Investment priorities
- Community building vulnerability

Example questions:
- "What areas are highest risk?"
- "Where should we put new chargers?"
- "What is the winter risk?"
- "Show investment priorities"

---

## Exporting Results

- **Plotly charts**: Use the toolbar (camera icon for PNG, download icon for data)
- **Screenshots**: `Windows + Shift + S`
