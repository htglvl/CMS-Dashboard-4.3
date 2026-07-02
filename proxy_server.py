"""
Reverse proxy that unifies the dashboard and OpenClaw under port 8501.

Routes:
    /           -> 302 redirect to /home
    /home/*     -> Streamlit on localhost:8502
    /oclaw/*    -> OpenClaw on localhost:18789
    /_stcore/*  -> Streamlit on localhost:8502 (internal endpoints)
"""

import sys
import asyncio
import logging
from urllib.parse import urlparse

import aiohttp
from aiohttp import web, ClientSession, WSMsgType

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

STREAMLIT_URL = "http://localhost:8502"
OPENCLAW_URL = "http://localhost:18789"
PROXY_PORT = 8501

# Hop-by-hop headers that should not be forwarded
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailers",
    "transfer-encoding", "upgrade",
})


def _filter_headers(headers):
    """Remove hop-by-hop headers."""
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}


def _get_target_url(base, path, query_string):
    """Construct target URL."""
    url = base + path
    if query_string:
        url += "?" + query_string
    return url


async def _proxy_ws(request, target_url):
    """Proxy a WebSocket connection."""
    ws_target = target_url.replace("http://", "ws://").replace("https://", "wss://")

    async with ClientSession() as session:
        try:
            async with session.ws_connect(
                ws_target,
                headers=_filter_headers(dict(request.headers)),
            ) as upstream_ws:
                client_ws = web.WebSocketResponse()
                await client_ws.prepare(request)

                async def forward_ws(source, dest):
                    async for msg in source:
                        if msg.type == WSMsgType.TEXT:
                            await dest.send_str(msg.data)
                        elif msg.type == WSMsgType.BINARY:
                            await dest.send_bytes(msg.data)
                        elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                            break
                    await dest.close()

                # Forward in both directions concurrently
                await asyncio.gather(
                    forward_ws(upstream_ws, client_ws),
                    forward_ws(client_ws, upstream_ws),
                )
        except Exception as e:
            logger.error(f"WebSocket proxy error: {e}")
            return web.Response(status=502, text="WebSocket proxy error")

    return client_ws


async def _proxy_http(request, target_url):
    """Proxy an HTTP request."""
    method = request.method
    headers = _filter_headers(dict(request.headers))

    # Set proper Host header for the target
    parsed = urlparse(target_url)
    headers["Host"] = parsed.netloc

    body = await request.read()

    async with ClientSession() as session:
        try:
            async with session.request(
                method=method,
                url=target_url,
                headers=headers,
                data=body if body else None,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                resp_headers = _filter_headers(dict(resp.headers))
                resp_body = await resp.read()

                return web.Response(
                    status=resp.status,
                    headers=resp_headers,
                    body=resp_body,
                )
        except aiohttp.ClientConnectorError:
            return web.Response(status=502, text="Backend service unavailable")
        except asyncio.TimeoutError:
            return web.Response(status=504, text="Backend service timeout")
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            return web.Response(status=500, text="Internal proxy error")


async def handle_request(request):
    """Route requests to the appropriate backend."""
    path = request.path
    query = request.query_string

    # Root redirect
    if path == "/":
        raise web.HTTPFound("/home")

    # Streamlit internal endpoints (/_stcore/*, /favicon.ico)
    if path.startswith("/_stcore") or path == "/favicon.ico":
        target = _get_target_url(STREAMLIT_URL, path, query)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await _proxy_ws(request, target)
        return await _proxy_http(request, target)

    # Route to OpenClaw
    if path.startswith("/oclaw"):
        target = _get_target_url(OPENCLAW_URL, path, query)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await _proxy_ws(request, target)
        return await _proxy_http(request, target)

    # Route to Streamlit (strip /home prefix)
    if path.startswith("/home"):
        stripped = path[len("/home"):] or "/"
        target = _get_target_url(STREAMLIT_URL, stripped, query)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await _proxy_ws(request, target)
        return await _proxy_http(request, target)

    # Fallback
    raise web.HTTPFound("/home")


def main():
    """Start the proxy server."""
    print(f"Starting reverse proxy on http://localhost:{PROXY_PORT}")
    print(f"  /         -> redirect to /home")
    print(f"  /home/*   -> {STREAMLIT_URL}")
    print(f"  /oclaw/*  -> {OPENCLAW_URL}")
    print(f"  /_stcore  -> {STREAMLIT_URL} (WebSocket support)")
    print()

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle_request)

    try:
        web.run_app(app, host="127.0.0.1", port=PROXY_PORT, print=None)
    except KeyboardInterrupt:
        print("\nProxy stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
