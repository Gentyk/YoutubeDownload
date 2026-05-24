"""Session-based login tests."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


def _reload_with_auth(monkeypatch, user: str, password: str, tmp_db_path, tmp_download_dir):
    monkeypatch.setenv("YT2MP3_DB_PATH", str(tmp_db_path))
    monkeypatch.setenv("YT2MP3_DOWNLOAD_DIR", str(tmp_download_dir))
    monkeypatch.setenv("YT2MP3_AUTH_USER", user)
    monkeypatch.setenv("YT2MP3_AUTH_PASS", password)
    monkeypatch.setenv("YT2MP3_SECRET_KEY", "test-secret-key-for-determinism")

    from yt2mp3 import app as app_module
    from yt2mp3 import config as config_module
    from yt2mp3 import queue as queue_module

    importlib.reload(config_module)
    importlib.reload(queue_module)
    importlib.reload(app_module)
    return app_module.app


def test_no_auth_required_when_env_unset(client):
    # client fixture leaves auth env vars unset → all routes open.
    assert client.get("/").status_code == 200
    assert client.get("/healthz").status_code == 200
    # /login still redirects somewhere reasonable when auth is off
    r = client.get("/login", follow_redirects=False)
    assert r.status_code == 303


def test_unauthenticated_request_redirects_to_login(monkeypatch, tmp_db_path, tmp_download_dir):
    app = _reload_with_auth(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        r = c.get("/", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/login")
        assert "next=" in r.headers["location"]


def test_login_form_renders(monkeypatch, tmp_db_path, tmp_download_dir):
    app = _reload_with_auth(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        r = c.get("/login")
        assert r.status_code == 200
        assert "Войти" in r.text
        assert 'name="username"' in r.text
        assert 'name="password"' in r.text


def test_login_with_correct_credentials_sets_cookie(monkeypatch, tmp_db_path, tmp_download_dir):
    app = _reload_with_auth(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        r = c.post(
            "/login",
            data={"username": "vlad", "password": "s3cret", "next": "/stats"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/stats"
        assert "session" in r.cookies or any("session" in k for k in r.cookies.keys())
        # Now authenticated requests work
        r2 = c.get("/", follow_redirects=False)
        assert r2.status_code == 200


def test_login_with_wrong_password_returns_401(monkeypatch, tmp_db_path, tmp_download_dir):
    app = _reload_with_auth(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        r = c.post("/login", data={"username": "vlad", "password": "wrong"})
        assert r.status_code == 401
        assert "Неверный" in r.text


def test_logout_clears_session(monkeypatch, tmp_db_path, tmp_download_dir):
    app = _reload_with_auth(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        c.post("/login", data={"username": "vlad", "password": "s3cret"})
        assert c.get("/", follow_redirects=False).status_code == 200
        r = c.post("/logout", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"
        # After logout: redirected to /login again
        r2 = c.get("/", follow_redirects=False)
        assert r2.status_code == 303
        assert r2.headers["location"].startswith("/login")


def test_healthz_open_even_when_auth_required(monkeypatch, tmp_db_path, tmp_download_dir):
    """Uptime monitors must be able to ping /healthz without login."""
    app = _reload_with_auth(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.json()["ok"] is True


def test_static_assets_open(monkeypatch, tmp_db_path, tmp_download_dir):
    """Tailwind/Chart.js must load on the login page."""
    app = _reload_with_auth(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        r = c.get("/static/tailwind.js", follow_redirects=False)
        assert r.status_code == 200


def test_open_redirect_protection(monkeypatch, tmp_db_path, tmp_download_dir):
    """next=... must only accept relative paths."""
    app = _reload_with_auth(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        r = c.post(
            "/login",
            data={"username": "vlad", "password": "s3cret", "next": "//evil.com/x"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/"

        r2 = c.post(
            "/login",
            data={"username": "vlad", "password": "s3cret", "next": "https://evil.com"},
            follow_redirects=False,
        )
        assert r2.headers["location"] == "/"


def test_already_logged_in_login_get_redirects_home(monkeypatch, tmp_db_path, tmp_download_dir):
    app = _reload_with_auth(monkeypatch, "vlad", "s3cret", tmp_db_path, tmp_download_dir)
    with TestClient(app) as c:
        c.post("/login", data={"username": "vlad", "password": "s3cret"})
        r = c.get("/login", follow_redirects=False)
        assert r.status_code == 303


@pytest.fixture(autouse=True)
def _restore_env(monkeypatch):
    """Make sure auth env vars don't leak between tests."""
    monkeypatch.delenv("YT2MP3_AUTH_USER", raising=False)
    monkeypatch.delenv("YT2MP3_AUTH_PASS", raising=False)
    monkeypatch.delenv("YT2MP3_SECRET_KEY", raising=False)
    yield
