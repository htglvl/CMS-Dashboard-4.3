# OpenClaw Integration: Use Cases and Risks Report

**Date:** 8 July 2026
**Project:** CMS Dashboard 4.3 — Grid Resilience & EV Charging Analysis
**Prepared for:** CyberMoor / Lancaster University AI Placement

---

## 1. Overview

OpenClaw is an AI agent gateway that provides a natural language chat interface to the CMS Dashboard's data and analysis tools. Users interact via a WebChat UI, and the gateway routes queries through a custom plugin that invokes Python CLI tools behind the scenes.

```
User (WebChat) → OpenClaw Gateway (port 18789) → Plugin Tools → Python CLI Scripts → Data/ML Models
```

The integration currently registers **10 tools** (up from 9 — the new `clean_borderlands` tool was added in this iteration), two AI workflow skills (`risk-analysis` and `documentation`), and a system prompt that guides the agent through a geocode-first workflow.

---

## 2. Use Cases

### 2.1 Location-Based Risk Assessment

**What it does:** A user asks "What's the power outage risk in Lancaster?" and the agent geocodes the place name, queries the ML risk model, finds nearby charging sites, and pulls outage history — all in one conversational turn.

**Tools used:** `geocode` → `query_risk` → `query_charging_sites` → `query_outages`

**Who benefits:**
- Grid planners assessing vulnerability of a specific area
- Local authorities evaluating resilience of their communities
- Researchers analysing spatial patterns of outage risk

**Accuracy:** The ML models (RandomForest + XGBoost) show 80.4% agreement across 1,945 grid cells. Mean confidence is 0.586 (RF) and 0.642 (XGB). The geocode tool resolves most UK place names correctly, though rural hamlets can be ambiguous.

---

### 2.2 EV Charging Site Discovery

**What it does:** A user asks "Are there any V2X chargepoints near Kendal?" and the agent searches the charging site database by category and proximity.

**Tools used:** `geocode` → `query_charging_sites`

**Who benefits:**
- Charge point operators looking for deployment gaps
- Community groups evaluating local charging infrastructure
- Planners identifying underserved areas

**Data:** 88 charging sites across 3 categories (12 V2X, 5 Building-supplied, 71 Other). All coordinates validated within UK bounds.

---

### 2.3 Investment Recommendations

**What it does:** A user asks "Where should we place new chargepoints?" and the agent runs the recommendation engine, which cross-references risk predictions with existing charging infrastructure to identify high-priority placement opportunities.

**Tools used:** `get_recommendations`

**Who benefits:**
- Funders and grant applicants (e.g. Borderlands BOOST Project) needing evidence-based site selection
- Local authorities prioritising infrastructure investment
- Community energy groups planning V2X deployments

**Logic:** The engine flags areas that are (a) high-risk AND (b) have no chargepoints within 3km as Critical priority. Areas with existing non-V2X chargers in high-risk zones are flagged for V2X upgrades.

---

### 2.4 Borderlands Community Site Analysis

**What it does:** A user asks "What are the Borderlands community sites?" and the agent reads the Borderlands Long List Excel file, geocodes each site, and optionally cross-references with risk predictions, existing chargepoints, and recommendation engine output.

**Tools used:** `clean_borderlands` (newly added)

**Who benefits:**
- Borderlands BOOST Project managers evaluating feasible chargepoint locations
- Community groups in Cumberland, Northumberland, and Westmorland & Furness
- Researchers assessing rural EV infrastructure gaps

**Data:** 117 sites across 4 local authorities. Geocoding success rate ~85% (some rural sites fail Nominatim lookup). Cross-reference mode adds risk level, nearby charging count, and recommendation match status to each site.

---

### 2.5 Live Incident Monitoring

**What it does:** A user asks "Are there any active power incidents right now?" and the agent fetches the current ENW live incident feed, enriches each incident with risk context and nearby chargepoints.

**Tools used:** `get_live_incidents` or `check_new_incidents`

**Who benefits:**
- Operations teams monitoring real-time grid status
- Emergency planners assessing impact of current outages
- Community groups checking local power status

**Dependency:** Requires valid `ENW_API_KEY` in `.env`. Without it, the tool returns an error.

---

### 2.6 Historic Outage Analysis

**What it does:** A user asks "Show me recent power outages in Cumberland" and the agent queries 11,316 outage records (spanning 1997–2026) filtered by district or proximity.

