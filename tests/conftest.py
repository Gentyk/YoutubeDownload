"""Shared fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Per-test SQLite file with full schema applied."""
    from yt2mp3 import db

    p = tmp_path / "yt2mp3.db"
    db.init_db(p)
    return p


@pytest.fixture
def tmp_download_dir(tmp_path: Path) -> Path:
    d = tmp_path / "downloads"
    d.mkdir()
    return d


@pytest.fixture
def client(tmp_db_path: Path, tmp_download_dir: Path, monkeypatch):
    """Test client with isolated DB + download dir."""
    monkeypatch.setenv("YT2MP3_DB_PATH", str(tmp_db_path))
    monkeypatch.setenv("YT2MP3_DOWNLOAD_DIR", str(tmp_download_dir))
    # Reload config so the env vars take effect.
    import importlib

    from yt2mp3 import app as app_module
    from yt2mp3 import config as config_module
    from yt2mp3 import queue as queue_module
    importlib.reload(config_module)
    importlib.reload(queue_module)
    importlib.reload(app_module)

    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as c:
        yield c


def pytest_configure(config):
    """Make sure online marker is registered."""
    config.addinivalue_line("markers", "online: real network test")
    # Ensure repo root is on sys.path so `import yt2mp3` works without install.
    import sys

    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    # Default downloads dir for tests that don't override
    os.environ.setdefault("YT2MP3_DOWNLOAD_DIR", str(repo_root / "downloads"))
