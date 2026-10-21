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
from datetime import date
from pathlib import Path
from typing import Any, Literal, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

# Path to the single source of truth — relative to repo root
PORTAL_YAML: Path = Path(__file__).resolve().parents[3] / "config" / "portal.yaml"
# Bench/challenger lanes live outside the production workspace catalog.
BENCH_YAML: Path = PORTAL_YAML.with_name("bench_workspaces.yaml")

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
    "music",
    "netforensics",
    "orchestration",
    "research",
    "icsot",
    "security",
    # Offensive-generation security variants (redteam / redteam-deep /
    # purpleteam-exec). Split from `security` so the everyday system can ship
    # without them while the defensive half stays on: a disabled module removes
    # only the variants that declare it (C7).
    "security_redteam",
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
    # Answer budget. None keeps council.reviewer_max_tokens (today's seat cap).
    max_tokens: int | None = Field(default=None, ge=64)
    # Extra tokens added only while this seat is thinking. Thinking models spend
    # num_predict on reasoning first; the answer budget stays intact.
    reasoning_max_tokens: int | None = Field(default=None, ge=0)
    # None uses the workspace think flag.
    think: bool | None = None
    # Explicit sampling overrides the matching model-card profile.
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    presence_penalty: float | None = None
    repeat_penalty: float | None = None
    repetition_penalty: float | None = None


class CouncilSpeedSpec(BaseModel):
    """Optional speed modes. Every flag defaults off: three parallel reviewers."""

    early_quorum: bool = False
    single_model: bool = False
    # Empty uses the synthesizer model so one resident model serves every seat.
    resident_model: str | None = None
    progress: bool = False
    decompose: bool = False
    decompose_model: str | None = None


class CouncilSpec(BaseModel):
    """Fan-out review configuration for an opt-in Council workspace."""

    members: list[CouncilMemberSpec] = Field(min_length=2)
    synthesizer_model: str
    minimum_participation: float = Field(default=0.66, ge=0.0, le=1.0)
    quorum: float = Field(default=0.66, gt=0.0, le=1.0)
    reviewer_max_tokens: int = Field(default=4096, ge=256)
    synthesizer_max_tokens: int = Field(default=4096, ge=256)
    speed: CouncilSpeedSpec = Field(default_factory=CouncilSpeedSpec)

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
    # False -> the auto-router never selects this workspace: it is absent from
    # the Layer 1 label set and grammar enum, and Layer 2 hands off instead of
    # returning it. It stays user-selectable in Open WebUI and callable by id
    # (`auto-security`, `auto-security::<variant>`), behaving exactly as before
    # when selected directly. `bench-*` is excluded by name in routing.py; this
    # is the declarative form for a named workspace. None means eligible, so the
    # runtime dict stays byte-equal for every workspace that does not set it.
    router: bool | None = None
    # When `router` is False, the lane an auto-routed request that looks like
    # this workspace's work is handed to instead, so it can decline and tell the
    # user to select this workspace explicitly.
    router_fallback: str | None = None
    # One line appended as a system note on that hand-off, naming what to select.
    router_handoff_note: str | None = None

    # True -> the seat needs more memory than the idle host leaves while the
    # Portal stack is up, so the operator runs it with the stack stopped. No
    # serving-path code reads this: only scripts/uat_engines.py, which skips
    # the id instead of reporting a 502. Valid at workspace level and as a
    # variant override. None means unset, so the runtime dict stays byte-equal
    # for every workspace that does not set it (same mechanism as `router`).
    stack_down_only: bool | None = None

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
    # True → an answer with no tool call in the whole turn is not delivered as is: the pipeline
    # asks once for a grounded answer, then delivers with a notice (router/tool_repeat.py).
    require_tool_before_answer: bool | None = None
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

    # C3 user-facing engine growth guard.
    engine: bool = False
    engine_reason: str | None = None

    @model_validator(mode="after")
    def _variant_modules_known(self) -> WorkspaceSpec:
        known = set(get_args(ModuleName))
        for name, cfg in self.variants.items():
            module = cfg.get("module") if isinstance(cfg, dict) else None
            if module is not None and module not in known:
                raise ValueError(f"variant {name!r}: unknown module {module!r}")
        return self


class WorkspaceAlias(BaseModel):
    to: str
    remove_after: date
    reason: str = Field(min_length=1)


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

    # C3 behavioural persona growth guard.
    persona_reason: str | None = None
    # role: instructions only, seeded as an Open WebUI slash prompt (`/slug `).
    # persona (default): seeded as an Open WebUI model preset, as before.
    delivery: Literal["persona", "role"] = "persona"


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
    host_native: bool = False
    launchd_label: str | None = None
    native_service: str | None = None  # scripts/native-mcp-service.sh selector
    compose_service: str | None = None

    @model_validator(mode="after")
    def _host_or_compose(self) -> McpServer:
        if self.host_native and not self.launchd_label:
            raise ValueError(f"mcp {self.id}: host_native requires launchd_label")
        if self.launchd_label and not self.host_native:
            raise ValueError(f"mcp {self.id}: launchd_label requires host_native")
        if self.launchd_label and not self.launchd_label.startswith("com.portal5."):
            raise ValueError(f"mcp {self.id}: launchd label must be com.portal5.*")
        if self.host_native and self.compose_service:
            raise ValueError(f"mcp {self.id}: host_native and compose_service are both set")
        return self


