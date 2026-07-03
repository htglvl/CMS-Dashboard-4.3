"""
OpenClaw reverse proxy — port 8503.

Handles /oclaw/* requests:
  - Strips /oclaw prefix
  - Injects auth token header
  - Injects __OPENCLAW_NATIVE_CONTROL_AUTH__ into HTML
  - Strips CSP header
  - Proxies WebSocket connections
"""

import sys, os, asyncio, logging, json
from urllib.parse import urlparse
import aiohttp
from aiohttp import web, ClientSession, WSMsgType

OPENCLAW = "http://localhost:18789"
PORT = 8503

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def read_oclaw_token():
    p = os.path.join(os.path.expanduser("~"), ".openclaw", "openclaw.json")
    try:
        with open(p) as f:
            return json.load(f).get("gateway", {}).get("auth", {}).get("token", "")
    except Exception:
        return ""


HOP = frozenset({"connection", "keep-alive", "proxy-authenticate",
                 "proxy-authorization", "te", "trailers",
                 "transfer-encoding", "upgrade"})


def clean(headers):
    return {k: v for k, v in headers.items() if k.lower() not in HOP}


async def ws_proxy(req, target_url, session):
    ws_url = target_url.replace("http://", "ws://")
    try:
        up = await session.ws_connect(ws_url, headers=clean(dict(req.headers)))
    except Exception as e:
        return web.Response(status=502, text=f"WS error: {e}")

    cli = web.WebSocketResponse(protocols=[up.protocol] if up.protocol else ())
    try:
        await cli.prepare(req)
    except Exception:
        await up.close()
        return web.Response(status=502, text="WS prepare error")

    async def fwd(src, dst):
        try:
            async for msg in src:
                if msg.type == WSMsgType.TEXT:
                    await dst.send_str(msg.data)
                elif msg.type == WSMsgType.BINARY:
                    await dst.send_bytes(msg.data)
                elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                    break
        except Exception:
            pass
        finally:
            if not dst.closed:
                await dst.close()

    try:
        await asyncio.gather(fwd(up, cli), fwd(cli, up))
    finally:
        if not up.closed:
            await up.close()
        if not cli.closed:
            await cli.close()
    return cli


async def http_proxy(req, target_url, session, token):
    headers = clean(dict(req.headers))
    headers["Host"] = urlparse(target_url).netloc
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = await req.read()

    try:
        async with session.request(
            method=req.method, url=target_url, headers=headers,
            data=body or None, allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            rh = clean(dict(resp.headers))
            rh.pop("Content-Encoding", None)
            rh.pop("Content-Length", None)
            rh.pop("Content-Security-Policy", None)
            rh.pop("X-Content-Security-Policy", None)

            ct = resp.headers.get("Content-Type", "")
            if token and "text/html" in ct:
                body_bytes = await resp.read()
                js = f'<script>window.__OPENCLAW_NATIVE_CONTROL_AUTH__={{"token":"{token}"}};</script>'
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
        return web.Response(status=502, text="OpenClaw unavailable")
    except Exception as e:
        return web.Response(status=500, text=f"Proxy error: {e}")


async def route(req):
    path = req.path
    q = req.query_string
    s = req.app["session"]
    token = req.app["token"]
    is_ws = req.headers.get("Upgrade", "").lower() == "websocket"

    # Strip /oclaw prefix — nginx forwards full path
    sub = path[len("/oclaw"):] if path.startswith("/oclaw") else path
    sub = sub or "/"
    target = OPENCLAW + sub + ("?" + q if q else "")

    if is_ws:
        return await ws_proxy(req, target, s)
    return await http_proxy(req, target, s, token)


async def on_start(app):
    app["session"] = ClientSession()
    app["token"] = read_oclaw_token()
    print(f"OpenClaw proxy: http://localhost:{PORT} -> {OPENCLAW}")


async def on_stop(app):
    await app["session"].close()


def main():
    app = web.Application(client_max_size=100 * 1024 * 1024)
    app.on_startup.append(on_start)
    app.on_cleanup.append(on_stop)
    app.router.add_route("*", "/{path:.*}", route)

    try:
        web.run_app(app, host="127.0.0.1", port=PORT, print=None)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
