"""Authentication endpoints."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import (
    ChangePasswordRequest,
    LoginRequest,
    SetupStatus,
    Token,
    UserCreate,
    UserOut,
)
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# --- Very small in-memory login throttle (per-IP). Good enough for a single-shop
# app. For serious multi-instance hosting, put a real rate limiter at the proxy.
_MAX_ATTEMPTS = 8
_WINDOW_SECONDS = 300
_attempts: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    # Behind a trusted proxy you may prefer X-Forwarded-For; keep it simple here.
    return request.client.host if request.client else "unknown"


def _check_throttle(ip: str) -> None:
    now = time.monotonic()
    window = [t for t in _attempts.get(ip, []) if now - t < _WINDOW_SECONDS]
    _attempts[ip] = window
    if len(window) >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait a few minutes and try again.",
        )


def _record_attempt(ip: str) -> None:
    _attempts.setdefault(ip, []).append(time.monotonic())


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Token:
    ip = _client_ip(request)
    _check_throttle(ip)

    user = db.execute(
        select(User).where(User.username == payload.username)
    ).scalar_one_or_none()

    # Constant-ish response: verify against a dummy hash if user missing, to
    # avoid leaking which usernames exist via timing.
    valid = False
    if user and user.is_active:
        valid = verify_password(payload.password, user.hashed_password)
    else:
        verify_password(payload.password, "$2b$12$" + "x" * 53)

    if not valid:
        _record_attempt(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # Success clears the throttle for this IP.
    _attempts.pop(ip, None)
    token = create_access_token(subject=user.id)
    return Token(access_token=token)


def _has_users(db: Session) -> bool:
    return db.scalar(select(User.id).limit(1)) is not None


@router.get("/setup", response_model=SetupStatus)
def setup_status(db: Session = Depends(get_db)) -> SetupStatus:
    """Public: tells the login screen to offer first-run setup instead."""
    return SetupStatus(needs_setup=not _has_users(db))


@router.post("/setup", response_model=Token, status_code=status.HTTP_201_CREATED)
def setup(payload: UserCreate, db: Session = Depends(get_db)) -> Token:
    """Create the first admin on an empty database, and log them in.

    Unauthenticated by necessity — there is nobody to authenticate as yet — so
    it only works while the users table is empty and refuses forever after.
    """
    if db.bind.dialect.name == "postgresql":
        # Serialise concurrent first-run requests so only one admin is created.
        db.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
    if _has_users(db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Setup is already complete. Sign in instead.",
        )
    user = User(
        username=payload.username.strip(),
        hashed_password=hash_password(payload.password),
        is_admin=True,
    )
    db.add(user)
    db.commit()
    return Token(access_token=create_access_token(subject=user.id))


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)) -> User:
    return current


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not verify_password(payload.current_password, current.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current.hashed_password = hash_password(payload.new_password)
    db.add(current)
    db.commit()