class ModuleToggle(BaseModel):
    enabled: bool


class HostJob(BaseModel):
    """A launchd job that has no mcp_fleet entry."""

    label: str
    module: ModuleName | Literal["platform"]
    port: int | None = None
    service: str | None = None

    @model_validator(mode="after")
    def _label_prefix(self) -> HostJob:
        if not self.label.startswith("com.portal5."):
            raise ValueError(f"host job label must be com.portal5.*: {self.label}")
        return self


class PortalConfig(BaseModel):
    """Top-level portal.yaml schema."""

    workspaces: dict[str, WorkspaceSpec]
    aliases: dict[str, WorkspaceAlias] = Field(default_factory=dict)
    mcp_fleet: list[McpServer]
    modules: dict[str, ModuleToggle] = Field(
        default_factory=dict,
        description="Per-module on/off. portal module enable/disable writes one line.",
    )
    orchestration_arm: dict[str, Any] = Field(default_factory=dict)
    host_jobs: list[HostJob] = Field(
        default_factory=list,
        description="Launchd jobs with no mcp_fleet entry. module platform is always on.",
    )
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

    @model_validator(mode="after")
    def _alias_targets_exist(self) -> PortalConfig:
        for alias_id, alias in self.aliases.items():
            if alias_id in self.workspaces:
                raise ValueError(f"Workspace alias {alias_id!r} conflicts with a workspace")
            engine_id, separator, variant = alias.to.partition("::")
            engine = self.workspaces.get(engine_id)
            if not separator or not variant or engine is None or variant not in engine.variants:
                raise ValueError(
                    f"Workspace alias {alias_id!r} targets unknown variant {alias.to!r}"
                )
        return self

    @model_validator(mode="after")
    def _known_module_keys(self) -> PortalConfig:
        known = set(get_args(ModuleName))
        unknown = sorted(name for name in self.modules if name not in known)
        if unknown:
            raise ValueError(f"Unknown modules in portal.yaml: {unknown}")
        return self

    @model_validator(mode="after")
    def _unique_launch_labels(self) -> PortalConfig:
        labels = [s.launchd_label for s in self.mcp_fleet if s.launchd_label]
        labels += [job.label for job in self.host_jobs]
        dupes = sorted({label for label in labels if labels.count(label) > 1})
        if dupes:
            raise ValueError(f"Duplicate launchd labels: {dupes}")
        fleet_ports = {s.port for s in self.mcp_fleet if s.port is not None}
        clash = sorted(job.port for job in self.host_jobs if job.port in fleet_ports)
        if clash:
            raise ValueError(f"host_jobs ports collide with mcp_fleet: {clash}")
        return self


# ── Loader ────────────────────────────────────────────────────────────────────

# Cache ambient loads by path and eval-env state; explicit bench loads are uncached.
_CONFIG_CACHE: dict[tuple[str, bool, bool], PortalConfig] = {}


def _bench_env_state() -> tuple[bool, bool]:
    """Return the two bench-related environment opt-ins."""
    truthy = ("true", "1", "yes")
    return (
        os.environ.get("PORTAL_BENCH_WORKSPACES", "").lower() in truthy,
        os.environ.get("PORTAL_ENABLE_EVAL", "").lower() in truthy,
    )


def _bench_env_opt_in() -> bool:
    """Whether the bench/WFE harness explicitly asks for the bench lanes."""
    return _bench_env_state()[0]


def _eval_enabled_raw(raw: dict[str, Any]) -> bool:
    """Return eval-module state from the raw portal config."""
    if os.environ.get("PORTAL_ENABLE_EVAL", "").lower() in ("true", "1", "yes"):
        return True
    state = (raw.get("modules") or {}).get("eval", {}).get("enabled")
    return bool(state)


def _bench_merge_requested(raw: dict[str, Any], include_bench: bool | None) -> bool:
    if include_bench is not None:
        return include_bench
    return _bench_env_opt_in() or _eval_enabled_raw(raw)


def load_bench_workspaces_raw(
    root: Path | None = None, *, path: Path | None = None
) -> dict[str, Any]:
    """Load the raw workspace mapping from the bench config file."""
    bench_path = path or (BENCH_YAML if root is None else root / "config" / "bench_workspaces.yaml")
    if not bench_path.is_file():
        return {}
    data = yaml.safe_load(bench_path.read_text()) or {}
    workspaces = data.get("workspaces") or {}
    if not isinstance(workspaces, dict):
        raise TypeError(
            f"{bench_path} `workspaces` must be a mapping of id -> spec, "
            f"got {type(workspaces).__name__}"
        )
    return workspaces


