"""Portal 5 — system monitoring primitives (Metal GPU memory, Ollama model state).

Promoted from tests/memory_guard.py so production routing code can react to
system state instead of relying on blind timeouts; tests import via the
tests/memory_guard.py re-export shim.

macOS Metal GPU buffers are released asynchronously after Ollama evicts a model
— /api/ps becoming empty does not mean GPU memory is reclaimed. Poll functions
exit when the condition is met and fall back to escalating recovery: Stage 1
poll vm_stat, Stage 2 run `purge`, Stage 3 restart Ollama (releases all Metal
contexts), then return failure.

Public API: ``memory_pct`` (used% from vm_stat), ``free_ram_gb`` (free+inactive
in GB), ``purge_memory``, ``restart_ollama``, ``wait_for_drain`` (sync; UAT
driver/bench_tps), ``wait_for_drain_async`` (async; acceptance v6),
``wait_for_model_loaded`` (async; pipeline fallback — polls /api/ps).
"""

from __future__ import annotations

import contextlib
import subprocess
import time

import httpx

# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_THRESHOLD_PCT = 75.0  # above this → Metal still draining
DEFAULT_TIMEOUT_S = 30.0  # per-attempt poll window
DEFAULT_POLL_S = 2.0  # sync poll interval
DEFAULT_RETRIES = 2  # purge (1) → restart (2) → give up


# ── vm_stat readers ───────────────────────────────────────────────────────────


def memory_pct() -> float:
    """Return current memory used % (active + wired / total) from vm_stat.

    Wired pages track Metal GPU buffers — they stay elevated after Ollama
    eviction until Metal releases its contexts. Returns 0.0 on parse failure
    (callers treat low as OK).
    """
    try:
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
        page_size = 16384  # Apple Silicon default; overridden if found in output
        free = active = inactive = speculative = wired = 0
        for line in result.stdout.splitlines():
            if "page size of" in line:
                with contextlib.suppress(ValueError, IndexError):
                    page_size = int(line.split()[-2])
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
        pass  # sysctl unavailable (Linux / permission) — caller gets 0.0
    return 0.0


def free_ram_gb() -> float:
    """Return approximate free + inactive unified memory in GB from vm_stat.

    Uses free + inactive (available or quickly reclaimable) rather than just
    free, matching Activity Monitor's "memory available". Returns 0.0 on parse
    failure.
    """
    try:
        out = subprocess.check_output(["vm_stat"], text=True, timeout=5)
        pages_free = pages_inactive = page_size = 0
        for line in out.splitlines():
            if "page size of" in line:
                with contextlib.suppress(ValueError, IndexError):
                    page_size = int(line.split()[-2])
            elif "Pages free:" in line:
                pages_free = int(line.split()[-1].rstrip("."))
            elif "Pages inactive:" in line:
                pages_inactive = int(line.split()[-1].rstrip("."))
        if page_size == 0:
            page_size = 16384
        return round((pages_free + pages_inactive) * page_size / (1024**3), 1)
    except Exception:
        return 0.0


# ── Active recovery actions ───────────────────────────────────────────────────


def purge_memory() -> None:
    """Run macOS `purge` to force inactive-page compaction.

    Often unblocks Metal GPU buffers that stopped draining on their own. Kills
    no process; safe to call between model loads.
    """
    try:
        subprocess.run(["purge"], timeout=15, check=False, capture_output=True)
        print("  [metal] purge completed", flush=True)
    except Exception as e:
        print(f"  [metal] purge failed (non-fatal): {e}", flush=True)


