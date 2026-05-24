"""Job queue: ThreadPoolExecutor + RLock + in-memory job dict + UUID job IDs.

Single critical section: DB-insert + remove-from-queue atomic so the dashboard
never shows a job that's not yet persisted, and the queue UI never shows a job
already in the DB.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from yt2mp3 import config, db, downloader
from yt2mp3.downloader import Result

log = logging.getLogger(__name__)


@dataclass
class Job:
    job_id: str
    url: str
    state: str = "queued"  # queued | downloading | converting | done | failed | cancelled
    progress: dict[str, Any] = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    submitted_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    result: Optional[Result] = None
    future: Optional[Future] = None


class QueueFull(Exception):
    pass


class JobQueue:
    """In-memory job registry on top of a ThreadPoolExecutor.

    Thread-safe: all reads/writes of the job dict go through ``self._lock``.
    """

    def __init__(
        self,
        max_workers: int = config.MAX_CONCURRENT,
        max_size: int = config.MAX_QUEUE_SIZE,
        db_path: Path | str = config.DB_PATH,
        download_dir: Path | str = config.DOWNLOAD_DIR,
    ) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="yt2mp3-dl"
        )
        self._max_size = max_size
        self._db_path = Path(db_path)
        self._download_dir = Path(download_dir)
        self._shutdown = False

    # ---- public API --------------------------------------------------------

    def submit(self, url: str, force: bool = False, yes_playlist: bool = False) -> str:
        if self._shutdown:
            raise RuntimeError("queue is shut down")
        with self._lock:
            if len([j for j in self._jobs.values() if j.state in ("queued", "downloading", "converting")]) >= self._max_size:
                raise QueueFull(f"queue is full ({self._max_size})")
            job = Job(job_id=str(uuid.uuid4()), url=url)
            self._jobs[job.job_id] = job
        log.info("submit url=%s job_id=%s", url, job.job_id)
        job.future = self._executor.submit(self._run, job, force, yes_playlist)
        return job.job_id

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return False
        job.cancel_event.set()
        # If still queued, mark cancelled now (worker will short-circuit).
        if job.state == "queued":
            with self._lock:
                job.state = "cancelled"
        return True

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def snapshot(self) -> list[Job]:
        """Active jobs, sorted by submission time."""
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.submitted_at)

    def wait_all(self, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                active = [j for j in self._jobs.values()
                          if j.state in ("queued", "downloading", "converting")]
            if not active:
                return
            time.sleep(0.05)
        raise TimeoutError(f"jobs still active after {timeout}s")

    def shutdown(self, wait: bool = True, cancel_pending: bool = True) -> None:
        self._shutdown = True
        if cancel_pending:
            with self._lock:
                for j in self._jobs.values():
                    j.cancel_event.set()
        self._executor.shutdown(wait=wait, cancel_futures=cancel_pending)

    # ---- internals ---------------------------------------------------------

    def _run(self, job: Job, force: bool, yes_playlist: bool) -> None:
        if job.cancel_event.is_set():
            with self._lock:
                job.state = "cancelled"
            self._persist_terminal(job, Result(status="cancelled", url=job.url))
            self._remove_after_grace(job)
            return

        with self._lock:
            job.state = "downloading"
            job.started_at = time.time()

        try:
            result = downloader.download(
                url=job.url,
                download_dir=self._download_dir,
                cancel=job.cancel_event,
                progress_state=job.progress,
                yes_playlist=yes_playlist,
            )
        except Exception as e:  # safety net — downloader should never raise
            log.exception("unhandled worker error job_id=%s", job.job_id)
            result = Result(status="failed", url=job.url, error=str(e), error_bucket="catastrophic")

        with self._lock:
            job.result = result
            if result.status == "success":
                job.state = "done"
            elif result.status == "cancelled":
                job.state = "cancelled"
            else:
                job.state = "failed"

        self._persist_terminal(job, result)
        # Keep terminal jobs visible for a short window so the UI can render
        # the "done"/"failed" transition before it disappears.
        self._remove_after_grace(job)

    def _persist_terminal(self, job: Job, result: Result) -> None:
        # Single critical section: insert into DB. We don't hold self._lock here
        # because DB writes are independent of in-memory state.
        from datetime import datetime, timezone

        finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        started = (
            datetime.fromtimestamp(job.started_at, tz=timezone.utc).isoformat(timespec="seconds")
            if job.started_at
            else finished
        )
        fields = {
            "job_id": job.job_id,
            "url": result.url or job.url,
            "video_id": result.video_id,
            "title": result.title,
            "channel": result.channel,
            "duration_s": result.duration_s,
            "file_size_bytes": result.file_size_bytes,
            "download_time_s": result.download_time_s,
            "avg_speed_mbps": result.avg_speed_mbps,
            "file_path": result.file_path,
            "status": result.status,
            "error": result.error,
            "error_bucket": result.error_bucket,
            "started_at": started,
            "finished_at": finished,
        }
        try:
            with db.connect(self._db_path) as conn:
                db.insert_download(conn, **fields)
        except Exception:
            log.exception("DB persist failed job_id=%s", job.job_id)

    def _remove_after_grace(self, job: Job, grace_s: float = 1.0) -> None:
        """Drop the job from the in-memory map after a short delay."""

        def drop() -> None:
            with self._lock:
                self._jobs.pop(job.job_id, None)

        timer = threading.Timer(grace_s, drop)
        timer.daemon = True
        timer.start()


# --- startup helpers --------------------------------------------------------

def cleanup_orphans(download_dir: Path | str) -> int:
    """Remove leftover *.part / *.m4a / *.webm files from a crashed previous run."""
    p = Path(download_dir)
    if not p.exists():
        return 0
    removed = 0
    for pattern in ("*.part", "*.m4a.part", "*.webm.part", "*.tmp"):
        for f in p.glob(pattern):
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    return removed
