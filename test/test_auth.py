import time
from datetime import timedelta
import jwt
import pytest
from fastapi import Depends, HTTPException
from fastapi.testclient import TestClient

from backend.core.auth import create_session_token, verify_demo_password, verify_session_token
from backend.core.config import get_settings
from backend.main import app

settings = get_settings()


# Protected test endpoint to verify dependency
@app.get("/api/v1/test-protected")
def protected_endpoint(principal: dict = Depends(verify_session_token)):
    return {"message": "authenticated", "principal": principal}


def test_auth_session_success(client: TestClient):
    """Test successful authentication with valid DEMO_ACCESS_PASSWORD."""
    response = client.post(
        "/api/v1/auth/session",
        json={"password": "test_demo_password_123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "session_token" in data
    assert "expires_at" in data

    # Verify token claims
    decoded = jwt.decode(
        data["session_token"],
        "test_jwt_secret_32_characters_minimum_key!",
        algorithms=["HS256"],
    )
    assert decoded["sub"] == "demo_principal"
    assert decoded["type"] == "session"
    assert decoded["exp"] > decoded["iat"]


def test_auth_session_invalid_password(client: TestClient):
    """Test authentication failure with incorrect password returns 401."""
    response = client.post(
        "/api/v1/auth/session",
        json={"password": "wrong_password_attempt"},
    )
    assert response.status_code == 401
    assert "Invalid access password" in response.json()["detail"]


def test_auth_session_empty_password(client: TestClient):
    """Test authentication failure with empty password returns 401."""
    response = client.post(
        "/api/v1/auth/session",
        json={"password": ""},
    )
    assert response.status_code == 401


def test_protected_route_with_valid_token(client: TestClient):
    """Verify protected endpoint access with valid Bearer session token."""
    login_resp = client.post(
        "/api/v1/auth/session",
        json={"password": "test_demo_password_123"},
    )
    token = login_resp.json()["session_token"]

    response = client.get(
        "/api/v1/test-protected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "authenticated"
    assert response.json()["principal"]["sub"] == "demo_principal"


def test_protected_route_missing_token(client: TestClient):
    """Verify 401 when Authorization header is absent."""
    response = client.get("/api/v1/test-protected")
    assert response.status_code == 401
    assert "Missing session token" in response.json()["detail"]


def test_protected_route_invalid_token_format(client: TestClient):
    """Verify 401 with malformed token."""
    response = client.get(
        "/api/v1/test-protected",
        headers={"Authorization": "Bearer not_a_valid_jwt_token"},
    )
    assert response.status_code == 401


def test_protected_route_wrong_jwt_secret(client: TestClient):
    """Verify 401 when token was signed with an alien secret."""
    alien_token = jwt.encode(
        {"sub": "demo_principal", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        "different_secret_key_that_does_not_match!",
        algorithm="HS256",
    )
    response = client.get(
        "/api/v1/test-protected",
        headers={"Authorization": f"Bearer {alien_token}"},
    )
    assert response.status_code == 401
    assert "Could not validate" in response.json()["detail"]


def test_protected_route_expired_token(client: TestClient):
    """Verify 401 when token is expired."""
    expired_token = jwt.encode(
        {
            "sub": "demo_principal",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
            "type": "session",
        },
        "test_jwt_secret_32_characters_minimum_key!",
        algorithm="HS256",
    )
    response = client.get(
        "/api/v1/test-protected",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_constant_time_password_verification():
    """Verify hmac.compare_digest functionality."""
    assert verify_demo_password("test_demo_password_123", settings) is True
    assert verify_demo_password("wrong_password", settings) is False
    assert verify_demo_password("", settings) is False
