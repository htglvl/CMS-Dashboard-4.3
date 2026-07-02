"""
Reverse proxy that unifies the dashboard and OpenClaw under port 8501.

Routes:
    /           -> 302 redirect to /home
    /home/*     -> Streamlit on localhost:8502
    /oclaw/*    -> OpenClaw on localhost:18789
"""

import sys
import logging
from urllib.parse import urljoin

import requests
from waitress import create_server

# Suppress noisy request logs from waitress in development
logging.getLogger("waitress").setLevel(logging.WARNING)

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
    """Remove hop-by-hop headers from a dict of headers."""
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}


def _build_target_url(base, path_info, query_string):
    """Construct the upstream URL from path info and query string."""
    url = urljoin(base, path_info)
    if query_string:
        url += "?" + query_string
    return url


def app(environ, start_response):
    """WSGI application that proxies requests to the appropriate backend."""
    path = environ.get("PATH_INFO", "/")
    query = environ.get("QUERY_STRING", "")

    # ── Root redirect ────────────────────────────────────────────────────
    if path == "/":
        start_response("302 Found", [("Location", "/home")])
        return [b""]

    # ── Route to OpenClaw ────────────────────────────────────────────────
    if path.startswith("/oclaw"):
        # OpenClaw expects the full /oclaw prefix
        target = _build_target_url(OPENCLAW_URL, path, query)
        return _proxy_request(environ, start_response, target)

    # ── Route to Streamlit (strip /home prefix) ──────────────────────────
    if path.startswith("/home"):
        # Strip /home prefix — Streamlit expects to serve from /
        stripped = path[len("home"):] or "/"
        target = _build_target_url(STREAMLIT_URL, stripped, query)
        return _proxy_request(environ, start_response, target)

    # ── Fallback: redirect to /home ──────────────────────────────────────
    start_response("302 Found", [("Location", "/home")])
    return [b""]


def _proxy_request(environ, start_response, target_url):
    """Forward a WSGI request to the target URL and return the response."""
    method = environ["REQUEST_METHOD"].upper()
    input_stream = environ.get("wsgi.input")

    # Build request headers from WSGI environ
    headers = {}
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            header_name = key[5:].replace("_", "-").title()
            headers[header_name] = value
    if "CONTENT_TYPE" in environ:
        headers["Content-Type"] = environ["CONTENT_TYPE"]
    if "CONTENT_LENGTH" in environ and environ["CONTENT_LENGTH"]:
        headers["Content-Length"] = environ["CONTENT_LENGTH"]

    # Read request body
    body = None
    if input_stream:
        content_length = int(environ.get("CONTENT_LENGTH", 0) or 0)
        if content_length > 0:
            body = input_stream.read(content_length)

    try:
        resp = requests.request(
            method=method,
            url=target_url,
            headers=headers,
            data=body,
            stream=True,
            timeout=120,
            allow_redirects=False,
        )
    except requests.ConnectionError:
        start_response("502 Bad Gateway", [("Content-Type", "text/plain")])
        return [b"Backend service unavailable"]
    except requests.Timeout:
        start_response("504 Gateway Timeout", [("Content-Type", "text/plain")])
        return [b"Backend service timeout"]

    # Build response headers
    resp_headers = []
    for key, value in resp.headers.items():
        if key.lower() not in HOP_BY_HOP:
            resp_headers.append((key, value))

    status_line = f"{resp.status_code} {resp.reason}"
    start_response(status_line, resp_headers)

    return [resp.content]


def main():
    """Start the proxy server."""
    print(f"Starting reverse proxy on http://localhost:{PROXY_PORT}")
    print(f"  /         -> redirect to /home")
    print(f"  /home/*   -> {STREAMLIT_URL}")
    print(f"  /oclaw/*  -> {OPENCLAW_URL}")
    print()

    from waitress import create_server
    server = create_server(app, host="0.0.0.0", port=PROXY_PORT)
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nProxy stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
