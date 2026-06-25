"""FastAPI routes. No business logic — delegates to queue/downloader/db/helpers."""

from __future__ import annotations

import logging
import secrets
import shutil
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from yt2mp3 import config, db
from yt2mp3.helpers import (
    dedup_check,
    extract_urls,
    filter_youtube,
    is_playlist_only_url,
    normalize_url,
)
from yt2mp3.library import group_by_day
from yt2mp3.logs import setup_logging
from yt2mp3.queue import JobQueue, QueueFull, cleanup_orphans

log = logging.getLogger("yt2mp3.app")

PKG_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PKG_DIR / "templates"
STATIC_DIR = PKG_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Module-level singleton; created in lifespan so test reload picks up env vars.
_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    if _queue is None:
        raise RuntimeError("queue not initialised")
    return _queue


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    setup_logging()
    global _queue

    # First-run hygiene: ffmpeg probe, log warning if missing
    if shutil.which("ffmpeg") is None:
        log.warning("ffmpeg not found in PATH — mp3 conversion will fail. brew install ffmpeg.")

    db.init_db(config.DB_PATH)
    refresh_login_required()
    removed = cleanup_orphans(config.DOWNLOAD_DIR)
    if removed:
        log.info("cleaned %s orphan .part files", removed)

    _queue = JobQueue(
        max_workers=config.MAX_CONCURRENT,
        max_size=config.MAX_QUEUE_SIZE,
        db_path=config.DB_PATH,
        download_dir=config.DOWNLOAD_DIR,
    )
    log.info("queue started: max_workers=%s max_size=%s", config.MAX_CONCURRENT, config.MAX_QUEUE_SIZE)
    if ADMIN_ENABLED:
        mode = "REQUIRED for whole site" if login_required_enabled() else "OPEN (admin panel only)"
        log.info("Admin ENABLED (user=%s); site login: %s", config.AUTH_USER, mode)
        if not config.SECRET_KEY:
            log.warning(
                "YT2MP3_SECRET_KEY not set — sessions invalidate on restart. "
                "Set a long random string for persistent logins."
            )
    else:
        log.warning(
            "Admin DISABLED (no YT2MP3_AUTH_USER/PASS) — site fully OPEN, no admin panel. "
            "Bind to 127.0.0.1 or use a VPN; do NOT expose publicly without admin creds."
        )
    try:
        yield
    finally:
        log.info("shutting down queue")
        if _queue is not None:
            _queue.shutdown(wait=True, cancel_pending=True)
        _queue = None


