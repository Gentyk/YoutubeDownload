"""U7: library.group_by_day — pure-function tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from yt2mp3.library import group_by_day


def _row(finished_at: str, title: str = "x", row_id: int = 0) -> dict:
    return {"id": row_id, "title": title, "finished_at": finished_at}


def test_group_by_day_empty():
    assert group_by_day([]) == []


def test_group_by_day_single_row():
    today = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    groups = group_by_day([_row(today, "track 1", 1)])
    assert len(groups) == 1
    assert groups[0][0] == "Сегодня"
    assert len(groups[0][1]) == 1


def test_group_by_day_today_and_yesterday():
    now = datetime.now(UTC)
    today = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    rows = [_row(today, "a", 1), _row(yesterday, "b", 2)]
    groups = group_by_day(rows)
    labels = [g[0] for g in groups]
    assert labels == ["Сегодня", "Вчера"]


def test_group_by_day_orders_newest_first():
    now = datetime.now(UTC)
    rows = [
        _row((now - timedelta(days=3)).isoformat(), "old", 1),
        _row(now.isoformat(), "new", 2),
        _row((now - timedelta(days=1)).isoformat(), "mid", 3),
    ]
    groups = group_by_day(rows)
    # First group should be today, then yesterday, then 3 days ago.
    assert groups[0][0] == "Сегодня"
    assert groups[1][0] == "Вчера"


def test_group_by_day_old_date_uses_human_label():
    # A date more than 7 days ago — expect format "DD month YYYY" in Russian
    old = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT12:00:00+00:00")
    groups = group_by_day([_row(old)])
    label = groups[0][0]
    # Must contain a month name in Russian (any of them)
    month_names = [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    assert any(m in label for m in month_names), f"got label: {label}"


def test_group_by_day_handles_null_finished_at():
    # Rows without finished_at land in a "Unknown" group at the end
    rows = [_row(None, "ghost", 1)]  # type: ignore[arg-type]
    groups = group_by_day(rows)
    assert len(groups) == 1
    assert "Без даты" in groups[0][0] or "Unknown" in groups[0][0]


def test_group_by_day_same_day_keeps_all_rows():
    today_morning = datetime.now(UTC).replace(hour=9).isoformat()
    today_evening = datetime.now(UTC).replace(hour=22).isoformat()
    groups = group_by_day([
        _row(today_morning, "morning"),
        _row(today_evening, "evening"),
    ])
    assert len(groups) == 1
    assert len(groups[0][1]) == 2
