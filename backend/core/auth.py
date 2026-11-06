import hmac
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.config import Settings, get_settings

security_bearer = HTTPBearer(auto_error=False)


def verify_demo_password(provided_password: str, settings: Settings) -> bool:
    """
    Validate provided password against backend-only DEMO_ACCESS_PASSWORD
    using constant-time comparison to prevent timing attacks.
    """
    if not provided_password:
        return False
    return hmac.compare_digest(
        provided_password.encode("utf-8"),
        settings.demo_access_password.encode("utf-8"),
    )


def create_session_token(
    settings: Settings,
    subject: str = "demo_principal",
    expires_delta: Optional[timedelta] = None,
) -> Dict[str, Any]:
    """
    Create an HMAC-SHA256 signed JWT session token using separate JWT_SECRET.
    Never exposes backend secrets.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(hours=settings.session_token_ttl_hours)

    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "session",
    }

    encoded_jwt = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return {
        "session_token": encoded_jwt,
        "expires_at": expire.isoformat(),
    }


def verify_session_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """
    FastAPI security dependency to verify JWT session token.
    Enforces Authorization: Bearer {session_token} on protected routes.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing session token. Authorization header required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub"]},
        )
        if payload.get("sub") != "demo_principal":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate session token",
            headers={"WWW-Authenticate": "Bearer"},
        )
