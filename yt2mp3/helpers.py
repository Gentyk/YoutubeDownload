"""Pure helper functions: sanitize, URL parsing, error classification, dedup.

No I/O except `dedup_check`, which reads SQLite + filesystem. Everything here
is independently unit-testable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yt_dlp

from yt2mp3 import config, db

# --- filename sanitize ------------------------------------------------------

_PATH_SEPS = re.compile(r"[\\/]")
_DOUBLE_DOTS = re.compile(r"\.{2,}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_TRIM_DOTS_SPACES = re.compile(r"[. ]+$")
_MAX_BYTES = 200


def _truncate_to_bytes(s: str, max_bytes: int) -> str:
    """Truncate to ``max_bytes`` of UTF-8 without splitting a codepoint."""
    encoded = s.encode("utf-8")
    if len(encoded) <= max_bytes:
        return s
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def sanitize(title: str | None, video_id: str | None) -> str:
    """Make a filesystem-safe filename. Preserves Unicode (incl. Cyrillic).

    Strips: path separators, control chars, ``..`` traversal patterns. Truncates
    to 200 bytes UTF-8. Falls back to ``video_id`` if title is empty, then
    ``"untitled"`` if both are empty.
    """
    t = (title or "").strip()
    t = unicodedata.normalize("NFC", t)
    t = _PATH_SEPS.sub("", t)
    t = _DOUBLE_DOTS.sub("", t)
    t = _CONTROL.sub("", t)
    t = _TRIM_DOTS_SPACES.sub("", t).strip()
    t = _truncate_to_bytes(t, _MAX_BYTES)
    t = _TRIM_DOTS_SPACES.sub("", t).strip()  # truncation may bare a trailing space

    if not t:
        vid = (video_id or "").strip()
        return vid or "untitled"
    return t


# --- URL parsing ------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s,]+")


def extract_urls(text: str) -> list[str]:
    """Pull all http(s) tokens out of arbitrary text. Trailing punctuation kept off."""
    if not text:
        return []
    found = _URL_RE.findall(text)
    return [u.rstrip(".,;:!?") for u in found]


def filter_youtube(urls: list[str]) -> list[str]:
    """Keep only URLs whose host is in the YouTube allowlist."""
    out: list[str] = []
    for u in urls:
        try:
            host = (urlparse(u).hostname or "").lower()
        except ValueError:
            continue
        if host in config.YOUTUBE_HOSTS:
            out.append(u)
    return out


_VIDEO_ID_RE = re.compile(config.VIDEO_ID_RE)


def is_valid_video_id(s: str | None) -> bool:
    return bool(s and _VIDEO_ID_RE.match(s))


def normalize_url(url: str) -> str | None:
    """Extract the canonical 11-char video_id from a YouTube URL, or None.

    Recognises ``youtu.be/<id>``, ``youtube.com/watch?v=<id>``,
    ``youtube.com/shorts/<id>``, ``youtube.com/embed/<id>``.
    """
    if not url:
        return None
    try:
        p = urlparse(url)
    except ValueError:
        return None
    host = (p.hostname or "").lower()
    if host not in config.YOUTUBE_HOSTS:
        return None
    if host == "youtu.be":
        cand = p.path.lstrip("/").split("/", 1)[0]
        return cand if is_valid_video_id(cand) else None
    # youtube.com variants
    if p.path == "/watch":
        v = parse_qs(p.query).get("v", [""])[0]
        return v if is_valid_video_id(v) else None
    for prefix in ("/shorts/", "/embed/", "/v/"):
        if p.path.startswith(prefix):
            cand = p.path[len(prefix):].split("/", 1)[0]
            return cand if is_valid_video_id(cand) else None
    return None


def is_playlist_url(url: str) -> bool:
    """True if URL has a `list=` query that looks like a playlist."""
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if (p.hostname or "").lower() not in config.YOUTUBE_HOSTS:
        return False
    qs = parse_qs(p.query)
    plist = qs.get("list", [""])[0]
    # YouTube playlist IDs typically start with PL/RD/UU/LL/FL/OL; minimum length 13+
    return bool(plist) and len(plist) >= 13 and p.path != "/watch"  # /playlist?list=...
    # Note: /watch?v=...&list=... is treated as single video, not playlist.


def is_playlist_only_url(url: str) -> bool:
    """`/playlist?list=...` form — explicit playlist."""
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if (p.hostname or "").lower() not in config.YOUTUBE_HOSTS:
        return False
    if p.path != "/playlist":
        return False
    qs = parse_qs(p.query)
    return bool(qs.get("list", [""])[0])


# --- error bucketing --------------------------------------------------------

def classify_error(e: BaseException) -> str:
    """Map an exception to one of: 'recoverable' | 'permanent' | 'catastrophic'.

    Buckets drive UX: recoverable = retry banner, permanent = per-row error,
    catastrophic = top banner with link to log.
    """
    msg = str(e).lower()

    # ffmpeg missing manifests as FileNotFoundError or yt-dlp PostProcessingError
    # with 'ffprobe/ffmpeg not found' inside.
    if isinstance(e, FileNotFoundError):
        return "catastrophic"
    if "ffmpeg" in msg or "ffprobe" in msg:
        return "catastrophic"

    # Disk full = OSError with ENOSPC
    if isinstance(e, OSError) and getattr(e, "errno", None) == 28:
        return "permanent"

    # yt-dlp specific
    if isinstance(e, yt_dlp.utils.GeoRestrictedError):
        return "permanent"
    if isinstance(e, yt_dlp.utils.PostProcessingError):
        return "permanent"
    if isinstance(e, yt_dlp.utils.ExtractorError):
        return "catastrophic"
    if isinstance(e, yt_dlp.utils.DownloadError):
        # Network blips, throttles
        return "recoverable"

    if isinstance(e, OSError):
        return "permanent"
    return "catastrophic"


# --- dedup ------------------------------------------------------------------

@dataclass(frozen=True)
class DedupResult:
    action: str  # 'download' | 'skip' | 'redownload' | 'invalid'
    existing_id: int | None = None
    existing_path: str | None = None


def dedup_check(
    db_path: Path | str,
    video_id: str,
    force: bool = False,
    client_ip: str | None = None,
) -> DedupResult:
    if not is_valid_video_id(video_id):
        return DedupResult(action="invalid")
    if force:
        return DedupResult(action="redownload")
    with db.connect(db_path) as conn:
        row = db.find_successful_by_video_id(conn, video_id, client_ip=client_ip)
    if row is None:
        return DedupResult(action="download")
    file_path = row["file_path"]
    if file_path and Path(file_path).exists():
        return DedupResult(
            action="skip", existing_id=int(row["id"]), existing_path=file_path
        )
    return DedupResult(
        action="redownload", existing_id=int(row["id"]), existing_path=file_path
    )
