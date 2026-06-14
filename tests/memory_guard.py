"""Shared Metal GPU memory guard for Portal 5 test harnesses.

Used by:  tests/uat/ (health, lifecycle, monitor — entry: tests/portal5_uat_driver.py)
          tests/benchmarks/bench_tps.py
          tests/portal5_acceptance_v6.py

macOS Metal GPU buffers are released asynchronously after Ollama evicts a
model — /api/ps becoming empty does not mean GPU memory is reclaimed.
Metal typically holds buffers for 30-60s, and can get stuck indefinitely
when a process crashes without releasing its Metal context (same failure
mode seen with MLX server crashes).

All functions here poll vm_stat rather than sleeping a fixed duration.
Polling exits immediately when the condition is met; it falls back to
escalating recovery actions when the drain stalls:

  Stage 1 (default 30s): poll vm_stat, exit on clear
  Stage 2 (timeout):     run `purge` — macOS memory compaction, no kills
  Stage 3 (timeout):     restart Ollama — releases all Metal contexts
  All retries exhausted: return failure — caller blocks/skips, does not
                         proceed into a known-bad memory state

Public API
----------
memory_pct() -> float
    Current used% from vm_stat (active + wired pages).

free_ram_gb() -> float
    Approximate free + inactive unified memory in GB.

purge_memory() -> None
    Run macOS `purge` to unblock stalled Metal buffers.

restart_ollama(ollama_url) -> bool
    Restart Ollama server; returns True when healthy again.

wait_for_drain(threshold_pct, timeout_s, poll_s, retries, label, ollama_url) -> bool
    Sync drain wait with retry+recovery. Use in UAT driver and bench_tps.

wait_for_drain_async(threshold_pct, timeout_s, poll_s, retries, ollama_url) -> float
    Async drain wait with retry+recovery. Use in acceptance v6 (asyncio context).
    Returns final free_ram_gb() reading.

wait_for_model_loaded(timeout_s, poll_s, ollama_url) -> bool  [async]
    Poll /api/ps until Ollama has at least one model loaded. Event-driven cold-
    load wait — call after a 408 timeout instead of sleeping a fixed duration.
    Returns True when a model appears, False on timeout.
"""

from __future__ import annotations

import subprocess
import time

import httpx

# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_THRESHOLD_PCT = 75.0   # above this → Metal still draining
DEFAULT_TIMEOUT_S = 30.0       # per-attempt poll window
DEFAULT_POLL_S = 2.0           # sync poll interval
DEFAULT_RETRIES = 2            # purge (1) → restart (2) → give up


# ── vm_stat readers ───────────────────────────────────────────────────────────

def memory_pct() -> float:
    """Return current memory used % (active + wired / total) from vm_stat.

    Wired pages are the key indicator for Metal GPU buffers — they remain
    elevated after Ollama eviction until Metal releases its contexts.
    Returns 0.0 on any parse failure (safe default — callers treat low as OK).
    """
    try:
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
        page_size = 16384  # Apple Silicon default; overridden if found in output
        free = active = inactive = speculative = wired = 0
        for line in result.stdout.splitlines():
            if "page size of" in line:
                try:
                    page_size = int(line.split()[-2])
                except (ValueError, IndexError):
                    pass
            elif "Pages free:" in line:
                free = int(line.split(":")[1].strip().rstrip("."))
            elif "Pages active:" in line:
                active = int(line.split(":")[1].strip().rstrip("."))
            elif "Pages inactive:" in line:
                inactive = int(line.split(":")[1].strip().rstrip("."))
            elif "Pages speculative:" in line:
                speculative = int(line.split(":")[1].strip().rstrip("."))
            elif "Pages wired down:" in line:
                wired = int(line.split(":")[1].strip().rstrip("."))
        _ = page_size  # used for free_ram_gb; kept here for consistency
        total = free + active + inactive + speculative + wired
        if total > 0:
            return round((active + wired) / total * 100, 1)
    except Exception:
        pass
    return 0.0


