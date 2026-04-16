"""
Shared FastAPI dependencies — authentication and current-user resolution.

The login endpoint in app/routers/auth.py issues a JWT containing:
  sub        — the user_id
  email      — for convenience
  role       — for convenience / future RBAC
  exp        — expiry timestamp
  session_id — opaque per-session UUID

get_current_user() extracts the bearer token, decodes it, looks up the User
row, and returns it. Any failure returns 401.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.auth import decode_token
from app.database import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    try:
        claims = decode_token(token)
    except JWTError:
        raise credentials_exception

    user_id = claims.get("sub")
    if not user_id:
        raise credentials_exception

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user or not user.is_active:
        raise credentials_exception

    return user
