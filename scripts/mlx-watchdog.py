#!/usr/bin/env python3
"""MLX Watchdog v2 — async, memory-aware MLX subsystem monitor.

Recovers from two distinct failure modes the in-proxy crash-recovery cannot:

  1. **Proxy crash.** The in-proxy `_cleanup_zombie_servers` is gone with the
     proxy. Only an external daemon can restart the proxy itself.

  2. **Zombie servers when the proxy is unable to reach them.** The proxy's
     own zombie cleanup runs only when the proxy is alive AND its watchdog
     thread is healthy. If the proxy is itself stuck (event loop blocked,
     deadlock, stalled on a long sync call), zombies accumulate. This
     watchdog detects and clears them independently.

Design notes:

  * **Async throughout.** A 30-second wait for Metal GPU memory reclamation
    must not block proxy health probing. asyncio.gather lets memory-reclaim
    waits run concurrent with proxy /health probes.

  * **Memory-aware decisions.** The proxy's /health response now includes
    GPU/system memory snapshots. Zombie kills that would free X GB are
    sequenced by available memory — a zombie holding 46GB while only 5GB
    is free escalates to SIGKILL faster than one with plenty of headroom.

  * **launchctl kickstart for proxy recovery** preserves the plist's
    EnvironmentVariables (HF_HOME, HF_HUB_CACHE, HF_TOKEN) and keeps the
    new process tracked by launchd's KeepAlive. Falls back to subprocess
    on Linux dev environments.

  * **Decaying recovery counter.** A flaky service that crashes once a week
    should not accumulate toward MAX_RECOVERY_ATTEMPTS forever. Counter
    decays by one each RECOVERY_DECAY_SECONDS of sustained health.

  * **Forensic capture on proxy crash.** /health snapshot, last N proxy log
    lines, memory state, and process listing are saved to
    /tmp/mlx-watchdog-forensics-<ts>.json so operators have something to
    debug from after the watchdog auto-recovers.

  * **Notification debounce.** Same event class within COOLDOWN_S is
    suppressed. A flapping service produces one alert per cooldown, not
    one per cycle.

  * **Prometheus metrics endpoint** (text exposition) on
    MLX_WATCHDOG_METRICS_PORT (default 9101). Counters and gauges feed the
    existing Grafana dashboard.

  * **Robust singleton** via fcntl.flock on a lockfile. Survives crashes
    cleanly; another instance attempting to start while the lock is held
    exits with code 0 (not an error — just "someone else is doing this").

Run: `python3 scripts/mlx-watchdog.py`. Configured via env (see Config below).
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import logging
import os
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# ── .env loading (before any env reads) ─────────────────────────────────────


def _load_dotenv() -> None:
    """Walk up from this script, source the first .env we find. Don't override."""
    script = Path(__file__).resolve()
    for candidate in (script.parent, script.parent.parent, script.parent.parent.parent):
        env_file = candidate / ".env"
        if env_file.is_file():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
            return


_load_dotenv()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [mlx-watchdog] %(levelname)s %(message)s",
)
logger = logging.getLogger("mlx-watchdog")


# ── Config ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Config:
    """All env-derived configuration in one place. Read once at startup."""

    # Component ports
    proxy_port: int = int(os.environ.get("MLX_PROXY_PORT", "8081"))
    lm_port: int = int(os.environ.get("MLX_LM_PORT", "18081"))
    vlm_port: int = int(os.environ.get("MLX_VLM_PORT", "18082"))

    # Cycle timing
    cycle_interval_s: int = int(os.environ.get("MLX_WATCHDOG_INTERVAL", "30"))
    proxy_probe_timeout_s: float = float(os.environ.get("MLX_WATCHDOG_PROBE_TIMEOUT", "5"))
    server_probe_timeout_s: float = float(os.environ.get("MLX_WATCHDOG_SERVER_TIMEOUT", "3"))

    # Zombie kill behavior
    zombie_sigterm_grace_s: int = int(os.environ.get("MLX_ZOMBIE_SIGTERM_GRACE", "3"))
    zombie_kill_wait_s: int = int(os.environ.get("MLX_ZOMBIE_KILL_WAIT_S", "30"))
    zombie_min_proxy_state_age_s: int = int(os.environ.get("MLX_ZOMBIE_MIN_AGE", "120"))
    """If proxy reports state=switching with state_duration < this, skip zombie checks."""

    # Memory pressure (GB)
    memory_critical_gb: float = float(os.environ.get("MLX_MEMORY_CRITICAL_GB", "8"))
    """Below this, escalate zombie kills (skip SIGTERM grace, go straight to SIGKILL)."""

    # Recovery state machine
    recovery_threshold_failures: int = int(os.environ.get("MLX_RECOVERY_THRESHOLD", "2"))
    max_recovery_attempts: int = int(os.environ.get("MLX_MAX_RECOVERY_ATTEMPTS", "3"))
    min_seconds_between_recoveries: int = int(os.environ.get("MLX_RECOVERY_MIN_INTERVAL", "60"))
    recovery_decay_seconds: int = int(os.environ.get("MLX_RECOVERY_DECAY_S", "3600"))
    """After this many seconds of sustained health, decrement recovery_attempts by 1."""

    # launchd integration
    proxy_launchd_label: str = os.environ.get("MLX_PROXY_LAUNCHD_LABEL", "com.portal5.mlx-proxy")

    # Notification debounce
    notification_cooldown_s: int = int(os.environ.get("MLX_NOTIFY_COOLDOWN_S", "300"))

    # Forensics
    forensics_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("MLX_FORENSICS_DIR", "/tmp"))
    )
    forensics_log_tail_lines: int = int(os.environ.get("MLX_FORENSICS_LOG_TAIL", "100"))
    proxy_log_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "MLX_PROXY_LOG_PATH",
                str(Path.home() / ".portal5" / "logs" / "mlx-proxy.log"),
            )
        )
    )

    # Metrics endpoint
    metrics_port: int = int(os.environ.get("MLX_WATCHDOG_METRICS_PORT", "9101"))
    metrics_enabled: bool = (
        os.environ.get("MLX_WATCHDOG_METRICS_ENABLED", "true").lower() != "false"
    )

    # Master enable
    enabled: bool = os.environ.get("MLX_WATCHDOG_ENABLED", "true").lower() != "false"

    # Notifications (read same env vars as pipeline)
    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_user_ids: str = os.environ.get("TELEGRAM_USER_IDS", "")
    pushover_token: str = os.environ.get("PUSHOVER_API_TOKEN", "")
    pushover_user: str = os.environ.get("PUSHOVER_USER_KEY", "")
    slack_webhook_url: str = os.environ.get("SLACK_WEBHOOK_URL", "")
    webhook_url: str = os.environ.get("WEBHOOK_URL", "")

    # Lock files
    watchdog_pid_file: Path = field(
        default_factory=lambda: Path(os.environ.get("MLX_WATCHDOG_PID_FILE", "/tmp/mlx-watchdog.pid"))
    )
    watchdog_lock_file: Path = field(
        default_factory=lambda: Path(
            os.environ.get("MLX_WATCHDOG_LOCK_FILE", "/tmp/mlx-watchdog.lock")
        )
    )


