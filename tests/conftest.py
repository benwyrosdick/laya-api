from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from laya_api.config import Settings
from laya_api.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        secret_key="test-secret-key-please-ignore",
        public_base_url="http://testserver",
        database_url="sqlite+aiosqlite://",
        allow_dev_login=True,
        engine="stub",
        rate_limit_rpm=60,
        google_client_id="",
        google_client_secret="",
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def signed_in(client: TestClient) -> TestClient:
    response = client.get("/auth/dev", follow_redirects=False)
    assert response.status_code in {302, 307}
    return client
