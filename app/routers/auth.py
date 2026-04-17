import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import create_access_token, decode_token, verify_password
from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuditLog, User

router = APIRouter(prefix="/auth", tags=["auth"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@router.post("/login")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    token = create_access_token(
        {"sub": user.user_id, "email": user.email, "role": user.role}
    )

    # Decode to get the session_id that was embedded in the token
    from app.auth import decode_token
    claims = decode_token(token)

    # Update last login timestamp
    user.last_login_at = _utcnow()

    # Immutable audit entry — timestamp set by DB server_default
    ip = request.client.host if request.client else None
    log = AuditLog(
        user_id=user.user_id,
        action="Accessed",
        entity_type="User",
        entity_id=user.user_id,
        detail=json.dumps({"event": "login"}),
        ip_address=ip,
        session_id=claims.get("session_id"),
    )
    db.add(log)
    db.commit()

    return {"access_token": token, "token_type": "bearer"}


@router.post("/refresh")
def refresh_token(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    token = create_access_token(
        {"sub": current_user.user_id, "email": current_user.email, "role": current_user.role}
    )
    db.add(AuditLog(
        user_id=current_user.user_id,
        action="TokenRefreshed",
        entity_type="User",
        entity_id=current_user.user_id,
    ))
    db.commit()
    return {"access_token": token, "token_type": "bearer"}
