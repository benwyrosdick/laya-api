from dataclasses import dataclass

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


def ctx(request: Request) -> AppContext:
    return request.app.state.ctx
