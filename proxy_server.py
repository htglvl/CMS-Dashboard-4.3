"""
Simple reverse proxy: forward requests from 8501 to two backends.

    /home/*, /_stcore/*, /component/*, /static/*  -> localhost:8502 (Streamlit)
    /oclaw/*                                      -> localhost:18789 (OpenClaw)

Transparent forwarding — does NOT modify Host header for Streamlit.
"""

import sys
import os
import asyncio
from urllib.parse import urlparse

import aiohttp
from aiohttp import web, ClientSession, WSMsgType

STREAMLIT = "http://localhost:8502"
OPENCLAW = "http://localhost:18789"
PORT = 8501

HOP = frozenset({"connection", "keep-alive", "proxy-authenticate",
                 "proxy-authorization", "te", "trailers",
                 "transfer-encoding", "upgrade"})


def clean(h):
    return {k: v for k, v in h.items() if k.lower() not in HOP}


def read_oclaw_token():
    import json
    p = os.path.join(os.path.expanduser("~"), ".openclaw", "openclaw.json")
    try:
        with open(p) as f:
            return json.load(f).get("gateway", {}).get("auth", {}).get("token", "")
    except Exception:
        return ""


async def ws_proxy(req, target, session):
    """Forward a WebSocket connection."""
    ws_url = target.replace("http://", "ws://").replace("https://", "wss://")
    protos = [p.strip() for p in req.headers.get("Sec-WebSocket-Protocol", "").split(",") if p]

    async def fwd(src, dst):
        try:
            async for m in src:
                if m.type == WSMsgType.TEXT:
                    await dst.send_str(m.data)
                elif m.type == WSMsgType.BINARY:
                    await dst.send_bytes(m.data)
                elif m.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                    break
        except Exception:
            pass
        finally:
            if not dst.closed:
                await dst.close()

    try:
        up = await session.ws_connect(ws_url, headers=clean(dict(req.headers)),
                                      protocols=protos or None)
    except Exception:
        return web.Response(status=502, text="WebSocket error")

    cli = web.WebSocketResponse(protocols=[up.protocol] if up.protocol else ())
    try:
        await cli.prepare(req)
    except Exception:
        await up.close()
        return web.Response(status=502, text="WebSocket error")

    try:
        await asyncio.gather(fwd(up, cli), fwd(cli, up))
    except Exception:
        pass
    finally:
        if not up.closed:
            await up.close()
        if not cli.closed:
            await cli.close()
    return cli


async def http_proxy(req, target, session, oclaw=False):
    """Forward an HTTP request."""
    headers = clean(dict(req.headers))

    # OpenClaw: override Host + inject auth
    if oclaw:
        headers["Host"] = urlparse(target).netloc
        token = req.app.get("token", "")
        if token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {token}"

    body = await req.read()

    try:
        async with session.request(
            method=req.method, url=target, headers=headers,
            data=body or None, allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            rh = clean(dict(resp.headers))
            rh.pop("Content-Encoding", None)
            rh.pop("Content-Length", None)
            rh.pop("Content-Security-Policy", None)
            rh.pop("X-Content-Security-Policy", None)

            # OpenClaw HTML: inject auth
            if oclaw:
                token = req.app.get("token", "")
                ct = resp.headers.get("Content-Type", "")
                if token and "text/html" in ct:
                    body_bytes = await resp.read()
                    js = '<script>window.__OPENCLAW_NATIVE_CONTROL_AUTH__={"token":"' + token + '"};</script>'
                    if b"</head>" in body_bytes:
                        body_bytes = body_bytes.replace(b"</head>", js.encode() + b"</head>")
                    return web.Response(status=resp.status, headers=rh, body=body_bytes)

            out = web.StreamResponse(status=resp.status, headers=rh)
            await out.prepare(req)
            try:
                async for chunk in resp.content.iter_any():
                    await out.write(chunk)
                await out.write_eof()
            except (ConnectionResetError, ConnectionError, OSError):
                pass
            return out
    except aiohttp.ClientConnectorError:
        return web.Response(status=502, text="Backend unavailable")
    except Exception:
        return web.Response(status=500, text="Proxy error")


async def route(req):
    path = req.path
    q = req.query_string
    s = req.app["session"]
    ws = req.headers.get("Upgrade", "").lower() == "websocket"

    if path == "/":
        raise web.HTTPFound("/home")

    # Streamlit internal
    if path.startswith("/_stcore") or path.startswith("/component") or path.startswith("/static") or path == "/favicon.ico":
        t = STREAMLIT + path + ("?" + q if q else "")
        return await ws_proxy(req, t, s) if ws else await http_proxy(req, t, s)

    # OpenClaw
    if path.startswith("/oclaw"):
        sub = path[len("/oclaw"):] or "/"
        t = OPENCLAW + sub + ("?" + q if q else "")
        if ws:
            return await ws_proxy(req, t, s)
        if path == "/oclaw":
            raise web.HTTPFound("/oclaw/" + ("?" + q if q else ""))
        return await http_proxy(req, t, s, oclaw=True)

    # Dashboard — Streamlit serves from /home (no strip needed)
    if path.startswith("/home"):
        t = STREAMLIT + path + ("?" + q if q else "")
        return await ws_proxy(req, t, s) if ws else await http_proxy(req, t, s)

    raise web.HTTPFound("/home")


async def on_start(app):
    app["session"] = ClientSession()
    app["token"] = read_oclaw_token()


async def on_stop(app):
    await app["session"].close()


def main():
    print(f"Proxy: http://localhost:{PORT}")
    print(f"  /home  -> {STREAMLIT}")
    print(f"  /oclaw -> {OPENCLAW}")
    print()

    app = web.Application(client_max_size=100 * 1024 * 1024)
    app.on_startup.append(on_start)
    app.on_cleanup.append(on_stop)
    app.router.add_route("*", "/{path:.*}", route)

    try:
        web.run_app(app, host="0.0.0.0", port=PORT, print=None)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
