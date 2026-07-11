import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";
import { execSync } from "node:child_process";
import path from "node:path";

// Resolve project root: one level up from this plugin directory
const PROJECT_ROOT = process.env.PROJECT_ROOT || path.resolve(__dirname, "..");
const TOOLS_DIR = path.join(PROJECT_ROOT, "tools");
const VENV_PYTHON = path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe");

/** Run a Python tool script and return its stdout. */
function runPythonTool(toolName: string, args: string[] = []): string {
  const scriptPath = path.join(TOOLS_DIR, `${toolName}.py`);
  const argStr = args.join(" ");
  const command = `"${VENV_PYTHON}" "${scriptPath}" ${argStr}`;

  try {
    const stdout = execSync(command, {
      encoding: "utf-8",
      timeout: 120_000,
      cwd: PROJECT_ROOT,
    });
    return stdout.trim();
  } catch (err: any) {
    return JSON.stringify({ error: err.message, tool: toolName });
  }
}

export default defineToolPlugin({
  id: "cms-dashboard",
  name: "CMS Dashboard Tools",
  description: "Grid resilience analysis tools for the CMS Dashboard",
  version: "1.0.0",

  tools: (tool) => [
    // ── geocode ─────────────────────────────────────────────────────────
    tool({
      name: "geocode",
      label: "Geocode Location",
      description:
        "Convert a place name, address, or postcode to latitude/longitude coordinates. Use this FIRST when a user mentions a location by name.",
      parameters: Type.Object({
        query: Type.String({
          description: "Place name, address, or postcode (e.g. 'Lancaster', 'LA1 1YW', 'Kendal')",
        }),
        limit: Type.Optional(
          Type.Number({ description: "Max number of results to return (default: 3)", default: 3 })
        ),
      }),
      async execute({ query, limit }) {
        const args: string[] = ["--query", query];
        if (limit) args.push("--limit", String(limit));
        return runPythonTool("geocode", args);
      },
    }),

    // ── query_risk ──────────────────────────────────────────────────────
    tool({
      name: "query_risk",
      label: "Query Risk",
      description:
        "Query ML risk predictions for a location (lat/lon) or district name. Returns risk level, confidence, and probability scores.",
      parameters: Type.Object({
        lat: Type.Optional(Type.Number({ description: "Latitude" })),
        lon: Type.Optional(Type.Number({ description: "Longitude" })),
        district: Type.Optional(Type.String({ description: "District name (e.g. 'Lancaster')" })),
        top: Type.Optional(Type.Number({ description: "Number of results", default: 10 })),
      }),
      async execute({ lat, lon, district, top }) {
        const args: string[] = [];
        if (lat !== undefined && lon !== undefined) {
          args.push("--lat", String(lat), "--lon", String(lon));
        }
        if (district) args.push("--district", district);
        if (top) args.push("--top", String(top));
        return runPythonTool("query_risk", args);
      },
    }),

    // ── query_outages ───────────────────────────────────────────────────
    tool({
      name: "query_outages",
      label: "Query Outages",
      description:
        "Query historic outage records (309k+). Filter by district, location (lat/lon with radius), year, cause, or minimum duration.",
      parameters: Type.Object({
        district: Type.Optional(Type.String({ description: "District name" })),
        lat: Type.Optional(Type.Number({ description: "Latitude for proximity search" })),
        lon: Type.Optional(Type.Number({ description: "Longitude for proximity search" })),
        radius: Type.Optional(Type.Number({ description: "Search radius in km (default: 15)", default: 15 })),
        year: Type.Optional(Type.Number({ description: "Year filter" })),
        cause: Type.Optional(Type.String({ description: "Outage cause category" })),
        min_duration: Type.Optional(Type.Number({ description: "Minimum duration in hours" })),
        top: Type.Optional(Type.Number({ description: "Number of results", default: 10 })),
        sort: Type.Optional(
          Type.Union([Type.Literal("duration"), Type.Literal("customers"), Type.Literal("date")], {
            description: "Sort field",
            default: "duration",
          })
        ),
      }),
      async execute({ district, lat, lon, radius, year, cause, min_duration, top, sort }) {
        const args: string[] = [];
        if (district) args.push("--district", district);
        if (lat !== undefined) args.push("--lat", String(lat));
        if (lon !== undefined) args.push("--lon", String(lon));
        if (radius !== undefined) args.push("--radius", String(radius));
        if (year !== undefined) args.push("--year", String(year));
        if (cause) args.push("--cause", cause);
        if (min_duration !== undefined) args.push("--min-duration", String(min_duration));
        if (top) args.push("--top", String(top));
        if (sort) args.push("--sort", sort);
        return runPythonTool("query_outages", args);
      },
    }),

    // ── get_live_incidents ───────────────────────────────────────────────
    tool({
      name: "get_live_incidents",
      label: "Live Incidents",
      description: "Retrieve current active power incidents from the ENW live incident feed.",
      parameters: Type.Object({}),
      async execute() {
        return runPythonTool("get_live_incidents");
      },
    }),

    // ── get_recommendations ─────────────────────────────────────────────
    tool({
      name: "get_recommendations",
      label: "Recommendations",
      description:
        "Get AI-generated recommendations for V2X placement, chargepoint placement, grid resilience, or all.",
      parameters: Type.Object({
        type: Type.Optional(
          Type.Union([Type.Literal("v2x"), Type.Literal("chargepoint"), Type.Literal("all")], {
            description: "Recommendation type",
            default: "all",
          })
        ),
      }),
      async execute({ type }) {
        const args: string[] = [];
        if (type) args.push("--type", type);
        return runPythonTool("get_recommendations", args);
      },
    }),

    // ── query_charging_sites ────────────────────────────────────────────
    tool({
      name: "query_charging_sites",
      label: "Charging Sites",
      description:
        "Look up EV charging sites. Filter by category or find sites near a coordinate.",
      parameters: Type.Object({
        category: Type.Optional(Type.String({ description: "Site category: V2X, Building-supplied, Other" })),
        near_lat: Type.Optional(Type.Number({ description: "Latitude for proximity search" })),
        near_lon: Type.Optional(Type.Number({ description: "Longitude for proximity search" })),
        radius: Type.Optional(Type.Number({ description: "Search radius in km", default: 5 })),
        top: Type.Optional(Type.Number({ description: "Number of results", default: 10 })),
      }),
      async execute({ category, near_lat, near_lon, radius, top }) {
        const args: string[] = [];
        if (category) args.push("--category", category);
        if (near_lat !== undefined) args.push("--near-lat", String(near_lat));
        if (near_lon !== undefined) args.push("--near-lon", String(near_lon));
        if (radius !== undefined) args.push("--radius", String(radius));
        if (top) args.push("--top", String(top));
        return runPythonTool("query_charging_sites", args);
      },
    }),

    // ── get_wiki ────────────────────────────────────────────────────────
    tool({
      name: "get_wiki",
      label: "Wiki",
      description:
        "Retrieve dashboard documentation and wiki pages. Search by topic or keyword.",
      parameters: Type.Object({
        topic: Type.Optional(
          Type.Union(
            [
              Type.Literal("home"),
              Type.Literal("dashboard"),
              Type.Literal("risk"),
              Type.Literal("spatial"),
              Type.Literal("api"),
              Type.Literal("cleaning"),
            ],
            { description: "Wiki topic" }
          )
        ),
        search: Type.Optional(Type.String({ description: "Search keyword across all wiki pages" })),
        list: Type.Optional(Type.Boolean({ description: "List all available wiki topics" })),
      }),
      async execute({ topic, search, list }) {
        const args: string[] = [];
        if (topic) args.push("--topic", topic);
        if (search) args.push("--search", search);
        if (list) args.push("--list");
        return runPythonTool("get_wiki", args);
      },
    }),

    // ── summarize_district ──────────────────────────────────────────────
    tool({
      name: "summarize_district",
      label: "District Summary",
      description:
        "Full district analysis: combines risk predictions, outage history, and charging sites for a district.",
      parameters: Type.Object({
        district: Type.String({ description: "District name (e.g. 'Lancaster')" }),
      }),
      async execute({ district }) {
        return runPythonTool("summarize_district", ["--district", district]);
      },
    }),

    // ── check_new_incidents ─────────────────────────────────────────────
    tool({
      name: "check_new_incidents",
      label: "Check Incidents",
      description:
        "Check for new incidents since the last check. Returns risk context, nearby chargepoints, and historic outage data for affected areas.",
      parameters: Type.Object({}),
      async execute() {
        return runPythonTool("check_new_incidents");
      },
    }),

    // ── clean_borderlands ─────────────────────────────────────────────
    tool({
      name: "clean_borderlands",
      label: "Borderlands Sites",
      description:
        "Clean and geocode the Borderlands Long List of highly feasible chargepoint sites. Optionally cross-reference with risk predictions, existing chargepoints, and recommendation engine. Use this when asked about Borderlands sites, community chargepoint locations, or the Borderlands BOOST project.",
      parameters: Type.Object({
        top: Type.Optional(
          Type.Number({ description: "Limit number of sites returned (default: all)" })
        ),
        local_authority: Type.Optional(
          Type.String({ description: "Filter by local authority area (e.g. 'Cumberland', 'Northumberland')" })
        ),
        cross_ref: Type.Optional(
          Type.Boolean({ description: "Cross-reference with risk/charging/recommendation data", default: false })
        ),
        radius: Type.Optional(
          Type.Number({ description: "Cross-reference radius in km (default: 10)", default: 10 })
        ),
      }),
      async execute({ top, local_authority, cross_ref, radius }) {
        const args: string[] = [];
        if (top !== undefined) args.push("--top", String(top));
        if (local_authority) args.push("--local-authority", local_authority);
        if (cross_ref) args.push("--cross-ref");
        if (radius !== undefined) args.push("--radius", String(radius));
        return runPythonTool("clean_borderlands", args);
      },
    }),

    // ── tag_counties ─────────────────────────────────────────────────────
    tool({
      name: "tag_counties",
      label: "County Lookup",
      description:
        "Check which UK ceremonial county a lat/lon belongs to. Supports single-point lookup or bulk tagging a CSV file (adds ceremonial_county column). Use this to find which county outages or charging sites are in.",
      parameters: Type.Object({
        lat: Type.Optional(Type.Number({ description: "Latitude for single-point lookup" })),
        lon: Type.Optional(Type.Number({ description: "Longitude for single-point lookup" })),
        bulk: Type.Optional(Type.String({ description: "CSV file path for bulk tagging (must have latitude/longitude columns)" })),
        output: Type.Optional(Type.String({ description: "Output CSV path for bulk mode (default: overwrite input)" })),
      }),
      async execute({ lat, lon, bulk, output }) {
        const args: string[] = [];
        if (bulk) {
          args.push("--bulk", bulk);
          if (output) args.push("--output", output);
        } else if (lat !== undefined && lon !== undefined) {
          args.push("--lat", String(lat), "--lon", String(lon));
        } else {
          return JSON.stringify({
            error: "Provide lat/lon for single lookup, or bulk=<csv_path> for bulk tagging",
          });
        }
        return runPythonTool("tag_counties", args);
      },
    }),
  ],
});

