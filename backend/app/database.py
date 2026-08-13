"""Database engine and session management."""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from .config import get_settings

settings = get_settings()

# SQLite needs a special flag when used with a threaded server like uvicorn.
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# On serverless (Vercel) every invocation may run in a fresh sandbox, so a
# client-side connection pool is worse than useless: pooled connections are
# never reused and each cold container holds Postgres slots open until they
# time out, which exhausts the database's connection limit. Use NullPool and
# let the *server-side* pooler (Neon's pgbouncer endpoint) do the pooling.
IS_SERVERLESS = bool(os.getenv("VERCEL"))

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    poolclass=NullPool if IS_SERVERLESS else None,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
