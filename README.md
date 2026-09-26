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

### Runtimes

Laya, [Lev](https://github.com/franckverrot/lev), and [Kev](https://github.com/jaredpalmer/kev) are separate engines, so they have separate paths. `/v1/...` stays the Laya alias.

| | Laya | Lev | Kev |
| --- | --- | --- | --- |
| Evaluate | `POST /laya/v1/systemone` or `POST /v1/systemone` | `POST /lev/v1/systemone` | `POST /kev/v1/systemone` |
| Models | `GET /laya/v1/models` | `GET /lev/v1/models` | `GET /kev/v1/models` |
| Default model | `laya-latest` | `lev-latest` | `kev-latest` |

Lev is the LFM2.5-350M decision model (`franckverrot/lev-350m`). Kev is Jared Palmer's Qwen decision family; `KEV_RUN` defaults to `jaredpalmer/kev-0.8b` so it fits a 16 GB GPU. Same question types. Neither returns a `routing` object. Load them with `ENGINES=laya,lev,kev` and `pip install -e '.[lev,kev]'`. Production Kamal stays Laya-only unless you set that.

## Real Laya engine

The production image (`ENGINE=laya`) installs PyTorch and bakes the three Laya checkpoints from Hugging Face (`convaiinnovations/laya`) into the image at build time. Boot preloads them into RAM so language switches do not reload weights.

Locally, without Docker:

```bash
pip install -e '.[engine]'
python -m laya_api.download_models
ENGINE=laya LAYA_PRELOAD=true LAYA_DEVICE=cpu uvicorn laya_api.main:app
```

The Kamal image uses **CPU** wheels. A GPU host would need a CUDA PyTorch image and Docker `--gpus`. Preload wants on the order of **8 GB RAM** for all three checkpoints. Inference is serialized in one process.

Checkpoints live on the host at `/var/lib/laya-api/huggingface` and are mounted into each new container, so later deploys reuse the download. The image still bakes a copy and seeds an empty volume on first boot.

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
| `RATE_LIMIT_RPM` | Per-key sliding window (default 180) |

## Deploy with Kamal

Production is deployed by GitHub Actions with Kamal to `house.wyrosdick.com`. Images go to GHCR as `ghcr.io/benwyrosdick/laya-api` and include the real Laya checkpoints (the first build is slow and the image is large). The app uses a Postgres instance you already host; there is no database accessory.

A push to `main` deploys. The first time, run the **Deploy** workflow with **setup** checked (Actions → Deploy → Run workflow) so Kamal can install Docker, boot `kamal-proxy`, and ship the app. `/up` becomes healthy as soon as the process and database are up so Kamal can finish. Checkpoints then load in the background (several minutes on CPU). `/ready` is 503 until they are resident; `POST /v1/systemone` returns 529 until then. `docker logs -f` on the `laya-api-web-*` container shows load progress.

### GitHub Actions values

Add these under **Settings → Secrets and variables → Actions**. Secrets are preferred for anything sensitive; the workflow also reads repository Variables of the same name if the secret is empty.

| Name | Kind | Purpose |
| --- | --- | --- |
| `SSH_PRIVATE_KEY` | secret | Private key that can SSH to `house.wyrosdick.com:2222` |
| `SECRET_KEY` | secret | Session cookie signing key |
| `DATABASE_URL` | secret | Postgres URL the **container** can reach, e.g. `postgresql://user:pass@host.docker.internal:5432/laya` (plain `postgresql://` is rewritten to asyncpg) |
| `GOOGLE_CLIENT_ID` | secret or variable | Google OAuth client |
| `GOOGLE_CLIENT_SECRET` | secret | Google OAuth secret |
| `KAMAL_SSH_USER` | variable | SSH user, default `root` |
| `KAMAL_REGISTRY_PASSWORD` | secret | Optional GHCR token. Defaults to `GITHUB_TOKEN` |

Google redirect URI: `https://laya-api.benwyrosdick.com/auth/google/callback`. Ports **80** and **443** must reach the house box for Let’s Encrypt.

After the first image is published, either make the GHCR package public or set `KAMAL_REGISTRY_PASSWORD` to a PAT with `read:packages` so the server can pull.
