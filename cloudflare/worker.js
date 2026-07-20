/**
 * Cloudflare Worker — CMS Dashboard Tunnel Redirect
 *
 * Reads the latest tunnel URL from KV and redirects visitors.
 * The KV key "tunnel_url" is updated by capture_tunnel_url.py on each restart.
 *
 * Setup:
 *   1. npx wrangler kv:namespace create TUNNEL_KV
 *   2. Put the returned id into wrangler.toml
 *   3. npx wrangler deploy
 */

export default {
  async fetch(request, env) {
    const url = await env.TUNNEL_KV.get("tunnel_url");

    if (!url) {
      return new Response("No tunnel URL configured yet. Start the dashboard first.", {
        status: 503,
        headers: { "Content-Type": "text/plain" },
      });
    }

    return Response.redirect(url, 302);
  },
};
