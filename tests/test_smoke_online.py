"""S1: end-to-end smoke test against real YouTube.

Excluded from default test run via the ``online`` marker; run with::

    uv run pytest -m online
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from yt2mp3 import db
from yt2mp3.queue import JobQueue


@pytest.mark.online
def test_smoke_real_youtube_download(tmp_db_path: Path, tmp_download_dir: Path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed in PATH — needed for mp3 conversion")

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    q = JobQueue(max_workers=1, db_path=tmp_db_path, download_dir=tmp_download_dir)
    try:
        q.submit(url)
        q.wait_all(timeout=120.0)
    finally:
        q.shutdown(wait=True, cancel_pending=False)

    files = list(tmp_download_dir.glob("*.mp3"))
    assert len(files) >= 1
    assert files[0].stat().st_size > 1_000_000

    with db.connect(tmp_db_path) as conn:
        row = conn.execute(
            "SELECT * FROM downloads WHERE video_id='dQw4w9WgXcQ'"
        ).fetchone()
    assert row is not None
    assert row["status"] == "success"
