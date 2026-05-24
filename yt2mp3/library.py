"""Library view helpers: group rows by day with human-readable labels.

Pure functions — no I/O, easy to unit-test.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any

_RU_MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _label_for(day: date | None, today: date) -> str:
    if day is None:
        return "Без даты"
    delta = (today - day).days
    if delta == 0:
        return "Сегодня"
    if delta == 1:
        return "Вчера"
    if day.year == today.year:
        return f"{day.day} {_RU_MONTHS[day.month - 1]}"
    return f"{day.day} {_RU_MONTHS[day.month - 1]} {day.year}"


def group_by_day(
    rows: Iterable[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> list[tuple[str, list[Mapping[str, Any]]]]:
    """Group rows by ``finished_at`` date.

    Returns ``[(label, [rows])]``, newest-day first. Rows with NULL
    ``finished_at`` land in a final "Без даты" group.
    """
    today = (now or datetime.now(UTC)).astimezone(UTC).date()

    buckets: dict[date | None, list[Mapping[str, Any]]] = {}
    for r in rows:
        dt = _parse_dt(r.get("finished_at"))
        day: date | None = dt.astimezone(UTC).date() if dt else None
        buckets.setdefault(day, []).append(r)

    known_days = sorted((d for d in buckets if d is not None), reverse=True)
    out: list[tuple[str, list[Mapping[str, Any]]]] = []
    for d in known_days:
        out.append((_label_for(d, today), buckets[d]))
    if None in buckets:
        out.append((_label_for(None, today), buckets[None]))
    return out