app = FastAPI(title="yt2mp3", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Access control: open-by-default site + optional admin login ------------
#
# Model:
#   * Admin features exist only when YT2MP3_AUTH_USER + YT2MP3_AUTH_PASS are set
#     (config.ADMIN_ENABLED).
#   * /admin and destructive actions (file delete) ALWAYS require admin login.
#   * The rest of the site is open to all UNLESS the runtime toggle
#     `settings.login_required` (stored in DB) is on — then the whole site
#     requires admin login. Default: off (open).

ADMIN_ENABLED = config.ADMIN_ENABLED
templates.env.globals["ADMIN_ENABLED"] = ADMIN_ENABLED

_OPEN_PATHS = frozenset({"/login", "/logout", "/healthz"})
_OPEN_PREFIXES = ("/static/",)

# In-process cache of the login_required flag; refreshed at startup and on toggle.
_login_required_cache: bool = False


def refresh_login_required() -> bool:
    """Re-read the login toggle from the DB into the module cache."""
    global _login_required_cache
    try:
        with db.connect(config.DB_PATH) as conn:
            _login_required_cache = db.get_login_required(conn)
    except Exception:
        log.exception("failed to read login_required setting")
    return _login_required_cache


def login_required_enabled() -> bool:
    return _login_required_cache


def _session_user(scope_or_request) -> str | None:
    session = getattr(scope_or_request, "session", None)
    if session is None and isinstance(scope_or_request, dict):
        session = scope_or_request.get("session")
    return (session or {}).get("user")


def _is_admin(request: Request) -> bool:
    """True when the request carries a valid admin session."""
    if not ADMIN_ENABLED:
        return False
    try:
        return request.session.get("user") == config.AUTH_USER
    except (AssertionError, KeyError, AttributeError):
        return False


# Expose to templates: {% if is_admin(request) %}
templates.env.globals["is_admin"] = _is_admin


def _is_admin_only_path(path: str) -> bool:
    """Paths that always require admin login, regardless of the open/closed toggle."""
    if path == "/admin" or path.startswith("/admin/"):
        return True
    # Destructive: POST /file/{id}/delete
    if path.startswith("/file/") and path.endswith("/delete"):
        return True
    return False


class SecurityHeadersMiddleware:
    """Add baseline security headers to every HTTP response."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                ])
            await send(message)

        await self.app(scope, receive, send_wrapper)


class AccessControlMiddleware:
    """Gate requests based on admin session + the login_required toggle.

    Active only when ADMIN_ENABLED. Open paths (static/login/logout/healthz) always
    pass. Admin-only paths require an admin session. Everything else requires a
    session only while the runtime toggle is on.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not ADMIN_ENABLED:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in _OPEN_PATHS or any(path.startswith(p) for p in _OPEN_PREFIXES):
            await self.app(scope, receive, send)
            return

        is_admin = _session_user(scope) == config.AUTH_USER
        admin_only = _is_admin_only_path(path)

        if admin_only or login_required_enabled():
            if is_admin:
                await self.app(scope, receive, send)
                return
            await self._redirect_login(scope, send)
            return

        await self.app(scope, receive, send)

    async def _redirect_login(self, scope, send) -> None:
        next_url = scope.get("path", "/")
        if scope.get("query_string"):
            next_url += "?" + scope["query_string"].decode("latin-1")
        location = "/login?next=" + next_url
        await send({
            "type": "http.response.start",
            "status": 303,
            "headers": [
                (b"location", location.encode("latin-1")),
                (b"content-length", b"0"),
            ],
        })
        await send({"type": "http.response.body", "body": b""})


app.add_middleware(SecurityHeadersMiddleware)
if ADMIN_ENABLED:
    # ORDER MATTERS — middlewares wrap LIFO, so the LAST added runs OUTERMOST.
    # Flow we want: Session populates scope["session"] → AccessControl reads it.
    # So add AccessControl FIRST, Session LAST (Session outermost / runs first).
    app.add_middleware(AccessControlMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.SECRET_KEY or secrets.token_urlsafe(32),
        max_age=config.SESSION_MAX_AGE,
        same_site="lax",
        https_only=config.SECURE_COOKIES,  # True when behind HTTPS (Caddy)
    )


# --- login brute-force throttle (in-process, per-IP) ------------------------

_LOGIN_WINDOW_S = 300  # 5 min
_LOGIN_MAX_FAILS = 10
_login_fails: dict[str, list[float]] = {}


def _login_throttled(ip: str | None) -> bool:
    if not ip:
        return False
    now = time.monotonic()
    fails = [t for t in _login_fails.get(ip, []) if now - t < _LOGIN_WINDOW_S]
    _login_fails[ip] = fails
    return len(fails) >= _LOGIN_MAX_FAILS


def _record_login_fail(ip: str | None) -> None:
    if not ip:
        return
    _login_fails.setdefault(ip, []).append(time.monotonic())


# --- routes -----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"queue": []})


@app.get("/queue", response_class=HTMLResponse)
async def queue_fragment(request: Request) -> HTMLResponse:
    q = get_queue()
    jobs = q.snapshot()
    return templates.TemplateResponse(request, "_queue.html", {"jobs": jobs})


def _client_ip(request: Request) -> str | None:
    """Real client IP, accounting for upstream proxies (Caddy/nginx)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        # X-Forwarded-For: client, proxy1, proxy2 — first is the real client.
        return fwd.split(",")[0].strip() or None
    return request.client.host if request.client else None


@app.post("/download", response_class=HTMLResponse)
async def post_download(
    request: Request,
    urls: str = Form(""),
    force: str = Form(""),
    allow_playlist: str = Form(""),
) -> HTMLResponse:
    q = get_queue()
    force_flag = bool(force)
    allow_playlist_flag = bool(allow_playlist)

    raw = extract_urls(urls)
    youtube_urls = filter_youtube(raw)

    if not youtube_urls:
        return templates.TemplateResponse(
            request,
            "_form_result.html",
            {"jobs": [], "errors": ["Не нашёл ни одной валидной YouTube-ссылки"]},
            status_code=400,
        )

    submitted: list[dict] = []
    skipped: list[dict] = []
    playlists: list[dict] = []
    errors: list[str] = []

    for url in youtube_urls:
        # Explicit /playlist?list= URL — needs confirm flow.
        if is_playlist_only_url(url) and not allow_playlist_flag:
            try:
                from yt2mp3.downloader import probe_info

                info = probe_info(url, yes_playlist=True)
                entries = info.get("entries") or []
                playlists.append({
                    "url": url,
                    "title": info.get("title"),
                    "count": len(entries),
                    "preview": [
                        {"id": e.get("id"), "title": e.get("title")}
                        for e in entries[:5]
                    ],
                })
            except Exception as e:
                log.exception("playlist probe failed")
                errors.append(f"Не смог прочитать плейлист: {e}")
            continue

        video_id = normalize_url(url)
        if not video_id:
            errors.append(f"Не разобрал video_id из {url}")
            continue

        decision = dedup_check(config.DB_PATH, video_id, force=force_flag)
        if decision.action == "skip":
            skipped.append({
                "url": url,
                "video_id": video_id,
                "existing_id": decision.existing_id,
            })
            continue

        try:
            job_id = q.submit(
                url,
                force=force_flag,
                yes_playlist=allow_playlist_flag,
                client_ip=_client_ip(request),
            )
        except QueueFull:
            return templates.TemplateResponse(
                request,
                "_form_result.html",
                {"errors": ["Очередь переполнена, подожди немного"], "jobs": []},
                status_code=429,
            )
        submitted.append({"job_id": job_id, "url": url, "video_id": video_id})

    return templates.TemplateResponse(
        request,
        "_form_result.html",
        {
            "submitted": submitted,
            "skipped": skipped,
            "playlists": playlists,
            "errors": errors,
            "jobs": get_queue().snapshot(),
        },
    )


@app.post("/cancel/{job_id}", response_class=HTMLResponse)
async def post_cancel(request: Request, job_id: str) -> HTMLResponse:
    q = get_queue()
    q.cancel(job_id)
    return await queue_fragment(request)


@app.get("/library", response_class=HTMLResponse)
async def library_page(request: Request) -> HTMLResponse:
    with db.connect(config.DB_PATH) as conn:
        rows = [dict(r) for r in db.get_library_rows(conn)]
    groups = group_by_day(rows)
    return templates.TemplateResponse(
        request,
        "library.html",
        {"groups": groups, "has_data": bool(rows)},
    )


@app.get("/library/fragment", response_class=HTMLResponse)
async def library_recent_fragment(request: Request) -> HTMLResponse:
    """Mini-panel on `/` — last 5 successful downloads."""
    with db.connect(config.DB_PATH) as conn:
        rows = [dict(r) for r in db.get_recent_successful(conn, limit=5)]
    return templates.TemplateResponse(request, "_library_recent.html", {"rows": rows})


@app.post("/file/{row_id}/delete", response_class=HTMLResponse)
async def delete_file(request: Request, row_id: int) -> HTMLResponse:
    """Hard-delete the mp3 from disk, soft-delete the DB row.

    Admin-only (even in open mode). Returns the refreshed `/library` page so
    HTMX can swap the content.
    """
    if ADMIN_ENABLED and not _is_admin(request):
        raise HTTPException(status_code=403, detail="forbidden")
    with db.connect(config.DB_PATH) as conn:
        row = db.get_by_id(conn, row_id)
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        file_path = row["file_path"]
        if file_path:
            p = Path(file_path).resolve()
            try:
                p.relative_to(config.DOWNLOAD_DIR)
            except ValueError:
                raise HTTPException(status_code=403, detail="forbidden") from None
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    log.exception("unlink failed for %s", p)
        db.soft_delete(conn, row_id)
    log.info("deleted row_id=%s", row_id)
    # Re-render the library so HTMX swap shows the row gone.
    return await library_page(request)


@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request) -> HTMLResponse:
    with db.connect(config.DB_PATH) as conn:
        kpi = db.kpi_totals(conn)
        recent = [dict(r) for r in db.get_recent(conn, limit=20)]
    return templates.TemplateResponse(
        request,
        "stats.html",
        {"kpi": kpi, "recent": recent, "has_data": kpi["total"] > 0},
    )


@app.get("/api/stats")
async def api_stats(request: Request) -> JSONResponse:
    with db.connect(config.DB_PATH) as conn:
        payload = {
            "kpi": db.kpi_totals(conn),
            "by_day": db.downloads_by_day(conn, days=30),
            "top_channels": db.top_channels(conn, limit=10),
            "speeds": db.speed_samples(conn, last_n=500),
            "durations": db.duration_samples(conn, last_n=500),
        }
        # IP breakdown is sensitive — admin-only (or fully open when no admin set).
        if not ADMIN_ENABLED or _is_admin(request):
            payload["by_ip"] = db.ip_breakdown(conn, days=30)
    return JSONResponse(payload)


@app.get("/file/{row_id}")
async def get_file(row_id: int) -> Response:
    with db.connect(config.DB_PATH) as conn:
        row = db.get_by_id(conn, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    file_path = row["file_path"]
    if not file_path:
        raise HTTPException(status_code=410, detail="file path missing")
    p = Path(file_path).resolve()
    # Security: only serve files inside the configured download dir.
    try:
        p.relative_to(config.DOWNLOAD_DIR)
    except ValueError:
        raise HTTPException(status_code=403, detail="forbidden") from None
    if not p.exists():
        raise HTTPException(status_code=410, detail="file no longer exists")
    return FileResponse(p, media_type="audio/mpeg", filename=p.name)


@app.get("/login", response_class=HTMLResponse)
async def get_login(request: Request, next: str = "/") -> Response:
    if not ADMIN_ENABLED:
        return RedirectResponse(url="/", status_code=303)
    if request.session.get("user") == config.AUTH_USER:
        return RedirectResponse(url=_safe_next(next), status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"next": _safe_next(next), "error": None}
    )


@app.post("/login", response_class=HTMLResponse)
async def post_login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
) -> Response:
    if not ADMIN_ENABLED:
        return RedirectResponse(url="/", status_code=303)
    ip = _client_ip(request)
    if _login_throttled(ip):
        log.warning("login throttled ip=%s", ip)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": _safe_next(next), "error": "Слишком много попыток. Подожди немного."},
            status_code=429,
        )
    ok_user = secrets.compare_digest(username, config.AUTH_USER)
    ok_pass = secrets.compare_digest(password, config.AUTH_PASS)
    if not (ok_user and ok_pass):
        _record_login_fail(ip)
        log.warning("failed login attempt user=%s ip=%s", username[:32], ip)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": _safe_next(next), "error": "Неверный логин или пароль"},
            status_code=401,
        )
    request.session["user"] = config.AUTH_USER
    return RedirectResponse(url=_safe_next(next), status_code=303)


@app.post("/logout")
async def post_logout(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# --- admin panel ------------------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request) -> Response:
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "admin_enabled": ADMIN_ENABLED,
            "login_required": login_required_enabled(),
            "admin_user": config.AUTH_USER,
            "secure_cookies": config.SECURE_COOKIES,
        },
    )


@app.post("/admin/toggle-login")
async def admin_toggle_login(request: Request, enabled: str = Form("")) -> Response:
    """Flip the site-wide login requirement. Admin-only (enforced by middleware)."""
    new_value = bool(enabled)
    with db.connect(config.DB_PATH) as conn:
        db.set_login_required(conn, new_value)
    refresh_login_required()
    log.info("login_required set to %s by admin", new_value)
    return RedirectResponse(url="/admin", status_code=303)


def _safe_next(next_url: str) -> str:
    """Only allow simple relative paths — prevent open-redirect.

    Rejects absolute URLs, scheme-relative (``//host``) and backslash tricks
    (``/\\host`` — browsers may treat ``\\`` as ``/``).
    """
    if not next_url or not next_url.startswith("/"):
        return "/"
    # Reject anything that could become protocol/host-relative.
    if next_url.startswith("//") or next_url.startswith("/\\") or "\\" in next_url:
        return "/"
    return next_url


@app.get("/healthz")
async def healthz() -> dict:
    return {
        "ok": True,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "downloads": str(config.DOWNLOAD_DIR),
        "now": datetime.now(UTC).isoformat(timespec="seconds"),
    }
