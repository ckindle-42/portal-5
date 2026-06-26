"""Typed configuration loader — config/portal.yaml → validated PortalConfig.

Validates workspace catalog and MCP fleet at load time; fails loud with a
precise message rather than silently delivering broken state.  Cached after
the first successful load for process lifetime.

Usage
-----
    from portal_pipeline.config import load_portal_config
    cfg = load_portal_config()
    print(cfg.ollama_url)          # canonical Ollama URL
    print(cfg.workspaces["auto"])  # WorkspaceSpec

Public API
----------
``load_portal_config(path=None, *, _force_reload=False)``
    Returns the cached (or freshly loaded) PortalConfig.

``get_workspace_dict(config)``
    Returns the runtime ``WORKSPACES``-compatible plain dict stripped of
    portal.yaml-only fields (``expose_to_owui``, ``enable_web_search``,
    ``owui_system_prompt``).

``get_pipeline_mcp_servers(config)``
    Returns env-overridden ``{id: url}`` dict for all pipeline-exposed MCPs.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

# Path to the single source of truth — relative to repo root
PORTAL_YAML: Path = Path(__file__).resolve().parent.parent / "config" / "portal.yaml"

# ── Schema models ─────────────────────────────────────────────────────────────


class ChainHop(BaseModel):
    """One hop in a multi-model chain workspace (e.g. purple-team)."""

    model: str
    label: str
    system: str
    user_template: str


class WorkspaceSpec(BaseModel):
    """One workspace entry from portal.yaml workspaces: block."""

    # --- Required ---
    name: str
    description: str

    # --- Routing ---
    model_hint: str | None = None

    # --- Tool whitelist ---
    tools: list[str] = Field(default_factory=list)

    # --- Output budget / context ---
    predict_limit: int | None = None
    context_limit: int | None = None

    # --- Concurrency ---
    max_concurrent: int | None = None

    # --- Model behaviour ---
    system_prompt_append: str | None = None
    think: bool | None = None
    emits_reasoning: bool | None = None
    keep_alive: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    repeat_penalty: float | None = None
    seed: int | None = None

    # --- Multi-model chain ---
    chain: list[ChainHop] = Field(default_factory=list)

    # --- Open WebUI projection (portal.yaml-only fields, not in WORKSPACES dict) ---
    expose_to_owui: bool = True
    enable_web_search: bool = False
    owui_system_prompt: str | None = None


class McpServerCommand(BaseModel):
    """Command spec for local (stdio) MCP servers registered in IDE configs."""

    type: str = "local"
    command: list[str]


class McpServer(BaseModel):
    """One MCP server in the fleet."""

    id: str
    name: str
    port: int | None = None              # None for command-based (IDE-only) servers
    expose_to_pipeline: bool = False
    expose_to_ide: bool = True
    aliases: list[str] = Field(default_factory=list)
    command: McpServerCommand | None = None


class PortalConfig(BaseModel):
    """Top-level portal.yaml schema."""

    workspaces: dict[str, WorkspaceSpec]
    mcp_fleet: list[McpServer]
    ollama_url: str = "http://host.docker.internal:11434"
    request_timeout: int = 300

    @model_validator(mode="after")
    def _no_port_collision(self) -> "PortalConfig":
        ports = [s.port for s in self.mcp_fleet if s.port is not None]
        seen: set[int] = set()
        dupes = [p for p in ports if p in seen or seen.add(p)]  # type: ignore[func-returns-value]
        if dupes:
            raise ValueError(f"Duplicate MCP ports in fleet: {sorted(set(dupes))}")
        return self

    @model_validator(mode="after")
    def _no_id_collision(self) -> "PortalConfig":
        ids = [s.id for s in self.mcp_fleet]
        seen: set[str] = set()
        dupes = [i for i in ids if i in seen or seen.add(i)]  # type: ignore[func-returns-value]
        if dupes:
            raise ValueError(f"Duplicate MCP ids in fleet: {sorted(set(dupes))}")
        return self


# ── Loader ────────────────────────────────────────────────────────────────────

_CONFIG_CACHE: PortalConfig | None = None


def load_portal_config(
    path: Path | None = None,
    *,
    _force_reload: bool = False,
) -> PortalConfig:
    """Load ``config/portal.yaml`` and return a validated :class:`PortalConfig`.

    Cached for process lifetime after the first successful load.  Pass
    ``_force_reload=True`` in tests that swap the YAML path.

    The ``OLLAMA_URL`` env var overrides the YAML value; ``OLLAMA_BASE_URL``
    is accepted as a deprecated alias and triggers a warning.
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not _force_reload:
        return _CONFIG_CACHE

    yaml_path = path or PORTAL_YAML
    raw: dict[str, Any] = yaml.safe_load(yaml_path.read_text()) or {}

    # Canonicalize Ollama URL — env wins over YAML
    env_url = os.environ.get("OLLAMA_URL") or None
    legacy_url = os.environ.get("OLLAMA_BASE_URL") or None
    if legacy_url and not env_url:
        logger.warning(
            "OLLAMA_BASE_URL is deprecated — set OLLAMA_URL instead (value forwarded for "
            "this cycle)"
        )
        env_url = legacy_url
    if env_url:
        raw["ollama_url"] = env_url

    try:
        _CONFIG_CACHE = PortalConfig.model_validate(raw)
    except Exception as exc:
        raise RuntimeError(
            f"portal.yaml failed validation ({yaml_path}): {exc}"
        ) from exc

    return _CONFIG_CACHE


# ── Derived-view helpers ──────────────────────────────────────────────────────

# Fields that exist only in portal.yaml and must NOT appear in the runtime
# WORKSPACES dict that the rest of the pipeline imports.
_OWUI_ONLY_FIELDS = frozenset({"expose_to_owui", "enable_web_search", "owui_system_prompt"})


def get_workspace_dict(config: PortalConfig) -> dict[str, dict[str, Any]]:
    """Return the runtime ``WORKSPACES``-compatible plain dict.

    Strips portal.yaml-only fields so the dict deep-equals the original
    Python literal that was captured in ``tests/fixtures/workspaces_snapshot.json``.
    """
    result: dict[str, dict[str, Any]] = {}
    for ws_id, spec in config.workspaces.items():
        # model_dump excludes None fields; this mirrors the original literal
        # where absent fields were simply not present (not None).
        raw = spec.model_dump(exclude_none=True, exclude=_OWUI_ONLY_FIELDS)
        # Ensure tools is always present (original literal always had it)
        if "tools" not in raw:
            raw["tools"] = []
        # Original literal omitted chain when empty; pydantic emits []; normalise.
        if "chain" in raw and raw["chain"] == []:
            del raw["chain"]
        result[ws_id] = raw
    return result


def get_pipeline_mcp_servers(config: PortalConfig) -> dict[str, str]:
    """Return ``{id: base_url}`` for all pipeline-exposed HTTP MCP servers.

    Env vars ``MCP_<ID_UPPER>_URL`` override the default
    ``http://localhost:{port}`` constructed from the fleet table.
    """
    servers: dict[str, str] = {}
    for server in config.mcp_fleet:
        if not server.expose_to_pipeline or server.port is None:
            continue
        env_key = f"MCP_{server.id.upper()}_URL"
        default_url = f"http://localhost:{server.port}"
        servers[server.id] = os.environ.get(env_key, default_url)
    return servers


def ollama_url(config: PortalConfig | None = None) -> str:
    """Return the canonical Ollama base URL for this process."""
    if config is None:
        config = load_portal_config()
    return config.ollama_url
