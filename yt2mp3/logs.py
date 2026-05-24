"""Structured logging setup — console + file (yt2mp3.log)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from yt2mp3 import config

_FMT = "%(asctime)s %(levelname)-5s %(name)s — %(message)s"


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if root.handlers:
        return  # already configured
    formatter = logging.Formatter(_FMT)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        config.LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