def free_ram_gb() -> float:
    """Return approximate free + inactive unified memory in GB from vm_stat.

    Uses free + inactive pages (memory available for immediate use or
    quickly reclaimable) rather than just free, matching macOS Activity
    Monitor's "memory available" reading.
    Returns 0.0 on parse failure.
    """
    try:
        out = subprocess.check_output(["vm_stat"], text=True, timeout=5)
        pages_free = pages_inactive = page_size = 0
        for line in out.splitlines():
            if "page size of" in line:
                try:
                    page_size = int(line.split()[-2])
                except (ValueError, IndexError):
                    pass
            elif "Pages free:" in line:
                pages_free = int(line.split()[-1].rstrip("."))
            elif "Pages inactive:" in line:
                pages_inactive = int(line.split()[-1].rstrip("."))
        if page_size == 0:
            page_size = 16384
        return round((pages_free + pages_inactive) * page_size / (1024 ** 3), 1)
    except Exception:
        return 0.0


# ── Active recovery actions ───────────────────────────────────────────────────

def purge_memory() -> None:
    """Run macOS `purge` to force inactive-page compaction.

    `purge` pressures the VM subsystem into reclaiming inactive pages, which
    often unblocks Metal GPU buffers that have stopped draining on their own.
    It does not kill any process and is safe to call between model loads.
    """
    try:
        subprocess.run(["purge"], timeout=15, check=False, capture_output=True)
        print("  [metal] purge completed", flush=True)
    except Exception as e:
        print(f"  [metal] purge failed (non-fatal): {e}", flush=True)


