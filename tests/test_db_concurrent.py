"""I1: concurrent SQLite writes from 5 threads."""

from __future__ import annotations

import threading
from pathlib import Path

from yt2mp3 import db


def test_concurrent_inserts_no_lock_errors(tmp_db_path: Path):
    def writer(thread_id: int) -> None:
        for i in range(20):
            with db.connect(tmp_db_path) as conn:
                db.insert_download(
                    conn,
                    url=f"https://youtu.be/t{thread_id}{i:02d}xxx",
                    video_id=f"t{thread_id}{i:02d}xxx",
                    status="success",
                )

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with db.connect(tmp_db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
    assert count == 100
