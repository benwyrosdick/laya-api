"""Hourly request and token series for the usage page."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone


def hour_floor(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.replace(minute=0, second=0, microsecond=0)


def day_floor(value: datetime) -> datetime:
    return hour_floor(value).replace(hour=0)


def build_series(
    events: list[tuple[datetime, int]],
    *,
    grain: str = "hour",
    now: datetime | None = None,
    days: int | None = None,
) -> list[dict]:
    if grain not in {"hour", "day"}:
        grain = "hour"
    if days is None:
        days = 7 if grain == "hour" else 30
    end = hour_floor(now or datetime.now(timezone.utc))
    if grain == "day":
        end = end.replace(hour=0)
        start = end - timedelta(days=days - 1)
        step = timedelta(days=1)
        floor = day_floor
    else:
        start = end - timedelta(hours=days * 24 - 1)
        step = timedelta(hours=1)
        floor = hour_floor
    buckets: list[dict] = []
    index: dict[datetime, int] = {}
    cursor = start
    while cursor <= end:
        index[cursor] = len(buckets)
        buckets.append({"start": cursor, "requests": 0, "tokens": 0})
        cursor += step
    for created_at, tokens in events:
        slot = index.get(floor(created_at))
        if slot is None:
            continue
        buckets[slot]["requests"] += 1
        buckets[slot]["tokens"] += int(tokens or 0)
    return buckets


def build_hourly_series(
    events: list[tuple[datetime, int]],
    *,
    now: datetime | None = None,
    days: int = 7,
) -> list[dict]:
    return build_series(events, grain="hour", now=now, days=days)


def nice_axis_max(peak: int) -> int:
    if peak <= 0:
        return 4
    raw = peak * 1.08
    exponent = math.floor(math.log10(raw))
    magnitude = 10**exponent
    fraction = raw / magnitude
    for step in (1, 1.2, 1.5, 2, 2.5, 4, 5, 8, 10):
        if step >= fraction:
            return max(4, int(step * magnitude))
    return max(4, int(10 * magnitude))


def axis_ticks(maximum: int, count: int = 5) -> list[dict]:
    ticks = []
    for i in range(count):
        value = int(round(maximum * i / (count - 1)))
        ticks.append({"value": value, "label": format_axis(value), "pct": (value / maximum) * 100 if maximum else 0})
    return ticks


def format_axis(value: int) -> str:
    if value >= 1_000_000 and value % 1_000_000 == 0:
        return f"{value // 1_000_000}M"
    if value >= 10_000 and value % 1_000 == 0:
        return f"{value // 1_000}K"
    if value >= 1_000:
        return f"{value:,}"
    return str(value)


def format_total(value: int) -> str:
    return f"{value:,}"


def chart_labels(buckets: list[dict], *, grain: str) -> list[dict]:
    if not buckets:
        return []
    last = len(buckets) - 1
    labels = []
    for i, bucket in enumerate(buckets):
        start: datetime = bucket["start"]
        if grain == "hour" and start.hour != 0 and i != 0:
            continue
        if grain == "day" and i % 5 != 0 and i != last:
            continue
        left = 0 if last == 0 else (i / last) * 100
        if grain == "day":
            text = f"{start.strftime('%b')} {start.day}"
        else:
            text = f"{start.strftime('%b')} {start.day}, 12 AM"
        labels.append({"left": round(left, 3), "label": text})
    return labels
