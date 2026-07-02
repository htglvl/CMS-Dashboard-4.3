"""
Reverse proxy that unifies the dashboard and OpenClaw under port 8501.

Routes:
    /           -> 302 redirect to /home
    /home/*     -> Streamlit on localhost:8502
    /oclaw/*    -> OpenClaw on localhost:18789
    /_stcore/*  -> Streamlit on localhost:8502 (internal endpoints)
"""

import sys
import os
import asyncio
import logging
from urllib.parse import urlparse

import aiohttp
from aiohttp import web, ClientSession, WSMsgType

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def _suppress_connection_reset(loop):
    """Suppress noisy ConnectionResetError on Windows when browser closes WebSocket."""
    default_handler = loop.default_exception_handler  # bound method: (context)

    def _handler(loop, context):
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError):
            return  # silently ignore
        default_handler(context)

    loop.set_exception_handler(_handler)

STREAMLIT_URL = "http://localhost:8502"
OPENCLAW_URL = "http://localhost:18789"
PROXY_PORT = 8501


def _read_oclaw_token():
    """Read the OpenClaw gateway token from config."""
    import json
    config_path = os.path.join(os.path.expanduser("~"), ".openclaw", "openclaw.json")
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
        return cfg.get("gateway", {}).get("auth", {}).get("token", "")
    except Exception:
        return ""

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


async def _proxy_ws(request, target_url, session):
    """Proxy a WebSocket connection."""
    ws_target = target_url.replace("http://", "ws://").replace("https://", "wss://")

    # Extract WebSocket subprotocols from client request
    ws_protocols = []
    if "Sec-WebSocket-Protocol" in request.headers:
        ws_protocols = [
            p.strip() for p in request.headers["Sec-WebSocket-Protocol"].split(",")
        ]

    async def forward_ws(source, dest):
        try:
            async for msg in source:
                if msg.type == WSMsgType.TEXT:
                    await dest.send_str(msg.data)
                elif msg.type == WSMsgType.BINARY:
                    await dest.send_bytes(msg.data)
                elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                    break
        except Exception:
            pass
        finally:
            if not dest.closed:
                await dest.close()

    # Step 1: Connect to upstream FIRST to discover accepted protocol
    try:
        upstream_ws = await session.ws_connect(
            ws_target,
            headers=_filter_headers(dict(request.headers)),
            protocols=ws_protocols if ws_protocols else None,
        )
    except Exception as e:
        logger.error(f"WebSocket upstream connection failed: {e}")
        return web.Response(status=502, text="WebSocket proxy error")

    # Step 2: Create client WS with the protocol upstream accepted
    accepted_protocol = upstream_ws.protocol
    client_ws = web.WebSocketResponse(
        protocols=[accepted_protocol] if accepted_protocol else ()
    )

    # Step 3: Prepare client WS — now it knows which protocol to accept
    try:
        await client_ws.prepare(request)
    except Exception as e:
        logger.error(f"WebSocket prepare failed: {e}")
        await upstream_ws.close()
        return web.Response(status=502, text="WebSocket prepare error")

    try:
        await asyncio.gather(
            forward_ws(upstream_ws, client_ws),
            forward_ws(client_ws, upstream_ws),
        )
    except Exception as e:
        logger.error(f"WebSocket proxy error: {e}")
    finally:
        if not upstream_ws.closed:
            await upstream_ws.close()
        if not client_ws.closed:
            await client_ws.close()

    return client_ws


