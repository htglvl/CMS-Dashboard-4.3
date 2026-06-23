import { Type } from "typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";

const execFileAsync = promisify(execFile);

export default definePluginEntry({
  id: "cms-dashboard",
  name: "CMS Dashboard Tools",
  description: "Grid resilience analysis tools for the CMS Dashboard",

  register(api) {
    /** Run a Python tool script and return its stdout. */
    async function runPythonTool(toolName: string, args: string[] = []): Promise<string> {
      const config = api.getConfig() as any;
      const pythonPath = config?.pythonPath || "python";
      const toolsDir = config?.toolsDir || path.join(process.cwd(), "tools");
      const scriptPath = path.join(toolsDir, `${toolName}.py`);

      try {
        const { stdout, stderr } = await execFileAsync(pythonPath, [scriptPath, ...args], {
          timeout: 120_000,
          maxBuffer: 10 * 1024 * 1024,
        });
        if (stderr) console.error(`[${toolName}] stderr:`, stderr);
        return stdout.trim();
      } catch (err: any) {
        return JSON.stringify({ error: err.message, tool: toolName });
      }
    }

    // ── query_risk ──────────────────────────────────────────────────────
    api.registerTool({
      name: "query_risk",
      description:
        "Query ML risk predictions for a location (lat/lon) or district name. Returns risk level, confidence, and probability scores.",
      parameters: Type.Object({
        lat: Type.Optional(Type.Number({ description: "Latitude" })),
        lon: Type.Optional(Type.Number({ description: "Longitude" })),
        district: Type.Optional(Type.String({ description: "District name (e.g. 'Lancaster')" })),
        top: Type.Optional(Type.Number({ description: "Number of results", default: 10 })),
      }),
      async execute(_id, params) {
        const args: string[] = [];
        if (params.lat !== undefined && params.lon !== undefined) {
          args.push("--lat", String(params.lat), "--lon", String(params.lon));
        }
        if (params.district) args.push("--district", params.district);
        if (params.top) args.push("--top", String(params.top));
        const result = await runPythonTool("query_risk", args);
        return { content: [{ type: "text", text: result }] };
      },
    });

    // ── query_outages ───────────────────────────────────────────────────
    api.registerTool({
      name: "query_outages",
      description:
        "Query historic outage records (309k+). Filter by district, year, cause, or minimum duration.",
      parameters: Type.Object({
        district: Type.Optional(Type.String({ description: "District name" })),
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
      async execute(_id, params) {
        const args: string[] = [];
        if (params.district) args.push("--district", params.district);
        if (params.year !== undefined) args.push("--year", String(params.year));
        if (params.cause) args.push("--cause", params.cause);
        if (params.min_duration !== undefined) args.push("--min-duration", String(params.min_duration));
        if (params.top) args.push("--top", String(params.top));
        if (params.sort) args.push("--sort", params.sort);
        const result = await runPythonTool("query_outages", args);
        return { content: [{ type: "text", text: result }] };
      },
    });

    // ── get_live_incidents ───────────────────────────────────────────────
    api.registerTool({
      name: "get_live_incidents",
      description: "Retrieve current active power incidents from the ENW live incident feed.",
      parameters: Type.Object({}),
      async execute(_id, _params) {
        const result = await runPythonTool("get_live_incidents");
        return { content: [{ type: "text", text: result }] };
      },
    });

    // ── get_recommendations ─────────────────────────────────────────────
    api.registerTool({
      name: "get_recommendations",
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
      async execute(_id, params) {
        const args: string[] = [];
        if (params.type) args.push("--type", params.type);
        const result = await runPythonTool("get_recommendations", args);
        return { content: [{ type: "text", text: result }] };
      },
    });

    // ── query_charging_sites ────────────────────────────────────────────
    api.registerTool({
      name: "query_charging_sites",
      description:
        "Look up EV charging sites. Filter by category or find sites near a coordinate.",
      parameters: Type.Object({
        category: Type.Optional(Type.String({ description: "Site category: V2X, Building-supplied, Other" })),
        near_lat: Type.Optional(Type.Number({ description: "Latitude for proximity search" })),
        near_lon: Type.Optional(Type.Number({ description: "Longitude for proximity search" })),
        radius: Type.Optional(Type.Number({ description: "Search radius in km", default: 5 })),
        top: Type.Optional(Type.Number({ description: "Number of results", default: 10 })),
      }),
      async execute(_id, params) {
        const args: string[] = [];
        if (params.category) args.push("--category", params.category);
        if (params.near_lat !== undefined) args.push("--near-lat", String(params.near_lat));
        if (params.near_lon !== undefined) args.push("--near-lon", String(params.near_lon));
        if (params.radius !== undefined) args.push("--radius", String(params.radius));
        if (params.top) args.push("--top", String(params.top));
        const result = await runPythonTool("query_charging_sites", args);
        return { content: [{ type: "text", text: result }] };
      },
    });

    // ── get_wiki ────────────────────────────────────────────────────────
    api.registerTool({
      name: "get_wiki",
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
      async execute(_id, params) {
        const args: string[] = [];
        if (params.topic) args.push("--topic", params.topic);
        if (params.search) args.push("--search", params.search);
        if (params.list) args.push("--list");
        const result = await runPythonTool("get_wiki", args);
        return { content: [{ type: "text", text: result }] };
      },
    });

    // ── summarize_district ──────────────────────────────────────────────
    api.registerTool({
      name: "summarize_district",
      description:
        "Full district analysis: combines risk predictions, outage history, and charging sites for a district.",
      parameters: Type.Object({
        district: Type.String({ description: "District name (e.g. 'Lancaster')" }),
      }),
      async execute(_id, params) {
        const result = await runPythonTool("summarize_district", ["--district", params.district]);
        return { content: [{ type: "text", text: result }] };
      },
    });

    // ── check_new_incidents ─────────────────────────────────────────────
    api.registerTool({
      name: "check_new_incidents",
      description:
        "Check for new incidents since the last check. Returns risk context, nearby chargepoints, and historic outage data for affected areas.",
      parameters: Type.Object({}),
      async execute(_id, _params) {
        const result = await runPythonTool("check_new_incidents");
        return { content: [{ type: "text", text: result }] };
      },
    });

    // ── System prompt injection on gateway start ────────────────────────
    api.registerHook("gateway_start", async () => {
      api.session.workflow.enqueueNextTurnInjection({
        content: `You are a grid resilience analyst for the CMS Dashboard. You have access to tools for:
- query_risk: ML risk predictions by location or district
- query_outages: Historic outage records (309k+)
- get_live_incidents: Current active power incidents
- get_recommendations: AI-generated V2X and chargepoint placement recommendations
- query_charging_sites: EV charging site locations
- get_wiki: Dashboard documentation and wiki
- summarize_district: Full district analysis (risk + outages + sites)
- check_new_incidents: Check for new incidents and get risk context

Use these tools to answer questions. Be concise and data-driven.
When incidents occur, provide context about the affected area's risk profile and nearby infrastructure.`,
        tag: "cms-system-prompt",
      });
    }, { name: "cms-system-prompt-hook" });
  },
});
