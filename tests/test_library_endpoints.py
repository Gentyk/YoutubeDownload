"""I6-I9: library, delete, X-Forwarded-For, stats redesign."""

from __future__ import annotations

from pathlib import Path

from yt2mp3 import db

# --- I6: delete endpoint ----------------------------------------------------

def test_delete_unlinks_file_and_soft_deletes_row(client, tmp_db_path: Path, tmp_download_dir: Path):
    f = tmp_download_dir / "to_delete.mp3"
    f.write_bytes(b"\x00" * 100)
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, video_id, title, file_path, status, finished_at) "
            "VALUES (?, ?, ?, ?, 'success', datetime('now'))",
            ("https://youtu.be/aaaBBBcccDD", "aaaBBBcccDD", "Test", str(f)),
        )
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    r = client.post(f"/file/{row_id}/delete", follow_redirects=False)
    assert r.status_code == 200
    assert not f.exists(), "file should be unlinked"

    with db.connect(tmp_db_path) as conn:
        row = conn.execute("SELECT deleted_at FROM downloads WHERE id=?", (row_id,)).fetchone()
    assert row["deleted_at"] is not None


def test_delete_nonexistent_row_returns_404(client):
    r = client.post("/file/99999/delete")
    assert r.status_code == 404


def test_delete_rejects_path_traversal(client, tmp_db_path: Path):
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, file_path, status) VALUES (?, ?, 'success')",
            ("https://youtu.be/x", "/etc/passwd"),
        )
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    r = client.post(f"/file/{row_id}/delete")
    assert r.status_code == 403


# --- I7: /library rendering -------------------------------------------------

def test_library_empty_state(client):
    r = client.get("/library")
    assert r.status_code == 200
    assert "Пока ничего не скачано" in r.text


def test_library_groups_by_day(client, tmp_db_path: Path):
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, video_id, title, status, finished_at, file_path, client_ip) "
            "VALUES (?, ?, ?, 'success', datetime('now'), 'a.mp3', 'testclient'), "
            "       (?, ?, ?, 'success', datetime('now', '-1 day'), 'b.mp3', 'testclient'), "
            "       (?, ?, ?, 'success', datetime('now', '-5 days'), 'c.mp3', 'testclient')",
            (
                "https://youtu.be/aaaaaaaaaaaa", "aaaaaaaaaaa1", "Today track",
                "https://youtu.be/bbbbbbbbbbbb", "bbbbbbbbbbb2", "Yesterday track",
                "https://youtu.be/cccccccccccc", "ccccccccccc3", "Old track",
            ),
        )
    r = client.get("/library")
    assert r.status_code == 200
    assert "Today track" in r.text
    assert "Yesterday track" in r.text
    assert "Old track" in r.text
    assert "Сегодня" in r.text
    assert "Вчера" in r.text


def test_library_excludes_deleted(client, tmp_db_path: Path):
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, video_id, title, status, finished_at, deleted_at, file_path) "
            "VALUES (?, ?, 'Should not show', 'success', datetime('now'), datetime('now'), 'ghost.mp3')",
            ("https://youtu.be/ghostghost1", "ghostghost1"),
        )
    r = client.get("/library")
    assert "Should not show" not in r.text


def test_library_fragment_returns_recent_5(client, tmp_db_path: Path):
    with db.connect(tmp_db_path) as conn:
        for i in range(7):
            conn.execute(
                "INSERT INTO downloads (url, video_id, title, status, finished_at, file_path, client_ip) "
                "VALUES (?, ?, ?, 'success', datetime('now', ?), ?, 'testclient')",
                (
                    f"https://youtu.be/zz{i:09d}",
                    f"zz{i:09d}",
                    f"Track {i}",
                    f"-{i} seconds",
                    f"file{i}.mp3",
                ),
            )
    r = client.get("/library/fragment")
    assert r.status_code == 200
    assert "Track 0" in r.text
    assert "Track 4" in r.text
    assert "Track 5" not in r.text
    assert "Track 6" not in r.text


# --- I8: X-Forwarded-For client IP ------------------------------------------

def test_client_ip_from_x_forwarded_for(client, monkeypatch):
    captured: dict = {}

    def capture(self, url, force=False, yes_playlist=False, client_ip=None):
        captured["ip"] = client_ip
        return "fake-job-id"

    from yt2mp3.queue import JobQueue
    monkeypatch.setattr(JobQueue, "submit", capture)

    client.post(
        "/download",
        data={"urls": "https://youtu.be/dQw4w9WgXcQ"},
        headers={"X-Forwarded-For": "203.0.113.5, 10.0.0.1"},
    )
    assert captured["ip"] == "203.0.113.5"


def test_client_ip_falls_back_to_request_client(client, monkeypatch):
    captured: dict = {}

    def capture(self, url, force=False, yes_playlist=False, client_ip=None):
        captured["ip"] = client_ip
        return "fake-job-id"

    from yt2mp3.queue import JobQueue
    monkeypatch.setattr(JobQueue, "submit", capture)

    client.post(
        "/download",
        data={"urls": "https://youtu.be/dQw4w9WgXcQ"},
    )
    assert captured["ip"] == "testclient"


# --- I9: stats redesign ------------------------------------------------------

def test_stats_no_longer_links_to_files(client, tmp_db_path: Path):
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, title, status, file_path, finished_at, client_ip) "
            "VALUES (?, 'show me', 'success', 'a.mp3', datetime('now'), 'testclient')",
            ("https://youtu.be/dQw4w9WgXcQ",),
        )
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    r = client.get("/stats")
    assert r.status_code == 200
    assert "show me" in r.text
    assert f'href="/file/{row_id}"' not in r.text


def test_api_stats_contains_by_ip(client, tmp_db_path: Path):
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, status, client_ip, finished_at) "
            "VALUES (?, 'success', ?, datetime('now')), (?, 'success', ?, datetime('now'))",
            (
                "https://youtu.be/aaaaaaaaaaaa", "1.2.3.4",
                "https://youtu.be/bbbbbbbbbbbb", "1.2.3.4",
            ),
        )
    r = client.get("/api/stats")
    assert r.status_code == 200
    payload = r.json()
    assert "by_ip" in payload
    assert len(payload["by_ip"]) >= 1
    assert payload["by_ip"][0]["ip"] == "1.2.3.4"
    assert payload["by_ip"][0]["n"] == 2


def test_kpi_totals_includes_active_count(client, tmp_db_path: Path):
    with db.connect(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, status, finished_at) "
            "VALUES (?, 'success', datetime('now')), "
            "       (?, 'success', datetime('now')), "
            "       (?, 'failed', datetime('now'))",
            (
                "https://youtu.be/aaaaaaaaaaaa",
                "https://youtu.be/bbbbbbbbbbbb",
                "https://youtu.be/cccccccccccc",
            ),
        )
        conn.execute("UPDATE downloads SET deleted_at=datetime('now') WHERE id=1")

    r = client.get("/api/stats")
    payload = r.json()
    assert payload["kpi"]["total"] == 3
    assert payload["kpi"]["success_count"] == 2
    assert payload["kpi"]["active_count"] == 1
