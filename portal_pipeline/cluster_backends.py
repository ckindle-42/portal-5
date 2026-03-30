"""Portal 5.0 — Backend Registry with health checks and workspace routing.

Config-driven backend selection. No hardcoded URLs. Supports Ollama and
OpenAI-compatible backends (vLLM, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

logger = logging.getLogger(__name__)

# Pre-compiled regex — avoid re-compiling on every string expansion (P5)
_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env(val: Any) -> Any:
    """Expand ${VAR:-default} and ${VAR} env var syntax in strings."""

    def _replace(m: re.Match) -> str:
        var, _, default = m.group(1).partition(":-")
        return os.environ.get(var, default)

    if isinstance(val, str):
        return _ENV_VAR_RE.sub(_replace, val)
    if isinstance(val, dict):
        return {k: _expand_env(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_expand_env(item) for item in val]
    return val


def _default_config_path() -> str:
    """Resolve backends.yaml path with environment awareness.

    Priority:
    1. BACKEND_CONFIG_PATH env var (explicit override)
    2. /app/config/backends.yaml (Docker container path)
    3. <repo_root>/config/backends.yaml (local development — relative to this file)
    """
    # Explicit override always wins
    if env_path := os.environ.get("BACKEND_CONFIG_PATH"):
        return env_path

    # Docker path
    docker_path = Path("/app/config/backends.yaml")
    if docker_path.exists():
        return str(docker_path)

    # Local dev: walk up from this file to find config/backends.yaml
    this_file = Path(__file__).resolve()
    for parent in [this_file.parent, this_file.parent.parent, this_file.parent.parent.parent]:
        candidate = parent / "config" / "backends.yaml"
        if candidate.exists():
            return str(candidate)

    # Fall back to Docker path (will log an error if not found — expected in CI)
    return str(docker_path)


DEFAULT_CONFIG_PATH = _default_config_path()


@dataclass
class Backend:
    """A single inference backend (Ollama, vLLM, etc.)."""

    id: str
    type: str  # "ollama" | "openai_compatible" | "mlx"
    url: str
    group: str  # e.g., "general", "coding", "creative"
    models: list[str]
    healthy: bool = True
    last_check: float = 0.0

    @property
    def chat_url(self) -> str:
        """Return the OpenAI-compatible chat completions URL for this backend.

        Both Ollama (>=0.1.24) and vLLM expose /v1/chat/completions.
        We always use the OpenAI-compatible endpoint so request body format
        is identical regardless of backend type.
        """
        return f"{self.url.rstrip('/')}/v1/chat/completions"

    @property
    def health_url(self) -> str:
        """Return the health/availability check URL for this backend."""
        if self.type == "ollama":
            return f"{self.url.rstrip('/')}/api/tags"  # Ollama: list models
        if self.type == "mlx":
            return f"{self.url.rstrip('/')}/v1/models"  # mlx_lm: OpenAI-compatible
        return f"{self.url.rstrip('/')}/health"  # vLLM: /health


class BackendRegistry:
    """Loads backends from YAML, monitors health, routes requests."""

    # Shared httpx client for health checks — single connection pool reused across
    # all health check cycles. Created lazily on first health check.
    _health_client: httpx.AsyncClient | None = None
    _health_semaphore: asyncio.Semaphore | None = None

    def __init__(self, config_path: str | None = None) -> None:
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._backends: dict[str, Backend] = {}
        self._workspace_routes: dict[str, list[str]] = {}
        self._fallback_group: str = "general"
        self._health_check_interval = 30.0
        self._request_timeout = 120.0  # Match config/backends.yaml defaults.request_timeout
        self._health_timeout = 10.0  # Defensive default before _load_config() runs
        self._max_concurrent_health_checks = 2  # P3: prevent health-check storm
        # P8: cached healthy-backend list — rebuilt only after each health check
        # cycle, not on every inference request.
        self._cached_healthy: list[Backend] = []

        self._load_config()

    def _load_config(self) -> None:
        """Parse backends.yaml and populate registry."""
        if not os.path.exists(self.config_path):
            logger.error("Backend config not found: %s", self.config_path)
            # Graceful fallback: create empty registry
            return

        with open(self.config_path, encoding="utf-8") as f:
            cfg: dict[str, Any] = yaml.safe_load(f) or {}

        # Verify env interpolation
        sample_url = (cfg.get("backends") or [{}])[0].get("url", "")
        if "${" in sample_url:
            logger.warning(
                "backends.yaml URLs contain unexpanded env vars (e.g. %s). "
                "Adding os.path.expandvars() expansion.",
                sample_url[:60],
            )

        # Expand environment variables
        cfg = _expand_env(cfg)

        # Load backends
        for be in cfg.get("backends", []):
            backend = Backend(
                id=be["id"],
                type=be.get("type", "ollama"),
                url=be["url"],
                group=be.get("group", "general"),
                models=be.get("models", []),
            )
            self._backends[backend.id] = backend
            logger.info(
                "Registered backend: %s (%s) in group '%s'", backend.id, backend.type, backend.group
            )

        # Load workspace routing
        self._workspace_routes = cfg.get("workspace_routing", {})

        # Load defaults
        defaults = cfg.get("defaults", {})
        self._fallback_group = defaults.get("fallback_group", "general")
        self._request_timeout = float(defaults.get("request_timeout", 120.0))
        self._health_check_interval = float(defaults.get("health_check_interval", 30.0))
        self._health_timeout = float(defaults.get("health_timeout", 10.0))

        logger.info(
            "BackendRegistry loaded: %d backends, %d workspace routes, request_timeout=%.0fs",
            len(self._backends),
            len(self._workspace_routes),
            self._request_timeout,
        )

    def list_backends(self) -> list[Backend]:
        """Return all registered backends."""
        return list(self._backends.values())

    def list_healthy_backends(self) -> list[Backend]:
        """Return only backends passing health checks.

        Returns the cached list populated after each health-check cycle (P8).
        Falls back to a live scan only before the first health check completes.
        """
        return (
            self._cached_healthy
            if self._cached_healthy
            else [b for b in self._backends.values() if b.healthy]
        )

    def _refresh_healthy_cache(self) -> None:
        """Rebuild the cached healthy-backend list. Called after each health cycle."""
        self._cached_healthy = [b for b in self._backends.values() if b.healthy]

    def get_backend_for_workspace(self, workspace_id: str) -> Backend | None:
        """Select the best healthy backend for a given workspace.

        Routing logic:
        1. Look up workspace → group(s) mapping
        2. Try each group in order for healthy backends
        3. If none found, fall back to any healthy backend in fallback_group
        4. Within a group, randomly select for load balancing
        """
        groups = self._workspace_routes.get(workspace_id, [self._fallback_group])

        healthy = self.list_healthy_backends()
        if not healthy:
            return None

        # Try each routed group in order
        for group in groups:
            candidates = [b for b in healthy if b.group == group]
            if candidates:
                return random.choice(candidates)

        # Final fallback: any healthy backend from fallback group
        fallback = [b for b in healthy if b.group == self._fallback_group]
        if fallback:
            return random.choice(fallback)

        # Absolute fallback: any healthy backend
        return random.choice(healthy) if healthy else None

    @classmethod
    def _get_health_semaphore(cls) -> asyncio.Semaphore:
        """Lazily-create shared semaphore for concurrent health checks (P3)."""
        if cls._health_semaphore is None:
            cls._health_semaphore = asyncio.Semaphore(2)
        return cls._health_semaphore

    @classmethod
    async def _get_health_client(cls, health_timeout: float) -> httpx.AsyncClient:
        """Lazily-create shared httpx client for health checks (P1+P4).

        A single client with a connection pool is reused across all health-check
        cycles, avoiding TCP/TLS handshake overhead on every 30s cycle.
        """
        if cls._health_client is None:
            cls._health_client = httpx.AsyncClient(
                timeout=health_timeout,
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                ),
            )
        return cls._health_client

    async def health_check_all(self) -> None:
        """Run async health checks against all backends, bounded by semaphore (P3)."""
        sem = self._get_health_semaphore()
        client = await self._get_health_client(self._health_timeout)
        await asyncio.gather(
            *[self._check_one(b, sem, client) for b in self._backends.values()],
            return_exceptions=True,
        )
        self._refresh_healthy_cache()  # P8: update cache after all checks complete
        healthy_count = len(self._cached_healthy)
        logger.info("Health check complete: %d/%d healthy", healthy_count, len(self._backends))

    async def _check_one(
        self,
        backend: Backend,
        sem: asyncio.Semaphore,
        client: httpx.AsyncClient,
    ) -> None:
        """Check a single backend's health using the shared client (P1+P4)."""
        async with sem:
            try:
                resp = await client.get(backend.health_url)
                backend.healthy = resp.status_code == 200
            except Exception as e:
                logger.debug("Health check failed for %s: %s", backend.id, e)
                backend.healthy = False
            finally:
                backend.last_check = time.time()

    async def start_health_loop(self) -> None:
        """Background task: run health checks periodically."""
        logger.info("Starting health check loop (interval: %ss)", self._health_check_interval)
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self.health_check_all()
            except asyncio.CancelledError:
                logger.info("Health check loop cancelled")
                break
            except Exception as e:
                logger.error("Health loop error: %s", e)

    @property
    def request_timeout(self) -> float:
        return self._request_timeout