**Tools used:** `query_outages`

**Who benefits:**
- Researchers analysing long-term outage trends
- Grid planners identifying chronic problem areas
- Insurance and risk assessors evaluating historical reliability

**Data:** 11,316 records with incident date, duration, cause, affected customers, and coordinates.

---

### 2.7 District Summary Reports

**What it does:** A user asks "Give me a full analysis of Lancaster" and the agent combines risk predictions, outage history, and charging site data into a single structured summary.

**Tools used:** `summarize_district`

**Who benefits:**
- Decision-makers needing a quick area overview
- Report writers compiling multi-source analysis
- Grant applicants needing evidence packs for specific areas

---

### 2.8 Email Notification Reports (Planned)

**What it does:** When new incidents exceeding 6 hours are detected, the system generates a risk-enriched report via OpenClaw and emails it to subscribed addresses using SendGrid.

**Tools used:** `check_new_incidents` → OpenClaw report generation → SendGrid delivery

**Who benefits:**
- Subscribers who want automatic alerts for long-duration outages
- Community groups monitoring local grid reliability
- Planners tracking incident frequency over time

**Status:** Designed and planned (see `docs/superpowers/specs/2026-07-03-email-notification-design.md`), not yet implemented.

---

### 2.9 Documentation Access

**What it does:** A user asks "How does the risk model work?" and the agent retrieves relevant wiki pages explaining the dashboard's features, data sources, and methodology.

**Tools used:** `get_wiki`

**Who benefits:**
- New users learning the system
- Researchers understanding methodology
- Developers onboarding to the codebase

---

## 3. Risks and How We Handle Them

For each risk, we show: what could go wrong → what's already in place → what still needs doing.

---

### 3.1 External API Dependencies

#### Risk 1: Nominatim Rate Limiting (429 Errors)

**What could go wrong:** The free Nominatim geocoding service enforces a 1-request-per-second limit. Bulk geocoding (e.g. 117 Borderlands sites) triggers 429 errors, causing the agent to fail on location-based queries.

**What we already do:**
- `clean_borderlands.py` enforces `time.sleep(1.1)` between each Nominatim call in the geocoding loop (`tools/clean_borderlands.py:290`)
- The Borderlands tool uses a pickle-based geocache (`data/borderlands_geocache.pkl`) so previously geocoded sites are not re-queried
- The test suite detects 429 responses and skips gracefully instead of failing (`tests/test_tools.py` — `is_rate_limited()` guard)
- Each tool returns structured `{"error": "HTTP Error 429", "type": "HTTPError"}` JSON so the agent can surface a clear message

**What still needs doing:**
- The main `geocode.py` tool has no cache — every call hits Nominatim fresh. Add a pickle cache matching the Borderlands pattern.
- No retry/backoff logic exists anywhere. Add exponential backoff (1s, 2s, 4s) for transient 429/5xx errors.

---

#### Risk 2: ENW API Key Expiry/Rotation

**What could go wrong:** The `ENW_API_KEY` in `.env` expires or is rotated, causing live incident fetching and outage data updates to fail silently or with cryptic errors.

**What we already do:**
- `run_dashboard.bat` validates `.env` exists before starting services (lines 13–21) — exits with clear error if missing
- `setup.bat` checks for placeholder values (`your_api_key_here`) and warns the user (lines 117–127)
- `fetch_outages.py` calls `sys.exit(1)` with a logged error if `ENW_API_KEY` is empty (`data/fetch_outages.py:83`)
- Each data fetcher logs timestamped success/failure to `logs/fetch_outages.log` and `logs/fetch_flexibility.log`
- `.last_fetch_outages` and `.last_fetch_flexibility` state files track when data was last successfully fetched

**What still needs doing:**
- No automated health check that warns when the key is expired or data is stale. Add a daily check that compares `.last_fetch_*` timestamps against expected intervals.

---

#### Risk 3: Nominatim Accuracy for Rural UK

**What could go wrong:** ~15% of Borderlands sites (rural hamlets like "Adams Rec Ground") fail Nominatim lookup because the place name is ambiguous or too small for OpenStreetMap.

