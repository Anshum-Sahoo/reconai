from fastapi import APIRouter, Depends, HTTPException, status
from backend.core.auth import create_session_token, verify_demo_password
from backend.core.config import Settings, get_settings
from backend.schemas.auth import AuthSessionRequest, AuthSessionResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/session",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Create shared demo authentication session",
)
def create_session(
    body: AuthSessionRequest,
    settings: Settings = Depends(get_settings),
) -> AuthSessionResponse:
    """
    Validate provided password against DEMO_ACCESS_PASSWORD using constant-time
    comparison (hmac.compare_digest). Issue short-lived HMAC-SHA256 session token
    signed with separate JWT_SECRET.
    """
    if not verify_demo_password(body.password, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = create_session_token(settings=settings)
    return AuthSessionResponse(**token_data)
