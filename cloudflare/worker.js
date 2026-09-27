/**
 * Cloudflare Worker — CMS Dashboard Reverse Proxy
 *
 * Reads the latest tunnel URL from KV and proxies requests to it.
 * Visitors keep the permanent Worker URL, including for WebSockets.
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

    const publicUrl = new URL(request.url);
    const upstreamUrl = new URL(request.url);
    const tunnel = new URL(url);
    upstreamUrl.protocol = tunnel.protocol;
    upstreamUrl.host = tunnel.host;
    upstreamUrl.port = tunnel.port;

    // Handle redirects here so nginx cannot expose the tunnel hostname.
    const upstreamRequest = new Request(new Request(upstreamUrl, request), {
      redirect: "manual",
    });
    upstreamRequest.headers.set("X-Forwarded-Host", publicUrl.host);
    upstreamRequest.headers.set("X-Forwarded-Proto", publicUrl.protocol.slice(0, -1));

    let response;
    try {
      response = await fetch(upstreamRequest);
    } catch {
      return new Response("Dashboard temporarily unavailable. Please try again shortly.", {
        status: 502,
        headers: { "Content-Type": "text/plain", "Cache-Control": "no-store" },
      });
    }

    // Return the upgrade response intact to preserve its WebSocket connection.
    if (response.status === 101) return response;

    const location = response.headers.get("Location");
    if (location) {
      const destination = new URL(location, upstreamUrl);
      if (destination.hostname === tunnel.hostname) {
        destination.protocol = publicUrl.protocol;
        destination.host = publicUrl.host;
        destination.port = publicUrl.port;
        response = new Response(response.body, response);
        response.headers.set("Location", destination.href);
      }
    }
    return response;
  },
};
