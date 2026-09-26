from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from laya_api.config import Settings
from laya_api.engine import DecisionEngine
from laya_api.rate_limit import RateLimiter


@dataclass
class AppContext:
    settings: Settings
    sessions: async_sessionmaker[AsyncSession]
    engine: DecisionEngine
    limiter: RateLimiter
    engine_ready: asyncio.Event = field(default_factory=asyncio.Event)
    engine_error: str | None = None
    engines: dict[str, DecisionEngine] = field(default_factory=dict)
    runtime_ready: dict[str, asyncio.Event] = field(default_factory=dict)
    runtime_error: dict[str, str | None] = field(default_factory=dict)


def ctx(request: Request) -> AppContext:
    return request.app.state.ctx
