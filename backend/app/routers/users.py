"""User management (admins only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import User
from ..schemas import UserCreate, UserOut, UserUpdate
from ..security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


def _active_admin_count(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(User).where(User.is_admin, User.is_active)
    )


@router.get("", response_model=list[UserOut])
def list_users(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="Username cannot be blank.")
    if db.scalar(select(User.id).where(User.username == username)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user named '{username}' already exists.",
        )
    user = User(
        username=username,
        hashed_password=hash_password(payload.password),
        is_admin=payload.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    current: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current.id and (payload.is_active is False or payload.is_admin is False):
        raise HTTPException(
            status_code=400,
            detail="You can't disable or demote your own account. Ask another admin.",
        )
    # Belt and braces for the self-check above: never leave nobody able to
    # manage users.
    losing_admin = user.is_admin and user.is_active and (
        payload.is_active is False or payload.is_admin is False
    )
    if losing_admin and _active_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="There must be at least one active admin.")

    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return user
