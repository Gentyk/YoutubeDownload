"""Basic Auth middleware tests."""

from __future__ import annotations

import base64
import importlib

import pytest
from fastapi.testclient import TestClient


def _reload_app(monkeypatch, user: str, password: str, tmp_db_path, tmp_download_dir):
    monkeypatch.setenv("YT2MP3_DB_PATH", str(tmp_db_path))
    monkeypatch.setenv("YT2MP3_DOWNLOAD_DIR", str(tmp_download_dir))
    monkeypatch.setenv("YT2MP3_AUTH_USER", user)
    monkeypatch.setenv("YT2MP3_AUTH_PASS", password)

    from yt2mp3 import app as app_module
    from yt2mp3 import config as config_module
    from yt2mp3 import queue as queue_module

    importlib.reload(config_module)
    importlib.reload(queue_module)
    importlib.reload(app_module)
    return app_module.app


def _basic_header(user: str, password: str) -> dict[str, str]:
    raw = f"{user}:{password}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def test_no_auth_required_when_env_unset(client):
    # Default `client` fixture leaves auth env vars unset → all routes open.
    assert client.get("/").status_code == 200
    assert client.get("/healthz").status_code == 200


def test_auth_required_when_env_set(monkeypatch, tmp_db_path, tmp_download_dir):
    app = _reload_app(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 401
        assert "WWW-Authenticate" in r.headers
        assert r.headers["WWW-Authenticate"].lower().startswith("basic")


def test_auth_succeeds_with_correct_credentials(monkeypatch, tmp_db_path, tmp_download_dir):
    app = _reload_app(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        r = c.get("/", headers=_basic_header("vlad", "s3cret"))
        assert r.status_code == 200
        assert "Скачать" in r.text


def test_auth_fails_with_wrong_password(monkeypatch, tmp_db_path, tmp_download_dir):
    app = _reload_app(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        r = c.get("/", headers=_basic_header("vlad", "wrong"))
        assert r.status_code == 401


def test_healthz_open_even_when_auth_required(monkeypatch, tmp_db_path, tmp_download_dir):
    """Hoster uptime monitors must be able to ping /healthz."""
    app = _reload_app(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.json()["ok"] is True


def test_auth_malformed_header_returns_401(monkeypatch, tmp_db_path, tmp_download_dir):
    app = _reload_app(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        # Not "Basic ", bare token, no creds
        for bad in ("Bearer xxx", "Basic", "Basic !!!notbase64!!!", ""):
            headers = {"Authorization": bad} if bad else {}
            r = c.get("/", headers=headers)
            assert r.status_code == 401, f"expected 401 for header {bad!r}"


@pytest.fixture(autouse=True)
def _restore_env(monkeypatch):
    """Make sure auth env vars don't leak between tests."""
    monkeypatch.delenv("YT2MP3_AUTH_USER", raising=False)
    monkeypatch.delenv("YT2MP3_AUTH_PASS", raising=False)
    yield
