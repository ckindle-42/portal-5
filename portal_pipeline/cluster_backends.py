"""Portal 5.0 — Backend Registry with health checks and workspace routing.

Config-driven backend selection. No hardcoded URLs. Supports Ollama and
OpenAI-compatible backends (vLLM, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from dataclasses import dataclass
from typing import Any

import httpx
import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.environ.get("BACKEND_CONFIG_PATH", "/app/config/backends.yaml")


@dataclass
class Backend:
    """A single inference backend (Ollama, vLLM, etc.)."""

    id: str
    type: str  # "ollama" | "openai_compatible"
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
        return f"{self.url.rstrip('/')}/health"  # vLLM: /health


class BackendRegistry:
    """Loads backends from YAML, monitors health, routes requests."""

    def __init__(self, config_path: str | None = None) -> None:
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._backends: dict[str, Backend] = {}
        self._workspace_routes: dict[str, list[str]] = {}
        self._fallback_group: str = "general"
        self._health_check_interval = 30.0
        self._request_timeout = 30.0

        self._load_config()

    def _load_config(self) -> None:
        """Parse backends.yaml and populate registry."""
        if not os.path.exists(self.config_path):
            logger.error("Backend config not found: %s", self.config_path)
            # Graceful fallback: create empty registry
            return

        with open(self.config_path, encoding="utf-8") as f:
            cfg: dict[str, Any] = yaml.safe_load(f) or {}

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
        """Return only backends passing health checks."""
        return [b for b in self._backends.values() if b.healthy]

    def get_backend_for_workspace(self, workspace_id: str) -> Backend | None:
        """Select the best healthy backend for a given workspace.

        Routing logic:
        1. Look up workspace → group(s) mapping
        2. Try each group in order for healthy backends
        3. If none found, fall back to any healthy backend in fallback_group
        4. Within a group, randomly select for load balancing
        """
        # Normalize workspace ID (strip "auto-" prefix if present for lookup)
        workspace_id.replace("auto-", "") if workspace_id.startswith("auto-") else workspace_id
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

    async def health_check_all(self) -> None:
        """Run async health checks against all backends."""
        await asyncio.gather(
            *[self._check_one(b) for b in self._backends.values()], return_exceptions=True
        )
        healthy_count = len([b for b in self._backends.values() if b.healthy])
        logger.info("Health check complete: %d/%d healthy", healthy_count, len(self._backends))

    async def _check_one(self, backend: Backend) -> None:
        """Check a single backend's health."""
        import time

        try:
            async with httpx.AsyncClient(timeout=self._health_timeout) as client:
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
