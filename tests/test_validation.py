from fastapi.testclient import TestClient

from tests.helpers import create_key


def test_unknown_model(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.post(
        "/v1/systemone",
        headers={"Authorization": f"Bearer {raw}"},
        json={
            "state": "hello",
            "model": "jev-latest",
            "questions": {"ok": {"type": "noul", "instructions": "yes?"}},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_model"


def test_choice_requires_criteria(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.post(
        "/v1/systemone",
        headers={"Authorization": f"Bearer {raw}"},
        json={
            "state": "hello",
            "questions": {"dept": {"type": "choice", "instructions": "Which?"}},
        },
    )
    assert response.status_code == 422


def test_score_needs_two_levels(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.post(
        "/v1/systemone",
        headers={"Authorization": f"Bearer {raw}"},
        json={
            "state": "hello",
            "questions": {
                "s": {"type": "score", "instructions": "How much?", "criteria": ["only-one"]}
            },
        },
    )
    assert response.status_code == 422


def test_empty_questions_rejected(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.post(
        "/v1/systemone",
        headers={"Authorization": f"Bearer {raw}"},
        json={"state": "hello", "questions": {}},
    )
    assert response.status_code == 422


def test_healthz(client: TestClient):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["engine"] == "stub"
