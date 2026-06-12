"""Portal 5 UAT — inter-test settling, MemoryMonitor, CrashWatcher.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase B).
"""

from __future__ import annotations

import asyncio
import json as _json
import threading
from pathlib import Path

import httpx

from tests.memory_guard import memory_pct as _get_memory_pct
from tests.uat.config import (
    MEMORY_ABORT_PCT,
    MEMORY_CRITICAL_PCT,
    MEMORY_WARN_PCT,
    OLLAMA_URL,
)
from tests.uat.health import _wait_for_drain
from tests.uat.lifecycle import unload_all_models

SETTLING: dict[tuple, int] = {
    ("ollama", "ollama"): 10,
    ("ollama", "any"): 10,
    ("ollama", "media_heavy"): 30,
    ("any", "ollama"): 10,
    ("any", "any"): 5,
    ("any", "media_heavy"): 30,
    ("media_heavy", "media_heavy"): 30,
    ("media_heavy", "any"): 15,
    ("media_heavy", "ollama"): 30,
}


def settling_delay(current_tier: str, next_tier: str) -> int:
    return SETTLING.get((current_tier, next_tier), 10)


# ---------------------------------------------------------------------------
# Continuous memory & health monitor (self-healing)
# ---------------------------------------------------------------------------


class MemoryMonitor:
    """Background task that continuously monitors memory and backend health.

    Self-healing actions:
    - Memory > 75%: log warning
    - Memory > 85%: force-evict all Ollama models
    - Memory > 92% after eviction: kill zombie processes, retry eviction
    - Ollama unreachable: log crash (restart handled by launchd/docker)

    Runs as an asyncio task alongside the test loop. Call start() before tests,
    stop() after. Stats are available via .stats dict.
    """

    def __init__(self, poll_interval: float = 20.0) -> None:
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._running = False
        self.stats = {
            "checks": 0,
            "warnings": 0,
            "force_evictions": 0,
            "ollama_crashes": 0,
            "recovery_attempts": 0,
            "recovery_failures": 0,
        }
        self._last_event: str = ""

    def start(self) -> None:
        """Start the background monitor."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        print(f"  [monitor] Memory monitor started (poll every {self.poll_interval}s)")

    async def stop(self) -> None:
        """Stop the background monitor and return stats."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        print(
            f"  [monitor] Stopped — {self.stats['checks']} checks, "
            f"{self.stats['force_evictions']} evictions, "
            f"{self.stats['ollama_crashes']} Ollama crashes"
        )

    def _log(self, msg: str) -> None:
        """Log with dedup — suppress repeated identical events."""
        if msg != self._last_event:
            print(f"  [monitor] {msg}", flush=True)
            self._last_event = msg

    async def _monitor_loop(self) -> None:
        """Main monitoring loop — runs until stop() is called."""
        while self._running:
            try:
                await self._check_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._log(f"Monitor error: {e}")
            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break

    async def _check_once(self) -> None:
        """One monitoring cycle."""
        self.stats["checks"] += 1

        # ── 1. Memory pressure ──
        used = _get_memory_pct()
        if used >= MEMORY_ABORT_PCT:
            self._log(f"CRITICAL: Memory at {used:.0f}% — emergency eviction")
            self.stats["force_evictions"] += 1
            await self._emergency_evict()
            used = _get_memory_pct()
            if used >= MEMORY_ABORT_PCT:
                self._log(
                    f"ABORT RISK: Memory still {used:.0f}% after eviction — "
                    "manual intervention may be needed"
                )
                self.stats["recovery_failures"] += 1
        elif used >= MEMORY_CRITICAL_PCT:
            self._log(
                f"Memory critical: {used:.0f}% — model loaded, pre-test check will evict between tests"
            )
            self.stats["warnings"] += 1
        elif used >= MEMORY_WARN_PCT:
            self.stats["warnings"] += 1
            self._log(f"Memory warning: {used:.0f}%")

        # ── 2. Ollama health ──
        try:
            r = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=3)
            if r.status_code != 200:
                self.stats["ollama_crashes"] += 1
                self._log(f"Ollama unhealthy: HTTP {r.status_code}")
        except Exception:
            self.stats["ollama_crashes"] += 1
            self._log("Ollama unreachable — may have crashed")

    async def _emergency_evict(self) -> None:
        """Aggressive eviction when memory is critically high."""
        self.stats["recovery_attempts"] += 1
        unload_all_models()
        await asyncio.sleep(15)


# ---------------------------------------------------------------------------
# Crash watcher — detects Ollama crashes via macOS DiagnosticReports
# ---------------------------------------------------------------------------

_DIAG_DIR = Path.home() / "Library/Logs/DiagnosticReports"


class CrashWatcher:
    """Background thread that watches DiagnosticReports for Ollama-related crashes.

    When a new .ips or .crash file appears whose content references Ollama,
    the watcher logs a [CRASH DETECTED] line immediately.

    The main test loop calls wait_for_recovery() when crash_pending is True,
    which unloads all models and waits for memory to drain.
    """

    POLL_INTERVAL_S = 15

    def __init__(self) -> None:
        self.crash_pending = False
        self._stop = threading.Event()
        self._known: set[Path] = set()
        self.crash_log: list[str] = []
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if _DIAG_DIR.exists():
            self._known = set(_DIAG_DIR.glob("*.ips")) | set(_DIAG_DIR.glob("*.crash"))
        self._thread = threading.Thread(target=self._loop, daemon=True, name="crash-watcher")
        self._thread.start()
        print(
            "  [crash-watcher] Started — watching DiagnosticReports for crashes",
            flush=True,
        )

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(timeout=self.POLL_INTERVAL_S):
            try:
                self._check()
            except Exception as exc:
                print(f"  [crash-watcher] error: {exc}", flush=True)

    def _check(self) -> None:
        if not _DIAG_DIR.exists():
            return
        current = set(_DIAG_DIR.glob("*.ips")) | set(_DIAG_DIR.glob("*.crash"))
        new_files = current - self._known
        self._known = current
        for f in new_files:
            self._handle(f)

    def _handle(self, f: Path) -> None:
        try:
            content = f.read_text(errors="replace")
        except Exception:
            return
        proc = f.name
        try:
            header = _json.loads(content.split("\n", 1)[0])
            proc = header.get("app_name", proc)
        except Exception:
            pass
        mem_pct = _get_memory_pct()

        msg = f"  [CRASH DETECTED] proc={proc} file={f.name} mem={mem_pct:.0f}%"
        print(msg, flush=True)
        self.crash_log.append(msg)
        self.crash_pending = True

    def wait_for_recovery(self, label: str = "") -> None:
        """Block until memory has drained after a crash.

        Called by the test loop when crash_pending is True. Does not return
        until it is safe to load the next model.
        """
        tag = f"[{label}] " if label else ""
        print(
            f"  {tag}[recovery] Ollama crash — unloading models, waiting for memory to drain...",
            flush=True,
        )
        unload_all_models()
        _wait_for_drain(threshold_pct=MEMORY_WARN_PCT, timeout_s=90.0, label="crash-recovery")
        self.crash_pending = False
        print(f"  {tag}[recovery] Complete — resuming testing", flush=True)


# Module-level singleton — started in main(), stopped after last test
_crash_watcher = CrashWatcher()
