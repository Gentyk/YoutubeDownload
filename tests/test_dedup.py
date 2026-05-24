"""U6: dedup logic."""

from __future__ import annotations

from pathlib import Path

from yt2mp3 import db
from yt2mp3.helpers import dedup_check


def test_dedup_same_video_id_skips_second(tmp_db_path, tmp_download_dir):
    mp3 = tmp_download_dir / "x.mp3"
    mp3.write_bytes(b"\x00")
    with db.connect(tmp_db_path) as conn:
        db.insert_download(
            conn, video_id="abcDEF12345", status="success", file_path=str(mp3),
            url="https://youtu.be/abcDEF12345",
        )
    result = dedup_check(tmp_db_path, "abcDEF12345", force=False)
    assert result.action == "skip"


def test_dedup_force_overrides(tmp_db_path, tmp_download_dir):
    mp3 = tmp_download_dir / "x.mp3"
    mp3.write_bytes(b"\x00")
    with db.connect(tmp_db_path) as conn:
        db.insert_download(
            conn, video_id="abcDEF12345", status="success", file_path=str(mp3),
            url="https://youtu.be/abcDEF12345",
        )
    result = dedup_check(tmp_db_path, "abcDEF12345", force=True)
    assert result.action == "redownload"


def test_dedup_file_missing_triggers_redownload(tmp_db_path, tmp_download_dir):
    missing = tmp_download_dir / "ghost.mp3"  # never created
    with db.connect(tmp_db_path) as conn:
        db.insert_download(
            conn, video_id="abcDEF12345", status="success", file_path=str(missing),
            url="https://youtu.be/abcDEF12345",
        )
    result = dedup_check(tmp_db_path, "abcDEF12345", force=False)
    assert result.action == "redownload"


def test_dedup_no_previous_returns_download(tmp_db_path):
    result = dedup_check(tmp_db_path, "abc12345xyz", force=False)
    assert result.action == "download"


def test_dedup_only_failed_attempts_returns_download(tmp_db_path):
    with db.connect(tmp_db_path) as conn:
        db.insert_download(
            conn, video_id="abcDEF12345", status="failed", url="https://youtu.be/abcDEF12345",
        )
    result = dedup_check(tmp_db_path, "abcDEF12345", force=False)
    assert result.action == "download"


def test_dedup_invalid_video_id_rejected(tmp_db_path):
    result = dedup_check(tmp_db_path, "not-an-id", force=False)
    assert result.action == "invalid"


def test_dedup_invalid_video_id_includes_path_chars(tmp_db_path):
    # Smoke for path-traversal-via-DB-stored video_id
    bad: str = "../" + "x" * 8
    result = dedup_check(tmp_db_path, bad, force=False)
    assert result.action == "invalid"
    _ = Path  # keep import noise quiet
