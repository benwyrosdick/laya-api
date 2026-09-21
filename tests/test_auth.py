from fastapi.testclient import TestClient

from laya_api.config import Settings
from laya_api.main import create_app


def test_landing_renders(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "Sign in" in response.text or "Dev sign in" in response.text
    assert "/v1/systemone" in response.text


def test_keys_requires_login(client: TestClient):
    response = client.get("/keys", follow_redirects=False)
    assert response.status_code in {302, 307, 401}


def test_dev_login_disabled():
    app = create_app(
        Settings(
            secret_key="test-secret-key-please-ignore",
            database_url="sqlite+aiosqlite://",
            allow_dev_login=False,
            engine="stub",
        )
    )
    with TestClient(app) as client:
        response = client.get("/auth/dev")
        assert response.status_code == 404


def test_dev_login_sets_session(client: TestClient):
    response = client.get("/auth/dev", follow_redirects=True)
    assert response.status_code == 200
    assert "API keys" in response.text
    assert "Dev User" in response.text


def test_google_login_without_config(client: TestClient):
    response = client.get("/auth/google")
    assert response.status_code == 400