def load_portal_config(
    path: Path | None = None,
    *,
    _force_reload: bool = False,
    include_bench: bool | None = None,
) -> PortalConfig:
    """Load ``config/portal.yaml`` and return a validated :class:`PortalConfig`.

    Cached for process lifetime after the first successful load.  Pass
    ``_force_reload=True`` in tests that swap the YAML path.

    The ``OLLAMA_URL`` env var overrides the YAML value; ``OLLAMA_BASE_URL``
    is accepted as a deprecated alias and triggers a warning.

    """
    global _CONFIG_CACHE
    yaml_path = path or PORTAL_YAML
    if _CONFIG_CACHE and include_bench is None and not _force_reload:
        cached = _CONFIG_CACHE.get((str(yaml_path), *_bench_env_state()))
        if cached is not None:
            return cached

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

    if _bench_merge_requested(raw, include_bench):
        bench = load_bench_workspaces_raw(path=yaml_path.with_name("bench_workspaces.yaml"))
        overlap = sorted(set(bench) & set(raw.get("workspaces") or {}))
        if overlap:
            raise RuntimeError(
                f"bench_workspaces.yaml collides with portal.yaml workspaces: {overlap}"
            )
        raw["workspaces"] = {**(raw.get("workspaces") or {}), **bench}

    try:
        config = PortalConfig.model_validate(raw)
    except Exception as exc:
        raise RuntimeError(f"portal.yaml failed validation ({yaml_path}): {exc}") from exc

    if include_bench is None:
        _CONFIG_CACHE[(str(yaml_path), *_bench_env_state())] = config
    return config


# ── Derived-view helpers ──────────────────────────────────────────────────────

# Fields that exist only in portal.yaml and must NOT appear in the runtime
# WORKSPACES dict that the rest of the pipeline imports.
_OWUI_ONLY_FIELDS = frozenset(
    {"expose_to_owui", "enable_web_search", "owui_system_prompt", "engine", "engine_reason"}
)

# Schema-only fields consulted by resolve_workspace_variant() via
# load_portal_config() directly — never surfaced in the runtime dict itself.
_INTERNAL_ONLY_FIELDS = frozenset({"variants"})


def _eval_enabled() -> bool:
    """Return whether eval workspaces are enabled by config or the environment."""
    if _bench_env_opt_in() or os.environ.get("PORTAL_ENABLE_EVAL", "").lower() in (
        "true",
        "1",
        "yes",
    ):
        return True
    from portal.platform.wiki.adapters.modules import enabled_modules

    return "eval" in enabled_modules()


def variant_module(engine_module: str, variant: dict[str, Any]) -> str:
    """The variant's module, or the engine's when the variant does not declare one."""
    declared = variant.get("module") if isinstance(variant, dict) else None
    return str(declared) if declared else engine_module


def engine_tools(spec: WorkspaceSpec) -> list[str]:
    """Return only the tools declared on an engine."""
    return list(spec.tools)


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
        raw = spec.model_dump(
            exclude_none=True, exclude=set(_OWUI_ONLY_FIELDS | _INTERNAL_ONLY_FIELDS)
        )
        raw["tools"] = engine_tools(spec)
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
# Bench personas load only with the bench workspace catalog.
_BENCH_PERSONAS_DIR: Path = _PERSONAS_DIR / "bench"


def load_persona_map(
    personas_dir: Path | None = None,
    config: PortalConfig | None = None,
    include_bench: bool | None = None,
) -> dict[str, PersonaSpec]:
    """Return ``{slug: PersonaSpec}`` for every YAML under ``config/personas/``.

    Invalid files are logged at WARNING and skipped, and the skipped count is
    logged once at the end. Does not validate that every ``workspace_model``
    resolves — call ``validate_persona_parents`` for that gate.

    """
    directory = personas_dir or _PERSONAS_DIR
    if not directory.is_dir():
        logger.warning("Personas directory not found: %s", directory)
        return {}

    files = sorted(directory.glob("*.yaml"))
    bench_wanted = (
        include_bench if include_bench is not None else (_bench_env_opt_in() or _eval_enabled())
    )
    if bench_wanted and directory == _PERSONAS_DIR:
        files += sorted(_BENCH_PERSONAS_DIR.glob("*.yaml"))

    result: dict[str, PersonaSpec] = {}
    skipped = 0
    for yf in files:
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
            skipped += 1
            logger.warning("Failed to load persona %s: %s", yf.name, exc)
    if skipped:
        logger.warning("%d personas skipped", skipped)
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


def merge_workspace_variant(base: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    """Merge variant settings over the engine, including its tool whitelist."""
    return {**base, **variant}


def effective_workspace(workspaces: dict[str, Any], workspace_id: str) -> dict[str, Any]:
    """Return an engine's base settings merged with the selected variant."""
    base_id, _, variant = workspace_id.partition("::")
    base = dict(workspaces[base_id])
    return merge_workspace_variant(base, (base.get("variants") or {})[variant]) if variant else base
