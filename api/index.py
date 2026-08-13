"""Vercel serverless entry point.

Vercel turns every file under `api/` into a function and, for Python, serves
any module-level ASGI app it finds named `app`. The whole FastAPI application
lives in `backend/`, so this shim just puts that directory on the import path
and re-exports the app.

Routing is handled by the `/api/(.*)` rewrite in `vercel.json`, which preserves
the original request path — so FastAPI still sees `/api/customers` and every
existing route works unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402  (path setup must run first)

__all__ = ["app"]