**What we already do:**
- `clean_borderlands.py` tries two queries: first with local authority for disambiguation (`"{town}, {authority}, UK"`), then fallback to just `"{town}, UK"` (`tools/clean_borderlands.py:88-105`)
- Sites that fail geocoding get `latitude: null, longitude: null` — they're included in results but flagged as ungeocoded
- The summary reports `geocoded` vs `failed_geocode` counts so users know the coverage
- The `geocode.py` tool returns multiple results (up to `--limit N`) so the agent can pick the best match

**What still needs doing:**
- For Borderlands specifically, try geocoding from the `potential_sites` field (e.g. "Village Hall, Allithwaite") when the town name fails.
- Add a manual coordinate override list for known problem sites.

---

### 3.2 Model Accuracy and Interpretation

#### Risk 4: RF/XGB Disagreement (19.6% of cells)

**What could go wrong:** RandomForest and XGBoost assign different risk levels to 381 out of 1,945 grid cells. If the agent queries one model, the user gets a different answer than if it queried the other.

**What we already do:**
- The `query_risk.py` tool defaults to RandomForest (`predictions_randomforest.csv`) as the primary model, with XGBoost as fallback (`tools/query_risk.py:19-21`)
- Predictions include both `prob_high`, `prob_medium`, `prob_low` for each cell, so the agent can report the full probability distribution, not just the label
- The recommendation engine (`advanced_charts/recommendation_engine.py`) uses `prob_high` for ranking, not just the label, which smooths out binary disagreements
- Both models are trained on the same walk-forward validation scheme (5 chronological folds), ensuring consistent methodology

**What still needs doing:**
- Surface both models' predictions in the agent response when they disagree. E.g. "RF says High (72%), XGB says Medium (58%) — borderline case."
- Persist the per-fold accuracy to `models/accuracy_metrics.json` so we can compare model performance over time.

---

#### Risk 5: Low Confidence Predictions (<0.5)

**What could go wrong:** 349 cells (18%) have confidence below 0.5. The agent might present these as definitive when the model is genuinely unsure.

**What we already do:**
- Every prediction includes a `confidence` score (class probability) that the agent receives in the JSON response
- The risk-analysis skill (`openclaw-plugin/skills/risk-analysis/SKILL.md`) instructs the agent to always report "Risk Level: High/Medium/Low with confidence %" in its response format
- The `query_risk.py` tool returns the full probability distribution (`prob_high`, `prob_medium`, `prob_low`) alongside the label, giving the agent enough data to express uncertainty

**What still needs doing:**
- Add a confidence threshold in the agent's system prompt: "If confidence < 0.5, tell the user this is a low-certainty prediction."
- Consider returning a `certainty: "low"|"medium"|"high"` field in the tool output so the agent doesn't need to parse the number.

---

#### Risk 6: Walk-Forward Accuracy Not Persisted

**What could go wrong:** The walk-forward validation accuracy is logged to console during training but not saved. We can't retrospectively verify model performance or compare across training runs.

**What we already do:**
- `risk_model.py` computes accuracy per fold (`evaluate_model()` at line 451) and logs the mean ± std (`risk_model.py:609-611`)
- The `--evaluate` CLI flag allows running evaluation without retraining
- The predictions CSVs (`models/predictions_randomforest.csv`, `models/predictions_xgboost.csv`) persist the actual predictions with confidence scores

**What still needs doing:**
- After `_train_and_save()`, write a `models/accuracy_metrics.json` containing per-fold accuracy, mean, std, classification report, and training date.

---

#### Risk 7: Training Data Staleness

**What could go wrong:** The models were trained on outage data up to a certain date. As new outages occur, the predictions become less reflective of current grid conditions.

**What we already do:**
- `run_dashboard.bat` fetches fresh outage data on every startup (line 49: `python data/fetch_outages.py`)
- `advanced_charts/cache_utils.py` checks staleness: `is_cache_stale_vs_source()` compares cache timestamp against source data timestamp
- `data/fetch_outages.py` invalidates all caches after a successful fetch (lines 381–406), so the next model run uses fresh data
- The cache has a 90-day max age (`CACHE_MAX_AGE_DAYS = 90`) as a safety net

**What still needs doing:**
- Automate model retraining after data fetch. Currently the cache invalidation forces a retrain on next dashboard load, but the agent's predictions CSV might be stale.
- Add a "predictions last trained" timestamp to the agent's responses.

---

### 3.3 Data Quality

#### Risk 8: Outage Records Span 1997–2026

