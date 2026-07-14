"""Seed fact-deriving WHAT units — the handful of numbers that drift.

DESIGN_WIKI_GENERATION_LOOP_V1.md F1. Unlike seed_code's structural
subsystem summaries (scraped file lists), these units COMPUTE their body
from live config on every run — persona/workspace counts, the security
variant vocabulary, MCP fleet, model catalog, and (most importantly)
reachability-resolved model bindings. Re-running re-derives from current
HEAD and is idempotent: save_unit() overwrites by unit.id, so no churn
when nothing changed.

unit-fact-model-bindings is deliberately reachability-resolved (same
logic as scripts/persona_intent_audit.py check 5 / RUN_THIS's GATE 1) —
it reports what a workspace/persona actually SERVES, not what it claims,
so the wiki surfaces a "pinned but unservable" gap at derivation time
instead of by audit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from portal.platform.wiki.schema import KnowledgeUnit, SourceRef
from portal.platform.wiki.store import load_unit, save_unit

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _get_current_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()[:12]
    except Exception:
        return "unknown"


def _load_yaml(path: Path) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def _group_models(backends_cfg: dict) -> dict[str, set[str]]:
    """backend group name (e.g. "reasoning") -> set of model ids it declares."""
    groups: dict[str, set[str]] = {}
    for be in backends_cfg.get("backends", []):
        name = be.get("group") or (be.get("id") or be.get("name") or "").replace("ollama-", "")
        groups[name] = {m.get("id") if isinstance(m, dict) else m for m in be.get("models", [])}
    return groups


def _reachable(model: str, ws_groups: list[str], group_models: dict[str, set[str]]) -> bool:
    return any(model in group_models.get(g, ()) for g in ws_groups)


def _make_unit(
    unit_id: str,
    title: str,
    sources: list[SourceRef],
    body: str,
    tags: list[str],
    commit: str,
    confidence: str = "high",
) -> KnowledgeUnit:
    """Construct a fact-unit that only changes on disk when its BODY changes.

    Two idempotency traps, both fixed here:

    1. KnowledgeUnit.__post_init__ defaults created_at/updated_at to "now"
       for any instance that doesn't already carry them — building a fresh
       KnowledgeUnit on every derive call would bump both fields every
       single run even when the body is byte-identical.
    2. `commit` is "whatever HEAD is right now" at derive time, which is
       usually the PARENT of the commit-in-progress (pre-commit hooks run
       before the commit lands) — baking it into `sources[].commit` /
       `last_generated_commit` unconditionally means the unit file changes
       on literally every future commit forever, even with zero functional
       change, because HEAD always differs from the value last stamped.

    Fix: when the body is unchanged from what's stored, reuse the PRIOR
    unit's sources/commit/timestamps wholesale (a true no-op write) —
    `last_generated_commit` means "commit at which this fact last actually
    changed," not "commit at which this script last ran." Only when the
    body differs do sources/commit/updated_at advance to the current call's
    values.
    """
    import time

    prior = load_unit(unit_id)
    if prior and prior.body.strip() == body.strip():
        return KnowledgeUnit(
            id=unit_id,
            kind="what",
            title=title,
            sources=prior.sources,
            body=body,
            tags=tags,
            confidence=confidence,
            last_generated_commit=prior.last_generated_commit,
            created_at=prior.created_at,
            updated_at=prior.updated_at,
        )
    return KnowledgeUnit(
        id=unit_id,
        kind="what",
        title=title,
        sources=sources,
        body=body,
        tags=tags,
        confidence=confidence,
        last_generated_commit=commit,
        created_at=prior.created_at if prior else 0.0,
        updated_at=time.time() if prior else 0.0,
    )


def derive_persona_roster(commit: str, save: bool = True) -> KnowledgeUnit:
    """unit-fact-persona-roster — config/personas/*.yaml."""
    persona_files = sorted((_REPO_ROOT / "config" / "personas").glob("*.yaml"))
    rows = []
    for f in persona_files:
        p = _load_yaml(f)
        rows.append(
            (
                p.get("slug", f.stem),
                p.get("module", ""),
                p.get("workspace_model", ""),
                p.get("model_pin", "") or "",
            )
        )

    body_lines = [
        f"# Persona roster ({len(rows)} personas)",
        "",
        "| Slug | Module | Workspace | Model Pin |",
        "|---|---|---|---|",
    ]
    for slug, module, ws, pin in rows:
        body_lines.append(f"| `{slug}` | {module} | `{ws}` | {f'`{pin}`' if pin else '—'} |")

    sources = [SourceRef(type="code", path="config/personas/", commit=commit)]
    sources += [
        SourceRef(type="code", path=str(f.relative_to(_REPO_ROOT)), commit=commit)
        for f in persona_files[:5]
    ]
    unit = _make_unit(
        "unit-fact-persona-roster",
        f"{len(rows)} personas",
        sources,
        "\n".join(body_lines),
        ["fact", "personas"],
        commit,
    )
    if save:
        save_unit(unit)
    return unit


def derive_workspace_roster(commit: str, save: bool = True) -> KnowledgeUnit:
    """unit-fact-workspace-roster — config/portal.yaml."""
    portal_cfg = _load_yaml(_REPO_ROOT / "config" / "portal.yaml")
    ws = portal_cfg["workspaces"]
    prod = sorted((w, c) for w, c in ws.items() if (c or {}).get("module") != "eval")
    ev = sorted((w, c) for w, c in ws.items() if (c or {}).get("module") == "eval")

    body_lines = [
        f"# Workspace roster ({len(prod)} production, {len(ev)} eval, {len(ws)} total)",
        "",
        "## Production workspaces (acceptance/UAT scope, eval OFF)",
        "",
        "| Workspace | Module | Model Hint |",
        "|---|---|---|",
    ]
    for wid, c in prod:
        body_lines.append(
            f"| `{wid}` | {(c or {}).get('module', '')} | `{(c or {}).get('model_hint', '')}` |"
        )
    body_lines += ["", "## Eval/bench workspaces (need PORTAL_ENABLE_EVAL=1)", ""]
    for wid, _c in ev:
        body_lines.append(f"- `{wid}`")

    unit = _make_unit(
        "unit-fact-workspace-roster",
        f"{len(prod)} production + {len(ev)} eval workspaces",
        [SourceRef(type="code", path="config/portal.yaml", commit=commit)],
        "\n".join(body_lines),
        ["fact", "workspaces"],
        commit,
    )
    if save:
        save_unit(unit)
    return unit


def derive_security_variants(commit: str, save: bool = True) -> KnowledgeUnit:
    """unit-fact-security-variants — config/portal.yaml auto-security.variants."""
    portal_cfg = _load_yaml(_REPO_ROOT / "config" / "portal.yaml")
    variants = sorted((portal_cfg["workspaces"].get("auto-security") or {}).get("variants") or {})
    canonical = [f"auto-security::{v}" for v in variants]

    body_lines = [
        f"# Security canonical variants ({len(canonical)})",
        "",
        "sec-bench `--workspaces` targets, addressed as `auto-security::<variant>`:",
        "",
    ]
    body_lines += [f"- `{v}`" for v in canonical]

    unit = _make_unit(
        "unit-fact-security-variants",
        f"{len(canonical)} security canonical variants",
        [
            SourceRef(
                type="code",
                path="config/portal.yaml",
                commit=commit,
                section="workspaces.auto-security.variants",
            )
        ],
        "\n".join(body_lines),
        ["fact", "security"],
        commit,
    )
    if save:
        save_unit(unit)
    return unit


def derive_model_bindings(commit: str, save: bool = True) -> KnowledgeUnit:
    """unit-fact-model-bindings — backends.yaml + personas, reachability-resolved.

    Reports what a workspace/persona ACTUALLY serves (reachable via
    workspace_routing groups), not what it claims. A "claims X, serves Y"
    row is a live gap — this is the check that would have caught the
    phi4stemanalyst class of bug at derivation time.
    """
    backends_cfg = _load_yaml(_REPO_ROOT / "config" / "backends.yaml")
    portal_cfg = _load_yaml(_REPO_ROOT / "config" / "portal.yaml")
    group_models = _group_models(backends_cfg)
    ws_routing = backends_cfg.get("workspace_routing", {})
    workspaces = portal_cfg["workspaces"]

    body_lines = [
        "# Model bindings (reachability-resolved)",
        "",
        "What each production workspace/persona actually SERVES, not what it",
        "claims. A row marked GAP means the intended model is unreachable via",
        "the workspace's routing groups and silently falls back to the pool",
        "default.",
        "",
        "## Workspace model_hint reachability",
        "",
        "| Workspace | model_hint | Reachable |",
        "|---|---|---|",
    ]
    gaps: list[str] = []
    for wid, c in sorted(workspaces.items()):
        if (c or {}).get("module") == "eval":
            continue
        hint = (c or {}).get("model_hint")
        if not hint:
            continue
        ok = _reachable(hint, ws_routing.get(wid, []), group_models)
        body_lines.append(f"| `{wid}` | `{hint}` | {'yes' if ok else '**GAP**'} |")
        if not ok:
            gaps.append(f"workspace `{wid}` cannot reach its own model_hint `{hint}`")

    body_lines += [
        "",
        "## Persona model_pin reachability",
        "",
        "| Persona | Workspace | model_pin | Reachable |",
        "|---|---|---|---|",
    ]
    for f in sorted((_REPO_ROOT / "config" / "personas").glob("*.yaml")):
        p = _load_yaml(f)
        pin = p.get("model_pin")
        if not pin:
            continue
        ws = p.get("workspace_model")
        ws_cfg = workspaces.get(ws) or {}
        if ws_cfg.get("module") == "eval":
            continue
        ok = _reachable(pin, ws_routing.get(ws, []), group_models)
        body_lines.append(
            f"| `{p.get('slug', f.stem)}` | `{ws}` | `{pin}` | {'yes' if ok else '**GAP**'} |"
        )
        if not ok:
            gaps.append(
                f"persona `{p.get('slug', f.stem)}` model_pin `{pin}` unreachable from `{ws}`"
            )

    body_lines += ["", f"**{len(gaps)} reachability gap(s)**" + (":" if gaps else " — clean.")]
    body_lines += [f"- {g}" for g in gaps]

    unit = _make_unit(
        "unit-fact-model-bindings",
        f"model bindings — {len(gaps)} reachability gap(s)",
        [
            SourceRef(type="code", path="config/backends.yaml", commit=commit),
            SourceRef(type="code", path="config/portal.yaml", commit=commit),
            SourceRef(type="code", path="config/personas/", commit=commit),
        ],
        "\n".join(body_lines),
        ["fact", "model-bindings", "reachability"],
        commit,
        confidence="high" if not gaps else "low",
    )
    if save:
        save_unit(unit)
    return unit


def derive_mcp_fleet(commit: str, save: bool = True) -> KnowledgeUnit:
    """unit-fact-mcp-fleet — config/portal.yaml mcp_fleet."""
    portal_cfg = _load_yaml(_REPO_ROOT / "config" / "portal.yaml")
    fleet = portal_cfg.get("mcp_fleet", [])

    body_lines = [
        f"# MCP fleet ({len(fleet)} servers)",
        "",
        "| ID | Name | Port |",
        "|---|---|---|",
    ]
    for svc in sorted(fleet, key=lambda s: s.get("port", 0)):
        body_lines.append(
            f"| `{svc.get('id', '')}` | {svc.get('name', '')} | {svc.get('port', '')} |"
        )

    unit = _make_unit(
        "unit-fact-mcp-fleet",
        f"{len(fleet)} MCP fleet servers",
        [SourceRef(type="code", path="config/portal.yaml", commit=commit, section="mcp_fleet")],
        "\n".join(body_lines),
        ["fact", "mcp"],
        commit,
    )
    if save:
        save_unit(unit)
    return unit


def derive_model_catalog(commit: str, save: bool = True) -> KnowledgeUnit:
    """unit-fact-model-catalog — config/backends.yaml, by backend group."""
    backends_cfg = _load_yaml(_REPO_ROOT / "config" / "backends.yaml")
    group_models = _group_models(backends_cfg)
    total = sum(len(m) for m in group_models.values())

    body_lines = [
        f"# Model catalog ({total} model ids across {len(group_models)} backend groups)",
        "",
    ]
    for group in sorted(group_models):
        models = sorted(group_models[group])
        body_lines.append(f"## {group} ({len(models)})")
        body_lines.append("")
        body_lines += [f"- `{m}`" for m in models]
        body_lines.append("")

    unit = _make_unit(
        "unit-fact-model-catalog",
        f"{total} model ids, {len(group_models)} backend groups",
        [SourceRef(type="code", path="config/backends.yaml", commit=commit)],
        "\n".join(body_lines),
        ["fact", "models"],
        commit,
    )
    if save:
        save_unit(unit)
    return unit


def _tool_names_in_file(path) -> list[str]:
    """Tool names registered in one MCP server file.

    Two registration patterns are in use across the fleet: `@mcp.tool()` immediately
    above a `def`/`async def` (most servers), and `@mcp.custom_route("/tools/<name>", ...)`
    with no matching `@mcp.tool()` at all (memory_mcp.py, rag_mcp.py, web_search_mcp.py).
    Both are real, live registrations — treating the second pattern as "unregistered" would
    falsely flag working tools as bugs, exactly what this deriver must never do.
    """
    import re as _re

    lines = path.read_text(encoding="utf-8").splitlines()
    names: list[str] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("@mcp.tool()"):
            for j in range(i + 1, min(i + 4, len(lines))):
                m = _re.match(r"\s*(?:async )?def (\w+)\(", lines[j])
                if m:
                    names.append(m.group(1))
                    break
        else:
            m = _re.match(r'@mcp\.custom_route\("/tools/(\w+)"', s)
            if m:
                names.append(m.group(1))
    return names


def _mcp_registry() -> dict[str, list[str]]:
    """server id -> sorted registered tool names, parsed from the server file.

    Resolves config/portal.yaml mcp_fleet -> portal/modules/<module>/tools/<id>_mcp.py,
    falling back to portal/platform/<module>/<id>_mcp.py, then to any portal/platform/*/
    subdirectory whose *_mcp.py filename matches the id (cross-cutting servers declare
    `module: platform` generically — e.g. `memory` lives under portal/platform/memory/ and
    `pipeline` under portal/platform/mcp_host/, neither named after the id/module directly).
    Servers whose file cannot be resolved get an empty list and are marked unresolved by the
    caller — never faked.
    """
    portal_cfg = _load_yaml(_REPO_ROOT / "config" / "portal.yaml")
    reg: dict[str, list[str]] = {}
    for svc in portal_cfg.get("mcp_fleet", []):
        sid = svc.get("id", "")
        module = svc.get("module", "")
        if not sid or not module:
            continue
        candidates = (f"{sid}_mcp.py", f"{sid.rstrip('s')}_mcp.py", f"{sid}s_mcp.py")
        candidate_dirs = [
            _REPO_ROOT / "portal" / "modules" / module / "tools",
            _REPO_ROOT / "portal" / "platform" / module,
        ]
        f = None
        for tools_dir in candidate_dirs:
            for cand in candidates:
                if (tools_dir / cand).exists():
                    f = tools_dir / cand
                    break
            if f is None and tools_dir.exists():
                allfiles = list(tools_dir.glob("*_mcp.py"))
                f = (
                    allfiles[0] if len(allfiles) == 1 else None
                )  # single-server dir only; else unresolved
            if f is not None:
                break
        if f is None:
            for cand in candidates:
                hits = list((_REPO_ROOT / "portal" / "platform").glob(f"*/{cand}"))
                if hits:
                    f = hits[0]
                    break
        tools = _tool_names_in_file(f) if f and f.exists() else []
        reg[sid] = sorted(set(tools))
    return reg


def _all_registered_tools() -> set[str]:
    """Union of every registered tool name across all MCP servers (module + cross-cutting).

    Independent of the fleet-id -> file mapping (which can miss on name variance), so the
    authorized-but-unregistered check is correct even when a server file can't be attributed
    to a specific fleet id. See `_tool_names_in_file` for the two registration patterns matched.
    """
    names: set[str] = set()
    globs = [
        (_REPO_ROOT / "portal" / "modules").glob("*/tools/*_mcp.py"),
        (_REPO_ROOT / "portal" / "platform").glob("*/*_mcp.py"),
    ]
    for g in globs:
        for f in g:
            names.update(_tool_names_in_file(f))
    return names


def derive_tool_registry(commit: str, save: bool = True) -> KnowledgeUnit:
    """unit-fact-tool-registry — registered tool defs per MCP server."""
    reg = _mcp_registry()
    total = sum(len(v) for v in reg.values())
    body_lines = [
        f"# MCP tool registry ({total} tools across {len(reg)} servers)",
        "",
        "What each MCP server actually registers — `@mcp.tool()` defs, or "
        '`@mcp.custom_route("/tools/<name>")` for servers that only expose that route form '
        "(memory, rag, web-search). Join with `unit-fact-tool-authorizations` to spot "
        "reachability gaps.",
        "",
        "| Server | Registered tools |",
        "|---|---|",
    ]
    for sid in sorted(reg):
        cell = (
            ", ".join(f"`{t}`" for t in reg[sid])
            if reg[sid]
            else "_(unresolved — server file not found)_"
        )
        body_lines.append(f"| `{sid}` | {cell} |")
    unit = _make_unit(
        "unit-fact-tool-registry",
        f"{total} MCP tools across {len(reg)} servers",
        [SourceRef(type="code", path="portal/modules/*/tools/*_mcp.py", commit=commit)],
        "\n".join(body_lines),
        ["fact", "tools", "mcp"],
        commit,
    )
    if save:
        save_unit(unit)
    return unit


def derive_tool_authorizations(commit: str, save: bool = True) -> KnowledgeUnit:
    """unit-fact-tool-authorizations — per-workspace tools: whitelist + reachability flag."""
    portal_cfg = _load_yaml(_REPO_ROOT / "config" / "portal.yaml")
    ws = portal_cfg["workspaces"]
    known = _all_registered_tools()
    prod = sorted((w, c) for w, c in ws.items() if (c or {}).get("module") != "eval")
    body_lines = [
        "# Tool authorizations (per-workspace `tools:` whitelist)",
        "",
        "The pipeline strips any tool a workspace does not authorize "
        "(metric `portal5_tool_workspace_strip_total`). A trailing `!` marks an authorized "
        "tool with no matching `@mcp.tool()` in the registry (see `unit-fact-tool-registry`).",
        "",
        "| Workspace | Module | Authorized tools |",
        "|---|---|---|",
    ]
    for wid, c in prod:
        c = c or {}
        tools = c.get("tools") or []
        if not tools:
            cell = "_(none)_"
        else:
            cell = ", ".join((f"`{t}`" if t in known else f"`{t}`!") for t in tools)
        body_lines.append(f"| `{wid}` | {c.get('module', '')} | {cell} |")
    unit = _make_unit(
        "unit-fact-tool-authorizations",
        f"tool authorizations for {len(prod)} production workspaces",
        [
            SourceRef(
                type="code", path="config/portal.yaml", commit=commit, section="workspaces[].tools"
            )
        ],
        "\n".join(body_lines),
        ["fact", "tools", "workspaces"],
        commit,
    )
    if save:
        save_unit(unit)
    return unit


# ── Media backend memory budget (Slice 7, TASK_VRAM_ADMISSION_V1) ───────────────
# No historical per-model GB table exists for ComfyUI/media backends — the retired
# MLX-proxy admission gate's MODEL_MEMORY dict (commit 91f13a9) only covered the old
# text/VLM inference tier (Qwen/Llama/Gemma), and config/MODEL_CATALOG.md is GGUF/Ollama
# only. These figures are session-observed (Slice P media bring-up, 2026-07-14): Flux
# summed from on-disk checkpoint+CLIP+VAE sizes, Wan2.1-NSFW-14B likewise (the exact
# combination that drove swap to 66.7GB/67.6GB and locked the system), SDXL from its
# single-file size, MusicGen from music_mcp.py's own list_music_models RAM figures.
# Operator-confirmed as the basis pending real vendor-spec numbers (see AskUserQuestion
# in that session — GATE: HISTORY had no applicable historical table to recover).
MEDIA_MODEL_MEMORY_GB: dict[str, float] = {
    "comfyui:flux-schnell": 27.2,  # checkpoint 22 + vae 0.32 + clip_l 0.235 + t5xxl_fp8 4.6
    "comfyui:sdxl": 6.5,  # single self-contained checkpoint
    # Corrected 38.2 -> 55.0 after a second live lockup during this same session's
    # verification test: a *tiny* job (9 frames, 5 steps) still crashed free RAM from
    # ~45GB to ~60MB. Static weight size (unet 27 + clip 11 + vae 0.24 = 38.2GB) does
    # not capture real peak usage — diffusion activation/buffer overhead pushes this
    # backend close to the entire 64GB unified pool regardless of frame count.
    "video:wan21-nsfw": 55.0,
    "music:small": 2.0,
    "music:medium": 6.0,
    "music:large": 12.0,
}


def derive_media_memory_budget(commit: str, save: bool = True) -> KnowledgeUnit:
    """unit-fact-media-memory-budget — per-media-backend GB estimates for VRAM admission."""
    body_lines = [
        "# Media backend memory budget (Tier 0, cross-engine VRAM admission)",
        "",
        "Session-observed peak unified-memory estimates per media backend/model — no "
        "historical per-model table exists for ComfyUI/media (the retired MLX-proxy admission "
        "gate only covered the text/VLM inference tier). Used by the Tier 1 pre-flight admission "
        "check (`portal/modules/media/tools/_admission.py`) to refuse a job before it OOMs "
        "instead of after.",
        "",
        "| Backend:model | Estimated GB |",
        "|---|---|",
    ]
    for key in sorted(MEDIA_MODEL_MEMORY_GB):
        body_lines.append(f"| `{key}` | {MEDIA_MODEL_MEMORY_GB[key]} |")
    unit = _make_unit(
        "unit-fact-media-memory-budget",
        f"memory budget for {len(MEDIA_MODEL_MEMORY_GB)} media backend/model combinations",
        [
            SourceRef(
                type="code",
                path="portal/platform/wiki/adapters/seed_facts.py",
                commit=commit,
                section="MEDIA_MODEL_MEMORY_GB",
            )
        ],
        "\n".join(body_lines),
        ["fact", "media", "memory"],
        commit,
    )
    if save:
        save_unit(unit)
    return unit


_DERIVERS = (
    derive_persona_roster,
    derive_workspace_roster,
    derive_security_variants,
    derive_model_bindings,
    derive_mcp_fleet,
    derive_model_catalog,
    derive_tool_authorizations,
    derive_tool_registry,
    derive_media_memory_budget,
)


def seed_facts(commit: str | None = None) -> list[KnowledgeUnit]:
    """Derive/re-derive all fact units from current config. Idempotent."""
    commit = commit or _get_current_commit()
    return [deriver(commit) for deriver in _DERIVERS]


def check_facts_current(commit: str | None = None) -> list[str]:
    """Read-only: which fact units would change if re-derived right now.

    Does NOT write anything — derives each unit in memory (save=False) and
    diffs its body against what's stored on disk. Used by the validate
    gate to catch a forgotten `sync-config` before commit.
    """
    from portal.platform.wiki.store import load_unit

    commit = commit or _get_current_commit()
    drifted: list[str] = []
    for deriver in _DERIVERS:
        fresh = deriver(commit, save=False)
        stored = load_unit(fresh.id)
        # KnowledgeUnit.from_markdown() strips the body on load (schema.py),
        # so a save/load round-trip normalizes leading/trailing whitespace —
        # compare stripped to match that normalization, not raw equality.
        if stored is None or stored.body.strip() != fresh.body.strip():
            drifted.append(fresh.id)
    return drifted
