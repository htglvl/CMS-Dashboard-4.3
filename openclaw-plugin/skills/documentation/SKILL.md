---
name: documentation
description: Access CMS Dashboard documentation, wiki pages, and project guides
---

# Documentation Skill

When users ask about how the dashboard works, what features are available, or need help understanding the system, use the `get_wiki` tool to retrieve relevant documentation.

## Core Workflow

1. **List topics** — Use `get_wiki(list=true)` to see all available documentation
2. **Get specific topic** — Use `get_wiki(topic="<topic>")` for detailed content
3. **Search docs** — Use `get_wiki(search="<keyword>")` to find specific information

## Available Topics

| Topic Key | Description | When to Use |
|-----------|-------------|-------------|
| `home` | Project overview, tech stack, structure | General questions about the project |
| `dashboard` | Dashboard guide, filters, map interaction | How to use the dashboard |
| `risk` | Risk assessment, ML predictions, vulnerability scores | Questions about risk analysis |
| `spatial` | Haversine distances, buffer zones | Questions about geographic analysis |
| `api` | ENW API, data fetching, live incidents | Questions about data sources |
| `cleaning` | Data cleaning utilities | Questions about data preparation |

## Common Question Patterns

### "What does the dashboard do?"
1. `get_wiki(topic="home")`
2. Summarize the overview and features

### "How do I use the map?"
1. `get_wiki(topic="dashboard")`
2. Explain map controls, filters, and layers

### "What is risk assessment?"
1. `get_wiki(topic="risk")`
2. Explain vulnerability scoring and ML predictions

### "How does the data fetching work?"
1. `get_wiki(topic="api")`
2. Explain ENW API integration and scheduling

### "What are buffer zones?"
1. `get_wiki(topic="spatial")`
2. Explain Haversine distances and 2-mile buffers

### Search for specific terms
1. `get_wiki(search="V2X")` — Find all mentions of V2X
2. `get_wiki(search="XGBoost")` — Find ML model references

## Response Format

When presenting documentation:
- **Quote relevant sections** — Don't paraphrase technical details
- **Include examples** — Show actual commands or code snippets
- **Link to related topics** — Suggest related wiki pages
- **Be concise** — Summarize long sections, link to full docs

## Example Response

> **Dashboard Overview:**
> The CMS Grid Resilience Dashboard analyzes unplanned power outages across the Electricity North West network and maps them against EV charging sites.
>
> **Key Features:**
> - Interactive map with color-coded charging sites
> - Live incident monitoring from ENW API
> - ML risk predictions (Random Forest + XGBoost)
> - Business recommendations for V2X placement
>
> **Getting Started:**
> ```bash
> pip install -r requirements.txt
> streamlit run enhanced_app.py
> ```
>
> For detailed usage, see the [Dashboard Guide](wiki/Dashboard-Guide.md).

## Important Notes

- Always use `get_wiki` tool instead of making up documentation
- If a topic isn't found, list available topics and suggest the closest match
- For tool-specific questions, combine wiki content with tool examples
- Link to the wiki/ directory for full documentation files
