"""Typed configuration loader — config/portal.yaml → validated PortalConfig.

Validates workspace catalog and MCP fleet at load time; fails loud with a
precise message rather than silently delivering broken state.  Cached after
the first successful load for process lifetime.

Usage
-----
    from portal.platform.inference.config import load_portal_config
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

``load_persona_map(personas_dir=None)``
    Returns ``{slug: PersonaSpec}`` for every YAML under ``config/personas/``.

``resolve_preset_tools(persona_spec, workspace_spec)``
    Single tool-resolution path for any persona × workspace pair.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

# Path to the single source of truth — relative to repo root
PORTAL_YAML: Path = Path(__file__).resolve().parents[3] / "config" / "portal.yaml"

# The nine discipline modules (BUILD_PROGRAM_COLLAPSE_V1.md Phase 2). "platform"
# is additionally valid on mcp_fleet entries (infra no discipline owns).
ModuleName = Literal[
    "cad", "coding", "compliance", "documents", "eval", "general", "media", "research", "security"
]

# ── Schema models ─────────────────────────────────────────────────────────────


class ChainHop(BaseModel):
    """One hop in a multi-model chain workspace (e.g. purple-team)."""

    model: str
    label: str
    system: str
    user_template: str


class ToolPreselectSpec(BaseModel):
    """Per-workspace opt-in for query-level tool-schema preselection.

    See portal/platform/inference/tool_preselect/README.md. Absence of
    this whole block on a workspace means the feature is bypassed for
    it even when PORTAL5_TOOL_PRESELECT=1 globally.
    """

    enabled: bool = False
    k: int | None = None
    confidence_floor: float = 0.5


class WorkspaceSpec(BaseModel):
    """One workspace entry from portal.yaml workspaces: block."""

    # --- Required ---
    name: str
    description: str
    module: ModuleName

    # --- Collapse axes (BUILD_PROGRAM_COLLAPSE_V1.md §4.1, DESIGN §D4) ---
    mode: Literal["single", "agentic"] = "single"
    depth: Literal["default", "deep", "exec"] = "default"
    guardrail: Literal["default", "uncensored"] = "default"
    variant: str = "default"

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

    # --- Tool preselection opt-in (P5-FUT-TOOL-PRESELECT) ---
    tool_preselect: ToolPreselectSpec | None = None

    # --- Open WebUI projection (portal.yaml-only fields, not in WORKSPACES dict) ---
    expose_to_owui: bool = True
    enable_web_search: bool = False
    owui_system_prompt: str | None = None


class PersonaSpec(BaseModel):
    """One persona entry from ``config/personas/<slug>.yaml``.

    A persona is a workspace override: it inherits ``workspace_model``'s
    routing, model, and default tools, then optionally overrides system
    prompt and tools.  ``workspace_model`` must be a key in the loaded
    ``WORKSPACES`` catalog — validated by ``load_persona_map``.
    """

    name: str
    slug: str
    category: str = "general"
    module: ModuleName
    workspace_model: str  # parent workspace key (= OWUI base_model_id)
    system_prompt: str = ""
    tags: list[str] = Field(default_factory=list)

    # Tool overrides — None means inherit workspace default
    tools_allow: list[str] | None = None
    tools_deny: list[str] = Field(default_factory=list)


class McpServerCommand(BaseModel):
    """Command spec for local (stdio) MCP servers registered in IDE configs."""

    type: str = "local"
    command: list[str]


class Model(BaseModel):
    """Single model registry entry.

    Used by ``portal models pull`` to resolve HuggingFace pull metadata.
    Workspaces reference models by ``ollama_name`` via ``model_hint``.
    """

    model_config = ConfigDict(extra="forbid")

    hf_id: str = Field(..., description="HuggingFace repo ID as known to the operator")
    actual_repo: str | None = Field(
        default=None,
        description="Canonical HF repo for the pull (defaults to hf_id)",
    )
    filename: str | None = Field(
        default=None,
        description=".gguf filename inside actual_repo (omit for native Ollama models)",
    )
    ollama_name: str = Field(..., description="Tag the model lands under in Ollama")
    gated: bool = Field(default=False, description="HF repo requires accepted terms")
    retired: bool = Field(
        default=False,
        description="Excluded from default pulls; retained for history",
    )

    @model_validator(mode="after")
    def _default_actual_repo(self) -> Model:
        if self.actual_repo is None:
            object.__setattr__(self, "actual_repo", self.hf_id)
        return self


class McpServer(BaseModel):
    """One MCP server in the fleet."""

    id: str
    name: str
    module: ModuleName | Literal["platform"]
    port: int | None = None  # None for command-based (IDE-only) servers
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
    models: list[Model] = Field(
        default_factory=list,
        description="HuggingFace → Ollama pull registry (consumed by portal models pull)",
    )

    @model_validator(mode="after")
    def _no_port_collision(self) -> PortalConfig:
        ports = [s.port for s in self.mcp_fleet if s.port is not None]
        seen: set[int] = set()
        dupes = [p for p in ports if p in seen or seen.add(p)]  # type: ignore[func-returns-value]
        if dupes:
            raise ValueError(f"Duplicate MCP ports in fleet: {sorted(set(dupes))}")
        return self

    @model_validator(mode="after")
    def _no_id_collision(self) -> PortalConfig:
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
        raise RuntimeError(f"portal.yaml failed validation ({yaml_path}): {exc}") from exc

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


# ── Persona loader ────────────────────────────────────────────────────────────

_PERSONAS_DIR: Path = Path(__file__).resolve().parents[3] / "config" / "personas"


def load_persona_map(
    personas_dir: Path | None = None,
    config: PortalConfig | None = None,
) -> dict[str, PersonaSpec]:
    """Return ``{slug: PersonaSpec}`` for every YAML under ``config/personas/``.

    Invalid files are logged and skipped (same "graceful-empty" pattern as
    the legacy loader).  Does **not** validate that every ``workspace_model``
    resolves — call ``validate_persona_parents`` if you need that gate.
    """
    directory = personas_dir or _PERSONAS_DIR
    if not directory.is_dir():
        logger.warning("Personas directory not found: %s", directory)
        return {}

    result: dict[str, PersonaSpec] = {}
    for yf in sorted(directory.glob("*.yaml")):
        try:
            raw = yaml.safe_load(yf.read_text()) or {}
            slug = raw.get("slug", yf.stem)
            raw.setdefault("slug", slug)
            spec = PersonaSpec.model_validate(raw)
            result[spec.slug] = spec
        except Exception as exc:
            logger.debug("Failed to load persona %s: %s", yf.name, exc)
    return result


def validate_persona_parents(
    personas: dict[str, PersonaSpec],
    config: PortalConfig | None = None,
) -> None:
    """Raise ``ValueError`` if any persona's ``workspace_model`` is not in WORKSPACES.

    Called at load time when strict validation is needed (e.g. seeding or
    the CI catalog schema test).  Production pipeline import skips this to
    avoid startup failure from a persona pointing at a since-removed workspace.
    """
    if config is None:
        config = load_portal_config()
    known = set(config.workspaces.keys())
    orphans = [
        f"{slug} → {p.workspace_model}"
        for slug, p in personas.items()
        if p.workspace_model not in known
    ]
    if orphans:
        raise ValueError(
            f"{len(orphans)} persona(s) reference unknown workspace_model:\n"
            + "\n".join(f"  {o}" for o in sorted(orphans))
        )


# ── Single tool-resolution path ───────────────────────────────────────────────


def resolve_preset_tools(
    persona: PersonaSpec | None,
    workspace_tools: list[str],
) -> list[str]:
    """Return the effective tool list for a persona × workspace pair.

    Resolution:
    1. ``tools_allow`` absent (``None``) → use ``workspace_tools`` unchanged.
    2. ``tools_allow`` present (even ``[]``) → that set replaces workspace default.
    3. ``tools_deny`` then removes any matching entries.

    Args:
        persona: Typed ``PersonaSpec``; pass ``None`` for bare-workspace requests.
        workspace_tools: The workspace's default tool whitelist (pre-resolved).

    Returns:
        Sorted, deduplicated list of tool names.
    """
    if persona is None:
        return sorted(set(workspace_tools))
    effective = set(workspace_tools) if persona.tools_allow is None else set(persona.tools_allow)
    deny = set(persona.tools_deny or [])
    return sorted(effective - deny)
