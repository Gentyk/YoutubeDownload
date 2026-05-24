"""Centralised config — env vars + computed paths.

Read once at startup; modules import these constants instead of touching os.environ.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DOWNLOAD_DIR = Path(
    os.environ.get("YT2MP3_DOWNLOAD_DIR") or (REPO_ROOT / "downloads")
).resolve()

DB_PATH = Path(
    os.environ.get("YT2MP3_DB_PATH") or (REPO_ROOT / "yt2mp3.db")
).resolve()

LOG_PATH = Path(
    os.environ.get("YT2MP3_LOG_PATH") or (REPO_ROOT / "yt2mp3.log")
).resolve()

MAX_CONCURRENT = int(os.environ.get("YT2MP3_MAX_CONCURRENT", "3"))
MAX_QUEUE_SIZE = int(os.environ.get("YT2MP3_MAX_QUEUE_SIZE", "50"))

HOST = os.environ.get("YT2MP3_HOST", "127.0.0.1")
PORT = int(os.environ.get("YT2MP3_PORT", "8000"))

# Login (cookie-session). Enforced when BOTH user and pass are set.
# Leave empty for local-only deployments.
AUTH_USER = os.environ.get("YT2MP3_AUTH_USER", "")
AUTH_PASS = os.environ.get("YT2MP3_AUTH_PASS", "")

# Signing key for session cookies. If unset, a random key is generated at
# startup — that means sessions invalidate on every restart. For stable
# sessions across restarts set this to a long random string.
SECRET_KEY = os.environ.get("YT2MP3_SECRET_KEY", "")

# Session cookie lifetime in seconds (default: 14 days).
SESSION_MAX_AGE = int(os.environ.get("YT2MP3_SESSION_MAX_AGE", str(14 * 24 * 3600)))

YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)

VIDEO_ID_RE = r"^[A-Za-z0-9_-]{11}$"

MIN_QUEUE_DISPLAY_MS = 800  # UX: keep "Downloading" visible at least this long
