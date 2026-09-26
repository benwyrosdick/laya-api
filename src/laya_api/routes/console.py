from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select

from laya_api import __version__
from laya_api.app_state import ctx
from laya_api.catalog import listed_models
from laya_api.models import ApiKey, UsageEvent, User
from laya_api.routes.v1 import run_system_one
from laya_api.schemas import SystemOneRequest
from laya_api.security import generate_api_key
from laya_api.usage_chart import (
    axis_ticks,
    build_series,
    chart_labels,
    format_total,
    nice_axis_max,
)

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
        "asset_version": __version__,
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


@router.get("/usage")
async def usage_page(request: Request):
    user = await require_user(request)
    grain = request.query_params.get("grain", "hour")
    if grain not in {"hour", "day"}:
        grain = "hour"
    key_filter = (request.query_params.get("key") or "").strip()
    model_filter = (request.query_params.get("model") or "").strip()
    catalog = (
        [card.name for card in listed_models("laya")]
        + [card.name for card in listed_models("lev")]
        + [card.name for card in listed_models("kev")]
    )
    async with ctx(request).sessions() as session:
        keys_result = await session.execute(
            select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
        )
        keys = list(keys_result.scalars())
        known_ids = {key.id for key in keys}
        if key_filter and key_filter != "playground" and key_filter not in known_ids:
            key_filter = ""
        seen = await session.execute(
            select(UsageEvent.requested_model, UsageEvent.resolved_model).where(UsageEvent.user_id == user.id)
        )
        model_names = list(catalog)
        for requested, resolved in seen.all():
            for name in (requested, resolved):
                if name and name not in model_names:
                    model_names.append(name)
        if model_filter and model_filter not in model_names:
            model_filter = ""
        stmt = select(UsageEvent.created_at, UsageEvent.input_tokens).where(UsageEvent.user_id == user.id)
        if key_filter == "playground":
            stmt = stmt.where(UsageEvent.api_key_id.is_(None))
        elif key_filter:
            stmt = stmt.where(UsageEvent.api_key_id == key_filter)
        if model_filter:
            stmt = stmt.where(
                or_(UsageEvent.requested_model == model_filter, UsageEvent.resolved_model == model_filter)
            )
        result = await session.execute(stmt)
        events = [(row[0], row[1]) for row in result.all()]
    buckets = build_series(events, grain=grain)
    total_requests = sum(bucket["requests"] for bucket in buckets)
    total_tokens = sum(bucket["tokens"] for bucket in buckets)
    token_max = nice_axis_max(max((bucket["tokens"] for bucket in buckets), default=0))
    request_max = nice_axis_max(max((bucket["requests"] for bucket in buckets), default=0))
    stamp = "%b %d" if grain == "day" else "%b %d %H:00 UTC"
    for bucket in buckets:
        bucket["token_pct"] = (bucket["tokens"] / token_max) * 100 if token_max else 0
        bucket["request_pct"] = (bucket["requests"] / request_max) * 100 if request_max else 0
        when = bucket["start"].strftime(stamp)
        bucket["token_title"] = f"{when} · {bucket['tokens']:,} tokens"
        bucket["request_title"] = f"{when} · {bucket['requests']:,} requests"
    window = "7 days, one bar per hour" if grain == "hour" else "30 days, one bar per day"
    return _template(
        request,
        "usage.html",
        user=user,
        keys=keys,
        model_names=model_names,
        grain=grain,
        key_filter=key_filter,
        model_filter=model_filter,
        window=window,
        buckets=buckets,
        labels=chart_labels(buckets, grain=grain),
        token_ticks=list(reversed(axis_ticks(token_max))),
        request_ticks=list(reversed(axis_ticks(request_max))),
        total_tokens=format_total(total_tokens),
        total_requests=format_total(total_requests),
    )


@router.get("/playground")
async def playground(request: Request):
    user = await require_user(request)
    return _template(
        request,
        "playground.html",
        user=user,
        models=listed_models("laya"),
        lev_models=listed_models("lev"),
        kev_models=listed_models("kev"),
        sample_state=SAMPLE_STATE,
        sample_questions=SAMPLE_QUESTIONS,
    )


@router.post("/console/evaluate")
async def console_evaluate(request: Request, body: SystemOneRequest):
    user = await require_user(request, json_api=True)
    runtime = "laya"
    model_name = (body.model or "").lower()
    if model_name.startswith("kev"):
        runtime = "kev"
    elif model_name.startswith("lev") or model_name in {"jev", "jev-latest"}:
        runtime = "lev"
    return await run_system_one(
        request,
        body,
        user_id=user.id,
        api_key_id=None,
        source="playground",
        runtime=runtime,
    )
