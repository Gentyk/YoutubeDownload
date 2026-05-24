"""FastAPI routes. No business logic — delegates to queue/downloader/db/helpers."""

from __future__ import annotations

import logging
import secrets
import shutil
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
    if AUTH_ENABLED:
        log.info("Login ENABLED (user=%s)", config.AUTH_USER)
        if not config.SECRET_KEY:
            log.warning(
                "YT2MP3_SECRET_KEY not set — sessions invalidate on restart. "
                "Set a long random string for persistent logins."
            )
    else:
        log.warning("Login DISABLED — bind to 127.0.0.1 or use VPN, do NOT expose publicly.")
    try:
        yield
    finally:
        log.info("shutting down queue")
        if _queue is not None:
            _queue.shutdown(wait=True, cancel_pending=True)
        _queue = None


app = FastAPI(title="yt2mp3", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Session-based login (optional) -----------------------------------------

AUTH_ENABLED = bool(config.AUTH_USER and config.AUTH_PASS)
templates.env.globals["AUTH_ENABLED"] = AUTH_ENABLED
_OPEN_PATHS = frozenset({"/login", "/logout", "/healthz"})
_OPEN_PREFIXES = ("/static/",)


class LoginRequiredMiddleware:
    """Redirect unauthenticated requests to ``/login``.

    Activated only when both ``YT2MP3_AUTH_USER`` and ``YT2MP3_AUTH_PASS`` are set.
    Reads the signed session cookie (populated by ``SessionMiddleware``) and
    checks for ``user == AUTH_USER``. /healthz and /login stay open.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not AUTH_ENABLED:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in _OPEN_PATHS or any(path.startswith(p) for p in _OPEN_PREFIXES):
            await self.app(scope, receive, send)
            return
        session = scope.get("session") or {}
        if session.get("user") == config.AUTH_USER:
            await self.app(scope, receive, send)
            return
        # Not logged in → redirect to /login (preserves the desired path)
        next_url = path
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


if AUTH_ENABLED:
    # ORDER MATTERS — middlewares are applied bottom-up at call time.
    # We want the request flow: Session populates scope["session"] → LoginRequired checks it.
    # add_middleware wraps in LIFO order, so add LoginRequired FIRST, Session LAST,
    # so that Session is outermost (runs first).
    app.add_middleware(LoginRequiredMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.SECRET_KEY or secrets.token_urlsafe(32),
        max_age=config.SESSION_MAX_AGE,
        same_site="lax",
        https_only=False,  # set True if you put HTTPS in front (Caddy/nginx)
    )


# --- routes -----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"queue": []})


@app.get("/queue", response_class=HTMLResponse)
async def queue_fragment(request: Request) -> HTMLResponse:
    q = get_queue()
    jobs = q.snapshot()
    return templates.TemplateResponse(request, "_queue.html", {"jobs": jobs})


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
            job_id = q.submit(url, force=force_flag, yes_playlist=allow_playlist_flag)
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
async def api_stats() -> JSONResponse:
    with db.connect(config.DB_PATH) as conn:
        payload = {
            "kpi": db.kpi_totals(conn),
            "by_day": db.downloads_by_day(conn, days=30),
            "top_channels": db.top_channels(conn, limit=10),
            "speeds": db.speed_samples(conn, last_n=500),
            "durations": db.duration_samples(conn, last_n=500),
        }
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
    if not AUTH_ENABLED:
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
    if not AUTH_ENABLED:
        return RedirectResponse(url="/", status_code=303)
    ok_user = secrets.compare_digest(username, config.AUTH_USER)
    ok_pass = secrets.compare_digest(password, config.AUTH_PASS)
    if not (ok_user and ok_pass):
        log.warning("failed login attempt user=%s", username[:32])
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


def _safe_next(next_url: str) -> str:
    """Only allow relative paths — prevent open-redirect."""
    if not next_url or not next_url.startswith("/") or next_url.startswith("//"):
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