# ── Typed snapshots ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProxyHealth:
    """Snapshot of proxy /health response. None values mean "field absent or proxy unreachable"."""

    reachable: bool
    state: str | None  # "ready" | "switching" | "down" | "none" | None
    active_server: str | None  # "lm" | "vlm" | None
    loaded_model: str | None
    state_duration_sec: float | None
    consecutive_failures: int | None
    switch_count: int | None
    last_error: str | None
    memory_free_gb: float | None
    memory_used_pct: float | None
    raw: dict[str, Any]  # original JSON for forensics


@dataclass(frozen=True)
class ServerProbe:
    """Snapshot of an mlx_lm/mlx_vlm server: PIDs found via pgrep, plus /health response."""

    name: str  # "mlx_lm" | "mlx_vlm"
    port: int
    process_pattern: str
    pids: list[int]
    http_responding: bool
    http_status: int | None  # None if no response


# ── Mutable state ───────────────────────────────────────────────────────────


@dataclass
class ComponentState:
    """Per-component health and recovery state."""

    name: str
    healthy: bool = True
    consecutive_failures: int = 0
    recovery_attempts: int = 0
    last_recovery_attempt: float = 0.0
    last_healthy_at: float = field(default_factory=time.time)


@dataclass
class WatchdogState:
    """All mutable state owned by the watchdog loop."""

    proxy: ComponentState = field(default_factory=lambda: ComponentState("MLX Proxy"))
    cycle_count: int = 0
    started_at: float = field(default_factory=time.time)
    last_zombie_kill_at: float = 0.0
    consecutive_zombie_kills: int = 0  # for backoff if servers keep zombifying


# ── Process discovery ───────────────────────────────────────────────────────


