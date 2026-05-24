"""SQLite DAL — conn-per-thread, WAL, PRAGMAs applied on every connect.

Schema versioning is tracked in a ``schema_version`` table; migrations are
applied in order at startup.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# --- schema -----------------------------------------------------------------

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS downloads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT,
    url             TEXT NOT NULL,
    video_id        TEXT,
    title           TEXT,
    channel         TEXT,
    duration_s      INTEGER,
    file_size_bytes INTEGER,
    download_time_s REAL,
    avg_speed_mbps  REAL,
    file_path       TEXT,
    status          TEXT NOT NULL,
    error           TEXT,
    error_bucket    TEXT,
    started_at      TIMESTAMP,
    finished_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_finished_at ON downloads(finished_at);
CREATE INDEX IF NOT EXISTS idx_video_id ON downloads(video_id);
CREATE INDEX IF NOT EXISTS idx_status ON downloads(status);
"""

MIGRATIONS: list[tuple[int, str]] = [
    (1, SCHEMA_V1),
]


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
    )
    cur = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
    current = cur.fetchone()[0]
    for version, sql in MIGRATIONS:
        if version > current:
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
    conn.commit()


def init_db(path: Path | str) -> None:
    """Idempotent: ensure the DB file + schema exist."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with connect(p) as conn:
        _ensure_schema(conn)


@contextmanager
def connect(path: Path | str) -> Iterator[sqlite3.Connection]:
    """Open a fresh connection per call. Safe to use across threads."""
    conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        _apply_pragmas(conn)
        yield conn
    finally:
        conn.close()


# --- write path -------------------------------------------------------------

def insert_download(conn: sqlite3.Connection, **fields: Any) -> int:
    """Insert a row; returns the new rowid."""
    fields.setdefault("status", "pending")
    cols = list(fields.keys())
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO downloads ({', '.join(cols)}) VALUES ({placeholders})"
    cur = conn.execute(sql, [fields[c] for c in cols])
    return int(cur.lastrowid or 0)


def update_download(conn: sqlite3.Connection, row_id: int, **fields: Any) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    sql = f"UPDATE downloads SET {sets} WHERE id=?"
    conn.execute(sql, [*fields.values(), row_id])


# --- read path --------------------------------------------------------------

def get_recent(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM downloads ORDER BY COALESCE(finished_at, started_at) DESC, id DESC LIMIT ?",
            (limit,),
        )
    )


def get_by_id(conn: sqlite3.Connection, row_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM downloads WHERE id=?", (row_id,)).fetchone()


def find_successful_by_video_id(
    conn: sqlite3.Connection, video_id: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM downloads WHERE video_id=? AND status='success' "
        "ORDER BY finished_at DESC LIMIT 1",
        (video_id,),
    ).fetchone()


# --- aggregates for /api/stats ---------------------------------------------

def kpi_totals(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            COUNT(*)                                                AS total,
            COALESCE(SUM(file_size_bytes), 0)                       AS total_bytes,
            COALESCE(SUM(download_time_s), 0)                       AS total_time_s,
            COALESCE(AVG(avg_speed_mbps), 0)                        AS avg_speed_mbps,
            SUM(CASE WHEN status='success' THEN 1 ELSE 0 END)       AS success_count,
            SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END)        AS failed_count
        FROM downloads
        """
    ).fetchone()
    return {k: row[k] for k in row.keys()}


def downloads_by_day(conn: sqlite3.Connection, days: int = 30) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT date(finished_at) AS day, COUNT(*) AS n
        FROM downloads
        WHERE status='success'
          AND finished_at >= date('now', ?)
        GROUP BY day
        ORDER BY day
        """,
        (f"-{int(days)} days",),
    ).fetchall()
    return [{"day": r["day"], "n": r["n"]} for r in rows]


def top_channels(conn: sqlite3.Connection, limit: int = 10) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT channel, COUNT(*) AS n
        FROM downloads
        WHERE status='success' AND channel IS NOT NULL AND channel != ''
        GROUP BY channel
        ORDER BY n DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [{"channel": r["channel"], "n": r["n"]} for r in rows]


def speed_samples(conn: sqlite3.Connection, last_n: int = 500) -> list[float]:
    rows = conn.execute(
        """
        SELECT avg_speed_mbps FROM downloads
        WHERE status='success' AND avg_speed_mbps IS NOT NULL
        ORDER BY id DESC LIMIT ?
        """,
        (last_n,),
    ).fetchall()
    return [float(r["avg_speed_mbps"]) for r in rows]


def duration_samples(conn: sqlite3.Connection, last_n: int = 500) -> list[int]:
    rows = conn.execute(
        """
        SELECT duration_s FROM downloads
        WHERE status='success' AND duration_s IS NOT NULL
        ORDER BY id DESC LIMIT ?
        """,
        (last_n,),
    ).fetchall()
    return [int(r["duration_s"]) for r in rows]
