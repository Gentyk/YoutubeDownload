"""Entry point: ``python -m yt2mp3``.

First-run hygiene: yt-dlp import probe, port-in-use detection, weekly staleness
warning. Server is bound to 127.0.0.1 by default (D8).
"""

from __future__ import annotations

import logging
import socket
import sys
from datetime import UTC, datetime, timedelta

import uvicorn

from yt2mp3 import config
from yt2mp3.logs import setup_logging

log = logging.getLogger("yt2mp3")


def _port_in_use(host: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
    except OSError:
        return True
    finally:
        s.close()
    return False


def _probe_yt_dlp() -> str | None:
    try:
        import yt_dlp  # noqa: F401
        return yt_dlp.version.__version__
    except ImportError as e:
        log.error("yt-dlp not importable: %s — run `uv sync`.", e)
        return None


def _staleness_warning(version: str) -> None:
    """yt-dlp releases ~weekly. Warn if our version is > 14 days behind today."""
    # yt-dlp version is "YYYY.MM.DD" (most modern builds)
    try:
        parts = [int(p) for p in version.split(".")[:3]]
        if len(parts) < 3:
            return
        v_date = datetime(parts[0], parts[1], parts[2], tzinfo=UTC)
    except (ValueError, IndexError):
        return
    age = datetime.now(UTC) - v_date
    if age > timedelta(days=14):
        log.warning(
            "yt-dlp version %s is %d days old. Run `uv add yt-dlp --upgrade` if YouTube changes its API.",
            version, age.days,
        )


def main() -> int:
    setup_logging()

    version = _probe_yt_dlp()
    if version is None:
        return 2
    log.info("yt-dlp version: %s", version)
    _staleness_warning(version)

    if _port_in_use(config.HOST, config.PORT):
        log.error(
            "Port %s:%s already in use. Stop the other process or set $YT2MP3_PORT.",
            config.HOST, config.PORT,
        )
        return 2

    log.info("Starting yt2mp3 on http://%s:%s", config.HOST, config.PORT)
    uvicorn.run(
        "yt2mp3.app:app",
        host=config.HOST,
        port=config.PORT,
        log_config=None,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
