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


def test_kev_systemone_uses_kev_catalog(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.post(
        "/kev/v1/systemone",
        headers={"Authorization": f"Bearer {raw}"},
        json={"state": "Refund this duplicate charge today.", "questions": QUESTIONS},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == "kev-latest"
    assert body["routing"] is None
    assert body["answers"]["department"]["type"] == "choice"


def test_kev_models(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.get("/kev/v1/models", headers={"Authorization": f"Bearer {raw}"})
    assert response.status_code == 200
    names = [item["name"] for item in response.json()["models"]]
    assert names == ["kev-latest"]


def test_kev_rejects_laya_model_name(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.post(
        "/kev/v1/systemone",
        headers={"Authorization": f"Bearer {raw}"},
        json={"state": "hi", "model": "laya", "questions": QUESTIONS},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_model"