def restart_ollama(ollama_url: str = DEFAULT_OLLAMA_URL) -> bool:
    """Restart the Ollama server to release all stuck Metal GPU contexts.

    Nuclear recovery: kills and restarts Ollama. Used only when `purge`
    fails to unblock Metal buffers. Waits up to 30s for Ollama to return
    healthy before returning.

    Returns True if Ollama is healthy after restart, False on timeout.
    """
    print("  [metal] Restarting Ollama to clear stuck Metal contexts ...", flush=True)
    try:
        subprocess.run(["brew", "services", "restart", "ollama"],
                       timeout=30, check=False, capture_output=True)
    except Exception:
        try:
            subprocess.run(["pkill", "-f", "ollama serve"],
                           timeout=5, check=False, capture_output=True)
            time.sleep(3)
            subprocess.Popen(["ollama", "serve"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"  [metal] Ollama restart failed: {e}", flush=True)
            return False
    deadline = time.time() + 30.0
    while time.time() < deadline:
        try:
            r = httpx.get(f"{ollama_url}/api/tags", timeout=3)
            if r.status_code == 200:
                print("  [metal] Ollama back healthy after restart", flush=True)
                return True
        except Exception:
            pass
        time.sleep(2.0)
    print("  [metal] Ollama did not recover within 30s", flush=True)
    return False


# ── Sync drain (UAT driver, bench_tps) ───────────────────────────────────────

def wait_for_drain(
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_s: float = DEFAULT_POLL_S,
    retries: int = DEFAULT_RETRIES,
    label: str = "",
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> bool:
    """Wait for Metal GPU buffers to drain below threshold_pct.

    Polling exits immediately when the condition is met. On timeout, takes
    escalating recovery actions before retrying:
      Attempt 1 timeout → purge_memory()
      Attempt 2 timeout → restart_ollama()
      All retries exhausted → return False

    Callers that receive False should BLOCK or skip the next operation rather
    than proceeding — continuing into high-memory state produces routing
    fallback and confusing false failures that mask the real cause.

    Args:
        threshold_pct: Target used% ceiling (default 75%).
        timeout_s:     Polling window per attempt in seconds (default 30s).
        poll_s:        vm_stat check interval in seconds (default 2s).
        retries:       Recovery attempts before giving up (default 2).
        label:         Short string appended to log prefix for context.
        ollama_url:    Ollama base URL for health checks after restart.

    Returns:
        True if memory cleared within retries, False if exhausted.
    """
    prefix = f"  [drain{' ' + label if label else ''}]"
    for attempt in range(retries + 1):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            used = memory_pct()
            if used < threshold_pct:
                print(f"{prefix} Clear at {used:.0f}% — safe to proceed", flush=True)
                return True
            remaining = int(deadline - time.time())
            print(
                f"{prefix} {used:.0f}%"
                f" (attempt {attempt + 1}/{retries + 1}, {remaining}s left)",
                flush=True,
            )
            time.sleep(poll_s)
        # Timeout — escalate before next attempt
        if attempt == 0:
            print(f"{prefix} Timeout — running purge to unblock Metal", flush=True)
            purge_memory()
        elif attempt == 1:
            print(f"{prefix} Timeout — restarting Ollama to clear Metal contexts", flush=True)
            restart_ollama(ollama_url)
    used = memory_pct()
    print(f"{prefix} DRAIN FAILED — {used:.0f}% after all retries", flush=True)
    return False


# ── Async drain (acceptance v6) ───────────────────────────────────────────────

async def wait_for_drain_async(
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_s: float = 3.0,
    retries: int = DEFAULT_RETRIES,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> float:
    """Async variant of wait_for_drain for use in asyncio contexts.

    Polls free_ram_gb() until it stabilises (stops increasing for two
    consecutive checks), applying the same purge → restart escalation on
    timeout.

    Uses free_ram_gb() (free + inactive) rather than memory_pct() (active +
    wired) because the acceptance runner expresses headroom in GB rather than
    used%. The two metrics are complementary — both reflect Metal drain state.

    Args:
        threshold_pct: Unused (kept for API symmetry); stability detection
                       replaces threshold-based exit for the async variant.
        timeout_s:     Polling window per attempt in seconds (default 30s).
        poll_s:        vm_stat check interval in seconds (default 3s).
        retries:       Recovery attempts before giving up (default 2).
        ollama_url:    Ollama base URL for health checks after restart.

    Returns:
        Final free_ram_gb() reading after drain (or timeout).
    """
    import asyncio

    for attempt in range(retries + 1):
        deadline = time.time() + timeout_s
        prev = free_ram_gb()
        stable_count = 0
        while time.time() < deadline:
            await asyncio.sleep(poll_s)
            cur = free_ram_gb()
            if cur > prev + 0.5:
                stable_count = 0        # still rising — Metal still draining
            else:
                stable_count += 1
                if stable_count >= 2:   # stable for two polls — drain complete
                    print(f"  [metal] Stable at {cur:.1f} GB free — drain complete",
                          flush=True)
                    return cur
            prev = cur
        # Timeout — escalate before next attempt
        if attempt == 0:
            print("  [metal] Timeout at attempt 1 — running purge", flush=True)
            purge_memory()
        elif attempt == 1:
            print("  [metal] Timeout at attempt 2 — restarting Ollama", flush=True)
            # Async restart: brew services restart is sync; wrap in thread
            import asyncio as _asyncio
            loop = _asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: restart_ollama(ollama_url))
    result = free_ram_gb()
    print(f"  [metal] DRAIN WARNING — {result:.1f} GB free after all retries", flush=True)
    return result


async def wait_for_model_loaded(
    timeout_s: float = 300.0,
    poll_s: float = 5.0,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> bool:
    """Poll /api/ps until Ollama has at least one model loaded.

    Event-driven cold-load wait. Call this after receiving a 408 timeout from
    the pipeline instead of sleeping a fixed duration. Ollama loads models
    asynchronously; the first request that triggers a cold load will time out
    while the model is loading. Polling /api/ps lets the harness react the
    moment the model becomes available rather than guessing a sleep interval.

    Args:
        timeout_s: Maximum seconds to wait (default 300s).
        poll_s:    Polling interval in seconds (default 5s).
        ollama_url: Ollama base URL.

    Returns:
        True when at least one model is loaded, False on timeout.
    """
    import asyncio as _asyncio

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(f"{ollama_url}/api/ps", timeout=5)
            if r.status_code == 200 and r.json().get("models"):
                return True
        except Exception:
            pass
        remaining = int(deadline - time.time())
        print(f"  [model-load] waiting for Ollama cold load ({remaining}s remaining)", flush=True)
        await _asyncio.sleep(poll_s)
    print("  [model-load] timeout — no model appeared in /api/ps", flush=True)
    return False
