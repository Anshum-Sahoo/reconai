from pydantic import BaseModel, Field


class AuthSessionRequest(BaseModel):
    password: str = Field(..., description="Shared demo access password")


class AuthSessionResponse(BaseModel):
    session_token: str = Field(..., description="HMAC-SHA256 session token")
    expires_at: str = Field(..., description="ISO 8601 UTC timestamp of token expiry")
