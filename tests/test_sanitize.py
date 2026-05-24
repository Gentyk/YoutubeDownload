"""U1-U3: filename sanitize."""

from __future__ import annotations

from yt2mp3.helpers import sanitize

# U1 — empty title fallback ---------------------------------------------------

def test_sanitize_empty_title_falls_back_to_video_id():
    assert sanitize("", "dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert sanitize("   ", "dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert sanitize(None, "dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_sanitize_both_empty_returns_untitled():
    assert sanitize("", "") == "untitled"
    assert sanitize(None, None) == "untitled"


# U2 — Cyrillic preserved + byte truncation -----------------------------------

def test_sanitize_preserves_cyrillic():
    s = sanitize("Пятница - Я слышу тебя", "abc")
    assert s == "Пятница - Я слышу тебя"


def test_sanitize_truncates_to_200_bytes():
    long_cyr = "Я" * 200  # ~400 bytes
    s = sanitize(long_cyr, "abc")
    assert len(s.encode("utf-8")) <= 200
    # Valid UTF-8 — not split mid-character.
    s.encode("utf-8").decode("utf-8")


def test_sanitize_truncates_ascii_to_200_chars():
    long_ascii = "a" * 300
    s = sanitize(long_ascii, "abc")
    assert len(s) <= 200


# U3 — path traversal + control chars ----------------------------------------

def test_sanitize_strips_path_separators():
    assert "/" not in sanitize("a/b/c", "x")
    assert "\\" not in sanitize("a\\b\\c", "x")


def test_sanitize_strips_double_dot_traversal():
    assert ".." not in sanitize("../../etc/passwd", "x")


def test_sanitize_strips_control_chars():
    assert "\x00" not in sanitize("hello\x00world", "x")
    for c in range(0x00, 0x20):
        assert chr(c) not in sanitize(f"a{chr(c)}b", "x")


def test_sanitize_strips_trailing_dots_and_spaces():
    assert sanitize("My Title...", "x").rstrip().rstrip(".") == sanitize("My Title...", "x")
    assert not sanitize("trailing ", "x").endswith(" ")
    assert not sanitize("trailing.", "x").endswith(".")
