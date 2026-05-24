"""I2 + I3: queue submits-complete and worker crash handling."""

from __future__ import annotations

import logging

import pytest

from yt2mp3 import db, downloader
from yt2mp3.downloader import Result
from yt2mp3.queue import JobQueue


def test_queue_processes_all_jobs_with_max_workers_3(tmp_db_path, tmp_download_dir, monkeypatch):
    calls = {"n": 0}
    lock = __import__("threading").Lock()

    def fake_download(url, download_dir, cancel=None, progress_state=None, yes_playlist=False):
        with lock:
            calls["n"] += 1
            n = calls["n"]
        return Result(
            status="success",
            url=url,
            video_id=f"vid{n:08d}",
            title=f"Track {n}",
            channel="Test",
            duration_s=10,
            file_size_bytes=100,
            download_time_s=0.1,
            avg_speed_mbps=8.0,
            file_path=str(tmp_download_dir / f"track-{n}.mp3"),
        )

    monkeypatch.setattr(downloader, "download", fake_download)
    q = JobQueue(max_workers=3, db_path=tmp_db_path, download_dir=tmp_download_dir)
    job_ids = [q.submit(f"https://youtu.be/v{i:09d}") for i in range(10)]
    q.wait_all(timeout=5.0)
    q.shutdown(wait=True, cancel_pending=False)

    with db.connect(tmp_db_path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
    assert rows == 10
    # Eventually all jobs are removed from in-memory state (grace timer is 1s).
    import time
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and any(q.get_job(jid) is not None for jid in job_ids):
        time.sleep(0.1)
    assert all(q.get_job(jid) is None for jid in job_ids)


def test_worker_exception_logged_and_marked_failed(tmp_db_path, tmp_download_dir, monkeypatch, caplog):
    def crashing_download(*args, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(downloader, "download", crashing_download)
    q = JobQueue(max_workers=1, db_path=tmp_db_path, download_dir=tmp_download_dir)

    with caplog.at_level(logging.ERROR, logger="yt2mp3.queue"):
        job_id = q.submit("https://youtu.be/xboomboomx")
        q.wait_all(timeout=2.0)
    q.shutdown(wait=True, cancel_pending=False)

    # Logged the unhandled error (message or exc_info traceback)
    def _includes_boom(r):
        if "boom" in r.getMessage():
            return True
        if r.exc_info:
            import traceback
            return "boom" in "".join(traceback.format_exception(*r.exc_info))
        return False

    assert any(_includes_boom(r) for r in caplog.records)

    # Marked failed in DB
    with db.connect(tmp_db_path) as conn:
        row = conn.execute(
            "SELECT status, error FROM downloads WHERE job_id=?", (job_id,)
        ).fetchone()
    assert row is not None
    assert row["status"] == "failed"
    assert "boom" in row["error"]


def test_queue_full_raises():
    from yt2mp3 import config
    from yt2mp3.queue import QueueFull
    q = JobQueue(max_workers=1, max_size=2, db_path=":memory:", download_dir=".")
    # Block the worker by submitting a slow job.
    import threading

    barrier = threading.Event()

    def slow_dl(url, download_dir, cancel=None, progress_state=None, yes_playlist=False):
        barrier.wait(timeout=2)
        return Result(status="success", url=url)

    import yt2mp3.downloader as dlmod
    orig = dlmod.download
    dlmod.download = slow_dl
    try:
        q.submit("https://youtu.be/a")
        q.submit("https://youtu.be/b")
        with pytest.raises(QueueFull):
            q.submit("https://youtu.be/c")
    finally:
        barrier.set()
        dlmod.download = orig
        q.shutdown(wait=True, cancel_pending=True)
    _ = config  # silence linter
