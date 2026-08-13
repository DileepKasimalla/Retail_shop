"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .config import get_settings
from .database import IS_SERVERLESS, Base, SessionLocal, engine
from .models import User
from .routers import auth, categories, customers, dashboard, products
from .schemas import MetaOut
from .security import hash_password

logger = logging.getLogger("uvicorn.error")
settings = get_settings()


def _init_db() -> None:
    """Create any missing tables.

    Skipped on serverless, where lifespan runs on every cold start: create_all
    issues a reflection query per table on each one, adding latency to the
    first request and doing nothing useful after the initial deploy. Create the
    schema once from a shell instead (see DEPLOY.md):
        python manage.py init-db
    """
    if IS_SERVERLESS:
        return
    Base.metadata.create_all(bind=engine)


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
        )
        db.add(user)
        db.commit()
        logger.info("Seeded initial admin user '%s' from environment.", user.username)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    _seed_admin()
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