def restart_ollama(ollama_url: str = DEFAULT_OLLAMA_URL) -> bool:
    """Restart the Ollama server to release stuck Metal GPU contexts.

    Nuclear recovery used only when `purge` fails. Waits up to 30s for Ollama
    to return healthy.

    Ollama runs as `com.portal5.ollama`, a system LaunchDaemon (deliberately
    system-domain, not a per-user LaunchAgent, so it's up before any user is
    logged in) — NOT Homebrew's `homebrew.mxcl.ollama` (stale, older version;
    disabled 2026-08-10, see reports/DAILY_WORK_SOAK_*.md). Restarting a
    system LaunchDaemon always requires root, so this shells out via `sudo -n`
    to a single, narrowly-scoped passwordless rule
    (`/etc/sudoers.d/portal5-ollama`: exactly
    `launchctl kickstart -k system/com.portal5.ollama`, nothing else). If that
    rule isn't installed, `sudo -n` fails fast (no password prompt hang) and
    this returns False rather than silently starting the wrong service.

    Returns True if healthy after restart, False on timeout or if the sudo
    rule is missing.
    """
    print("  [metal] Restarting Ollama to clear stuck Metal contexts ...", flush=True)
    try:
        result = subprocess.run(
            ["sudo", "-n", "/bin/launchctl", "kickstart", "-k", "system/com.portal5.ollama"],
            timeout=30,
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            print(
                "  [metal] Ollama restart failed — sudo rule missing or kickstart errored: "
                f"{result.stderr.decode(errors='replace').strip()}",
                flush=True,
            )
            return False
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
            pass  # Ollama not yet up — poll loop continues until 30 s deadline
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
    """Wait for Metal GPU buffers to drain below ``threshold_pct``.

    Polling exits immediately when the condition is met. On timeout, escalates:
    attempt 1 → ``purge_memory()``, attempt 2 → ``restart_ollama()``, retries
    exhausted → return False. Callers that get False should BLOCK or skip the
    next operation — continuing into high-memory state produces routing
    fallback and confusing false failures.

    Args:
        threshold_pct: Target used% ceiling (default 75%).
        timeout_s:     Polling window per attempt (default 30s).
        poll_s:        vm_stat check interval (default 2s).
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
                f"{prefix} {used:.0f}% (attempt {attempt + 1}/{retries + 1}, {remaining}s left)",
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

    Polls free_ram_gb() until it stabilises (no increase for two consecutive
    checks), applying the same purge → restart escalation on timeout. Uses
    free_ram_gb() rather than memory_pct() because the acceptance runner
    expresses headroom in GB; the two metrics are complementary.

    Args:
        threshold_pct: Unused (kept for API symmetry); stability detection
            replaces threshold-based exit.
        timeout_s:     Polling window per attempt (default 30s).
        poll_s:        vm_stat check interval (default 3s).
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
                stable_count = 0  # still rising — Metal still draining
            else:
                stable_count += 1
                if stable_count >= 2:  # stable for two polls — drain complete
                    print(f"  [metal] Stable at {cur:.1f} GB free — drain complete", flush=True)
                    return cur
            prev = cur
        # Timeout — escalate before next attempt
        if attempt == 0:
            print("  [metal] Timeout at attempt 1 — running purge", flush=True)
            purge_memory()
        elif attempt == 1:
            print("  [metal] Timeout at attempt 2 — restarting Ollama", flush=True)
            import asyncio as _asyncio

            loop = _asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: restart_ollama(ollama_url))
    result = free_ram_gb()
    print(f"  [metal] DRAIN WARNING — {result:.1f} GB free after all retries", flush=True)
    return result


# ── Model load detection (pipeline routing) ───────────────────────────────────


async def wait_for_model_loaded(
    timeout_s: float = 300.0,
    poll_s: float = 5.0,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> bool:
    """Poll /api/ps until Ollama has at least one model loaded.

    Event-driven wait for the non-streaming fallback path: when a backend times
    out, call this before cascading to the next candidate — if the model is
    still in /api/ps it is still generating, not dead.

    Args:
        timeout_s:  Maximum seconds to wait (default 300s).
        poll_s:     Polling interval in seconds (default 5s).
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
            pass  # Ollama not yet responding — poll loop continues
        remaining = int(deadline - time.time())
        if remaining > 0:
            await _asyncio.sleep(min(poll_s, remaining))
    return False