// System prompt injection to tell the LLM about available tools
export const hooks = {
  gateway_start: async (api: any) => {
    api.session.workflow.enqueueNextTurnInjection({
      content: `You are a grid resilience analyst for the CMS Dashboard. You have access to specialized tools for analyzing power grid data in North West England.

AVAILABLE TOOLS (USE THESE INSTEAD OF GENERIC COMMANDS):
- geocode: Convert place names to lat/lon coordinates. USE THIS FIRST when user mentions a location.
- query_risk: Get ML risk predictions for a location (by lat/lon or district name)
- query_outages: Query historic outage records (309k+). Supports lat/lon proximity search.
- query_charging_sites: Find EV charging sites near a location or by category
- get_recommendations: Get AI-generated V2X and chargepoint placement recommendations
- get_live_incidents: Get current active power incidents
- summarize_district: Full district analysis (risk + outages + sites)
- get_wiki: Dashboard documentation
- check_new_incidents: Check for new incidents
- clean_borderlands: Clean and geocode Borderlands Long List sites. Cross-ref with risk/charging/recommendations.
- tag_counties: Check which UK ceremonial county a lat/lon belongs to. Single lookup or bulk CSV tagging.

WORKFLOW FOR LOCATION QUERIES:
1. When user mentions a place name → call geocode(query="<place>") first
2. Use returned lat/lon for subsequent tool calls
3. Call query_risk, query_charging_sites, query_outages with the coordinates
4. Combine results into a comprehensive answer

EXAMPLE: "What's the risk in Lancaster?"
→ geocode(query="Lancaster") → get lat/lon
→ query_risk(lat=54.05, lon=-2.80) → get risk data
→ query_charging_sites(near_lat=54.05, near_lon=-2.80, radius=10) → find chargers
→ query_outages(lat=54.05, lon=-2.80, radius=15) → get outage history

WORKFLOW FOR COUNTY-LEVEL ANALYSIS:
To find which county outages or charging sites are in, use tag_counties in bulk mode.
This adds a "ceremonial_county" column to the CSV so you can group/filter by county.

EXAMPLE: "Which county has the most unplanned outages?"
→ tag_counties(bulk="data/df_cleaned.csv") → bulk-tag all outages with counties
→ Then read the CSV and group by ceremonial_county to count outages per county

EXAMPLE: "Tag all charging sites with their county"
→ tag_counties(bulk="data/all_charging_sites.csv") → adds ceremonial_county column

EXAMPLE: "What county is this specific outage in?"
→ tag_counties(lat=54.89, lon=-2.93) → returns ceremonial_county for that point

IMPORTANT: Always use these tools instead of writing Python scripts or using PowerShell commands. The tools return structured JSON data that you can summarize for the user.`,
      tag: "cms-system-prompt",
    });
  },
};