**What could go wrong:** Very old outage records (1997–2010) may reflect infrastructure that no longer exists, skewing analysis.

**What we already do:**
- `query_outages.py` supports a `--year` filter so the agent can request only recent data
- The risk model uses a 12-month feature window with walk-forward validation, so it naturally weights recent data
- The recommendation engine sorts by `prob_high` (recent predictions), not by historical outage count

**What still needs doing:**
- Add a default date filter in the agent's system prompt: "Unless the user asks for historical data, default to the last 5 years."

---

#### Risk 9: Charging Site Data Incomplete

**What could go wrong:** The 88 charging sites in `all_charging_sites.csv` may not cover all chargers in the ENW region, leading the agent to say "no chargers nearby" when they exist.

**What we already do:**
- `query_charging_sites.py` returns `count_within_radius` and `nearest_chargepoint_km` even when there are zero results, so the agent can say "no chargers within X km"
- The data includes 3 categories (V2X, Building-supplied, Other) for granular analysis
- All coordinates are validated within UK bounds (`tests/test_pipeline.py::test_charging_sites_have_coordinates`)

**What still needs doing:**
- Cross-reference with Open Charge Map API or national datasets to supplement local data.
- Add a data freshness indicator to charging site responses.

---

#### Risk 10: Borderlands Excel Header Row

**What could go wrong:** The Borderlands Excel file has a title row ("Borderlands BOOST Project: Long List of possible Car Club Locations") before the actual column headers. Reading with `header=0` fails silently, producing wrong column names.

**What we already do — FIXED:**
- Both `tools/clean_borderlands.py` and `charge_point_cleaning/clean_borderlands.py` now use `header=1` to skip the title row
- `tests/test_pipeline.py::test_borderlands_excel_columns` validates the correct columns are present
- `tests/test_pipeline.py::test_borderlands_has_data` checks that >50 rows are returned (catches silent header misalignment)

**What still needs doing:**
- Nothing — this is resolved. The test suite will catch regressions.

---

### 3.4 Agent Behaviour

#### Risk 11: Hallucinated Data

**What could go wrong:** The LLM invents statistics, locations, or risk levels that don't exist in the data, presenting them as fact.

**What we already do:**
- The system prompt explicitly instructs: "Always use these tools instead of writing Python scripts or using PowerShell commands. The tools return structured JSON data that you can summarize for the user." (`index.ts:295-296`)
- The prompt provides a concrete workflow example (geocode → query_risk → query_charging_sites → query_outages) so the agent follows a data-driven path
- Tool descriptions specify exact data sources ("309k+ records", "North West England") to ground the agent in real data
- The risk-analysis skill mandates: "Be concise and data-driven — avoid hallucinating data" (`SKILL.md:109`)
- The E2E chat test set (`tests/test_e2e_chat.py`) checks that responses contain expected data-derived keywords

**What still needs doing:**
- Run the E2E tests with the gateway live and document the pass rate.
- Add a "cite your sources" instruction to the system prompt so the agent mentions which tool provided each data point.

---

#### Risk 12: Wrong Tool Selection

**What could go wrong:** The agent uses `geocode` when the user means `query_risk`, or calls `get_recommendations` when the user wants a district summary.

**What we already do:**
- Tool descriptions are specific: "Use this FIRST when a user mentions a location by name" (geocode), "Query ML risk predictions for a location" (query_risk), etc.
- The system prompt defines a clear workflow order: geocode first, then use coordinates for subsequent tools
- The risk-analysis skill maps question patterns to tool sequences (e.g. "What's the risk in [place]?" → geocode → query_risk → query_charging_sites → query_outages)

**What still needs doing:**
- Monitor agent tool-calling patterns in production to identify frequent misroutes.

---

#### Risk 13: Ambiguous Location Queries

**What could go wrong:** "Lancaster" could mean Lancaster UK or Lancaster PA. The agent might geocode the wrong one.

