"""Shared FastAPI dependencies (authentication)."""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_access_token

# auto_error=False so we can return a clean 401 with a JSON body ourselves.
_bearer = HTTPBearer(auto_error=False)

_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise _credentials_exception
    try:
        payload = decode_access_token(creds.credentials)
        user_id = payload.get("sub")
        if user_id is None:
            raise _credentials_exception
    except jwt.PyJWTError:
        raise _credentials_exception

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise _credentials_exception
    return user