async def _proxy_http(request, target_url, session, inject_auth=False):
    """Proxy an HTTP request."""
    method = request.method
    headers = _filter_headers(dict(request.headers))

    # Set proper Host header for the target
    parsed = urlparse(target_url)
    headers["Host"] = parsed.netloc

    # For OpenClaw requests, inject auth token header
    if inject_auth:
        token = request.app.get("oclaw_token", "")
        if token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {token}"

    body = await request.read()

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
            # Remove encoding headers — iter_any() decompresses the body
            resp_headers.pop("Content-Encoding", None)
            resp_headers.pop("Content-Length", None)

            # For OpenClaw responses, strip CSP so we can inject auth token
            if inject_auth:
                resp_headers.pop("Content-Security-Policy", None)
                resp_headers.pop("X-Content-Security-Policy", None)

            content_type = resp.headers.get("Content-Type", "")
            token = request.app.get("oclaw_token", "")

            # For HTML responses from OpenClaw, inject auth token
            if inject_auth and token and "text/html" in content_type:
                body_bytes = await resp.read()
                auth_script = (
                    '<script>window.__OPENCLAW_NATIVE_CONTROL_AUTH__='
                    '{"token":"' + token + '"};</script>'
                )
                if b"</head>" in body_bytes:
                    body_bytes = body_bytes.replace(b"</head>", auth_script.encode() + b"</head>")
                elif b"<head>" in body_bytes:
                    body_bytes = body_bytes.replace(b"<head>", b"<head>" + auth_script.encode())
                else:
                    body_bytes = auth_script.encode() + body_bytes
                resp_headers.pop("Content-Length", None)
                response = web.Response(
                    status=resp.status,
                    headers=resp_headers,
                    body=body_bytes,
                )
                return response

            response = web.StreamResponse(status=resp.status, headers=resp_headers)
            await response.prepare(request)
            try:
                async for chunk in resp.content.iter_any():
                    await response.write(chunk)
                await response.write_eof()
            except (ConnectionResetError, ConnectionError, OSError):
                pass  # client disconnected
            return response
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
    session = request.app["session"]

    # Root redirect
    if path == "/":
        raise web.HTTPFound("/home")

    # Streamlit internal endpoints (/_stcore/*, /component/*, /static/*, /favicon.ico)
    if path.startswith("/_stcore") or path.startswith("/component") or path.startswith("/static") or path == "/favicon.ico":
        target = _get_target_url(STREAMLIT_URL, path, query)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await _proxy_ws(request, target, session)
        return await _proxy_http(request, target, session)

    # Route to OpenClaw
    if path.startswith("/oclaw"):
        # Redirect /oclaw → /oclaw/ so relative asset paths resolve correctly
        if path == "/oclaw":
            redirect_url = "/oclaw/"
            if query:
                redirect_url += "?" + query
            raise web.HTTPFound(redirect_url)
        # Strip /oclaw/ prefix — OpenClaw serves from /
        stripped = path[len("/oclaw"):] or "/"
        target = _get_target_url(OPENCLAW_URL, stripped, query)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await _proxy_ws(request, target, session)
        return await _proxy_http(request, target, session, inject_auth=True)

    # Route to Streamlit (strip /home prefix)
    if path.startswith("/home"):
        stripped = path[len("/home"):] or "/"
        target = _get_target_url(STREAMLIT_URL, stripped, query)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await _proxy_ws(request, target, session)
        return await _proxy_http(request, target, session)

    # Fallback
    raise web.HTTPFound("/home")


async def on_startup(app):
    _suppress_connection_reset(asyncio.get_running_loop())
    app["session"] = ClientSession()
    app["oclaw_token"] = _read_oclaw_token()
    if app["oclaw_token"]:
        logger.info("OpenClaw token loaded from config")
    else:
        logger.warning("No OpenClaw token found in config")


async def on_cleanup(app):
    await app["session"].close()


def main():
    """Start the proxy server."""
    print(f"Starting reverse proxy on http://localhost:{PROXY_PORT}")
    print(f"  /         -> redirect to /home")
    print(f"  /home/*   -> {STREAMLIT_URL}")
    print(f"  /oclaw/*  -> {OPENCLAW_URL}")
    print(f"  /_stcore  -> {STREAMLIT_URL} (WebSocket support)")
    print()

    app = web.Application(client_max_size=100 * 1024 * 1024)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", "/{path:.*}", handle_request)

    try:
        web.run_app(app, host="127.0.0.1", port=PROXY_PORT, print=None)
    except KeyboardInterrupt:
        print("\nProxy stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
