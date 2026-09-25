from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from laya_api.db import get_session_factory
from laya_api.models import UsageEvent, User
from laya_api.models import ApiKey
from laya_api.usage_chart import build_hourly_series, build_series, format_total, nice_axis_max


def test_hourly_series_counts_only_the_window():
    end = datetime(2026, 9, 24, 15, tzinfo=timezone.utc)
    inside = end - timedelta(hours=2)
    outside = end - timedelta(days=8)
    buckets = build_hourly_series(
        [(inside, 500), (inside, 20), (outside, 9999)],
        now=end,
        days=7,
    )
    assert len(buckets) == 7 * 24
    hit = next(bucket for bucket in buckets if bucket["start"] == inside.replace(minute=0, second=0, microsecond=0))
    assert hit["requests"] == 2
    assert hit["tokens"] == 520
    assert sum(bucket["tokens"] for bucket in buckets) == 520


def test_daily_series_rolls_hours_into_one_bar():
    end = datetime(2026, 9, 24, 18, tzinfo=timezone.utc)
    morning = datetime(2026, 9, 24, 2, tzinfo=timezone.utc)
    evening = datetime(2026, 9, 24, 16, tzinfo=timezone.utc)
    buckets = build_series([(morning, 10), (evening, 5)], grain="day", now=end, days=30)
    assert len(buckets) == 30
    today = next(bucket for bucket in buckets if bucket["start"] == datetime(2026, 9, 24, tzinfo=timezone.utc))
    assert today["requests"] == 2
    assert today["tokens"] == 15


def test_axis_max_covers_peak():
    assert nice_axis_max(0) == 4
    assert nice_axis_max(380) >= 380
    assert format_total(1290373) == "1,290,373"


def test_usage_page_shows_totals(signed_in: TestClient):
    import anyio

    async def seed() -> None:
        factory = get_session_factory()
        async with factory() as session:
            user = (await session.execute(select(User))).scalar_one()
            now = datetime.now(timezone.utc).replace(minute=10, second=0, microsecond=0)
            session.add(
                UsageEvent(
                    user_id=user.id,
                    source="api",
                    requested_model="laya-latest",
                    resolved_model="laya",
                    input_tokens=1200,
                    question_count=1,
                    latency_ms=40,
                    status_code=200,
                    created_at=now,
                )
            )
            await session.commit()

    anyio.run(seed)
    page = signed_in.get("/usage")
    assert page.status_code == 200
    assert "Tokens" in page.text
    assert "Requests" in page.text
    assert "1,200" in page.text
    assert ">Usage<" in page.text or 'href="/usage"' in page.text


def test_usage_filters_by_key_and_grain(signed_in: TestClient):
    import anyio

    async def seed() -> str:
        factory = get_session_factory()
        async with factory() as session:
            user = (await session.execute(select(User))).scalar_one()
            key = ApiKey(user_id=user.id, name="prod", prefix="laya_prod123", key_hash="abc")
            session.add(key)
            await session.flush()
            now = datetime.now(timezone.utc)
            session.add_all(
                [
                    UsageEvent(
                        user_id=user.id,
                        api_key_id=key.id,
                        source="api",
                        requested_model="laya-latest",
                        resolved_model="laya",
                        input_tokens=50,
                        question_count=1,
                        latency_ms=10,
                        status_code=200,
                        created_at=now,
                    ),
                    UsageEvent(
                        user_id=user.id,
                        api_key_id=None,
                        source="playground",
                        requested_model="laya-latest",
                        resolved_model="laya",
                        input_tokens=900,
                        question_count=1,
                        latency_ms=10,
                        status_code=200,
                        created_at=now,
                    ),
                ]
            )
            await session.commit()
            return key.id

    key_id = anyio.run(seed)
    all_keys = signed_in.get("/usage")
    assert "All keys" in all_keys.text
    assert "950" in all_keys.text
    only = signed_in.get(f"/usage?grain=day&key={key_id}")
    assert only.status_code == 200
    assert "Daily" in only.text
    assert "30 days" in only.text
    assert "50" in only.text
    assert "950" not in only.text


def test_usage_requires_login(client: TestClient):
    response = client.get("/usage", follow_redirects=False)
    assert response.status_code == 302
