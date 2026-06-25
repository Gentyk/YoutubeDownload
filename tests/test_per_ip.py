"""v3.1: per-IP track visibility, rolling 20/IP cap, inactivity cleanup, SEO."""

from __future__ import annotations

from pathlib import Path

from yt2mp3 import config, db
from yt2mp3.queue import JobQueue, cleanup_inactive


def _seed(conn, ip, title, file_path, when="now"):
    conn.execute(
        "INSERT INTO downloads (url, video_id, title, status, finished_at, file_path, client_ip) "
        f"VALUES (?, ?, ?, 'success', datetime('now', '{when}'), ?, ?)",
        (f"https://youtu.be/{title}", title[:11].ljust(11, 'x'), title, file_path, ip),
    )


# --- per-IP visibility ------------------------------------------------------

def test_library_scoped_to_requesting_ip(client, tmp_db_path: Path):
    with db.connect(tmp_db_path) as conn:
        _seed(conn, "1.1.1.1", "MineTrack", "mine.mp3")
        _seed(conn, "2.2.2.2", "OtherTrack", "other.mp3")

    mine = client.get("/library", headers={"X-Forwarded-For": "1.1.1.1"})
    assert "MineTrack" in mine.text
    assert "OtherTrack" not in mine.text

    other = client.get("/library", headers={"X-Forwarded-For": "2.2.2.2"})
    assert "OtherTrack" in other.text
    assert "MineTrack" not in other.text


def test_file_download_blocked_for_other_ip(client, tmp_db_path: Path, tmp_download_dir: Path):
    f = tmp_download_dir / "owned.mp3"
    f.write_bytes(b"ID3\x03" + b"\x00" * 50)
    with db.connect(tmp_db_path) as conn:
        _seed(conn, "1.1.1.1", "Owned", str(f))
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    ok = client.get(f"/file/{row_id}", headers={"X-Forwarded-For": "1.1.1.1"})
    assert ok.status_code == 200

    blocked = client.get(f"/file/{row_id}", headers={"X-Forwarded-For": "9.9.9.9"})
    assert blocked.status_code == 404  # someone else's file is invisible


# --- rolling 20/IP cap ------------------------------------------------------

def test_ip_cap_evicts_oldest(tmp_db_path: Path, tmp_download_dir: Path, monkeypatch):
    monkeypatch.setattr(config, "MAX_TRACKS_PER_IP", 5)
    files = []
    with db.connect(tmp_db_path) as conn:
        for i in range(7):
            fp = tmp_download_dir / f"cap{i}.mp3"
            fp.write_bytes(b"x")
            files.append(fp)
            _seed(conn, "cap.ip", f"Cap{i}", str(fp), when=f"-{7 - i} minutes")

    q = JobQueue(db_path=tmp_db_path, download_dir=tmp_download_dir)
    try:
        q._enforce_ip_cap("cap.ip")
    finally:
        q.shutdown(wait=False)

    with db.connect(tmp_db_path) as conn:
        assert db.count_active_by_ip(conn, "cap.ip") == 5
    # The two oldest files are gone, newest remain.
    assert not files[0].exists() and not files[1].exists()
    assert files[6].exists()


# --- inactivity cleanup -----------------------------------------------------

def test_inactivity_cleanup_removes_idle_ip(tmp_db_path: Path, tmp_download_dir: Path):
    fresh = tmp_download_dir / "fresh.mp3"
    fresh.write_bytes(b"x")
    stale = tmp_download_dir / "stale.mp3"
    stale.write_bytes(b"x")
    with db.connect(tmp_db_path) as conn:
        _seed(conn, "fresh.ip", "Fresh", str(fresh))
        _seed(conn, "stale.ip", "Stale", str(stale))
        db.touch_ip(conn, "fresh.ip")  # active now
        # stale.ip: backdate last_seen well past the threshold
        conn.execute(
            "INSERT INTO ip_activity(ip, last_seen) VALUES ('stale.ip', datetime('now','-10 days'))"
        )

    removed = cleanup_inactive(tmp_db_path, tmp_download_dir, days=3)
    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()
    with db.connect(tmp_db_path) as conn:
        assert db.count_active_by_ip(conn, "fresh.ip") == 1
        assert db.count_active_by_ip(conn, "stale.ip") == 0


# --- SEO --------------------------------------------------------------------

def test_robots_txt(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "User-agent: *" in r.text
    assert "Sitemap:" in r.text


def test_sitemap_xml(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert "<urlset" in r.text
    assert "/stats" in r.text


def test_one_audio_at_a_time_script_present(client):
    r = client.get("/")
    # global handler that pauses other media when one starts
    assert "addEventListener('play'" in r.text


# --- owner can delete own track; sysmon ------------------------------------

def test_owner_can_delete_own_track(client, tmp_db_path: Path, tmp_download_dir: Path):
    f = tmp_download_dir / "mine_del.mp3"
    f.write_bytes(b"x")
    with db.connect(tmp_db_path) as conn:
        _seed(conn, "testclient", "MineDel", str(f))
        rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    r = client.post(f"/file/{rid}/delete", follow_redirects=False)
    assert r.status_code == 200
    assert not f.exists()


def test_sysmon_samples():
    from yt2mp3.sysmon import SysMonitor
    m = SysMonitor(interval=1)
    m._prev_cpu = (100.0, 50.0)
    m._sample()
    latest = m.latest()
    assert "cpu_pct" in latest and "ram_pct" in latest
