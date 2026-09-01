"""Typed configuration loader — config/portal.yaml → validated PortalConfig.

Validates the workspace catalog and MCP fleet at load time, failing loud with a
precise message rather than silently delivering broken state. Cached after the
first successful load for process lifetime.

Public API: ``load_portal_config`` (cached load, OLLAMA_URL env override),
``get_workspace_dict`` (runtime WORKSPACES dict), ``get_pipeline_mcp_servers``
(env-overridden {id: url}), ``load_persona_map`` ({slug: PersonaSpec}),
``resolve_preset_tools`` (single tool-resolution path).
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

# The discipline modules; "platform" is additionally valid on mcp_fleet
# entries (infra no discipline owns).
ModuleName = Literal[
    "cad",
    "coding",
    "compliance",
    "data",
    "detection",
    "documents",
    "eval",
    "general",
    "image",
    "media",
    "netforensics",
    "research",
    "icsot",
    "security",
    "video",
    "vulnintel",
]

# ── Schema models ─────────────────────────────────────────────────────────────


class ChainHop(BaseModel):
    """One hop in a multi-model chain workspace (e.g. purple-team)."""

    model: str
    label: str
    system: str
    user_template: str


class CouncilMemberSpec(BaseModel):
    """One isolated reviewer in a Council Review workspace."""

    id: str
    label: str
    model: str
    system: str


class CouncilSpec(BaseModel):
    """Fan-out review configuration for an opt-in Council workspace."""

    members: list[CouncilMemberSpec] = Field(min_length=2)
    synthesizer_model: str
    minimum_participation: float = Field(default=0.66, ge=0.0, le=1.0)
    quorum: float = Field(default=0.66, gt=0.0, le=1.0)
    reviewer_max_tokens: int = Field(default=4096, ge=256)
    synthesizer_max_tokens: int = Field(default=4096, ge=256)

    @model_validator(mode="after")
    def unique_member_ids(self) -> CouncilSpec:
        """Member ids are stable evidence references and must be unique."""
        ids = [member.id for member in self.members]
        if len(ids) != len(set(ids)):
            raise ValueError("council member ids must be unique")
        return self


class ToolPreselectSpec(BaseModel):
    """Per-workspace opt-in for query-level tool-schema preselection.

    Absence of this block on a workspace means the feature is bypassed for it
    even when PORTAL5_TOOL_PRESELECT=1 globally.
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

    # --- Collapse axes ---
    mode: Literal["single", "agentic"] = "single"
    depth: Literal["default", "deep", "exec"] = "default"
    guardrail: Literal["default", "uncensored"] = "default"
    variant: str = "default"
    # security-specific axis: red/blue/purple/pentest engagement role
    role: Literal["red", "blue", "purple", "pentest"] = "purple"

    # --- Named variant overrides ---
    # variant name -> partial field overrides, applied on top of this workspace's
    # own fields by resolve_workspace_variant(). Internal-only: never appears in
    # the runtime WORKSPACES dict (see get_workspace_dict's _INTERNAL_ONLY_FIELDS).
    variants: dict[str, dict[str, Any]] = Field(default_factory=dict)

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
    # Workspace-level tool_choice default. persona.tool_choice, when set, still
    # wins. Use only on workspaces whose entire purpose depends on a real tool
    # call happening — a narrow, single-purpose workspace, not a general one.
    tool_choice: str | None = None
    think: bool | None = None
    emits_reasoning: bool | None = None
    keep_alive: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    repeat_penalty: float | None = None
    presence_penalty: float | None = None
    seed: int | None = None
    # Verified per-model thinking/instruct tables — see _resolve_sampling_values.
    think_profiles: dict[str, dict[str, float]] | None = None

    # --- Multi-model chain ---
    chain: list[ChainHop] = Field(default_factory=list)

    # --- Isolated multi-model review ---
    council: CouncilSpec | None = None

    # --- Tool preselection opt-in ---
    tool_preselect: ToolPreselectSpec | None = None

    # --- Proactive context injection (router/context_inject.py) ---
    # Per-workspace opt-ins for memory recall / RAG retrieval / writeback /
    # temporal context. Absent = disabled (missing is treated as False).
    inject_memory: bool | None = None
    auto_rag: bool | None = None
    memory_writeback: bool | None = None
    memory_writeback_all: bool | None = None
    inject_temporal_context: bool | None = None

    # --- Open WebUI projection (portal.yaml-only fields, not in WORKSPACES dict) ---
    expose_to_owui: bool = True
    enable_web_search: bool = False
    owui_system_prompt: str | None = None


