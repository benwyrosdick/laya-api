from __future__ import annotations

from datetime import datetime, timezone

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from laya_api.app_state import ctx
from laya_api.models import User

router = APIRouter(tags=["auth"])


def build_oauth(settings) -> OAuth:
    oauth = OAuth()
    if settings.google_enabled:
        oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    return oauth


async def upsert_user(session, *, google_sub: str, email: str, name: str, picture_url: str) -> User:
    result = await session.execute(select(User).where(User.google_sub == google_sub))
    user = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if user is None:
        user = User(
            google_sub=google_sub,
            email=email,
            name=name or email.split("@")[0],
            picture_url=picture_url or "",
            last_login_at=now,
        )
        session.add(user)
    else:
        user.email = email or user.email
        user.name = name or user.name
        if picture_url:
            user.picture_url = picture_url
        user.last_login_at = now
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/auth/google")
async def google_login(request: Request):
    settings = ctx(request).settings
    if not settings.google_enabled:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    oauth: OAuth = request.app.state.oauth
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get("/auth/google/callback")
async def google_callback(request: Request):
    oauth: OAuth = request.app.state.oauth
    token = await oauth.google.authorize_access_token(request)
    info = token.get("userinfo") or {}
    sub = info.get("sub")
    email = info.get("email")
    if not sub or not email:
        raise HTTPException(status_code=400, detail="Google did not return an email identity")
    async with ctx(request).sessions() as session:
        user = await upsert_user(
            session,
            google_sub=str(sub),
            email=str(email),
            name=str(info.get("name") or ""),
            picture_url=str(info.get("picture") or ""),
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/keys", status_code=302)


@router.get("/auth/dev")
async def dev_login(request: Request):
    settings = ctx(request).settings
    if not settings.allow_dev_login:
        raise HTTPException(status_code=404, detail="Not found")
    async with ctx(request).sessions() as session:
        user = await upsert_user(
            session,
            google_sub="dev-local",
            email="dev@localhost",
            name="Dev User",
            picture_url="",
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/keys", status_code=302)


@router.post("/logout")
@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
