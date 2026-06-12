"""Portal 5 UAT — backend health, memory pressure, OOM/zombie detection.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase B). _backend_alive and _wait_for_backend_alive are co-located here so
unit-test monkeypatching of tests.uat.health._backend_alive takes effect.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from tests.memory_guard import (
    memory_pct as _get_memory_pct,
)
from tests.memory_guard import (
    wait_for_drain as _wait_for_drain_impl,
)
from tests.uat.config import (
    BACKEND_SETTLE_WAIT_S,
    MEMORY_ABORT_PCT,
    MEMORY_CRITICAL_PCT,
    MEMORY_WARN_PCT,
    OLLAMA_URL,
)
from tests.uat.lifecycle import unload_all_models

# Backend health + zombie detection
# ---------------------------------------------------------------------------


def _wait_for_drain(
    threshold_pct: float = MEMORY_CRITICAL_PCT,
    timeout_s: float = 30.0,
    poll_s: float = 2.0,
    label: str = "",
    retries: int = 2,
) -> bool:
    """Wait for Metal GPU buffers to drain. See tests/memory_guard.py for full docs."""
    return _wait_for_drain_impl(
        threshold_pct=threshold_pct,
        timeout_s=timeout_s,
        poll_s=poll_s,
        retries=retries,
        label=label,
        ollama_url=OLLAMA_URL,
    )


def _check_memory_before_test(test_name: str = "") -> bool:
    """Check memory pressure before running a test. Returns True if safe to proceed.

    If critical: force-evicts all models and returns False (caller should skip/retry).
    If abort: raises SystemExit to prevent OOM crash.
    """
    used = _get_memory_pct()

    if used >= MEMORY_ABORT_PCT:
        print(
            f"\n  [OOM RISK] Memory at {used:.0f}% — aborting to prevent crash. Test: {test_name}",
            flush=True,
        )
        unload_all_models()
        # Wait for actual Metal reclaim — event-driven, not a blind sleep.
        _wait_for_drain(threshold_pct=MEMORY_WARN_PCT, timeout_s=30.0, label="oom-risk")
        used_after = _get_memory_pct()
        print(f"  [OOM RISK] After eviction: {used_after:.0f}%", flush=True)
        if used_after >= MEMORY_ABORT_PCT:
            raise SystemExit(
                f"ABORT: Memory still at {used_after:.0f}% after full eviction. "
                "Manual intervention required — check for leaked processes."
            )
        return False

    if used >= MEMORY_CRITICAL_PCT:
        print(
            f"\n  [MEMORY] Critical: {used:.0f}% — evicting before {test_name}",
            flush=True,
        )
        unload_all_models()
        if not _wait_for_drain(threshold_pct=MEMORY_WARN_PCT, timeout_s=90.0, label=test_name):
            print(f"  [MEMORY] Still above {MEMORY_WARN_PCT:.0f}% after 90s drain — skipping {test_name}", flush=True)
            return False
        return True

    if used >= MEMORY_WARN_PCT:
        print(f"  [MEMORY] Warning: {used:.0f}% used", flush=True)

    return True


def _check_for_oom_crash() -> str | None:
    """Check if any backend crashed due to OOM since last check.

    Detects:
    1. Ollama unreachable
    2. System memory above abort threshold

    Returns crash description or None if healthy.
    """
    # Ollama dead?
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=3)
        if r.status_code != 200:
            return f"Ollama returned {r.status_code}"
    except Exception:
        return "Ollama unreachable (process may have crashed)"

    # System memory critical?
    used = _get_memory_pct()
    if used >= MEMORY_ABORT_PCT:
        return f"System memory at {used:.0f}% — OOM imminent"

    return None


def _backend_alive(tier: str) -> tuple[bool, str]:
    """Return (alive, detail) for the given workspace tier."""
    if tier in ("ollama",):
        try:
            r = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=5)
            return r.status_code == 200, f"ollama={r.status_code}"
        except Exception:
            return False, "ollama_unreachable"
    if tier == "media_heavy":
        try:
            r = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=5)
            ollama_ok = r.status_code == 200
        except Exception:
            ollama_ok = False
        return ollama_ok, f"ollama={'ok' if ollama_ok else 'down'}"
    return True, "tier=any"
async def _wait_for_backend(tier: str, max_wait: int = 120) -> bool:
    """Poll backend until ready or max_wait seconds elapsed.

    Returns True if the backend became ready, False if it stayed down.
    Emits progress lines every 20s so the operator can see what's happening.
    """
    if tier not in ("ollama", "media_heavy"):
        return True
    t0 = time.time()
    last_log = 0.0
    while True:
        alive, detail = _backend_alive(tier)
        if alive:
            return True
        elapsed = time.time() - t0
        if elapsed >= max_wait:
            print(
                f"  [health] backend still not ready after {max_wait:.0f}s ({detail})", flush=True
            )
            return False
        if time.time() - last_log >= 20:
            print(
                f"  [health] waiting for backend ({detail}, {elapsed:.0f}s/{max_wait}s)…",
                flush=True,
            )
            last_log = time.time()
        await asyncio.sleep(10)
async def _wait_for_backend_alive(tier: str, max_wait: float = BACKEND_SETTLE_WAIT_S) -> bool:
    """Poll _backend_alive until the backend reports healthy or max_wait elapses.

    Replaces blind asyncio.sleep(15) waits after retry-related actions
    (zombie cleanup, manual settle). Returns True if backend recovered,
    False on timeout. Polls at 0.5s for the first 5s, then 1s.
    """
    if tier not in ("ollama",):
        await asyncio.sleep(min(2.0, max_wait))
        return True
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            alive, _ = _backend_alive(tier)
            if alive:
                return True
        except Exception:
            pass
        elapsed = max_wait - (deadline - time.monotonic())
        delay = 0.5 if elapsed < 5.0 else 1.0
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(delay, remaining))
    return False
