from fastapi.testclient import TestClient

from tests.helpers import create_key

TICKET = (
    "Duplicate charge on invoice #4411. We were billed twice for March. "
    "Please refund the duplicate today or we will cancel our plan."
)

QUESTIONS = {
    "department": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {
            "billing": "invoices, payments, refunds",
            "technical": "bugs, outages, integrations",
            "sales": "pricing, new contracts",
        },
    },
    "frustration": {
        "type": "score",
        "instructions": "How frustrated is the customer?",
        "criteria": ["Calm", "Frustrated", "Very angry"],
    },
    "is_urgent": {
        "type": "noul",
        "instructions": "Does this convey urgency?",
    },
}


def test_systemone_with_api_key(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.post(
        "/v1/systemone",
        headers={"Authorization": f"Bearer {raw}"},
        json={"state": TICKET, "model": "laya-latest", "questions": QUESTIONS},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] in {"laya", "laya-multilingual", "laya-typed-decisions"}
    assert body["answers"]["department"]["type"] == "choice"
    assert body["answers"]["department"]["choice"] == "billing"
    assert abs(sum(body["answers"]["department"]["probabilities"].values()) - 1) < 0.02
    assert "confidence" in body["answers"]["department"]
    assert body["answers"]["frustration"]["type"] == "score"
    assert 0 <= body["answers"]["frustration"]["score"] <= 2
    assert body["answers"]["is_urgent"]["type"] == "noul"
    assert body["answers"]["is_urgent"]["noul"] >= 0.5
    assert "confidence" not in body["answers"]["is_urgent"]
    assert body["usage"]["input_tokens"] > 0
    assert body["usage"]["output_tokens"] == 0
    assert body["routing"]["model"] in {"english", "multilingual", "typed-decisions"}


def test_playground_evaluate(signed_in: TestClient):
    response = signed_in.post(
        "/console/evaluate",
        json={"state": TICKET, "model": "laya", "questions": QUESTIONS},
    )
    assert response.status_code == 200, response.text
    assert response.json()["answers"]["department"]["choice"] == "billing"


def test_explicit_model_alias(signed_in: TestClient):
    raw = create_key(signed_in)
    response = signed_in.post(
        "/v1/systemone",
        headers={"Authorization": f"Bearer {raw}"},
        json={
            "state": "hello",
            "model": "multilingual",
            "questions": {"ok": {"type": "noul", "instructions": "Is this English?"}},
        },
    )
    assert response.status_code == 200
    assert response.json()["model"] == "laya-multilingual"
    assert response.json()["routing"]["model"] == "multilingual"


def test_rate_limit(signed_in: TestClient, app):
    app.state.ctx.limiter.rpm = 2
    raw = create_key(signed_in, "limited")
    payload = {
        "state": "hi",
        "questions": {"ok": {"type": "noul", "instructions": "Is this a greeting?"}},
    }
    headers = {"Authorization": f"Bearer {raw}"}
    assert signed_in.post("/v1/systemone", headers=headers, json=payload).status_code == 200
    assert signed_in.post("/v1/systemone", headers=headers, json=payload).status_code == 200
    limited = signed_in.post("/v1/systemone", headers=headers, json=payload)
    assert limited.status_code == 429
    assert limited.json()["error"] == "rate_limited"
    assert "Retry-After" in limited.headers
