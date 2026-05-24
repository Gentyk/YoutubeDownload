"""U4: URL extraction + YouTube allowlist."""

from __future__ import annotations

from yt2mp3.helpers import extract_urls, filter_youtube, normalize_url


def test_url_parser_extracts_from_mixed_text():
    text = "вот https://youtu.be/abc и https://www.youtube.com/watch?v=xyz123ABCDE"
    urls = extract_urls(text)
    assert "https://youtu.be/abc" in urls
    assert "https://www.youtube.com/watch?v=xyz123ABCDE" in urls


def test_url_parser_extracts_with_commas():
    text = "https://youtu.be/abc, https://youtu.be/def"
    urls = extract_urls(text)
    # Commas are stripped, not glued onto URL.
    assert "https://youtu.be/abc" in urls
    assert "https://youtu.be/def" in urls


def test_url_parser_rejects_non_youtube():
    text = "https://example.com/foo https://youtu.be/dQw4w9WgXcQ"
    urls = filter_youtube(extract_urls(text))
    assert urls == ["https://youtu.be/dQw4w9WgXcQ"]


def test_url_parser_empty_input():
    assert extract_urls("") == []
    assert extract_urls("no urls here") == []
    assert filter_youtube([]) == []


def test_normalize_url_extracts_video_id_from_short_form():
    vid = normalize_url("https://youtu.be/dQw4w9WgXcQ")
    assert vid == "dQw4w9WgXcQ"


def test_normalize_url_extracts_video_id_from_watch_form():
    vid = normalize_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RD")
    assert vid == "dQw4w9WgXcQ"


def test_normalize_url_returns_none_for_non_video():
    assert normalize_url("https://youtube.com/") is None
