"""Entry point: ``python -m yt2mp3``."""

from __future__ import annotations

import logging
import socket
import sys

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


def main() -> int:
    setup_logging()
    if _port_in_use(config.HOST, config.PORT):
        log.error("Port %s:%s already in use. Stop the other process or set $YT2MP3_PORT.",
                  config.HOST, config.PORT)
        return 2
    log.info("Starting yt2mp3 on http://%s:%s", config.HOST, config.PORT)
    uvicorn.run(
        "yt2mp3.app:app",
        host=config.HOST,
        port=config.PORT,
        log_config=None,  # we set up logging ourselves
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
