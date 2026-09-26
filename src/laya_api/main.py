from __future__ import annotations

import asyncio
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
from laya_api.routes.v1 import kev_router, laya_router, lev_router, router as v1_router

logger = logging.getLogger("laya_api")

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_engine(settings.database_url)
        await create_schema()
        real = settings.real_runtimes()
        engines = {
            "laya": build_engine(
                "laya" if "laya" in real else "stub",
                settings.laya_device,
                settings.laya_preload,
            ),
            "lev": build_engine(
                "lev" if "lev" in real else "stub",
                settings.laya_device,
                settings.laya_preload,
                lev_run=settings.lev_run,
            ),
            "kev": build_engine(
                "kev" if "kev" in real else "stub",
                settings.laya_device,
                settings.laya_preload,
                kev_run=settings.kev_run,
            ),
        }
        context = AppContext(
            settings=settings,
            sessions=get_session_factory(),
            engine=engines["laya"],
            limiter=RateLimiter(settings.rate_limit_rpm),
        )
        context.engines = engines
        context.runtime_ready = {name: asyncio.Event() for name in engines}
        context.runtime_error = {name: None for name in engines}
        context.engine_ready = context.runtime_ready["laya"]
        app.state.ctx = context
        app.state.oauth = build_oauth(settings)
        if settings.secret_key == "dev-insecure-change-me":
            logger.warning("SECRET_KEY is the development default. Set a real secret before hosting this.")
        if settings.allow_dev_login:
            logger.warning("ALLOW_DEV_LOGIN is enabled. Turn this off on any public host.")

        load_tasks: list[asyncio.Task] = []

        async def load_engine(name: str, engine) -> None:
            try:
                logger.info("Starting %s engine", name)
                await engine.startup()
                context.runtime_ready[name].set()
                logger.info("%s engine ready", name)
            except Exception as exc:
                context.runtime_error[name] = str(exc)
                logger.exception("%s engine failed to load", name)

        for name, engine in engines.items():
            if engine.blocking_startup:
                await load_engine(name, engine)
            else:
                load_tasks.append(asyncio.create_task(load_engine(name, engine)))

        yield
        for task in load_tasks:
            task.cancel()
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
    app.include_router(laya_router)
    app.include_router(lev_router)
    app.include_router(kev_router)

    @app.get("/up")
    @app.get("/healthz")
    async def healthz(request: Request):
        context = getattr(request.app.state, "ctx", None)
        ready = bool(context and context.engine_ready.is_set())
        return {
            "ok": True,
            "version": __version__,
            "engine": settings.engine,
            "engine_ready": ready,
        }

    @app.get("/ready")
    async def ready(request: Request):
        context = request.app.state.ctx
        if context.engine_error:
            return JSONResponse(
                status_code=503,
                content={"ok": False, "engine_ready": False, "error": context.engine_error},
            )
        if not context.engine_ready.is_set():
            return JSONResponse(
                status_code=503,
                content={"ok": False, "engine_ready": False, "message": "Checkpoints are still loading."},
            )
        return {"ok": True, "engine_ready": True}

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
