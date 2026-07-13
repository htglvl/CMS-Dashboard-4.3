# OpenClaw Deployment Evaluation

**Date:** 11 July 2026
**Project:** CMS Dashboard 4.3 — Grid Resilience & EV Charging Analysis
**Prepared for:** CyberMoor / Lancaster University AI Placement

---

## Table of Contents

1. [Technical Report: OpenClaw Integration](#1-technical-report-openclaw-integration)
2. [Website Operations Manual](#2-website-operations-manual)
3. [OpenClaw Use Cases](#3-openclaw-use-cases)
4. [Risks and Limitations of Using OpenClaw](#4-risks-and-limitations-of-using-openclaw)
5. [Recommendations: Implementing OpenClaw in Other Projects](#5-recommendations-implementing-openclaw-in-other-projects)

---

## 1. Technical Report: OpenClaw Integration

### 1.1 What Is OpenClaw?

OpenClaw is an open-source AI agent gateway. It provides a WebChat interface where users type natural language questions, and the gateway routes those questions to registered "tools" — backend functions that return structured data. The LLM interprets the user's intent, decides which tools to call, and synthesises the results into a human-readable answer. If the tool is not sufficient, it create it's own tool to manipulate the data.

The key architectural idea is that **the LLM never touches the data directly**. It can only call pre-defined tools that return JSON. This limits hallucination because the agent's answers are grounded in real tool output, not the model's training data.

### 1.2 How It Integrates with CMS Dashboard

The CMS Dashboard already had Python data scripts, CSV files, and ML models. OpenClaw was added as a **conversational layer on top** — it does not replace the existing Streamlit dashboard, it supplements it.

```
┌─────────────────────────────────────────────────────────────────┐
│                        High level architecture                  │
│                                                                 │
│  ┌──────────────┐              ┌──────────────────────────────┐ │
│  │   WebChat    │              │      Streamlit Dashboard     │ │
│  │  (OpenClaw)  │              │         port 8501            │ │
│  │  port 8501   │              │                              │ │
│  └──────┬───────┘              └──────────────┬───────────────┘ │
│         │                                     │                 │
│  ┌──────▼───────┐              ┌──────────────▼───────────────┐ │
│  │  OpenClaw    │              │      nginx reverse proxy     │ │
│  │  Gateway     │              │    (localhost:8502 -> 8501)  │ │
│  │  (Node.js)   │              │                              │ │                                        
│  └──────┬───────┘              └──────────────┬───────────────┘ │
│         │                                     │                 │
│  ┌──────▼───────┐              ┌──────────────▼───────────────┐ │
│  │  Plugin      │              │                              │ │
│  │  (tools)     │              │      (enhanced_app.py)       │ │
│  │ .md files    │              │                              │ │
│  └──────┬───────┘              └──────────────┬───────────────┘ │
│         │                                     │                 │               
│  ┌──────▼───────┐                      ┌──────▼───────┐         │
│  │  Data/Models │                      │  Python CLI  │         │
│  │  CSV, GeoJSON│◄─────────────────────│  website's   │         │
│  │  XGB, RF     │    Both interfaces   │  python code │         │
│  └──────────────┘    share the data    └──────────────┘         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Integration Components

| Layer | Component | File(s) | Technology | Role |
|-------|-----------|---------|-----------|------|
| **User Interface** | WebChat | `~/.openclaw/openclaw.json` | OpenClaw | Natural language chat — accessible on port 8501 via nginx |
| **User Interface** | Streamlit Dashboard | `enhanced_app.py` | Python/Streamlit | Visual maps, charts, filters — accessible on port 8501 via nginx |
| **Routing** | nginx reverse proxy | `nginx/conf/nginx.conf` | nginx | Single entry point on port 8501; routes `/` → Streamlit (8502), `/oclaw` → OpenClaw Gateway (18789) |
| **Agent** | OpenClaw Gateway | `openclaw serve` (Node.js) | Node.js | Routes chat messages to tools, manages LLM context, orchestrates tool calls |
| **Tools** | Plugin | `openclaw-plugin/`, `.md` skill files | TypeScript/Markdown | Registers tools with the gateway, maps tool names to Python scripts; skills guide the agent's workflow |
| **Backend** | Python CLI | `tools/*.py`, website's Python code | Python 3.12 | CLI wrappers — `argparse` input, JSON output to stdout; reuses the existing dashboard codebase |
| **Data** | Data/Models | `data/`, `models/` | CSV, GeoJSON, pkl | Shared by both WebChat and Streamlit — same data, same models |
| **Bootstrap** | Startup scripts | `setup.bat`, `run_dashboard.bat` | Batch | Builds plugin, starts all services, validates `.env` |

### 1.4 How a Tool Call Works

1. User types "What's the outage risk in Lancaster?" in WebChat
2. OpenClaw Gateway sends the message to the LLM (via API key — OpenAI, Anthropic, or Xiaomi)
3. LLM decides to call `geocode` with `{"place": "Lancaster"}`
4. Gateway finds the registered tool in the plugin, calls `runPythonTool("geocode", {"place": "Lancaster"})`
5. Plugin spawns: `python tools/geocode.py --place Lancaster`
6. Python script hits Nominatim API, returns `{"lat": 54.0466, "lon": -2.8007, "display_name": "Lancaster, ..."}`
7. Gateway feeds the JSON result back to the LLM
8. LLM decides to call `query_risk` with `{"lat": 54.0466, "lon": -2.8007}`
9. Repeat until the LLM has enough data to answer
10. LLM synthesises a natural language response from all tool outputs

### 1.5 Tool Registration Pattern

Each tool is registered in `openclaw-plugin/index.ts` with a TypeBox schema defining its parameters:

```typescript
// Example: registering the geocode tool
{
  name: "geocode",
  description: "Convert a UK place name to latitude/longitude coordinates using Nominatim.",
  parameters: Type.Object({
    place: Type.String({ description: "Place name, e.g. 'Lancaster' or 'Kendal, Cumbria'" }),
    limit: Type.Optional(Type.Number({ description: "Max results to return (default 3)" }))
  })
}
```

When the tool is called, the plugin constructs a command and runs it:

```typescript
const result = execSync(
  `"${VENV_PYTHON}" "${scriptPath}" ${argStr}`,
  { timeout: 120_000 }
);
```

### 1.6 Tool Convention

All 13 tools follow the same pattern:

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
- JSON to stdout, progress/errors to stderr
- `sys.path.insert` at top for project imports
- Try/except with structured error JSON
- Register in `index.ts` with TypeBox schema
- Write tests in `tests/test_<tool_name>.py`

### 1.7 Tool Reference

| # | Tool | Script | Key Arguments | Description |
|---|------|--------|---------------|-------------|
| 1 | `geocode` | `tools/geocode.py` | `--query`, `--limit` | UK place name → lat/lon (Nominatim) |
| 2 | `query_risk` | `tools/query_risk.py` | `--lat --lon` or `--district`, `--top` | ML risk predictions for a location or district |
| 3 | `query_outages` | `tools/query_outages.py` | `--district`, `--lat --lon --radius`, `--year`, `--cause`, `--min-duration`, `--sort`, `--top` | Historic outage records with multiple filter options |
| 4 | `query_charging_sites` | `tools/query_charging_sites.py` | `--category`, `--near-lat --near-lon --radius`, `--top` | EV charging site lookups by category or proximity |
| 5 | `get_recommendations` | `tools/get_recommendations.py` | `--type v2x\|chargepoint\|all` | V2X/chargepoint placement recommendations |
| 6 | `get_live_incidents` | `tools/get_live_incidents.py` | *(none)* | Current ENW live power incidents |
| 7 | `summarize_district` | `tools/summarize_district.py` | `--district` | Full district analysis (risk + outages + charging) |
| 8 | `get_wiki` | `tools/get_wiki.py` | `--topic`, `--search`, `--list` | Dashboard documentation lookup |
| 9 | `check_new_incidents` | `tools/check_new_incidents.py` | *(none)* | New incidents since last check, with risk context |
| 10 | `clean_borderlands` | `tools/clean_borderlands.py` | `--top`, `--local-authority`, `--cross-ref`, `--radius` | Borderlands site cleaning, geocoding, cross-reference |
| 11 | `count_outages_near_chargepoints` | `tools/count_outages_near_chargepoints.py` | `--radius`, `--category`, `--top` | Outages within radius of each CMS chargepoint |
| 12 | `forecast_outages_by_season` | `tools/forecast_outages_by_season.py` | `--season`, `--year`, `--district`, `--cause`, `--include-duration`, `--include-causes` | Seasonal outage forecasting from historical data |
| 13 | `tag_counties` | `tools/tag_counties.py` | `--lat --lon` or `--bulk`, `--output` | UK ceremonial county lookup (single or bulk CSV) |

Additionally, 4 quick scripts exist for ad-hoc analysis (`query_castle_carrock.py`, `query_longridge.py`, `query_longridge_chargers.py`, `recommendation_sites.py`). These are not registered with OpenClaw — they have no argparse and no JSON output.

### 1.8 Test Results

| Layer | Tests | Passed | Skipped | Notes |
|-------|-------|--------|---------|-------|
| Tool output correctness | 27 | 26 | 1 | Skipped: recommendations structure (no output generated) |
| Pipeline integrity | 18 | 16 | 2 | Skipped: streamlit not in test env |
| Additional tool tests (count_outages, forecast, tag_counties) | 45 | 45 | 0 | Full coverage of new tools |
| Tool chain consistency | 4 | 4 | 0 | All chains produce valid JSON |

**Total: 94 tests, 91 passed, 3 skipped, 0 failed.**

## 2. Website Operations Manual

### 2.1 System Components

The CMS Dashboard runs as a multi-process system. All services are started by `run_dashboard.bat`.

| Service | Port | Process | Log Output |
|---------|------|---------|------------|
| **Streamlit dashboard** | 8502 | `enhanced_app.py` | Terminal window titled "Streamlit Dashboard" |
| **OpenClaw proxy** | 18790 | `openclaw_proxy.py` | Terminal window titled "OpenClaw Proxy" |
| **nginx** | 8501 | `nginx/nginx.exe` | Terminal window titled "nginx" |
| **OpenClaw Gateway** | 18789 | `openclaw serve` | Terminal window titled "OpenClaw Gateway" |
| **Data fetcher** | — | `data/fetch_outages.py` | Runs once on startup, logs to `logs/fetch_outages.log` |

### 2.2 Starting the System

```bash
# First time only — builds plugin, configures OpenClaw
setup.bat

# Start all services
run_dashboard.bat
```

`run_dashboard.bat` does the following in order:
1. Validates `.env` exists and contains real API keys (not placeholders)
2. Fetches fresh outage data from ENW API (`python data/fetch_outages.py`)
3. Builds the OpenClaw plugin (`cd openclaw-plugin && npm install && npm run build`)
4. Starts Streamlit on port 8502
5. Starts OpenClaw proxy on port 18790
6. Starts nginx on port 8501
7. Waits 3 seconds for services to stabilise
8. Starts OpenClaw Gateway on port 18789
9. Optionally starts ngrok tunnel for remote access

### 2.3 Accessing the System

| Interface | URL | Purpose |
|-----------|-----|---------|
| **Streamlit Dashboard** | http://127.0.0.1:8501/ | Visual maps, charts, filters |
| **WebChat (OpenClaw)** | http://127.0.0.1:18789/ | Natural language chat with AI agent |
| **WebChat via nginx** | http://127.0.0.1:8501/oclaw/ | Same chat, proxied through nginx (single URL) |

### 2.4 Using the Streamlit Dashboard

The dashboard is accessed at **http://127.0.0.1:8501/**. It has a two-column layout: the map and detailed analysis on the left, the AI Dashboard panel on the right. All global controls are in the sidebar.

#### 2.4.1 Opening OpenClaw Chat

The **"OpenClaw AI Chat"** button is at the top of the sidebar (purple gradient). Click it to open the WebChat interface in a new browser tab at `/oclaw/`. This is the natural language interface described in section 1.

#### 2.4.2 Map Interaction

**Clicking on the map:**
- **Click a chargepoint marker** — a pink 2-mile buffer circle appears around the site, and a detailed analysis panel loads below the map with 5 tabs (see below).
- **Click empty space** — a pin drops at that location with a 2-mile buffer, showing outages and risk data for the area.
- **Click a flexibility tender polygon** — a detail panel appears showing substation data (postcodes, voltage, need type, delivery dates, pricing). Use ◀/▶ buttons to paginate through tenders for that substation.
- **Click a live incident marker** — shows incident details (number, status, customers off supply, restoration time).

**Layer control** (top-right corner of the map):
Toggle layers on/off using the built-in Folium layer control:

| Layer | What it shows |
|-------|--------------|
| Risk Heatmap | Coloured grid cells (green → yellow → red) based on ML risk predictions |
| Flexibility Tender Polygons | Substation areas with flexibility contracts (blue = Variable Availability, purple = + Operational Utilisation) |
| Buffer Zones | 2-mile dashed circles around each chargepoint |
| Chargepoints | Circle markers sized by outage count, colour-coded by category (pink = V2X, blue = Building-supplied, green = Other) |
| Outage Heatmap | Heat density of outages weighted by duration |
| AI Recommended Sites | Red bolt (V2X) and blue plug (chargepoint) icons from the recommendation engine |
| Live Incidents | Red circles for active ENW power incidents |

#### 2.4.3 Site Analysis Tabs

When a chargepoint or location is clicked, 5 tabs appear below the map:

| Tab | Content |
|-----|---------|
| **Frequency Timeline** | Two line charts — outage count per month by duration category, and customer-hours lost over time |
| **Customer Impact** | Two pie charts — proportion of customer-hours from short vs long outages, and outage frequency by duration |
| **Risk Assessment** | Radar chart showing normalised risk metrics (Frequency, Duration, Impact, Consistency) with a vulnerability score out of 100 |
| **Insights** | Rule-based risk classification (Critical/High/Medium/Low) with bullet-point recommendations and key metrics |
| **Risk Prediction** | ML-based prediction — risk level, confidence, class probability bar chart, and top 3 contributing features |

#### 2.4.4 Sidebar Controls

**Filters:**
- **Years** — multiselect to filter outages by year
- **Daytime only (9AM-9PM)** — on by default
- **Exclude exceptional events** — on by default
- **Chargepoint Categories** — filter by V2X, Building-supplied, Other

**Statistical filters:**
- **IQR outlier removal** — on by default, slider controls multiplier (0.0–4.0, default 1.5)
- **Significance filter** — on by default, slider controls quantile threshold (0.0–1.0, default 0.5)

**Risk prediction controls:**
- **Prediction model** — switch between Random Forest and XGBoost
- **Show risk heatmap** — toggle the heatmap layer (on by default)
- **Minimum confidence** — slider (0.0–1.0, default 0.95) to filter which heatmap cells are shown

**Auto-refresh:**
- **Data refresh interval** — 30 seconds / Hourly / Daily / Weekly / Monthly
- **Live incidents refresh** — 15 min / 30 min / 1 hour / 2 hours / Disabled

#### 2.4.5 Retraining Models

The **"Retrain Risk Models"** button is in the sidebar under Risk Prediction. Click it to:

1. Invalidate the features cache
2. Retrain both Random Forest and XGBoost using 5-fold walk-forward validation
3. Save updated prediction CSVs to `models/`
4. Reload predictions and refresh the dashboard

A spinner shows "Retraining models... this may take a minute". On success, a toast confirms "Risk models retrained successfully." On failure, an error message appears in the sidebar.

**Automatic retraining** also happens when new outage data is fetched from the ENW API — if new records are found, models are retrained automatically.

#### 2.4.6 Right Panel — AI Dashboard

The right panel shows:

- **Metric cards** — Customers Affected, Customer Hours Lost, Median Outage Duration, Top Cause (with month-over-month deltas)
- **Site Distribution** — pie chart of charging sites by category
- **Quick Insights** — % of winter outages, % of outages >12 hours, count of V2X-capable sites
- **AI Recommendations** — expandable cards showing placement and grid resilience recommendations with priority, category, and detail

#### 2.4.7 Live Incidents

Below the sidebar, a live status indicator shows:
- Green dot + "No active incidents" when the grid is clear
- Red pulsing dot + count when incidents are active

Each incident expands to show: incident number, type, reported time, customers off supply, status, and estimated restoration time.

### 2.5 Stopping the System

Close all terminal windows, or:

```bash
# Kill all services
taskkill /FI "WINDOWTITLE eq Streamlit Dashboard"
taskkill /FI "WINDOWTITLE eq OpenClaw Proxy"
taskkill /FI "WINDOWTITLE eq nginx"
taskkill /FI "WINDOWTITLE eq OpenClaw Gateway"
```

`run_dashboard.bat` also cleans up on exit (Ctrl+C).

### 2.6 Environment Configuration

The `.env` file in the project root controls API keys and service settings:

| Variable | Required | Purpose |
|----------|----------|---------|
| `XIAOMI_API_KEY` | One of these three | LLM provider for OpenClaw agent |
| `OPENAI_API_KEY` | One of these three | LLM provider for OpenClaw agent |
| `ANTHROPIC_API_KEY` | One of these three | LLM provider for OpenClaw agent |
| `ENW_API_KEY` | Yes | Electricity North West live incidents API |
| `SENDGRID_API_KEY` | No | Email notifications (planned feature) |

**Never commit `.env` to git** — it is in `.gitignore`.

### 2.7 Data Refresh

| Data | Source | Refresh Method |
|------|--------|---------------|
| Outage records | ENW API | `python data/fetch_outages.py` (runs on startup) |
| Charging sites | Manual CSV update | Edit `data/all_charging_sites.csv` |
| Risk predictions | ML models | `python advanced_charts/risk_model.py` (auto-trains if cache stale) |
| Live incidents | ENW API | Real-time via `get_live_incidents` tool |
| Borderlands sites | Excel file | Edit `data/borderlands_long_list.xlsx`, then `clean_borderlands` tool |

Cache staleness is managed automatically: `advanced_charts/cache_utils.py` checks if the source data is newer than the cached predictions and invalidates if so.


### 2.8 File Structure

```
CMS Dashboard 4.3/
├── enhanced_app.py          # Streamlit main app
├── openclaw_proxy.py        # Auth token proxy for OpenClaw
├── proxy_server.py          # General proxy server
├── run_dashboard.bat        # Start all services
├── setup.bat                # First-time setup
├── .env                     # API keys (not in git)
│
├── openclaw-plugin/         # OpenClaw plugin
│   ├── index.ts             # Tool registration + system prompt
│   ├── dist/index.js        # Compiled output (gateway loads this)
│   ├── skills/              # AI workflow skills
│   └── package.json
│
├── tools/                   # CLI tool scripts
│   ├── geocode.py
│   ├── query_risk.py
│   ├── query_outages.py
│   ├── query_charging_sites.py
│   ├── get_recommendations.py
│   ├── get_live_incidents.py
│   ├── summarize_district.py
│   ├── get_wiki.py
│   ├── check_new_incidents.py
│   ├── clean_borderlands.py
│   └── README.md
│
├── data/                    # Data files (not in git)
│   ├── df_cleaned.csv       # 309k+ outage records
│   ├── all_charging_sites.csv
│   ├── borderlands_long_list.xlsx
│   └── fetch_outages.py     # Data fetcher script
│
├── models/                  # Trained ML models
│   ├── predictions_randomforest.csv
│   ├── predictions_xgboost.csv
│   └── *.pkl                # Serialized model files
│
├── advanced_charts/         # Risk model, recommendation engine
│   ├── risk_model.py
│   ├── recommendation_engine.py
│   └── cache_utils.py
│
├── dashboard/               # Streamlit UI components
├── tests/                   # pytest test files
├── wiki/                    # Documentation
├── docs/                    # Design specs and reports
└── nginx/                   # nginx configuration
    └── conf/nginx.conf
```

---

## 3. OpenClaw Use Cases

### 3.1 Location-Based Risk Assessment

**What it does:** User asks "What's the power outage risk in Lancaster?" — the agent geocodes the place name, queries the ML risk model, finds nearby charging sites, and pulls outage history in one conversational turn.

**Tools used:** `geocode` → `query_risk` → `query_charging_sites` → `query_outages`

**Who benefits:** Grid planners, local authorities, researchers.

---

### 3.2 EV Charging Site Discovery

**What it does:** User asks "Are there any V2X chargepoints near Kendal?" — the agent searches the charging site database by category and proximity.

**Tools used:** `geocode` → `query_charging_sites`

---

### 3.3 Investment Recommendations

**What it does:** User asks "Where should we place new chargepoints?" — the recommendation engine cross-references risk predictions with existing infrastructure.

**Tools used:** `get_recommendations`

**Logic:** High-risk areas with no chargepoints within 3km are flagged as Critical priority. Non-V2X chargers in high-risk zones are flagged for V2X upgrades.

---

### 3.4 Borderlands Community Site Analysis

**What it does:** User asks "What are the Borderlands community sites?" — the agent reads the Excel file, geocodes each site, and optionally cross-references with risk predictions and charging infrastructure.

**Tools used:** `clean_borderlands`

**Data:** 117 sites across 4 local authorities. Geocoding success rate ~85%.

---

### 3.5 Live Incident Monitoring

**What it does:** User asks "Are there any active power incidents right now?" — the agent fetches the current ENW live incident feed and enriches each incident with risk context.

**Tools used:** `get_live_incidents` or `check_new_incidents`

---

### 3.6 Historic Outage Analysis

**What it does:** User asks "Show me recent power outages in Cumberland" — the agent queries 11,316 outage records (1997–2026) filtered by district or proximity.

**Tools used:** `query_outages`

---

### 3.7 District Summary Reports

**What it does:** User asks "Give me a full analysis of Lancaster" — the agent combines risk predictions, outage history, and charging site data into a single structured summary.

**Tools used:** `summarize_district`

---

### 3.8 Documentation Access

**What it does:** User asks "How does the risk model work?" — the agent retrieves relevant wiki pages.

**Tools used:** `get_wiki`

---

## 4. Risks and Limitations of Using OpenClaw

This section focuses on OpenClaw as a platform — the risks and limitations inherent to using it as an AI agent gateway, independent of the CMS Dashboard's domain-specific data.

### 4.1 Risks

#### R1: LLM Hallucination in data generation Despite Tool Grounding

**Risk:** Even though OpenClaw forces the agent through structured JSON tools, the LLM can still halluculate when **synthesising** tool results into a natural language answer. It might misinterpret a confidence score, overstate certainty, or combine data points incorrectly. The user's query can also make it to hallucinate if the query is so out of scope.

**Likelihood:** Medium
**Impact:** High — users may act on incorrect summaries

**Mitigations in place:**
- System prompt instructs
- Tool descriptions specify exact data sources to ground the agent
- Allow Openclaw to create new tool for out of scope task and give it enough data/context in the first place.
- E2E test set checks for expected keywords in responses

---

#### R2: LLM Hallucination on Tool Calling, Agent Automation Cause Harm

**Risk:** The LLM can call the wrong tool, pass incorrect parameters, or misinterpret tool output — leading to hallucinated answers presented as fact. If the agent is given write/delete capabilities (e.g. modifying data files, triggering retraining), a hallucinated tool call could cause real damage to the system.

**Likelihood:** Medium — depends on model quality and prompt clarity
**Impact:** High — users act on incorrect data; automated actions could corrupt data or trigger unintended side effects

**Mitigations in place:**
- System prompt instructs the agent to always use tools, never make up data
- Tool descriptions are specific to reduce misrouting
- Gateway controls what the agent can access and what it can edit
- Approval gates before destructive actions (edit, delete)
- Smarter model reduce hallucination likelihood, enable thinking mode if exist/necessary 
- Two-layer try/except ensures tool errors return structured JSON, not raw exceptions

---

#### R3: Token Burn — LLM Loops, Excessive Tool Calls, and Daemon Overhead

**Risk:** The LLM can get stuck in a thinking loop — calling the same tool repeatedly, chaining unnecessary tool calls, or retrying on errors without progressing toward an answer. Each tool call costs API tokens, and a single runaway query can burn through an entire token budget in minutes. Additionally, background daemons (e.g. `check_new_incidents`, auto-refresh timers, cron jobs) run periodically and make LLM calls on schedule, consuming tokens even when no user is actively interacting.

**Likelihood:** High — LLM loops are a known failure mode; daemon calls are constant
**Impact:** High — unexpected API costs, rate limiting from the LLM provider, degraded service

**Mitigations in place:**
- `execSync` timeout (120s) prevents infinite tool execution
- Tool errors return structured JSON so the agent can handle failures without retrying blindly
- Offload deamon, cron jobs, auto update to code, not relying on openclaw to minimize deamon, automation jobs calling.
- System prompt to prevent it.

---

#### R4: External API Dependency Fragility

**Risk:** OpenClaw tools depend on external APIs (Nominatim for geocoding, ENW for live incidents). If these APIs go down, rate-limit, or change their response format, tools fail silently or return errors that the agent may not handle gracefully.

**Likelihood:** High (Nominatim rate limiting is frequent)
**Impact:** Medium — degraded functionality, not total failure

**Mitigations in place:**
- Rate limit the API

#### R5: Plugin Build Dependency

**Risk:** The OpenClaw gateway loads `openclaw-plugin/dist/index.js` — the compiled TypeScript output. If `npm run build` fails (TypeScript errors, missing dependencies), the gateway starts with no tools registered, and the agent has nothing to call.

**Likelihood:** Low (build happens on startup)
**Impact:** Medium — agent don't know how to use and find the tools

**Mitigations in place:**
- `run_dashboard.bat` runs `npm install && npm run build` before starting the gateway
- `setup.bat` also builds during initial setup
- `AGENTS.md, TOOLS.md, SOUL.md` can give openclaw a hint on where to look for the tool.

---


### 4.2 Limitations

| # | Limitation | Detail |
|---|-----------|--------|
| L1 | **No streaming responses** | OpenClaw when enable thinking mode (if llm supported), add up with tool call can feel slow because the user sees nothing until the LLM finishes. |
| L2 | **Limited-user design** | The software/hardware is designed and limit for few user at a time. Concurrent sessions share the same data execution context, which can cause timeouts or race conditions. |
| L3 | **No tool result caching at gateway level** | Each tool call executes the Python script from scratch. The recommendation engine caches internally, but the gateway doesn't cache repeated queries. |
| L4 | **120-second default timeout** | `execSync` has a hard timeout. Complex queries (recommendations, Borderlands cross-ref) can exceed this, causing silent failures. |
| L5 | **No tool prioritisation or routing** | The LLM decides which tools to call. There's no mechanism to force certain tools or prevent others based on user role or context. |
| L6 | **API dependency** | OpenClaw need LLM to work which relies on external API. The agent is useless if the API is wrong, out of date or the LLM is not capable of executing tools, query. |
| L7 | **Plugin reload requires restart** | Adding or modifying a tool requires rebuilding the plugin and restarting the gateway. There's no hot-reload. |
| L8 | **No built-in analytics** | OpenClaw doesn't track which tools are called most, which fail most, or how long responses take. All analytics must be built externally. |

---

## 5. Recommendations: Implementing OpenClaw in Other Projects

This section provides guidance for teams considering OpenClaw as a conversational AI layer for their own projects.

### 5.1 When to Use OpenClaw

OpenClaw is a good fit when:

| Condition | Why it matters |
|-----------|---------------|
| You have **structured data tools** (APIs, CLI scripts, databases) that return JSON | OpenClaw's value is routing LLM intent to the right tool. If you don't have tools, you're just wrapping an LLM in a chat UI. |
| Your users are **non-technical** and need ad-hoc queries | Predefined dashboards work for known questions. OpenClaw handles "what about..." and "compare X to Y" style questions. |
| You need **hallucination control** | The tool-first architecture forces the LLM to use real data, not its training knowledge. |
| You want a **quick prototype** of conversational AI | OpenClaw handles the chat UI, LLM routing, and tool execution. You only write the tools. |

OpenClaw is **not** a good fit when:

| Condition | Why it matters |
|-----------|---------------|
| You need **real-time streaming / time-sensitive responses** | OpenClaw waits for the full LLM response before returning anything. Not suitable for live dashboards or instant feedback. Traditional code is faster for time-critical paths. |
| You need **deterministic / reproducible results** | The same question can produce different answers depending on LLM non-determinism. If you need the same output every time, use a function, not an agent. |
| Your **queries are deterministic** (e.g. traditional FAQ) | If users ask the same predictable questions with known answers, a static FAQ or simple lookup table is cheaper, faster, and more reliable than an LLM agent. |
| You operate in **regulated industries requiring explainability** | If regulations require you to explain why a decision was made, an LLM's reasoning is a black box. You cannot trace exactly how the agent arrived at an answer. |


### 5.2 Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| **Tools return HTML/error pages instead of JSON** | Add try/except to every tool. Test error paths. |
| **Agent calls wrong tools** | Make tool descriptions specific. Add "Use this tool when..." to descriptions. |
| **Agent hallucinates data** | System prompt must say "Never make up data. Always use tools." Test with E2E golden set. |
| **Tool timeout** | Increase `execSync` timeout for slow tools. Add caching inside tools. |
| **Gateway crashes silently** | Add health check. Run with PM2 or supervisor for auto-restart. |
| **Plugin build fails in CI** | Add `npm run build` to CI pipeline. Commit `dist/` and add plugin path, instruction, description so openclaw can auto fix as fallback. |
| **Rate limiting on external APIs** | Add retry with backoff, rate limit. Cache results. Use pickle files for expensive lookups. |
| **Agent gives different answers each time** | LLM non-determinism can reduce by edit temperature, top p, top k and seed. For critical paths, use structured tool output, not agent synthesis. |

### 5.3 Security Checklist

Before exposing OpenClaw to users beyond your development team, try to balance between Security-Convenience-Functionality. This is just a guideline of some core checklist to put in mind when integrating openclaw in other project:

- [ ] Set `auth.mode: "token"` in gateway config
- [ ] Set `allowInsecureAuth: false`
- [ ] Bind to loopback, not `0.0.0.0`
- [ ] Add rate limiting on the reverse proxy
- [ ] Sanitise all tool inputs (don't trust LLM-generated parameters)
- [ ] Log all tool calls (name, params, timestamp)
- [ ] Rotate API keys regularly
- [ ] Don't commit `.env` or tokens to version control
- [ ] Run tools with least-privilege (don't run as admin)
- [ ] Set `execSync` timeout to the minimum needed

---

*This document consolidates the technical report, operations manual, use case analysis, platform risk assessment, implementation guidance, and deployment discussion for the OpenClaw integration in CMS Dashboard 4.3.*