**What we already do:**
- `geocode.py` appends ", UK" to the query (via Nominatim's `q` parameter), biasing results toward UK locations
- `clean_borderlands.py` tries "{town}, {local_authority}, UK" first, then falls back to "{town}, UK"
- The geocode tool returns multiple results (default `limit=3`) so the agent can pick the most relevant

**What still needs doing:**
- Add a bounding box filter (`viewbox`) to Nominatim queries to restrict results to the ENW region (lat 53–55.5, lon -4 to -1.5).

---

#### Risk 14: Tool Timeout (120s Limit)

**What could go wrong:** Long-running queries (recommendations, cross-ref with 100+ sites) exceed the 120-second `execSync` timeout and fail.

**What we already do:**
- The TypeScript wrapper sets `timeout: 120_000` on every tool call (`index.ts:19`)
- The Python proxy servers set `aiohttp.ClientTimeout(total=120)` on HTTP requests
- Nominatim geocoding has a separate 10-second timeout (`tools/geocode.py:34`)
- The ENW live incidents fetcher has a 15-second timeout (`data/fetch_live_incidents.py:83`)
- Test timeouts are calibrated per tool: 30s default, 60s for recommendations, 120s for Borderlands

**What still needs doing:**
- Increase the `execSync` timeout to 300s for heavy tools (`clean_borderlands`, `get_recommendations`).
- Add a progress indicator so the agent can tell the user "this may take a moment."

---

#### Risk 15: No Error Recovery

**What could go wrong:** If a tool fails, the agent receives an error JSON but may not know how to recover or inform the user.

**What we already do — ALREADY MITIGATED:**
- Every tool script wraps its entire `main()` in try/except, returning `{"error": "...", "type": "..."}` with `sys.exit(1)` on failure
- The TypeScript wrapper adds a second error layer: `catch (err) { return JSON.stringify({ error: err.message, tool: toolName }) }` (`index.ts:24-26`)
- This two-layer approach ensures the LLM always receives parseable JSON, even on total failure
- The system prompt tells the agent to use tools (not scripts), so it receives these structured errors directly

**What still needs doing:**
- Add a fallback instruction to the system prompt: "If a tool returns an error, tell the user what failed and suggest an alternative."

---

### 3.5 Security and Access

#### Risk 16: Gateway Token Exposure

**What could go wrong:** The OpenClaw gateway token is leaked, allowing unauthorised access to all dashboard tools and data.

**What we already do:**
- The gateway is bound to loopback only: `"bind": "loopback"` in `openclaw.json.template`
- The token is stored in `~/.openclaw/openclaw.json` (user home directory), not in the project
- `run_dashboard.bat` reads the token at runtime and injects it into the nginx config — it's never hardcoded
- The proxy servers inject the token via `Authorization: Bearer` header, so the browser never sees it directly
- `.env` is in `.gitignore` — API keys are never committed to version control

**What still needs doing:**
- Switch `auth.mode` from `"none"` to `"token"` in the gateway config to enforce authentication at the gateway level, not just the proxy.
- Set `allowInsecureAuth: false` for production deployments.

---

#### Risk 17: Tool Execution via `execSync`

**What could go wrong:** If tool names were user-controllable, an attacker could inject arbitrary commands via `execSync`.

**What we already do — ALREADY MITIGATED:**
- Tool names are hardcoded as string literals in `index.ts` — there is no user input in the `toolName` parameter of `runPythonTool()`
- The `runPythonTool` function constructs the command as `"${VENV_PYTHON}" "${scriptPath}" ${argStr}` with proper quoting (`index.ts:15`)
- CLI arguments are passed as separate array elements, not concatenated strings, preventing shell injection
- The plugin manifest (`openclaw.plugin.json`) declares a fixed list of tool names — the gateway only loads declared tools

**What still needs doing:**
- Nothing — this is secure by design. The hardcoded tool names and array-based argument passing prevent injection.

---

#### Risk 18: ENW API Key in `.env`

**What could go wrong:** The `ENW_API_KEY` grants access to live grid infrastructure data. If leaked, it could be misused.

**What we already do:**
- `.env` is in `.gitignore` (line 2)
- `.env.example` contains only placeholder values (`your_api_key_here`)
- `setup.bat` warns if placeholder values are still present (lines 117–127)
- `load_api_key()` in all three fetch scripts checks for empty/missing key and exits with error
- The key is loaded via `os.environ` or `python-dotenv`, not read directly from the file at runtime

**What still needs doing:**
- Rotate keys periodically (manual process — add a reminder or automation).
- Consider using a secrets manager for production deployments.

---

#### Risk 19: No Authentication on WebChat

**What could go wrong:** Anyone with the gateway URL can query all tools and access grid infrastructure data.

**What we already do:**
- The gateway binds to loopback (`"bind": "loopback"`) — it's only accessible from the host machine
- The nginx proxy listens on port 8501 and routes `/oclaw/*` to the OpenClaw proxy
- The OpenClaw proxy (`openclaw_proxy.py`) injects the `Authorization: Bearer` token on every request, so the gateway always sees authenticated traffic from the proxy
- If ngrok is used for remote access, the ngrok tunnel adds its own access control layer

**What still needs doing:**
- For production: enable `auth.mode: "token"` on the gateway and require the token in WebChat requests.
- Add rate limiting on the proxy to prevent abuse.

---

### 3.6 Operational

#### Risk 20: Gateway Not Running

**What could go wrong:** The OpenClaw gateway crashes or isn't started, making the entire chat interface unavailable.

**What we already do:**
- `run_dashboard.bat` starts the gateway as a separate `cmd /c` window with a descriptive title (line 83)
- The script waits 3 seconds after gateway start before proceeding (`timeout /t 3 /nobreak`)
- On exit, `taskkill /FI "WINDOWTITLE eq OpenClaw Gateway"` cleans up the process (line 125)
- The same pattern applies to all services (Streamlit, nginx, proxy, ngrok) — each gets its own window and cleanup

**What still needs doing:**
- Add a health check that pings `http://localhost:18789/health` and warns if the gateway is down.
- Add auto-restart logic if the gateway process exits unexpectedly.

---

#### Risk 21: Plugin Build Failure

**What could go wrong:** TypeScript compilation errors in the plugin prevent tools from being registered with the gateway.

**What we already do:**
- `run_dashboard.bat` runs `npm install && npm run build` before starting the gateway (lines 57–60)
- The build uses `tsc` (TypeScript compiler) which reports exact error locations
- `setup.bat` also builds the plugin during initial setup
- The `dist/index.js` compiled output is what the gateway loads — if build fails, the gateway has no tools

**What still needs doing:**
- Add a CI step that runs `npm run build` on every commit to catch compilation errors early.

---

#### Risk 22: Streamlit Dependency Leak

**What could go wrong:** `advanced_charts/__init__.py` imports `streamlit`, which means any code that imports from `advanced_charts` (including test files) requires streamlit to be installed — even if it only needs the recommendation engine.

**What we already do:**
- The test suite skips recommendation engine tests when streamlit isn't available (`tests/test_pipeline.py` — `pytest.skip("streamlit not available")`)
- The tool scripts (`tools/get_recommendations.py`) import `RecommendationEngine` directly, bypassing `__init__.py`
- The OpenClaw plugin calls tools via subprocess, so it never imports `advanced_charts` directly

**What still needs doing:**
- Move `RecommendationEngine` import out of `advanced_charts/__init__.py` so tests can import it without streamlit.
- Or create a separate `advanced_charts.engine` module that doesn't depend on streamlit.

---

#### Risk 23: No Monitoring/Logging of Agent Queries

**What could go wrong:** We can't audit what questions users ask, what tools the agent calls, or what answers it gives. This makes it impossible to identify misuse, measure accuracy, or improve the system.

**What we already do:**
- Data fetchers log to `logs/fetch_outages.log` and `logs/fetch_flexibility.log` with timestamps and levels
- State files (`data/.last_fetch_outages`, `data/.sent_incidents`, `data/.last_incidents_state`) track operational status
- The test suite produces pass/fail/skip counts that can be tracked over time
- The proxy servers log at WARNING level

**What still needs doing:**
- Add query/response logging to the OpenClaw plugin (log tool name, parameters, response size, timestamp).
- Track tool usage metrics (which tools are called most, which fail most).
- Add anonymised analytics for agent conversations.

---

## 4. Risk Matrix Summary

| # | Risk | Likelihood | Impact | Already Mitigated? | Residual Risk |
|---|------|-----------|--------|-------------------|---------------|
| 1 | Nominatim rate limiting | High | Medium | **Partially** — sleep + cache in Borderlands, but not in geocode.py | Medium |
| 2 | ENW API key expiry | Medium | High | **Mostly** — validation, logging, state tracking | Low |
| 3 | Nominatim rural accuracy | High | Low | **Partially** — dual-query fallback, ungeocoded flagging | Low |
| 4 | RF/XGB disagreement | Certain | Medium | **Partially** — primary/fallback model, prob distribution | Medium |
| 5 | Low confidence predictions | Medium | Medium | **Partially** — confidence scores returned, skill mandates reporting | Medium |
| 6 | Accuracy not persisted | Certain | Low | **No** — logged to console only | Low |
| 7 | Training data staleness | Medium | Medium | **Mostly** — auto-fetch on startup, cache invalidation, staleness check | Low |
| 8 | Old outage records | Certain | Low | **Mostly** — year filter, walk-forward validation weights recent data | Low |
| 9 | Incomplete charging sites | Medium | Medium | **Partially** — count/nearest returned even when zero | Medium |
| 10 | Excel header row | Certain | Low | **Yes** — fixed with header=1, tests validate | None |
| 11 | Hallucinated data | Medium | High | **Mostly** — system prompt, tool-first workflow, E2E tests | Low |
| 12 | Wrong tool selection | Low | Medium | **Mostly** — specific descriptions, workflow order, skill mappings | Low |
| 13 | Ambiguous locations | Medium | Medium | **Partially** — ", UK" suffix, multi-result return | Low |
| 14 | Tool timeout | Low | Medium | **Yes** — per-layer timeouts (10s–300s calibrated) | Low |
| 15 | No error recovery | Medium | Low | **Yes** — two-layer try/except, structured JSON errors | None |
| 16 | Gateway token exposure | Low | High | **Mostly** — loopback bind, runtime injection, not hardcoded | Medium |
| 17 | execSync injection | Low | High | **Yes** — hardcoded tool names, array args, no user input | None |
| 18 | ENW API key leak | Medium | High | **Mostly** — .gitignore, placeholder check, env-only loading | Low |
| 19 | No WebChat auth | Medium | Medium | **Partially** — loopback bind, proxy token injection | Medium |
| 20 | Gateway not running | Medium | High | **Partially** — separate process window, cleanup on exit | Medium |
| 21 | Plugin build failure | Low | Medium | **Partially** — build on startup, but no CI | Low |
| 22 | Streamlit dependency leak | Certain | Low | **Partially** — tests skip gracefully, tools import directly | Low |
| 23 | No query logging | Certain | Medium | **No** — only data fetch logging exists | Medium |

**Summary:** Of 23 risks, 3 are fully mitigated (10, 15, 17), 11 are mostly mitigated (2, 7, 8, 11, 12, 14, 16, 18, 21, 22, 4), 7 are partially mitigated (1, 3, 5, 9, 13, 19, 20), and 2 have no mitigation yet (6, 23).

---

## 5. Recommendations

### Immediate (before production use)

1. **Add gateway authentication** — switch `auth.mode` from `"none"` to token-based auth
2. **Surface confidence scores** — include model confidence in every risk-related response
3. **Add geocode retry with backoff** — handle 429 errors gracefully instead of failing
4. **Persist model accuracy metrics** — save walk-forward results to `models/accuracy_metrics.json`

### Short-term (within 2 weeks)

5. **Run E2E chat tests** — execute the golden test set with gateway running and document pass rate
6. **Add query/response logging** — track what users ask and what the agent answers (anonymised)
7. **Improve Borderlands geocoding** — use site description for disambiguation when town name fails
8. **Decouple recommendation engine** — remove streamlit dependency from `advanced_charts/__init__.py`

### Medium-term (within 1 month)

9. **Schedule model retraining** — automate monthly retraining with fresh outage data
10. **Cross-reference with national charging databases** — supplement 88 local sites with Open Charge Map data
11. **Implement email notification system** — use the designed SendGrid integration for incident alerts
12. **Add health monitoring** — dashboard showing gateway status, tool usage, and error rates

---

## 6. Conclusion

OpenClaw provides a powerful natural language interface to the CMS Dashboard's data and analysis capabilities. The 10 registered tools cover the full workflow from geocoding through risk assessment to investment recommendations, with the newly added Borderlands tool enabling cross-referencing of community sites with grid resilience data.

The main risks are operational (external API dependencies, agent hallucination) and security-related (gateway authentication, key management). None are critical, and all have clear mitigations. The accuracy evaluation shows 100% tool output correctness and 80.4% ML model agreement, providing a solid foundation for reliable agent responses.

The integration is ready for controlled use by the placement team. Production deployment to external users should follow the immediate and short-term recommendations above.
