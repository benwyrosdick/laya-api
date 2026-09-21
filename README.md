# Laya API

Hosted System One API for [Laya](https://github.com/NandhaKishorM/laya), in the same shape as TypeSafe [Jev](https://docs.typesafe.ai/api).

Sign in with Google, mint an API key, then evaluate `state` against typed `choice` / `score` / `noul` questions.

```http
POST /v1/systemone
Authorization: Bearer <LAYA_API_KEY>
```

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000). With `ALLOW_DEV_LOGIN=true` (the compose default) you can sign in without Google, create a key, and call the engine.

The default `ENGINE=stub` is a deterministic stand-in so the stack boots without downloading 300–400M checkpoints. Point `ENGINE=laya` at a machine with the optional extra installed when you want the real Router.

## Google login

1. Create an OAuth **Web application** client in Google Cloud.
2. Add authorized redirect URI `{PUBLIC_BASE_URL}/auth/google/callback` (local: `http://localhost:8000/auth/google/callback`).
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
4. Set `ALLOW_DEV_LOGIN=false` on any public host.

Accounts are stored in Postgres (`users`). API secrets are stored as SHA-256 hashes (`api_keys`); the raw token is shown once in the console.

## Call the engine

```bash
export LAYA_API_KEY="laya_…"

curl -s http://localhost:8000/v1/systemone \
  -H "Authorization: Bearer $LAYA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "state": "Duplicate charge on invoice #4411. Refund today or we cancel.",
    "model": "laya-latest",
    "questions": {
      "department": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {
          "billing": "invoices, payments, refunds",
          "technical": "bugs, outages, integrations",
          "sales": "pricing, new contracts"
        }
      },
      "is_urgent": {
        "type": "noul",
        "instructions": "Does this convey urgency?"
      }
    }
  }'
```

List models with `GET /v1/models` and the same bearer token. Interactive OpenAPI is at `/docs`. The signed-in [playground](http://localhost:8000/playground) hits the same engine without a key.

### Models

| Request `model` | What runs |
| --- | --- |
| `laya-latest` (default) | Laya `Router` — English vs multilingual vs typed-decisions per request |
| `laya` | English ModernBERT-large checkpoint |
| `laya-multilingual` | mmBERT-base, 100+ languages |
| `laya-typed-decisions` | Fine-tuned typed-decisions checkpoint |

Aliases such as `router`, `english`, and `multilingual` are accepted. The response `model` field is the resolved public name; `routing` records why the Router picked that checkpoint.

The answer objects follow Jev: `choice` includes `probabilities` and `confidence`; `score` includes `legend`; `noul` is a probability in `[0, 1]`. Usage reports `input_tokens` / `output_tokens` (output is always 0 — Laya is not generative).

## Real Laya engine

```bash
pip install -e '.[engine]'
ENGINE=laya LAYA_PRELOAD=true LAYA_DEVICE=cuda uvicorn laya_api.main:app
```

First start downloads checkpoints from Hugging Face into the local hub cache. Preload keeps them resident so language switches do not reload weights. Inference is serialized on one process — this is a single-node API, not a model-parallel cluster.

## Local development without Docker

Postgres is the hosted store. Tests and a solo process can use SQLite:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
DATABASE_URL=sqlite+aiosqlite:///./laya.db ALLOW_DEV_LOGIN=true SECRET_KEY=dev \
  uvicorn laya_api.main:app --reload
pytest
```

## Environment

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Signs session cookies |
| `PUBLIC_BASE_URL` | Canonical origin; builds the Google redirect URI |
| `DATABASE_URL` | SQLAlchemy URL (`postgresql+asyncpg://…`) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth |
| `ALLOW_DEV_LOGIN` | `/auth/dev` shortcut — off in production |
| `ENGINE` | `stub` or `laya` |
| `LAYA_DEVICE` | Optional `cuda` / `cpu` / `mps` |
| `LAYA_PRELOAD` | Load all checkpoints at boot |
| `RATE_LIMIT_RPM` | Per-key sliding window (default 60) |