async def _pgrep(pattern: str) -> list[int]:
    """Return PIDs matching `pgrep -f pattern`. Empty list on no match or error."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "pgrep",
            "-f",
            pattern,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        return [int(p) for p in stdout.decode().split() if p.isdigit()]
    except (asyncio.TimeoutError, FileNotFoundError, ValueError):
        return []


async def _http_get_json(client: httpx.AsyncClient, url: str, timeout: float) -> tuple[int | None, dict | None]:
    """GET a URL, return (status_code, parsed_json) or (None, None) on any failure."""
    try:
        r = await client.get(url, timeout=timeout)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, None
    except Exception:
        return None, None


# ── Probes ──────────────────────────────────────────────────────────────────


async def probe_proxy(client: httpx.AsyncClient, config: Config) -> ProxyHealth:
    """Read proxy /health, return typed snapshot. reachable=False if any failure."""
    status, body = await _http_get_json(
        client, f"http://127.0.0.1:{config.proxy_port}/health", config.proxy_probe_timeout_s
    )

    if status is None or body is None:
        return ProxyHealth(
            reachable=False,
            state=None,
            active_server=None,
            loaded_model=None,
            state_duration_sec=None,
            consecutive_failures=None,
            switch_count=None,
            last_error=None,
            memory_free_gb=None,
            memory_used_pct=None,
            raw={},
        )

    memory = body.get("memory") or {}
    return ProxyHealth(
        reachable=True,
        state=body.get("state"),
        active_server=body.get("active_server"),
        loaded_model=body.get("loaded_model"),
        state_duration_sec=body.get("state_duration_sec"),
        consecutive_failures=body.get("consecutive_failures"),
        switch_count=body.get("switch_count"),
        last_error=body.get("last_error"),
        memory_free_gb=memory.get("free_gb"),
        memory_used_pct=memory.get("used_pct"),
        raw=body,
    )


async def probe_server(client: httpx.AsyncClient, name: str, port: int, pattern: str, timeout: float) -> ServerProbe:
    """Probe a single MLX server: pgrep + /health in parallel."""
    pids_task = asyncio.create_task(_pgrep(pattern))
    http_task = asyncio.create_task(
        _http_get_json(client, f"http://127.0.0.1:{port}/health", timeout)
    )
    pids, (status, _) = await asyncio.gather(pids_task, http_task)
    return ServerProbe(
        name=name,
        port=port,
        process_pattern=pattern,
        pids=pids,
        http_responding=(status == 200),
        http_status=status,
    )


# ── Zombie classifier ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ZombieDecision:
    """Whether to act on a server probe and how aggressively."""

    is_zombie: bool
    reason: str
    aggressive: bool  # skip SIGTERM grace, go straight to SIGKILL


def classify_zombie(server: ServerProbe, proxy: ProxyHealth, config: Config) -> ZombieDecision:
    """Decide whether `server` is a zombie that warrants killing.

    A zombie is: process alive (pids non-empty), /health unresponsive, AND we have
    confidence the server is not legitimately busy loading a model.

    Guards against false positives:
      * If proxy reports state=switching AND state_duration < zombie_min_proxy_state_age_s,
        the server may be loading. Skip.
      * If process count == 0, there's nothing to kill. Skip.
      * If /health responded 200, server is healthy. Skip.

    Aggressive escalation when:
      * memory_free_gb < memory_critical_gb (every byte counts; skip SIGTERM grace)
    """
    if not server.pids:
        return ZombieDecision(False, "no process found", False)

    if server.http_responding:
        return ZombieDecision(False, "/health responding 200", False)

    # Proxy state check — skip if a model load is in progress
    if (
        proxy.reachable
        and proxy.state == "switching"
        and proxy.state_duration_sec is not None
        and proxy.state_duration_sec < config.zombie_min_proxy_state_age_s
    ):
        return ZombieDecision(
            False,
            f"proxy state=switching for only {proxy.state_duration_sec}s — model may be loading",
            False,
        )

    # Confirmed zombie. Decide aggressiveness based on memory pressure.
    aggressive = (
        proxy.memory_free_gb is not None and proxy.memory_free_gb < config.memory_critical_gb
    )
    reason = (
        f"process alive (pids={server.pids}), /health unresponsive (status={server.http_status})"
    )
    if aggressive:
        reason += f", memory critical (free={proxy.memory_free_gb}GB)"
    return ZombieDecision(True, reason, aggressive)


# ── Recovery actions ────────────────────────────────────────────────────────


async def kill_pids(pids: list[int], aggressive: bool, sigterm_grace_s: int) -> int:
    """Send SIGTERM (then SIGKILL after grace) to pids. Returns count actually killed.

    aggressive=True skips SIGTERM and goes straight to SIGKILL — used when memory
    pressure is critical and we cannot afford to wait for a graceful exit.
    """
    killed = 0
    if aggressive:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                logger.info("SIGKILL → PID %d (aggressive: memory critical)", pid)
                killed += 1
            except ProcessLookupError:
                pass
        return killed

    # SIGTERM phase
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("SIGTERM → PID %d", pid)
        except ProcessLookupError:
            pass

    await asyncio.sleep(sigterm_grace_s)

    # SIGKILL stragglers
    for pid in pids:
        try:
            os.kill(pid, 0)  # check alive
            os.kill(pid, signal.SIGKILL)
            logger.info("SIGKILL → PID %d (survived SIGTERM)", pid)
            killed += 1
        except ProcessLookupError:
            killed += 1  # exited cleanly
    return killed


async def restart_proxy_via_launchctl(config: Config) -> tuple[bool, str]:
    """Ask launchd to restart the MLX proxy via `launchctl kickstart -k`.

    Preserves the plist's EnvironmentVariables (HF_HOME etc.) and keeps the new
    process under launchd's KeepAlive. Fallback to subprocess.Popen if launchctl
    is unavailable (Linux dev) or returns non-zero.

    Returns (success, message_for_log_or_notification).
    """
    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{config.proxy_launchd_label}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "launchctl",
            "kickstart",
            "-k",
            target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode == 0:
            return True, f"launchctl kickstart -k {target} OK"

        err_msg = stderr.decode().strip() or stdout.decode().strip()
        logger.warning("launchctl kickstart returned %d: %s", proc.returncode, err_msg)
        return False, f"launchctl kickstart returned {proc.returncode}: {err_msg}"
    except FileNotFoundError:
        return False, "launchctl not found — Linux dev environment"
    except asyncio.TimeoutError:
        return False, "launchctl kickstart timed out after 30s"
    except Exception as e:
        return False, f"launchctl kickstart raised: {e}"


async def restart_proxy_fallback_popen(config: Config) -> tuple[bool, str]:
    """Direct-spawn the proxy. Used only when launchctl is unavailable.

    NOTE: this loses the launchd plist's EnvironmentVariables. Logs a warning so
    operators investigate why launchctl wasn't usable.
    """
    logger.warning("Falling back to direct proxy spawn — plist environment is lost")

    # Kill any existing proxy
    pids = await _pgrep("mlx-proxy.py")
    for pid in pids:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)
    await asyncio.sleep(2)

    script_dir = Path(__file__).parent
    proxy_script = script_dir / "mlx-proxy.py"
    if not proxy_script.exists():
        return False, f"mlx-proxy.py not found at {proxy_script}"

    try:
        subprocess.Popen(  # noqa: S603 — intentional spawn
            ["python3", str(proxy_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True, "spawned mlx-proxy.py via subprocess.Popen (no launchd)"
    except Exception as e:
        return False, f"Popen failed: {e}"


async def wait_for_proxy_ready(client: httpx.AsyncClient, config: Config, max_wait_s: int = 60) -> bool:
    """Poll proxy /health until any HTTP response. Returns True if alive within max_wait_s."""
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        h = await probe_proxy(client, config)
        if h.reachable:
            return True
        await asyncio.sleep(2)
    return False


# ── Forensic capture ────────────────────────────────────────────────────────


async def capture_proxy_forensics(
    config: Config, last_known_health: ProxyHealth | None, reason: str
) -> Path | None:
    """Snapshot diagnostic state to a JSON file before restarting the proxy.

    Captures:
      * Last successful /health response we have on file
      * Last N lines of the proxy log
      * Process listing for mlx-related processes
      * System memory state (vm_stat output)
      * Timestamp + the reason recovery was triggered
    """
    config.forensics_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = config.forensics_dir / f"mlx-watchdog-forensics-{ts}.json"

    payload: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "trigger_reason": reason,
        "last_known_proxy_health": last_known_health.raw if last_known_health else None,
    }

    # Proxy log tail
    try:
        if config.proxy_log_path.is_file():
            with config.proxy_log_path.open("r", errors="replace") as f:
                lines = deque(f, maxlen=config.forensics_log_tail_lines)
                payload["proxy_log_tail"] = list(lines)
        else:
            payload["proxy_log_tail"] = f"(log not found at {config.proxy_log_path})"
    except Exception as e:
        payload["proxy_log_tail"] = f"(read failed: {e})"

    # MLX-related process listing
    try:
        proc = await asyncio.create_subprocess_exec(
            "ps",
            "-eo",
            "pid,pcpu,pmem,etime,command",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        mlx_lines = [
            line
            for line in stdout.decode().splitlines()
            if any(p in line for p in ("mlx-proxy", "mlx_lm", "mlx_vlm"))
        ]
        payload["mlx_processes"] = mlx_lines
    except Exception as e:
        payload["mlx_processes"] = f"(ps failed: {e})"

    # System memory
    try:
        proc = await asyncio.create_subprocess_exec(
            "vm_stat",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        payload["vm_stat"] = stdout.decode()
    except Exception as e:
        payload["vm_stat"] = f"(vm_stat failed: {e})"

    try:
        out.write_text(json.dumps(payload, indent=2, default=str))
        logger.info("Forensics captured to %s", out)
        return out
    except Exception as e:
        logger.warning("Failed to write forensics file: %s", e)
        return None


# ── Notifications (with debounce) ───────────────────────────────────────────


class NotificationBus:
    """Multi-channel notification bus with per-event-class debounce.

    Channels are async (httpx.AsyncClient.post) so a slow Telegram API doesn't
    block Slack delivery. Each event class has a cooldown — repeated events of
    the same class within COOLDOWN_S log instead of dispatch.
    """

    def __init__(self, config: Config, client: httpx.AsyncClient) -> None:
        self.config = config
        self.client = client
        self._last_sent: dict[str, float] = {}  # event_class -> timestamp

    def _channels_configured(self) -> list[str]:
        names = []
        if self.config.telegram_bot_token:
            names.append("Telegram")
        if self.config.pushover_token and self.config.pushover_user:
            names.append("Pushover")
        if self.config.slack_webhook_url:
            names.append("Slack")
        if self.config.webhook_url:
            names.append("Webhook")
        return names

    async def send(self, event_class: str, severity: str, message: str, *, force: bool = False) -> bool:
        """Dispatch a notification across all configured channels.

        event_class is a short stable string (e.g. 'proxy_down', 'zombie_killed_lm').
        Cooldown is per event_class.
        Returns True if dispatched, False if suppressed by cooldown.
        """
        now = time.time()
        last = self._last_sent.get(event_class, 0.0)
        if not force and (now - last) < self.config.notification_cooldown_s:
            logger.debug(
                "notification suppressed (event=%s, cooldown active for %ds more)",
                event_class,
                int(self.config.notification_cooldown_s - (now - last)),
            )
            return False

        self._last_sent[event_class] = now
        title = f"[MLX {severity}]"
        full_message = f"{title} {message}"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        full_with_ts = f"{full_message}\n{ts}"

        tasks: list[asyncio.Task] = []
        if self.config.telegram_bot_token:
            tasks.append(asyncio.create_task(self._telegram(full_with_ts)))
        if self.config.pushover_token and self.config.pushover_user:
            tasks.append(asyncio.create_task(self._pushover(severity, message)))
        if self.config.slack_webhook_url:
            tasks.append(asyncio.create_task(self._slack(severity, message)))
        if self.config.webhook_url:
            tasks.append(asyncio.create_task(self._webhook(severity, message)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return True

    async def _telegram(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
        user_ids = [
            int(uid.strip())
            for uid in self.config.telegram_user_ids.split(",")
            if uid.strip().isdigit()
        ]
        for uid in user_ids:
            try:
                await self.client.post(url, json={"chat_id": uid, "text": text}, timeout=10)
            except Exception as e:
                logger.warning("Telegram notification failed: %s", e)

    async def _pushover(self, severity: str, message: str) -> None:
        priority = {"DOWN": 1, "CRITICAL": 2, "ERROR": 1, "RECOVERED": 0}.get(severity, 0)
        try:
            await self.client.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": self.config.pushover_token,
                    "user": self.config.pushover_user,
                    "title": f"MLX {severity}",
                    "message": message,
                    "priority": priority,
                },
                timeout=10,
            )
        except Exception as e:
            logger.warning("Pushover notification failed: %s", e)

    async def _slack(self, severity: str, message: str) -> None:
        emoji = {
            "DOWN": ":warning:",
            "CRITICAL": ":rotating_light:",
            "RECOVERED": ":white_check_mark:",
        }.get(severity, ":bell:")
        try:
            await self.client.post(
                self.config.slack_webhook_url,
                json={"text": f"{emoji} *MLX {severity}*\n{message}"},
                timeout=10,
            )
        except Exception as e:
            logger.warning("Slack notification failed: %s", e)

    async def _webhook(self, severity: str, message: str) -> None:
        try:
            await self.client.post(
                self.config.webhook_url,
                json={
                    "source": "mlx-watchdog",
                    "severity": severity,
                    "message": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                timeout=10,
            )
        except Exception as e:
            logger.warning("Webhook notification failed: %s", e)


# ── Metrics endpoint ────────────────────────────────────────────────────────


class WatchdogMetrics:
    """Tracks counters and gauges. Exposes via simple async HTTP server.

    Output is Prometheus text exposition format. Scrapeable from existing
    Grafana setup at MLX_WATCHDOG_METRICS_PORT.
    """

    def __init__(self) -> None:
        # Counters
        self.zombie_kills_total: dict[str, int] = {"mlx_lm": 0, "mlx_vlm": 0}
        self.proxy_restarts_total: int = 0
        self.proxy_restart_failures_total: int = 0
        self.notifications_sent_total: int = 0
        self.notifications_suppressed_total: int = 0
        self.cycles_total: int = 0
        # Gauges (set on each cycle)
        self.proxy_state: str = "unknown"
        self.proxy_consecutive_failures: int = 0
        self.proxy_recovery_attempts: int = 0
        self.memory_free_gb: float = 0.0
        self.memory_used_pct: float = 0.0
        self.last_zombie_kill_seconds_ago: float = -1.0
        self.last_cycle_seconds_ago: float = -1.0
        self.last_cycle_at: float = 0.0

    def observe_cycle(self) -> None:
        self.cycles_total += 1
        self.last_cycle_at = time.time()

    def observe_proxy(self, h: ProxyHealth, state: ComponentState) -> None:
        self.proxy_state = h.state or ("unreachable" if not h.reachable else "unknown")
        self.proxy_consecutive_failures = state.consecutive_failures
        self.proxy_recovery_attempts = state.recovery_attempts
        if h.memory_free_gb is not None:
            self.memory_free_gb = h.memory_free_gb
        if h.memory_used_pct is not None:
            self.memory_used_pct = h.memory_used_pct

    def observe_zombie_kill(self, server_name: str) -> None:
        self.zombie_kills_total[server_name] = self.zombie_kills_total.get(server_name, 0) + 1

    def observe_proxy_restart(self, success: bool) -> None:
        if success:
            self.proxy_restarts_total += 1
        else:
            self.proxy_restart_failures_total += 1

    def observe_notification(self, dispatched: bool) -> None:
        if dispatched:
            self.notifications_sent_total += 1
        else:
            self.notifications_suppressed_total += 1

    def render_text(self) -> str:
        """Return Prometheus text-format exposition."""
        now = time.time()
        self.last_cycle_seconds_ago = (
            now - self.last_cycle_at if self.last_cycle_at else -1.0
        )

        lines = [
            "# HELP mlx_watchdog_zombie_kills_total Total zombie servers killed",
            "# TYPE mlx_watchdog_zombie_kills_total counter",
        ]
        for srv, n in self.zombie_kills_total.items():
            lines.append(f'mlx_watchdog_zombie_kills_total{{server="{srv}"}} {n}')
        lines += [
            "# HELP mlx_watchdog_proxy_restarts_total Total successful proxy restarts",
            "# TYPE mlx_watchdog_proxy_restarts_total counter",
            f"mlx_watchdog_proxy_restarts_total {self.proxy_restarts_total}",
            "# HELP mlx_watchdog_proxy_restart_failures_total Total failed proxy restart attempts",
            "# TYPE mlx_watchdog_proxy_restart_failures_total counter",
            f"mlx_watchdog_proxy_restart_failures_total {self.proxy_restart_failures_total}",
            "# HELP mlx_watchdog_notifications_sent_total Total notifications dispatched",
            "# TYPE mlx_watchdog_notifications_sent_total counter",
            f"mlx_watchdog_notifications_sent_total {self.notifications_sent_total}",
            "# HELP mlx_watchdog_notifications_suppressed_total Notifications suppressed by cooldown",
            "# TYPE mlx_watchdog_notifications_suppressed_total counter",
            f"mlx_watchdog_notifications_suppressed_total {self.notifications_suppressed_total}",
            "# HELP mlx_watchdog_cycles_total Total monitoring cycles completed",
            "# TYPE mlx_watchdog_cycles_total counter",
            f"mlx_watchdog_cycles_total {self.cycles_total}",
            "# HELP mlx_watchdog_proxy_state Current proxy state",
            "# TYPE mlx_watchdog_proxy_state gauge",
            f'mlx_watchdog_proxy_state{{state="{self.proxy_state}"}} 1',
            "# HELP mlx_watchdog_proxy_consecutive_failures Consecutive proxy health-check failures",
            "# TYPE mlx_watchdog_proxy_consecutive_failures gauge",
            f"mlx_watchdog_proxy_consecutive_failures {self.proxy_consecutive_failures}",
            "# HELP mlx_watchdog_proxy_recovery_attempts Proxy recovery attempt count (decays with sustained health)",
            "# TYPE mlx_watchdog_proxy_recovery_attempts gauge",
            f"mlx_watchdog_proxy_recovery_attempts {self.proxy_recovery_attempts}",
            "# HELP mlx_watchdog_memory_free_gb GPU/system memory free per last proxy /health",
            "# TYPE mlx_watchdog_memory_free_gb gauge",
            f"mlx_watchdog_memory_free_gb {self.memory_free_gb}",
            "# HELP mlx_watchdog_memory_used_pct Memory used percent per last proxy /health",
            "# TYPE mlx_watchdog_memory_used_pct gauge",
            f"mlx_watchdog_memory_used_pct {self.memory_used_pct}",
            "# HELP mlx_watchdog_last_cycle_seconds_ago Seconds since last completed monitoring cycle",
            "# TYPE mlx_watchdog_last_cycle_seconds_ago gauge",
            f"mlx_watchdog_last_cycle_seconds_ago {self.last_cycle_seconds_ago:.1f}",
        ]
        return "\n".join(lines) + "\n"


async def _serve_metrics(metrics: WatchdogMetrics, port: int) -> None:
    """Tiny async HTTP server: GET /metrics returns text exposition."""

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            # Read request line + headers (we ignore them but must consume)
            try:
                await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
            except asyncio.TimeoutError:
                return
            body = metrics.render_text().encode("utf-8")
            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain; version=0.0.4\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                b"Connection: close\r\n"
                b"\r\n" + body
            )
            writer.write(response)
            await writer.drain()
        except Exception as e:
            logger.debug("metrics request handling error: %s", e)
        finally:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", port)
    logger.info("Metrics endpoint listening on http://127.0.0.1:%d/metrics", port)
    async with server:
        await server.serve_forever()


# ── Singleton lock ──────────────────────────────────────────────────────────


def acquire_singleton_lock(config: Config):
    """Acquire exclusive flock on the lock file. Returns the open file handle.

    On failure (another instance holds the lock), exits with code 0 — this is
    expected behavior when launchd starts a watchdog that's already running.

    Caller must keep the returned handle alive for the lifetime of the watchdog.
    """
    config.watchdog_lock_file.parent.mkdir(parents=True, exist_ok=True)
    f = config.watchdog_lock_file.open("w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.info(
            "Another mlx-watchdog instance holds %s — exiting cleanly",
            config.watchdog_lock_file,
        )
        f.close()
        sys.exit(0)
    f.write(str(os.getpid()))
    f.flush()
    return f


def write_pid_file(config: Config) -> None:
    """Write the current PID for tooling that reads /tmp/mlx-watchdog.pid (e.g., status commands)."""
    try:
        config.watchdog_pid_file.parent.mkdir(parents=True, exist_ok=True)
        config.watchdog_pid_file.write_text(str(os.getpid()))
    except OSError as e:
        logger.warning("Could not write PID file %s: %s", config.watchdog_pid_file, e)


# ── Recovery decision helpers ───────────────────────────────────────────────


def _maybe_decay_recovery_attempts(state: ComponentState, config: Config) -> None:
    """If the component has been healthy for recovery_decay_seconds, decrement attempts.

    A flaky component that crashes once a week should not accumulate forever
    toward max_recovery_attempts. Sustained health earns back recovery budget.
    """
    if state.recovery_attempts <= 0:
        return
    if not state.healthy:
        return
    age = time.time() - state.last_healthy_at
    if age >= config.recovery_decay_seconds:
        state.recovery_attempts -= 1
        state.last_healthy_at = time.time()  # reset clock for next decay
        logger.info(
            "Recovery attempts decayed to %d after %ds of sustained health",
            state.recovery_attempts,
            int(age),
        )


def _can_attempt_recovery(state: ComponentState, config: Config) -> tuple[bool, str]:
    """Return (allowed, reason). reason is a short string for logs/notifications."""
    if state.recovery_attempts >= config.max_recovery_attempts:
        return False, f"max attempts ({config.max_recovery_attempts}) reached"
    age = time.time() - state.last_recovery_attempt
    if age < config.min_seconds_between_recoveries:
        return False, f"in cooldown ({int(config.min_seconds_between_recoveries - age)}s remaining)"
    return True, "ok"


# ── Watchdog cycle ──────────────────────────────────────────────────────────


async def watchdog_cycle(
    config: Config,
    state: WatchdogState,
    client: httpx.AsyncClient,
    bus: NotificationBus,
    metrics: WatchdogMetrics,
    last_known_proxy: ProxyHealth | None,
) -> ProxyHealth:
    """One monitoring cycle.

    Returns the proxy health snapshot from this cycle (or last_known_proxy if
    the proxy was unreachable this cycle and we have a previous one).
    """
    state.cycle_count += 1
    metrics.observe_cycle()

    # ── 1. Probe proxy + servers concurrently ──
    proxy_task = asyncio.create_task(probe_proxy(client, config))
    lm_task = asyncio.create_task(
        probe_server(client, "mlx_lm", config.lm_port, "mlx_lm.server", config.server_probe_timeout_s)
    )
    vlm_task = asyncio.create_task(
        probe_server(client, "mlx_vlm", config.vlm_port, "mlx_vlm.server", config.server_probe_timeout_s)
    )
    proxy_health, lm_probe, vlm_probe = await asyncio.gather(proxy_task, lm_task, vlm_task)

    metrics.observe_proxy(proxy_health, state.proxy)

    # ── 2. Update proxy component state ──
    if proxy_health.reachable:
        if not state.proxy.healthy:
            logger.info("Proxy recovered (was unhealthy)")
            dispatched = await bus.send(
                "proxy_recovered",
                "RECOVERED",
                f"MLX Proxy recovered on :{config.proxy_port}",
            )
            metrics.observe_notification(dispatched)
        state.proxy.healthy = True
        state.proxy.consecutive_failures = 0
        state.proxy.last_healthy_at = time.time()
        _maybe_decay_recovery_attempts(state.proxy, config)
    else:
        state.proxy.healthy = False
        state.proxy.consecutive_failures += 1
        logger.warning(
            "Proxy unreachable (failure %d/%d before recovery)",
            state.proxy.consecutive_failures,
            config.recovery_threshold_failures,
        )
        if state.proxy.consecutive_failures == 1:
            dispatched = await bus.send(
                "proxy_down",
                "DOWN",
                f"MLX Proxy not responding on :{config.proxy_port}",
            )
            metrics.observe_notification(dispatched)

    # ── 3. Zombie scan (independent of proxy state, with guards) ──
    # We still scan even if the proxy is down — zombies during a proxy crash
    # are common and need clearing before the proxy can re-spawn cleanly.
    for server_probe in (lm_probe, vlm_probe):
        decision = classify_zombie(server_probe, proxy_health, config)
        if not decision.is_zombie:
            if decision.reason and not server_probe.http_responding and server_probe.pids:
                logger.debug(
                    "%s skipped zombie kill: %s", server_probe.name, decision.reason
                )
            continue

        logger.warning(
            "%s zombie on :%d — %s",
            server_probe.name,
            server_probe.port,
            decision.reason,
        )
        dispatched = await bus.send(
            f"zombie_{server_probe.name}",
            "DOWN",
            f"{server_probe.name} zombie on :{server_probe.port} — "
            f"{decision.reason}. Killing{' aggressively' if decision.aggressive else ''}.",
        )
        metrics.observe_notification(dispatched)

        killed = await kill_pids(
            server_probe.pids, decision.aggressive, config.zombie_sigterm_grace_s
        )
        if killed > 0:
            metrics.observe_zombie_kill(server_probe.name)
            state.last_zombie_kill_at = time.time()
            state.consecutive_zombie_kills += 1

            logger.info(
                "Waiting %ds for Metal GPU memory reclamation…",
                config.zombie_kill_wait_s,
            )
            await asyncio.sleep(config.zombie_kill_wait_s)

            dispatched = await bus.send(
                f"zombie_{server_probe.name}_cleared",
                "RECOVERED",
                f"{server_probe.name} zombie cleared. GPU memory releasing.",
            )
            metrics.observe_notification(dispatched)

    # ── 4. Proxy recovery if threshold reached ──
    if (
        not state.proxy.healthy
        and state.proxy.consecutive_failures >= config.recovery_threshold_failures
    ):
        allowed, reason = _can_attempt_recovery(state.proxy, config)
        if not allowed:
            logger.warning("Proxy recovery skipped: %s", reason)
            if state.proxy.recovery_attempts >= config.max_recovery_attempts:
                # Only notify once when we hit max — don't spam every cycle
                dispatched = await bus.send(
                    "proxy_max_attempts",
                    "CRITICAL",
                    (
                        f"MLX Proxy failed {config.max_recovery_attempts} recovery attempts. "
                        "Manual intervention required."
                    ),
                )
                metrics.observe_notification(dispatched)
        else:
            await _attempt_proxy_recovery(
                config, state, client, bus, metrics, last_known_proxy
            )

    # Reset consecutive zombie kills on a clean cycle
    if proxy_health.reachable and proxy_health.state == "ready":
        state.consecutive_zombie_kills = 0

    return proxy_health if proxy_health.reachable else last_known_proxy


async def _attempt_proxy_recovery(
    config: Config,
    state: WatchdogState,
    client: httpx.AsyncClient,
    bus: NotificationBus,
    metrics: WatchdogMetrics,
    last_known_proxy: ProxyHealth | None,
) -> None:
    """Capture forensics, restart the proxy, wait for it to come up."""
    state.proxy.last_recovery_attempt = time.time()
    state.proxy.recovery_attempts += 1

    logger.warning(
        "Attempting proxy recovery (attempt %d/%d)",
        state.proxy.recovery_attempts,
        config.max_recovery_attempts,
    )

    # 1. Forensic snapshot before we wipe state
    forensics_path = await capture_proxy_forensics(
        config,
        last_known_proxy,
        f"recovery attempt {state.proxy.recovery_attempts} — proxy unreachable for "
        f"{state.proxy.consecutive_failures} consecutive cycles",
    )

    # 2. Restart via launchctl, fall back to Popen
    success, msg = await restart_proxy_via_launchctl(config)
    if not success:
        logger.warning("launchctl restart failed (%s) — trying direct spawn", msg)
        success, msg = await restart_proxy_fallback_popen(config)

    metrics.observe_proxy_restart(success)

    if not success:
        logger.error("Proxy recovery FAILED: %s", msg)
        dispatched = await bus.send(
            "proxy_recovery_failed",
            "ERROR",
            f"Proxy recovery attempt {state.proxy.recovery_attempts} failed: {msg}",
            force=True,  # always notify on recovery failure
        )
        metrics.observe_notification(dispatched)
        return

    # 3. Wait for proxy to respond
    logger.info("Proxy restart issued (%s) — waiting for /health to respond…", msg)
    came_up = await wait_for_proxy_ready(client, config, max_wait_s=60)
    if came_up:
        logger.info("Proxy recovered after restart")
        state.proxy.healthy = True
        state.proxy.consecutive_failures = 0
        state.proxy.last_healthy_at = time.time()
        forensic_note = f" Forensics: {forensics_path}" if forensics_path else ""
        dispatched = await bus.send(
            "proxy_recovered_after_restart",
            "RECOVERED",
            f"MLX Proxy restarted and recovered on :{config.proxy_port}.{forensic_note}",
        )
        metrics.observe_notification(dispatched)
    else:
        logger.error("Proxy did not respond within 60s after restart")
        dispatched = await bus.send(
            "proxy_recovery_timeout",
            "ERROR",
            "Proxy restarted but did not come up within 60 seconds.",
            force=True,
        )
        metrics.observe_notification(dispatched)


# ── Lifecycle ───────────────────────────────────────────────────────────────


async def main_async() -> None:
    config = Config()

    if not config.enabled:
        logger.info("MLX_WATCHDOG_ENABLED=false — exiting")
        return

    # Singleton — must hold for entire lifetime
    lock_handle = acquire_singleton_lock(config)
    write_pid_file(config)

    logger.info(
        "MLX Watchdog v2 starting — proxy :%d, mlx_lm :%d, mlx_vlm :%d, cycle %ds",
        config.proxy_port,
        config.lm_port,
        config.vlm_port,
        config.cycle_interval_s,
    )
    logger.info(
        "Recovery: threshold=%d, max=%d, decay=%ds. Memory critical < %.0fGB.",
        config.recovery_threshold_failures,
        config.max_recovery_attempts,
        config.recovery_decay_seconds,
        config.memory_critical_gb,
    )

    state = WatchdogState()
    metrics = WatchdogMetrics()

    # httpx AsyncClient is shared by probes and notifications
    timeout = httpx.Timeout(10.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        bus = NotificationBus(config, client)
        channels = bus._channels_configured()
        logger.info(
            "Notification channels: %s",
            ", ".join(channels) if channels else "(none configured)",
        )

        # Startup notification
        startup_dispatched = await bus.send(
            "watchdog_started",
            "STARTED",
            (
                f"MLX Watchdog v2 monitoring proxy :{config.proxy_port}, "
                f"mlx_lm :{config.lm_port}, mlx_vlm :{config.vlm_port}. "
                f"Channels: {', '.join(channels) if channels else 'none'}"
            ),
            force=True,
        )
        metrics.observe_notification(startup_dispatched)

        # Spin up metrics endpoint as a background task
        metrics_task: asyncio.Task | None = None
        if config.metrics_enabled:
            try:
                metrics_task = asyncio.create_task(_serve_metrics(metrics, config.metrics_port))
            except Exception as e:
                logger.warning("Could not start metrics endpoint: %s", e)

        # Signal handlers — graceful shutdown
        loop = asyncio.get_running_loop()
        shutdown = asyncio.Event()

        def _on_signal(sig_num: int) -> None:
            logger.info("Received signal %d — shutting down", sig_num)
            shutdown.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _on_signal, sig)

        # Main loop
        last_known_proxy: ProxyHealth | None = None
        try:
            while not shutdown.is_set():
                cycle_start = time.monotonic()
                try:
                    last_known_proxy = await watchdog_cycle(
                        config, state, client, bus, metrics, last_known_proxy
                    )
                except Exception:
                    logger.exception("Cycle error")

                elapsed = time.monotonic() - cycle_start
                sleep_for = max(1.0, config.cycle_interval_s - elapsed)

                # Use shutdown.wait so SIGTERM exits promptly
                try:
                    await asyncio.wait_for(shutdown.wait(), timeout=sleep_for)
                except asyncio.TimeoutError:
                    pass
        finally:
            shutdown_dispatched = await bus.send(
                "watchdog_stopped",
                "STOPPED",
                f"MLX Watchdog stopped after {state.cycle_count} cycles.",
                force=True,
            )
            metrics.observe_notification(shutdown_dispatched)

            if metrics_task is not None:
                metrics_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await metrics_task

            with contextlib.suppress(OSError):
                config.watchdog_pid_file.unlink(missing_ok=True)

            # Lock handle is released when the file closes (here)
            lock_handle.close()
            logger.info("Watchdog stopped cleanly")


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
