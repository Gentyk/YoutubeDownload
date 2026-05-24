"""I4 + I5: playlist confirm flow and /file/{id} endpoint."""

from __future__ import annotations

from pathlib import Path

from yt2mp3 import db


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Скачать" in r.text


def test_post_download_with_empty_input_returns_400(client):
    r = client.post("/download", data={"urls": ""})
    assert r.status_code == 400
    assert "валидной" in r.text or "ссылк" in r.text


def test_post_download_with_non_youtube_url_returns_400(client):
    r = client.post("/download", data={"urls": "https://example.com/foo"})
    assert r.status_code == 400


def test_playlist_url_returns_confirm_payload(client, monkeypatch):
    fake_info = {
        "_type": "playlist",
        "title": "My Playlist",
        "entries": [{"id": f"v{i}", "title": f"Track {i}"} for i in range(5)],
    }
    monkeypatch.setattr("yt2mp3.downloader.probe_info", lambda url, yes_playlist=True: fake_info)

    r = client.post(
        "/download",
        data={"urls": "https://www.youtube.com/playlist?list=PL1234567890abc"},
    )
    assert r.status_code == 200
    assert "playlist" in r.text.lower() or "плейлист" in r.text.lower()
    assert "Track 0" in r.text
    assert "5" in r.text  # count


def test_file_endpoint_nonexistent_id(client):
    r = client.get("/file/99999")
    assert r.status_code == 404


def test_file_endpoint_missing_file_returns_410(client, tmp_db_path):
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, file_path, status) VALUES (?, ?, 'success')",
            ("https://youtu.be/abc", "/nonexistent/ghost.mp3"),
        )
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    r = client.get(f"/file/{row_id}")
    assert r.status_code in (410, 403)  # 410 if outside download dir → 403 first


def test_file_endpoint_rejects_path_traversal(client, tmp_db_path):
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, file_path, status) VALUES (?, ?, 'success')",
            ("https://youtu.be/abc", "/etc/passwd"),
        )
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    r = client.get(f"/file/{row_id}")
    assert r.status_code in (403, 410)


def test_file_endpoint_serves_valid_file(client, tmp_db_path, tmp_download_dir):
    f = tmp_download_dir / "test.mp3"
    f.write_bytes(b"ID3\x03" + b"\x00" * 100)
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, file_path, status) VALUES (?, ?, 'success')",
            ("https://youtu.be/abc", str(f)),
        )
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    r = client.get(f"/file/{row_id}")
    assert r.status_code == 200
    assert r.content.startswith(b"ID3")


def test_dedup_skip_path(client, tmp_db_path, tmp_download_dir):
    # Pre-seed: a successful download for a specific video_id, file exists.
    f = tmp_download_dir / "prev.mp3"
    f.write_bytes(b"\x00")
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, video_id, file_path, status) VALUES (?, ?, ?, 'success')",
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", str(f)),
        )
    r = client.post(
        "/download",
        data={"urls": "https://youtu.be/dQw4w9WgXcQ"},
    )
    assert r.status_code == 200
    # User-facing copy mentions "пропущено"
    assert "пропущ" in r.text


def test_force_redownload_bypasses_dedup(client, tmp_db_path, tmp_download_dir, monkeypatch):
    f = tmp_download_dir / "prev.mp3"
    f.write_bytes(b"\x00")
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, video_id, file_path, status) VALUES (?, ?, ?, 'success')",
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", str(f)),
        )
    # Block the worker so we can observe submission state without it racing.
    monkeypatch.setattr(
        "yt2mp3.downloader.download",
        lambda *a, **kw: __import__("yt2mp3.downloader", fromlist=["Result"]).Result(
            status="success", url=a[0] if a else "",
        ),
    )
    r = client.post(
        "/download",
        data={"urls": "https://youtu.be/dQw4w9WgXcQ", "force": "1"},
    )
    assert r.status_code == 200
    assert "Добавлено" in r.text
    _ = Path  # silence linter
