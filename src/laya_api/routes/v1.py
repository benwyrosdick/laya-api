from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from laya_api.app_state import ctx
from laya_api.catalog import UnknownModelError, listed_models, resolve_model
from laya_api.models import ApiKey, UsageEvent
from laya_api.schemas import ModelListItem, ModelListResponse, SystemOneRequest, SystemOneResponse
from laya_api.security import extract_bearer, hash_api_key

router = APIRouter(prefix="/v1", tags=["v1"])


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error": "unauthorized", "message": "Missing or invalid API key."},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def authenticate_key(request: Request, authorization: str | None) -> ApiKey:
    raw = extract_bearer(authorization)
    if not raw:
        raise _unauthorized()
    async with ctx(request).sessions() as session:
        result = await session.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw)))
        key = result.scalar_one_or_none()
        if key is None or key.revoked:
            raise _unauthorized()
        allowed, retry_after = ctx(request).limiter.check(key.id)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={"error": "rate_limited", "message": "Too many requests. Back off and retry."},
                headers={"Retry-After": str(retry_after)},
            )
        key.last_used_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(key)
        return key


async def record_usage(
    request: Request,
    *,
    user_id: str,
    api_key_id: str | None,
    source: str,
    requested_model: str,
    resolved_model: str,
    input_tokens: int,
    question_count: int,
    latency_ms: int,
    status_code: int,
) -> None:
    async with ctx(request).sessions() as session:
        session.add(
            UsageEvent(
                user_id=user_id,
                api_key_id=api_key_id,
                source=source,
                requested_model=requested_model,
                resolved_model=resolved_model,
                input_tokens=input_tokens,
                question_count=question_count,
                latency_ms=latency_ms,
                status_code=status_code,
            )
        )
        await session.commit()


async def run_system_one(
    request: Request,
    body: SystemOneRequest,
    *,
    user_id: str,
    api_key_id: str | None,
    source: str,
) -> SystemOneResponse:
    try:
        card = resolve_model(body.model)
    except UnknownModelError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_model", "message": str(exc)},
        ) from exc

    questions = {qid: q.model_dump() for qid, q in body.questions.items()}
    started = time.perf_counter()
    try:
        result = await ctx(request).engine.predict(body.state, questions, card)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_request", "message": str(exc)},
        ) from exc
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        await record_usage(
            request,
            user_id=user_id,
            api_key_id=api_key_id,
            source=source,
            requested_model=body.model,
            resolved_model=card.name,
            input_tokens=0,
            question_count=len(questions),
            latency_ms=latency_ms,
            status_code=500,
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "engine_error", "message": "The decision engine failed to evaluate this request."},
        ) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    await record_usage(
        request,
        user_id=user_id,
        api_key_id=api_key_id,
        source=source,
        requested_model=body.model,
        resolved_model=result.model,
        input_tokens=result.usage.input_tokens,
        question_count=len(questions),
        latency_ms=latency_ms,
        status_code=200,
    )
    return result


@router.get("/models", response_model=ModelListResponse)
async def list_models(request: Request, authorization: str | None = Header(default=None)):
    await authenticate_key(request, authorization)
    return ModelListResponse(
        models=[
            ModelListItem(name=m.name, description=m.description, release_date=m.release_date)
            for m in listed_models()
        ]
    )


@router.post("/systemone", response_model=SystemOneResponse)
async def system_one(
    request: Request,
    body: SystemOneRequest,
    authorization: str | None = Header(default=None),
):
    key = await authenticate_key(request, authorization)
    return await run_system_one(
        request,
        body,
        user_id=key.user_id,
        api_key_id=key.id,
        source="api",
    )


@router.api_route("/systemone", methods=["GET", "PUT", "PATCH", "DELETE"])
async def system_one_wrong_method():
    return JSONResponse(
        status_code=405,
        content={"error": "method_not_allowed", "message": "Use POST /v1/systemone."},
        headers={"Allow": "POST"},
    )
