FROM python:3.12-slim

# ffmpeg + ffprobe (required by yt-dlp postprocessor)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# uv — fast Python package manager
RUN pip install --no-cache-dir uv==0.11.16

WORKDIR /app

# Install deps first (better caching)
COPY pyproject.toml ./
COPY README.md ./
COPY yt2mp3/ ./yt2mp3/
RUN uv sync --no-dev

# Persistent data lives outside the image; mount these from host.
ENV YT2MP3_DOWNLOAD_DIR=/data/downloads \
    YT2MP3_DB_PATH=/data/yt2mp3.db \
    YT2MP3_LOG_PATH=/data/yt2mp3.log \
    YT2MP3_HOST=0.0.0.0 \
    YT2MP3_PORT=8000

VOLUME ["/data"]
EXPOSE 8000

# Healthcheck — uses the open /healthz route
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3); sys.exit(0 if r.status==200 else 1)" || exit 1

CMD ["uv", "run", "python", "-m", "yt2mp3"]
