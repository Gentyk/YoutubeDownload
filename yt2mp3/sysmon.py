"""Lightweight CPU/RAM sampler — no external deps, reads /proc on Linux.

Samples every N seconds in a background thread; keeps the latest reading plus a
short rolling history for the admin dashboard. Off-Linux (no /proc) it degrades
gracefully to None values.
"""

from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)


def _read_cpu() -> tuple[float, float] | None:
    """Return (total_jiffies, idle_jiffies) from /proc/stat, or None."""
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        parts = [float(x) for x in line.split()[1:]]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0.0)  # idle + iowait
        return sum(parts), idle
    except Exception:
        return None


def _read_mem() -> tuple[float, float, float] | None:
    """Return (used_pct, total_mb, used_mb), or None."""
    try:
        info: dict[str, float] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                info[k] = float(v.strip().split()[0])  # kB
        total = info["MemTotal"]
        avail = info.get("MemAvailable", info.get("MemFree", 0.0))
        used = total - avail
        return used / total * 100.0, total / 1024, used / 1024
    except Exception:
        return None


class SysMonitor:
    """Background CPU/RAM sampler. Thread-safe latest()/history()."""

    def __init__(self, interval: int = 15, history: int = 40) -> None:
        self.interval = interval
        self._max = history
        self._hist: list[dict] = []
        self._latest: dict = {}
        self._prev_cpu: tuple[float, float] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        cpu_pct: float | None = None
        c = _read_cpu()
        if c and self._prev_cpu:
            dt = c[0] - self._prev_cpu[0]
            di = c[1] - self._prev_cpu[1]
            if dt > 0:
                cpu_pct = max(0.0, min(100.0, (1 - di / dt) * 100))
        if c:
            self._prev_cpu = c
        m = _read_mem()
        sample = {
            "cpu_pct": round(cpu_pct, 1) if cpu_pct is not None else None,
            "ram_pct": round(m[0], 1) if m else None,
            "ram_total_mb": round(m[1]) if m else None,
            "ram_used_mb": round(m[2]) if m else None,
        }
        with self._lock:
            self._latest = sample
            self._hist.append(sample)
            if len(self._hist) > self._max:
                self._hist.pop(0)

    def _loop(self) -> None:
        self._prev_cpu = _read_cpu()  # prime so the first delta is meaningful
        while not self._stop.is_set():
            self._stop.wait(self.interval)
            if self._stop.is_set():
                break
            self._sample()

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._loop, name="yt2mp3-sysmon", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def latest(self) -> dict:
        with self._lock:
            return dict(self._latest)

    def history(self) -> list[dict]:
        with self._lock:
            return list(self._hist)