class PersonaSpec(BaseModel):
    """One persona entry from ``config/personas/<slug>.yaml``.

    A persona is a workspace override: it inherits ``workspace_model``'s
    routing, model, and default tools, then optionally overrides system prompt
    and tools. ``workspace_model`` must be a key in the loaded ``WORKSPACES``
    catalog.
    """

    name: str
    slug: str
    category: str = "general"
    module: ModuleName
    workspace_model: str  # parent workspace key (= OWUI base_model_id)
    # Optional named variant of workspace_model — e.g. a coding persona pointing
    # at auto-coding with variant: laguna. Resolved by resolve_workspace_variant().
    variant: str | None = None
    # Ordered model fallback chain; advisory metadata only — nothing in the
    # serving path consumes it. ?model=<hint> lets a caller select any entry.
    preferred_models: list[str] = Field(default_factory=list)
    # Exact backends.yaml model id to pin this persona to, applied via the same
    # bounded _resolve_model_override() mechanism the ?model=<hint> query param
    # uses. Unlike preferred_models, this field IS read in the serving path.
    # An unknown/mistyped pin is a silent no-op, never an error.
    model_pin: str | None = None
    system_prompt: str = ""
    # Named reference to a shared prompt body under
    # portal/modules/eval/persona_matrix/prompts/<name>.txt — dedupes
    # bench-matrix personas that previously carried byte-identical inline
    # system_prompt. Exactly one of system_prompt/prompt_template must be set
    # (enforced in load_persona_map).
    prompt_template: str | None = None
    tags: list[str] = Field(default_factory=list)

    # Tool overrides — None means inherit workspace default
    tools_allow: list[str] | None = None
    tools_deny: list[str] = Field(default_factory=list)

    # Force the model to actually invoke a tool rather than narrate an intent
    # and stop without calling one. None = inherit the request default ("auto");
    # set to "required" only for personas whose entire purpose depends on a tool
    # call happening. Do not set broadly — it breaks the tool-free case.
    tool_choice: str | None = None

    # Flags a persona for the opencode/Claude-Code curated model picker so
    # /v1/models can advertise it without exposing every persona in the repo.
    ide_expose: bool = False


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
    default_enabled: bool = Field(
        default=True,
        description=(
            "False for fleet members that stay declared for tool advertisement "
            "but are off by default (e.g. video_mlx — the `video` module is "
            "disabled by default). validate_system.py's fleet-health check must "
            "not treat these as down when unreachable."
        ),
    )


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

# Schema-only fields consulted by resolve_workspace_variant() via
# load_portal_config() directly — never surfaced in the runtime dict itself.
_INTERNAL_ONLY_FIELDS = frozenset({"variants"})


def _eval_enabled() -> bool:
    """Whether the eval module's workspaces/mcp entries should be loaded.

    True when ``PORTAL_ENABLE_EVAL=1`` is set or the eval module is enabled via
    the wiki module toggle.
    """
    if os.environ.get("PORTAL_ENABLE_EVAL", "").lower() in ("true", "1", "yes"):
        return True
    from portal.platform.wiki.adapters.modules import enabled_modules

    return "eval" in enabled_modules()


def get_workspace_dict(config: PortalConfig) -> dict[str, dict[str, Any]]:
    """Return the runtime ``WORKSPACES``-compatible plain dict.

    Strips portal.yaml-only fields so the dict deep-equals the original Python
    literal (tests/fixtures/workspaces_snapshot.json). Excludes workspaces whose
    module is disabled; the eval module additionally honors
    ``PORTAL_ENABLE_EVAL=1`` as a bench-harness opt-in.
    """
    from portal.platform.wiki.adapters.modules import enabled_modules

    enabled = set(enabled_modules())
    eval_on = _eval_enabled()
    result: dict[str, dict[str, Any]] = {}
    for ws_id, spec in config.workspaces.items():
        if spec.module == "eval" and not eval_on:
            continue
        if spec.module != "eval" and spec.module not in enabled:
            continue
        # model_dump excludes None fields; this mirrors the original literal
        # where absent fields were simply not present (not None).
        raw = spec.model_dump(exclude_none=True, exclude=_OWUI_ONLY_FIELDS | _INTERNAL_ONLY_FIELDS)
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
    ``http://localhost:{port}`` constructed from the fleet table. Hyphens in the
    fleet id become underscores in the key (``music-minimax`` → ``MCP_MUSIC_MINIMAX_URL``)
    since shell/compose env names can't carry hyphens.
    """
    servers: dict[str, str] = {}
    for server in config.mcp_fleet:
        if not server.expose_to_pipeline or server.port is None:
            continue
        env_key = f"MCP_{server.id.upper().replace('-', '_')}_URL"
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

    Invalid files are logged and skipped. Does not validate that every
    ``workspace_model`` resolves — call ``validate_persona_parents`` for that
    gate.
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
            if spec.prompt_template:
                if spec.system_prompt:
                    raise ValueError(
                        f"persona {spec.slug!r} has both system_prompt and prompt_template — "
                        "exactly one is required"
                    )
                spec = spec.model_copy(
                    update={"system_prompt": _load_prompt_template(spec.prompt_template)}
                )
            elif not spec.system_prompt:
                raise ValueError(
                    f"persona {spec.slug!r} has neither system_prompt nor prompt_template — "
                    "exactly one is required"
                )
            result[spec.slug] = spec
        except Exception as exc:
            logger.debug("Failed to load persona %s: %s", yf.name, exc)
    return result


_PROMPT_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2] / "modules" / "eval" / "persona_matrix" / "prompts"
)


def _load_prompt_template(name: str) -> str:
    """Read a shared bench-persona prompt body; raises if the file doesn't exist
    (a dangling prompt_template: reference is a config error, not a silent empty
    prompt)."""
    path = _PROMPT_TEMPLATES_DIR / f"{name}.txt"
    return path.read_text()


def validate_persona_parents(
    personas: dict[str, PersonaSpec],
    config: PortalConfig | None = None,
) -> None:
    """Raise ``ValueError`` if any persona's ``workspace_model`` is not in WORKSPACES.

    Called when strict validation is needed (seeding, CI catalog schema test);
    production pipeline import skips this so a persona pointing at a
    since-removed workspace doesn't block startup.
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
