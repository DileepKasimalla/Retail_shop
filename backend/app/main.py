"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, select, text

from .config import get_settings
from .database import IS_SERVERLESS, Base, SessionLocal, engine
from .models import User
from .routers import auth, categories, customers, dashboard, products, users
from .schemas import MetaOut
from .security import hash_password

logger = logging.getLogger("uvicorn.error")
settings = get_settings()


def _init_db() -> None:
    """Create any missing tables.

    On serverless this runs on every cold start, where create_all's
    reflection query per table would add latency for nothing after the first
    deploy. So there, list the existing tables in one query and only call
    create_all when something is missing — which bootstraps a fresh database
    straight from the deployment, with no shell needed.
    """
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    if not IS_SERVERLESS or not set(Base.metadata.tables) <= existing:
        if IS_SERVERLESS:
            logger.info("Creating missing tables: %s", sorted(set(Base.metadata.tables) - existing))
        Base.metadata.create_all(bind=engine)
    if "users" in existing:
        _add_users_is_admin(insp)


def _add_users_is_admin(insp) -> None:
    """Add `users.is_admin` to a database created before roles existed.

    create_all never alters an existing table. Every user from that era was
    the full-power shopkeeper, so they all become admins — nobody loses
    access they had.
    """
    if any(c["name"] == "is_admin" for c in insp.get_columns("users")):
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("UPDATE users SET is_admin = TRUE"))
    logger.info("Added users.is_admin; existing users are now admins.")


def _seed_admin() -> None:
    """Create the first shopkeeper account from env vars, if no user exists."""
    if not (settings.admin_username and settings.admin_password):
        return
    with SessionLocal() as db:
        existing = db.scalar(select(User).limit(1))
        if existing is not None:
            return
        user = User(
            username=settings.admin_username.strip(),
            hashed_password=hash_password(settings.admin_password),
            is_admin=True,
        )
        db.add(user)
        db.commit()
        logger.info("Seeded initial admin user '%s' from environment.", user.username)


_bootstrapped = False


def bootstrap() -> None:
    """Create missing tables and seed the first admin. Idempotent, best-effort.

    Called from lifespan, and also directly by the Vercel entry point
    (api/index.py) so it does not depend on the platform running ASGI
    lifespan events. A transient database error is logged rather than raised:
    escaping here would fail the whole invocation instead of just the one
    request that actually needs the database.
    """
    global _bootstrapped
    if _bootstrapped:
        return
    try:
        _init_db()
        _seed_admin()
        _bootstrapped = True
    except Exception:
        logger.exception("Startup initialisation failed; continuing without it.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,  # we use bearer tokens, not cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(dashboard.router)
app.include_router(products.router)
app.include_router(categories.router)
app.include_router(users.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/meta", response_model=MetaOut, tags=["meta"])
def meta() -> MetaOut:
    return MetaOut(
        app_name=settings.app_name,
        currency_code=settings.currency_code,
        currency_symbol=settings.currency_symbol,
    )
