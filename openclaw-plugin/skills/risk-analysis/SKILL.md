---
name: risk-analysis
description: Analyze grid resilience risk for locations in North West England
---

# Risk Analysis Skill

When users ask about risk, outages, or charging sites for a location, follow this workflow.

## Core Workflow

1. **Geocode first** — Always convert place names to coordinates using `geocode`
2. **Get risk data** — Query risk at those coordinates using `query_risk`
3. **Find nearby chargers** — Search using `query_charging_sites` with lat/lon
4. **Get outage history** — Search using `query_outages` with lat/lon/radius
5. **Generate recommendations** — Use `get_recommendations` if asked

## Tool Usage

### geocode
- Use FIRST when user mentions a place by name
- Returns lat/lon coordinates
- Example: `geocode(query="Lancaster")` → `{ lat: 54.0466, lon: -2.7983 }`

### query_risk
- Use lat/lon from geocode for precision
- Returns grid cells with risk levels (High/Medium/Low) and confidence scores
- Example: `query_risk(lat=54.0466, lon=-2.7983, top=5)`

### query_charging_sites
- Use lat/lon from geocode
- Set radius=10 for 10km search area
- Returns site names, categories (V2X, Building-supplied, Other), distances
- Example: `query_charging_sites(near_lat=54.0466, near_lon=-2.7983, radius=10)`

### query_outages
- Use lat/lon from geocode for proximity search
- Set radius=15 for 15km search area
- Returns historic outage records with duration, causes, affected customers
- Example: `query_outages(lat=54.0466, lon=-2.7983, radius=15, top=10)`

### get_recommendations
- Returns V2X upgrades and chargepoint placement recommendations
- Use type="v2x" for V2X upgrades, type="chargepoint" for new placements, type="all" for everything
- Example: `get_recommendations(type="all")`

## Common Question Patterns

### "What's the risk in [place]?"
1. geocode(query="<place>")
2. query_risk(lat=..., lon=..., top=5)
3. query_charging_sites(near_lat=..., near_lon=..., radius=10)
4. query_outages(lat=..., lon=..., radius=15, top=10)
5. Summarize: risk level, nearby chargers, outage history

### "Where should we put new chargers?"
1. get_recommendations(type="chargepoint")
2. For top 3 recommendations, geocode the area and show details

### "Show me V2X upgrade opportunities"
1. get_recommendations(type="v2x")
2. Explain each recommendation with risk and charger context

### "What's the outage history in [place]?"
1. geocode(query="<place>")
2. query_outages(lat=..., lon=..., radius=15, top=10)
3. Summarize: total outages, avg duration, top causes

### "Show me charging sites near [place]"
1. geocode(query="<place>")
2. query_charging_sites(near_lat=..., near_lon=..., radius=10)
3. List sites with names, categories, distances

## Response Format

Always include:
- **Location**: Full name and coordinates
- **Risk Level**: High/Medium/Low with confidence %
- **Nearby Chargers**: Count, names, distances
- **Outage History**: Count, avg duration, total customer-hours
- **Recommendations**: V2X upgrades or new charger placements (if relevant)

## Example Response

> **Lancaster** (54.05°N, 2.80°W)
>
> **Risk Assessment:**
> - 3 high-risk grid cells (85% confidence)
> - 5 medium-risk cells (72% confidence)
>
> **Nearby Charging Infrastructure:**
> - 2 chargers within 10km
> - Lancaster Town Hall (V2X, 1.2km)
> - Morrisons Lancaster (Other, 3.5km)
>
> **Outage History:**
> - 45 historic outages
> - Average duration: 3.2 hours
> - Total customer-hours lost: 12,500
>
> **Recommendation:**
> V2X upgrade at Morrisons Lancaster would provide backup power during outages.

## Important Notes

- Always use geocode FIRST when user mentions a place name
- Use lat/lon coordinates for all subsequent tool calls (more accurate than district names)
- Combine data from multiple tools for comprehensive answers
- Be concise and data-driven — avoid hallucinating data
