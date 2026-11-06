import os
import pytest
from datetime import timedelta
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure test environment variables
os.environ["ENVIRONMENT"] = "test"
os.environ["DEMO_ACCESS_PASSWORD"] = "test_demo_password_123"
os.environ["JWT_SECRET"] = "test_jwt_secret_32_characters_minimum_key!"

from backend.core.config import Settings, get_settings
from backend.db.models import Base
from backend.db.session import get_db
from backend.main import app


# Test settings override
def get_test_settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        demo_access_password="test_demo_password_123",
        jwt_secret="test_jwt_secret_32_characters_minimum_key!",
        session_token_ttl_hours=8,
        environment="test",
        log_level="DEBUG",
    )


# In-memory SQLite engine for fast, isolated test execution
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = get_test_settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
