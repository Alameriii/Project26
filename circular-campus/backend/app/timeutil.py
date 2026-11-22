"""Time helpers. SQLite returns naive datetimes, so everything is normalised to UTC."""
from __future__ import annotations

from typing import Optional

from datetime import date, datetime, timedelta, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def add_working_days(start: datetime, days: int) -> datetime:
    """Add working days (Monday–Friday, the UAE working week) to a timestamp (BR-7)."""
    result = start
    added = 0
    while added < days:
        result += timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result


def today() -> date:
    return now().date()
