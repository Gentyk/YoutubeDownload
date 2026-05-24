# yt2mp3

Personal YouTube → MP3 archive with a colourful stats dashboard.

## Requirements

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) (`pip install --user uv`)
- `ffmpeg` in `PATH` (`brew install ffmpeg`)

## Run

```bash
uv sync
uv run python -m yt2mp3
```

Then open <http://127.0.0.1:8000>.

## Config

| Env var                  | Default            | Description                              |
|--------------------------|--------------------|------------------------------------------|
| `YT2MP3_DOWNLOAD_DIR`    | `./downloads`      | Where mp3 files land                     |
| `YT2MP3_MAX_CONCURRENT`  | `3`                | Concurrent downloads                     |
| `YT2MP3_DB_PATH`         | `./yt2mp3.db`      | SQLite database file                     |
| `YT2MP3_HOST`            | `127.0.0.1`        | Bind address (localhost only by default) |
| `YT2MP3_PORT`            | `8000`             | HTTP port                                |
| `YT2MP3_AUTH_USER`       | *(empty)*          | HTTP Basic Auth user — enable on host    |
| `YT2MP3_AUTH_PASS`       | *(empty)*          | HTTP Basic Auth password                 |

## Деплой на сервер

Полная пошаговая инструкция в [`HOSTING.md`](HOSTING.md). Коротко:
```bash
docker compose up -d --build
```

## Tests

```bash
uv run pytest                # unit + integration (skips online)
uv run pytest -m online      # smoke test against real YouTube
```
