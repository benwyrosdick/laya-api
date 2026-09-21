from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from laya_api import __version__
from laya_api.app_state import AppContext
from laya_api.config import Settings
from laya_api.db import create_schema, dispose_engine, get_session_factory, init_engine
from laya_api.engine import build_engine
from laya_api.rate_limit import RateLimiter
from laya_api.routes.auth import build_oauth, router as auth_router
from laya_api.routes.console import SignInRequired, router as console_router
from laya_api.routes.v1 import router as v1_router

logger = logging.getLogger("laya_api")

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_engine(settings.database_url)
        await create_schema()
        engine = build_engine(settings.engine, settings.laya_device, settings.laya_preload)
        await engine.startup()
        app.state.ctx = AppContext(
            settings=settings,
            sessions=get_session_factory(),
            engine=engine,
            limiter=RateLimiter(settings.rate_limit_rpm),
        )
        app.state.oauth = build_oauth(settings)
        if settings.secret_key == "dev-insecure-change-me":
            logger.warning("SECRET_KEY is the development default. Set a real secret before hosting this.")
        if settings.allow_dev_login:
            logger.warning("ALLOW_DEV_LOGIN is enabled. Turn this off on any public host.")
        yield
        await dispose_engine()

    app = FastAPI(
        title="Laya API",
        version=__version__,
        description="Hosted System One API for the Laya decision engine.",
        lifespan=lifespan,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie=settings.session_cookie_name,
        https_only=settings.https_only,
        same_site="lax",
        max_age=60 * 60 * 24 * 14,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(auth_router)
    app.include_router(console_router)
    app.include_router(v1_router)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "version": __version__, "engine": settings.engine}

    @app.exception_handler(SignInRequired)
    async def sign_in_required(_request: Request, _exc: SignInRequired):
        return RedirectResponse("/", status_code=302)

    @app.exception_handler(HTTPException)
    async def api_http_exception(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_exception(request: Request, exc: RequestValidationError):
        return await request_validation_exception_handler(request, exc)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("laya_api.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
