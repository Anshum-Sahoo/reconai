from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status ('ok' or 'degraded')")
    version: str = Field(..., description="API version")
    database: str = Field(..., description="Database connection status ('connected' or 'disconnected')")
    ai_provider: str = Field(..., description="AI provider status ('gemini' or 'unavailable')")
    ai_fallback: Optional[str] = Field(None, description="AI fallback adapter if provider is degraded")
