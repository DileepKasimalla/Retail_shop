"""Vercel serverless entry point.

Vercel turns every file under `api/` into a function and, for Python, serves
any module-level ASGI app it finds named `app`. The whole FastAPI application
lives in `backend/`, so this shim puts that directory on the import path and
re-exports the app.

`vercel.json` rewrites `/api/(.*)` onto this one function. Vercel has two
different behaviours for what path the function then sees:

  * it forwards the *original* path (`/api/customers`), or
  * it forwards the *rewritten destination* (`/api/index`), which the build log
    warns about for backend framework projects.

Under the second behaviour every FastAPI route would 404, since nothing is
registered at `/api/index`. So the rewrite also carries the original path in a
query parameter, and the middleware below restores it when needed. When Vercel
forwards the original path the middleware does nothing, so this is correct
either way.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path
from urllib.parse import parse_qs, urlencode

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    from app.main import app  # noqa: E402  (path setup must run first)
except Exception:  # pragma: no cover - only on a misconfigured deployment
    # An exception escaping this module makes Vercel serve an opaque
    # FUNCTION_INVOCATION_FAILED page with no clue as to the cause. Print the
    # traceback (it lands in the runtime logs) and stand up a placeholder app
    # so the error reaches the browser as a readable 500 instead.
    _STARTUP_ERROR = traceback.format_exc()
    print(_STARTUP_ERROR, file=sys.stderr, flush=True)

    async def app(scope, receive, send):  # type: ignore[misc]
        if scope["type"] != "http":
            return
        body = (
            b"The API failed to start. This is almost always a missing or "
            b"malformed environment variable (SECRET_KEY, DATABASE_URL). "
            b"The full traceback is in the Vercel runtime logs."
        )
        await send({
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({"type": "http.response.body", "body": body})

# Must match the query parameter used in vercel.json's rewrite destination.
_PATH_PARAM = "__vercel_path"
_FUNCTION_PATHS = {"/api/index", "/api/index/"}


class RestoreOriginalPath:
    """Rewrite `/api/index?__vercel_path=customers` back to `/api/customers`.

    A pure-ASGI middleware rather than an `@app.middleware("http")` hook,
    because this has to run *before* the router matches — an HTTP middleware
    would only see the request after routing had already failed.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") in _FUNCTION_PATHS:
            params = parse_qs(
                scope.get("query_string", b"").decode("latin-1"),
                keep_blank_values=True,
            )
            original = params.pop(_PATH_PARAM, [None])[0]
            if original is not None:
                scope = dict(scope)
                scope["path"] = "/api/" + original.lstrip("/")
                scope["raw_path"] = scope["path"].encode("utf-8")
                # Drop the marker so handlers see only their own query params.
                scope["query_string"] = urlencode(params, doseq=True).encode("latin-1")
        await self.app(scope, receive, send)


# Added at import time: Starlette freezes the middleware stack once the app
# starts handling requests. Skipped when `app` is the plain-callable fallback
# above, which answers every path identically anyway.
if hasattr(app, "add_middleware"):
    app.add_middleware(RestoreOriginalPath)

__all__ = ["app"]
