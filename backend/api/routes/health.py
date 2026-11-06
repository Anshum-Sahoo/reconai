from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.db.session import get_db
from backend.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
)
def health_check(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """
    Check health of the backend application, database connectivity,
    and AI provider status. Never exposes internal credentials.
    """
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "disconnected"

    ai_provider = "gemini" if settings.gemini_api_key else "unavailable"
    ai_fallback = "null_adapter" if not settings.gemini_api_key else None

    status_str = "ok" if db_status == "connected" else "degraded"
    if db_status == "connected" and ai_provider == "unavailable":
        status_str = "degraded"

    return HealthResponse(
        status=status_str,
        version=settings.app_version,
        database=db_status,
        ai_provider=ai_provider,
        ai_fallback=ai_fallback,
    )
