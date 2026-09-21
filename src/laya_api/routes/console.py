from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from laya_api.app_state import ctx
from laya_api.catalog import listed_models
from laya_api.models import ApiKey, UsageEvent, User
from laya_api.routes.v1 import run_system_one
from laya_api.schemas import SystemOneRequest
from laya_api.security import generate_api_key

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

router = APIRouter(tags=["console"])

SAMPLE_STATE = (
    "Hi, I've been trying to connect my Stripe account for 3 days and the integration "
    "keeps failing. I'm losing sales. Please help ASAP."
)

class SignInRequired(Exception):
    """Browser hit a console page without a session."""


SAMPLE_QUESTIONS = {
    "department": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {
            "billing": "Payments, invoicing, refunds",
            "technical": "Bugs, outages, integrations",
            "sales": "Pricing, upgrades, new accounts",
        },
    },
    "frustration": {
        "type": "score",
        "instructions": "How frustrated is the customer?",
        "criteria": ["Calm, just stating facts", "Frustrated but civil", "Very angry, strong language"],
    },
    "is_urgent": {
        "type": "noul",
        "instructions": "Does this message convey urgency?",
    },
}


async def current_user(request: Request) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    async with ctx(request).sessions() as session:
        return await session.get(User, user_id)


async def require_user(request: Request, *, json_api: bool = False) -> User:
    user = await current_user(request)
    if user is None:
        if json_api:
            raise HTTPException(status_code=401, detail="Sign in required")
        raise SignInRequired()
    return user


def _template(request: Request, name: str, **context):
    settings = ctx(request).settings
    base = {
        "request": request,
        "settings": settings,
        "app_name": settings.app_name,
        "google_enabled": settings.google_enabled,
        "allow_dev_login": settings.allow_dev_login,
    }
    base.update(context)
    return TEMPLATES.TemplateResponse(request, name, base)


@router.get("/")
async def landing(request: Request):
    user = await current_user(request)
    return _template(request, "index.html", user=user)


@router.get("/keys")
async def keys_page(request: Request):
    user = await require_user(request)
    flash = request.session.pop("flash_key", None)
    flash_name = request.session.pop("flash_key_name", None)
    async with ctx(request).sessions() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
        )
        keys = list(result.scalars())
        counts_result = await session.execute(
            select(UsageEvent.api_key_id, func.count())
            .where(UsageEvent.user_id == user.id)
            .group_by(UsageEvent.api_key_id)
        )
        usage_counts = {row[0]: row[1] for row in counts_result.all()}
    return _template(
        request,
        "keys.html",
        user=user,
        keys=keys,
        usage_counts=usage_counts,
        flash_key=flash,
        flash_key_name=flash_name,
    )


@router.post("/keys")
async def create_key(request: Request, name: str = Form(default="default")):
    user = await require_user(request)
    label = (name or "default").strip()[:80] or "default"
    raw, prefix, key_hash = generate_api_key()
    async with ctx(request).sessions() as session:
        session.add(ApiKey(user_id=user.id, name=label, prefix=prefix, key_hash=key_hash))
        await session.commit()
    request.session["flash_key"] = raw
    request.session["flash_key_name"] = label
    return RedirectResponse("/keys", status_code=303)


@router.post("/keys/{key_id}/revoke")
async def revoke_key(request: Request, key_id: str):
    user = await require_user(request)
    async with ctx(request).sessions() as session:
        key = await session.get(ApiKey, key_id)
        if key is None or key.user_id != user.id:
            raise HTTPException(status_code=404, detail="Key not found")
        if key.revoked_at is None:
            key.revoked_at = datetime.now(timezone.utc)
            await session.commit()
    return RedirectResponse("/keys", status_code=303)


@router.get("/playground")
async def playground(request: Request):
    user = await require_user(request)
    return _template(
        request,
        "playground.html",
        user=user,
        models=listed_models(),
        sample_state=SAMPLE_STATE,
        sample_questions=SAMPLE_QUESTIONS,
    )


@router.post("/console/evaluate")
async def console_evaluate(request: Request, body: SystemOneRequest):
    user = await require_user(request, json_api=True)
    return await run_system_one(
        request,
        body,
        user_id=user.id,
        api_key_id=None,
        source="playground",
    )
