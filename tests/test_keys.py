from fastapi.testclient import TestClient
from sqlalchemy import select

from laya_api.db import get_session_factory
from laya_api.models import ApiKey
from tests.helpers import create_key


async def _latest_key() -> ApiKey:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
        key = result.scalars().first()
        assert key is not None
        return key


def test_create_and_use_key(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.get("/v1/models", headers={"Authorization": f"Bearer {raw}"})
    assert response.status_code == 200
    names = [m["name"] for m in response.json()["models"]]
    assert "laya-latest" in names
    assert "laya-multilingual" in names


def test_key_shown_only_once(signed_in: TestClient):
    raw = create_key(signed_in, "once")
    again = signed_in.get("/keys")
    assert raw not in again.text
    assert "once" in again.text
    assert "laya_" in again.text


def test_revoked_key_is_rejected(signed_in: TestClient):
    import anyio

    raw = create_key(signed_in, "temp")
    key = anyio.run(_latest_key)
    revoked = signed_in.post(f"/keys/{key.id}/revoke", follow_redirects=True)
    assert revoked.status_code == 200
    assert "Revoked" in revoked.text
    denied = signed_in.get("/v1/models", headers={"Authorization": f"Bearer {raw}"})
    assert denied.status_code == 401
    assert denied.json()["error"] == "unauthorized"


def test_missing_bearer_is_401(client: TestClient):
    response = client.post(
        "/v1/systemone",
        json={"state": "hello", "questions": {"ok": {"type": "noul", "instructions": "Is this a greeting?"}}},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
