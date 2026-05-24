"""Single-URL yt-dlp wrapper. Pure function, fresh ydl_opts per call.

Returns a ``Result`` dataclass; never raises (errors are bucketed into the result).
Cancellation is cooperative via a ``threading.Event`` checked in the progress hook.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yt_dlp

from yt2mp3.helpers import classify_error, sanitize

log = logging.getLogger(__name__)


@dataclass
class Result:
    status: str  # 'success' | 'failed' | 'cancelled'
    url: str = ""
    video_id: str | None = None
    title: str | None = None
    channel: str | None = None
    duration_s: int | None = None
    file_size_bytes: int | None = None
    download_time_s: float | None = None
    avg_speed_mbps: float | None = None
    file_path: str | None = None
    error: str | None = None
    error_bucket: str | None = None
    progress: dict[str, Any] = field(default_factory=dict)


class _Cancelled(Exception):
    pass


def _make_progress_hook(cancel: threading.Event | None, state: dict[str, Any]):
    def hook(d: dict[str, Any]) -> None:
        if cancel is not None and cancel.is_set():
            raise _Cancelled("cancelled by user")
        # O(1) — overwrite the same keys; queue UI polls this dict.
        state["status"] = d.get("status", state.get("status"))
        if d.get("status") == "downloading":
            state["downloaded_bytes"] = d.get("downloaded_bytes")
            state["total_bytes"] = d.get("total_bytes") or d.get("total_bytes_estimate")
            state["speed"] = d.get("speed")
            state["eta"] = d.get("eta")
    return hook


def _make_postprocessor_hook(state: dict[str, Any]):
    def hook(d: dict[str, Any]) -> None:
        if d.get("status") == "started":
            state["phase"] = "converting"
        elif d.get("status") == "finished":
            state["phase"] = "converted"
    return hook


def download(
    url: str,
    download_dir: Path | str,
    cancel: threading.Event | None = None,
    progress_state: dict[str, Any] | None = None,
    yes_playlist: bool = False,
) -> Result:
    """Download a single video as MP3. Never raises — errors bucketed in Result."""
    state = progress_state if progress_state is not None else {}
    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    # First pass: extract info to get the real title for sanitized filename.
    info_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": not yes_playlist,
        "extract_flat": False,
    }
    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return Result(
            status="failed", url=url, error=str(e), error_bucket=classify_error(e)
        )

    if not info:
        return Result(status="failed", url=url, error="empty info", error_bucket="catastrophic")

    title = sanitize(info.get("title"), info.get("id"))
    outtmpl_base = str(download_dir / f"{title}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl_base,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": not yes_playlist,
        "restrictfilenames": False,  # preserve Cyrillic (D8 spec)
        "progress_hooks": [_make_progress_hook(cancel, state)],
        "postprocessor_hooks": [_make_postprocessor_hook(state)],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        # Don't write info/thumbs/subs by default.
        "writethumbnail": False,
        "writesubtitles": False,
        "writeinfojson": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.process_ie_result(info, download=True)
    except _Cancelled:
        return Result(status="cancelled", url=url, video_id=info.get("id"))
    except Exception as e:
        return Result(
            status="failed",
            url=url,
            video_id=info.get("id"),
            title=info.get("title"),
            error=str(e),
            error_bucket=classify_error(e),
        )

    finished = time.monotonic()
    elapsed = max(finished - started, 1e-6)
    out_path = download_dir / f"{title}.mp3"

    # Collision: append _2, _3, ...  (only matters when sanitized titles equal)
    if not out_path.exists():
        # yt-dlp may have produced .mp3 via collision suffix; pick the latest.
        candidates = sorted(
            download_dir.glob(f"{title}*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if candidates:
            out_path = candidates[0]

    size = out_path.stat().st_size if out_path.exists() else None
    speed_mbps = (size * 8 / 1_000_000 / elapsed) if size else None

    return Result(
        status="success",
        url=url,
        video_id=info.get("id"),
        title=info.get("title"),
        channel=info.get("uploader") or info.get("channel"),
        duration_s=int(info.get("duration") or 0) or None,
        file_size_bytes=size,
        download_time_s=elapsed,
        avg_speed_mbps=speed_mbps,
        file_path=str(out_path),
    )


def probe_info(url: str, yes_playlist: bool = False) -> dict[str, Any]:
    """Read URL metadata without downloading. Used for playlist detection."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": not yes_playlist,
        "extract_flat": "in_playlist",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info or {}
