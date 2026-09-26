from fastapi.testclient import TestClient

from tests.helpers import create_key

QUESTIONS = {
    "department": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {"billing": "invoices and refunds", "technical": "bugs and outages"},
    },
    "is_urgent": {"type": "noul", "instructions": "Does this convey urgency?"},
}


def test_lev_systemone_uses_lev_catalog(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.post(
        "/lev/v1/systemone",
        headers={"Authorization": f"Bearer {raw}"},
        json={"state": "Refund this duplicate charge today.", "questions": QUESTIONS},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == "lev-latest"
    assert body["routing"] is None
    assert body["answers"]["department"]["type"] == "choice"
    assert body["answers"]["is_urgent"]["type"] == "noul"


def test_lev_models(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.get("/lev/v1/models", headers={"Authorization": f"Bearer {raw}"})
    assert response.status_code == 200
    names = [item["name"] for item in response.json()["models"]]
    assert names == ["lev-latest"]


def test_laya_alias_still_routes(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.post(
        "/laya/v1/systemone",
        headers={"Authorization": f"Bearer {raw}"},
        json={"state": "Refund this duplicate charge today.", "model": "laya", "questions": QUESTIONS},
    )
    assert response.status_code == 200, response.text
    assert response.json()["model"] == "laya"
    assert response.json()["routing"]["model"] == "english"


def test_lev_rejects_laya_model_name(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.post(
        "/lev/v1/systemone",
        headers={"Authorization": f"Bearer {raw}"},
        json={"state": "hi", "model": "laya-multilingual", "questions": QUESTIONS},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_model"
