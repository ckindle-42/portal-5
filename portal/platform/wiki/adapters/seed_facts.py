"""Compute current fact units from config, code, and claims probes."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, cast

import yaml

from portal.platform.inference.config import load_bench_workspaces_raw
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef

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


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as fh:
        return cast(dict[str, Any], yaml.safe_load(fh))


def _group_models(backends_cfg: dict[str, Any]) -> dict[str, set[str]]:
    """backend group name (e.g. "reasoning") -> set of model ids it declares.

    Multiple backend entries can share one group name (P5-FUT-013 B2: an
    oMLX entry and an Ollama entry both declaring `group: coding`, engine
    preference expressed via `priority:` rather than a separate group) — a
    plain assignment here would let the later entry silently clobber the
    earlier one's models instead of the group representing everything
    reachable through it. Union across entries instead.
    """
    groups: dict[str, set[str]] = {}
    for be in backends_cfg.get("backends", []):
        name = be.get("group") or (be.get("id") or be.get("name") or "").replace("ollama-", "")
        model_ids = (m.get("id") if isinstance(m, dict) else m for m in be.get("models", []))
        groups.setdefault(name, set()).update(cast(Iterable[str], model_ids))
    return groups


def _reachable(model: str, ws_groups: list[str], group_models: dict[str, set[str]]) -> bool:
    return any(model in group_models.get(g, ()) for g in ws_groups)


def _make_unit(
    unit_id: str,
    title: str,
    sources: list[SourceRef],
    body: str,
    tags: list[str],
    confidence: str = "high",
    why: str = "",
    claims: list[dict[str, Any]] | None = None,
) -> KnowledgeUnit:
    """Construct an in-memory fact unit from live sources."""
    if why:
        body = body.rstrip() + "\n\n## Why\n\n" + why.strip()
    return KnowledgeUnit(
        id=unit_id,
        kind="what",
        title=title,
        sources=sources,
        body=body,
        tags=tags,
        confidence=confidence,
        claims=claims or [],
    )


def derive_persona_roster(commit: str) -> KnowledgeUnit:
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
        why=(
            "The roster is derived from the persona YAML files under "
            "`config/personas/`, one per specialist, so the count and the "
            "slug/module/workspace bindings always reflect what the pipeline "
            "can actually route to. Personas are seeded into Open WebUI as model "
            "presets by the same files, so the wiki roster and the served roster "
            "cannot drift apart."
        ),
        claims=[
            {
                "probe": "personas.count",
                "pattern": "Persona roster ({value} personas)",
            }
        ],
    )
    return unit


def derive_workspace_roster(commit: str) -> KnowledgeUnit:
    """unit-fact-workspace-roster — config/portal.yaml + bench_workspaces.yaml."""
    portal_cfg = _load_yaml(_REPO_ROOT / "config" / "portal.yaml")
    # Bench lanes moved to their own file (C step 1); the roster still lists them.
    portal_cfg["workspaces"] = {
        **(portal_cfg.get("workspaces") or {}),
        **load_bench_workspaces_raw(_REPO_ROOT),
    }
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
        [
            SourceRef(type="code", path="config/portal.yaml", commit=commit),
            SourceRef(type="code", path="config/bench_workspaces.yaml", commit=commit),
        ],
        "\n".join(body_lines),
        ["fact", "workspaces"],
        why=(
            "The roster is the workspace mapping in `config/portal.yaml` plus the "
            "bench lanes in `config/bench_workspaces.yaml`, split "
            "into the production workspaces that acceptance/UAT exercises and the "
            "eval/bench workspaces gated behind `PORTAL_ENABLE_EVAL=1`. The counts "
            "and the per-workspace model hints come straight from those files, so the "
            "roster cannot disagree with what routing serves."
        ),
        claims=[
            {
                "probe": "workspaces.total",
                "pattern": "{value} total)",
            }
        ],
    )
    return unit


def derive_security_variants(commit: str) -> KnowledgeUnit:
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
        why=(
            "The canonical variant set is the `variants` map on the "
            "`auto-security` workspace in `config/portal.yaml`. Each entry is an "
            "`auto-security::<variant>` id that `sec-bench --workspaces` targets; "
            "the pipeline resolves the variant to a model pool the same way a "
            "`?variant=` hint on any workspace does. Deriving the list from config "
            "keeps the documented target set and the live routing surface aligned."
        ),
    )
    return unit


def derive_model_bindings(commit: str) -> KnowledgeUnit:
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
        confidence="high" if not gaps else "low",
        why=(
            "Model bindings are the reachability-resolved view of what each "
            "workspace `model_hint` and persona `model_pin` actually serve: a hint "
            "is reachable only when the workspace's routing groups in "
            "`config/backends.yaml` contain the model. The gap count is the live "
            "measure of how many bindings silently fall back to the pool default, "
            "and is regenerated from the same config the router reads."
        ),
    )
    return unit


def derive_mcp_fleet(commit: str) -> KnowledgeUnit:
    """unit-fact-mcp-fleet — config/portal.yaml mcp_fleet + live .mcp.json count."""
    import json

    portal_cfg = _load_yaml(_REPO_ROOT / "config" / "portal.yaml")
    fleet = portal_cfg.get("mcp_fleet", [])
    mcp_json_path = _REPO_ROOT / ".mcp.json"
    ide_count = (
        len((json.loads(mcp_json_path.read_text(encoding="utf-8"))).get("mcpServers") or {})
        if mcp_json_path.is_file()
        else 0
    )

    body_lines = [
        f"# MCP fleet ({len(fleet)} servers, {ide_count} IDE-exposed in .mcp.json)",
        "",
        "| ID | Name | Port | Module |",
        "|---|---|---|---|",
    ]
    for svc in sorted(fleet, key=lambda s: s.get("port", 0)):
        body_lines.append(
            f"| `{svc.get('id', '')}` | {svc.get('name', '')} | {svc.get('port', '')} | {svc.get('module', '')} |"
        )

    unit = _make_unit(
        "unit-fact-mcp-fleet",
        f"{len(fleet)} MCP fleet servers ({ide_count} in .mcp.json)",
        [
            SourceRef(type="code", path="config/portal.yaml", commit=commit, section="mcp_fleet"),
            SourceRef(type="code", path=".mcp.json", commit=commit),
        ],
        "\n".join(body_lines),
        ["fact", "mcp"],
        why=(
            "The fleet table is the `mcp_fleet` list in `config/portal.yaml`, the "
            "single source for every MCP tool server the pipeline can dispatch to. "
            "Each entry carries the server id, display name, module, and reserved port, "
            "and `.mcp.json` records the subset currently launched and exposed to IDEs."
        ),
        claims=[
            {
                "probe": "mcp.fleet.entries",
                "pattern": "MCP fleet ({value} servers",
            },
            {
                "probe": "mcpjson.servers",
                "pattern": "{value} IDE-exposed in .mcp.json)",
            },
        ],
    )
    return unit


def derive_module_states(commit: str) -> KnowledgeUnit:
    """unit-fact-module-states — live module enable states from config/modules.generated.yaml + portal.yaml."""
    from portal.platform.wiki.adapters.modules import ALL_MODULES, DEFAULT_ENABLED_MODULES

    portal_cfg = _load_yaml(_REPO_ROOT / "config" / "portal.yaml")
    gen_path = _REPO_ROOT / "config" / "modules.generated.yaml"
    gen_data = _load_yaml(gen_path) if gen_path.is_file() else {}
    gen_mods = gen_data.get("modules") or {}

    ws_by_mod: dict[str, list[str]] = {m: [] for m in ALL_MODULES}
    for wid, spec in (portal_cfg.get("workspaces") or {}).items():
        if isinstance(spec, dict) and spec.get("module"):
            ws_by_mod.setdefault(str(spec["module"]), []).append(str(wid))

    mcp_by_mod: dict[str, list[str]] = {m: [] for m in ALL_MODULES}
    for svc in portal_cfg.get("mcp_fleet") or []:
        if isinstance(svc, dict) and svc.get("module") and svc.get("id"):
            mcp_by_mod.setdefault(str(svc["module"]), []).append(str(svc["id"]))

    enabled_count = 0
    rows: list[str] = []
    for mod in sorted(ALL_MODULES):
        entry = gen_mods.get(mod)
        is_on = (
            bool(entry.get("enabled"))
            if isinstance(entry, dict) and "enabled" in entry
            else mod in DEFAULT_ENABLED_MODULES
        )
        if is_on:
            enabled_count += 1
        default_posture = "on" if mod in DEFAULT_ENABLED_MODULES else "off"
        wss = ", ".join(f"`{w}`" for w in sorted(ws_by_mod.get(mod, ()))) or "—"
        mcps = ", ".join(f"`{m}`" for m in sorted(mcp_by_mod.get(mod, ()))) or "—"
        rows.append(
            f"| `{mod}` | {'enabled' if is_on else 'disabled'} | {default_posture} | {wss} | {mcps} |"
        )

    body_lines = [
        f"# Module states ({enabled_count} modules enabled of {len(ALL_MODULES)} modules total)",
        "",
        "Live module enablement from `config/portal.yaml` (`modules.<name>.enabled`) / "
        "`config/modules.generated.yaml`. Toggle with `portal module enable|disable <name> --yes`.",
        "",
        "| Module | State | Default | Workspaces | MCP servers |",
        "|---|---|---|---|---|",
        *rows,
    ]
    return _make_unit(
        "unit-fact-module-states",
        f"{enabled_count}/{len(ALL_MODULES)} modules enabled",
        [
            SourceRef(type="code", path="config/portal.yaml", commit=commit, section="modules"),
            SourceRef(type="code", path="config/modules.generated.yaml", commit=commit),
            SourceRef(type="code", path="portal/platform/wiki/adapters/modules.py", commit=commit),
        ],
        "\n".join(body_lines),
        ["fact", "modules"],
        why=(
            "Module enable state lives in `config/portal.yaml` and its rendered snapshot "
            "`config/modules.generated.yaml`, never in authored `unit-module-*` prose. "
            "Computing this table on demand lets operators toggle modules without editing "
            "any canonical wiki unit."
        ),
        claims=[
            {"probe": "modules.enabled.count", "pattern": "{value} modules enabled"},
            {"probe": "modules.total", "pattern": "{value} modules total"},
        ],
    )


def derive_model_catalog(commit: str) -> KnowledgeUnit:
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
        why=(
            "The catalog groups every model id registered in "
            "`config/backends.yaml` by its routing group, which is the same "
            "grouping `workspace_routing` uses to resolve which backends a "
            "workspace can draw from. Deriving the catalog from the backend file "
            "keeps the documented model inventory and the actually-served pool "
            "identical."
        ),
        claims=[
            {
                "probe": "backends.groups.count",
                "pattern": "{value} backend groups)",
            }
        ],
    )
    return unit


def _tool_names_in_file(path: Path) -> list[str]:
    """Tool names registered in one MCP server file.

    Two registration patterns are in use across the fleet: `@mcp.tool()` immediately
    above a `def`/`async def` (most servers), and `@mcp.custom_route("/tools/<name>", ...)`
    with no matching `@mcp.tool()` at all (memory_mcp.py, rag_mcp.py).
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


def derive_tool_registry(commit: str) -> KnowledgeUnit:
    """unit-fact-tool-registry — registered tool defs per MCP server."""
    reg = _mcp_registry()
    total = sum(len(v) for v in reg.values())
    body_lines = [
        "# MCP tool registry",
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
        why=(
            "The registry is parsed directly from the MCP server source files: "
            '`@mcp.tool()` decorated functions, or `@mcp.custom_route("/tools/<name>")` '
            "registrations for servers that only expose that route form. Joining it with "
            "the per-workspace authorizations unit exposes which authorized tools are "
            "unreachable because no server registers them."
        ),
    )
    return unit


def derive_tool_authorizations(commit: str) -> KnowledgeUnit:
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
        why=(
            "The authorizations table is the per-workspace `tools:` whitelist in "
            "`config/portal.yaml`, which is exactly what the pipeline enforces at "
            "dispatch time. A trailing `!` marks an authorized tool with no matching "
            "registration in `unit-fact-tool-registry`, so the table doubles as a "
            "reachability check between what a workspace is allowed to call and what "
            "any MCP server actually exposes."
        ),
    )
    return unit


# ── Media backend memory budget (Slice 7, TASK_VRAM_ADMISSION_V1) ───────────────
# Session-observed peak unified-memory figures per media backend/model, consumed by
# the Tier-1 admission check in portal/modules/media/tools/_admission.py to refuse a
# job before it OOMs the host. Music XL-Turbo is a research estimate; the music
# fallback and image/video figures are measured MLX peaks (quantize 8 + --low-ram /
# block streaming) from TASK_IMAGE_VIDEO_OVERHAUL_V1.
MEDIA_MODEL_MEMORY_GB: dict[str, float] = {
    # Measured live: MiniMax-Music3-MLX 60s/30-step, vm_stat sampled peak working set.
    # Raw peak only — admit() adds MEMORY_HEADROOM_GB on top (every other entry here
    # is likewise a raw size, not a headroom-inclusive figure). Was 27.0 with 4GB of
    # headroom double-counted, which false-refused real 22GB jobs on this 64GB host.
    # Unified music MCP: XL-Turbo is a research estimate (not a live sample);
    # the 8-bit MiniMax-Music3 fallback carries main's live MiniMax-Music3-MLX
    # measurement (same family, vm_stat sampled peak working set).
    "music:acestep-xl-turbo": 16.0,  # plan: 12–18 GB quantized XL-turbo peak
    "music:minimax3-8bit": 22.0,  # measured live (main): sampled delta 22.02GiB, rounded down to the GiB
    # MLX-native image generation (MFLUX / mflux-generate-* CLI, host MLX layer) —
    # keys mirror portal/modules/media/tools/_admission.py exactly; keep in sync.
    "mflux:schnell": 15.0,
    "mflux:dev": 16.0,
    "mflux:flux2-klein": 18.0,  # measured 17.95 peak MLX, flux2-klein-4b q8 + --low-ram
    "mflux:flux3-klein": 23.0,  # upstream q8 peak 22.8GB @1024²; not measured here
    "mflux:z-image": 30.0,  # measured 26.83GB peak MLX, z-image-turbo q8 + --low-ram, 8 steps 768px
    "mflux:qwen-image": 40.0,  # measured 36.82GB peak MLX, q8 + --low-ram (retired tag)
    "mflux:qwen-image-edit": 42.0,  # same text encoder + edit transformer (retired tag)
    "mflux:qwen-2.1": 26.0,  # reasoned: 17.5GB bf16 text encoder + q8 transformer (see _admission.py)
    # MLX-native video generation (ltx-2-mlx CLI, host MLX layer) — LTX-2.5
    # distilled, --low-ram. Measured live in the 2026-10-28 LTX-2.3 vs 2.5 A/B.
    # Size-aware buckets mirror _admission.py: -512 measured, -704 estimated
    # from the pixel-area scaling; wan2.2-5b is the mlx-video fallback (sourced
    # 18-23GB Q8 weights, peak unmeasured).
    "video_mlx:ltx-2.5-q4": 18.0,  # measured 15.8GiB peak footprint, --distilled --low-ram, 512x320 97fr (2026-10-28)
    "video_mlx:ltx-2.5-q4-512": 18.0,  # same measurement, the 512x320 (or smaller) admission bucket
    "video_mlx:ltx-2.5-q4-704": 25.0,  # estimated, 704x480 97fr (unmeasured — scaled from the measured 512x320 peak)
    "video_mlx:wan2.2-5b": 23.0,
}


def derive_media_memory_budget(commit: str) -> KnowledgeUnit:
    """unit-fact-media-memory-budget — per-media-backend GB estimates for VRAM admission."""
    body_lines = [
        "# Media backend memory budget (Tier 0, cross-engine VRAM admission)",
        "",
        "Session-observed peak unified-memory estimates per media backend/model. Used by "
        "the Tier 1 pre-flight admission check (`portal/modules/media/tools/_admission.py`) "
        "to refuse a job before it OOMs instead of after.",
        "",
        "Image is `mflux:*` (MLX-native FLUX, host layer), video is `video_mlx:*` "
        "(ltx-2-mlx, host layer), music is `music:*`. Peaks are measured MLX "
        "figures where marked, or sourced/reasoned bounds (see comments) until a "
        "local measurement replaces them.",
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
        why=(
            "The budget is the `MEDIA_MODEL_MEMORY_GB` table in this seeder, the "
            "session-observed peak unified-memory estimate the Tier-1 admission "
            "check in `_admission.py` consults to refuse a media job before it "
            "OOMs. Keeping it here rather than in a runtime config makes the "
            "numbers part of the reviewed, versioned wiki instead of an "
            "unreviewed setting."
        ),
    )
    return unit


def derive_doc_migration_coverage(commit: str) -> KnowledgeUnit:
    """unit-fact-doc-migration-coverage — render_report() numbers from live state."""
    from portal.platform.wiki.render import render_report

    report = render_report(_REPO_ROOT)
    migrated = report["migrated"]
    unmigrated = report["unmigrated"]
    total = len(migrated) + len(unmigrated)
    pct = report["coverage_pct"]
    blocks = report["blocks_total"]

    body_lines = [
        f"# Doc migration coverage ({len(migrated)}/{total} docs migrated, {pct}%)",
        "",
        f"Total generated blocks across migrated docs: {blocks}",
        "",
        "## Migrated docs (content-hash gate only)",
        "",
    ]
    body_lines += [f"- `{d}`" for d in migrated]
    body_lines += ["", "## Unmigrated docs", ""]
    body_lines += [f"- `{d}`" for d in unmigrated]

    unit = _make_unit(
        "unit-fact-doc-migration-coverage",
        f"{len(migrated)}/{total} docs migrated ({pct}%)",
        [
            SourceRef(
                type="code",
                path="portal/platform/wiki/render.py",
                commit=commit,
                section="render_report",
            )
        ],
        "\n".join(body_lines),
        ["fact", "wiki", "migration"],
        why=(
            "The migration numbers come from `render_report()` in "
            "`portal/platform/wiki/render.py`, which classifies every Tier-1 doc "
            "as migrated, unmigrated, or gamed and counts the generated blocks. "
            "Deriving the coverage figure from that same function keeps the "
            "documented migration state and the one the renderer actually computes "
            "identical."
        ),
    )
    return unit


def derive_capability_rollup(commit: str) -> KnowledgeUnit:
    """unit-readme-capability-rollup — one derived headline count by kind, every
    figure bound to a probe so BS fails the moment one drifts (Rule 12)."""
    from portal.platform.wiki.claims import probe

    root = _REPO_ROOT
    mods_on = probe("modules.enabled.count", root)
    mods_all = probe("modules.total", root)
    ws_func = probe("workspaces.functional", root)
    ws_bench = probe("workspaces.bench", root)
    ws_all = probe("workspaces.total", root)
    personas = probe("personas.count", root)
    fleet = probe("mcp.fleet.entries", root)

    body = "\n".join(
        [
            "Portal 5 is one platform assembled from a small set of switchable",
            "parts. The headline figures below are derived from config on every",
            "seed, never hand-written.",
            "",
            "| Kind | Count | Source |",
            "|---|---|---|",
            f"| Modules | {mods_on} modules enabled of {mods_all} modules total | `config/modules.generated.yaml` |",
            f"| Functional workspaces | {ws_func} | `config/portal.yaml` `workspaces` |",
            f"| Benchmark workspaces | {ws_bench} | `config/portal.yaml` `workspaces` (eval module) |",
            f"| Workspaces total | {ws_all} | `config/portal.yaml` `workspaces` |",
            f"| Personas | {personas} | `config/personas/` |",
            f"| MCP tool servers | {fleet} | `config/portal.yaml` `mcp_fleet` |",
            "",
            f"That is {mods_on} modules enabled of {mods_all} modules total, "
            f"{ws_func} functional workspaces ({ws_bench} benchmark workspaces, "
            f"{ws_all} workspaces total), {personas} personas and {fleet} MCP "
            "tool servers — plus the Telegram and Slack channels, which carry no"
            " count of their own.",
        ]
    )

    sources = [
        SourceRef(type="code", path="config/portal.yaml", commit=commit, section="workspaces"),
        SourceRef(type="code", path="config/portal.yaml", commit=commit, section="mcp_fleet"),
        SourceRef(type="code", path="config/personas/", commit=commit),
        SourceRef(type="code", path="config/modules.generated.yaml", commit=commit),
    ]
    unit = _make_unit(
        "unit-readme-capability-rollup",
        "Portal 5 capability rollup",
        sources,
        body,
        ["fact", "readme", "rollup"],
        why=(
            "A first-time reader needs one number before they need eighty-one, "
            "so the README opens its capability section on a single rollup. It "
            "has to be derived rather than typed because every figure here moves "
            "between releases as modules, workspaces and personas are added or "
            "retired, and a README that quotes a stale count is the fastest way "
            "to lose a new reader's trust in the rest of the page."
        ),
        claims=[
            {"probe": "modules.enabled.count", "pattern": "{value} modules enabled"},
            {"probe": "modules.total", "pattern": "{value} modules total"},
            {"probe": "workspaces.functional", "pattern": "{value} functional workspaces"},
            {"probe": "workspaces.bench", "pattern": "{value} benchmark workspaces"},
            {"probe": "workspaces.total", "pattern": "{value} workspaces total"},
            {"probe": "personas.count", "pattern": "{value} personas"},
            {"probe": "mcp.fleet.entries", "pattern": "{value} MCP tool servers"},
        ],
    )
    return unit


def derive_config_index(commit: str) -> KnowledgeUnit:
    """Compute the live config-file index."""
    files = sorted((_REPO_ROOT / "config").glob("*.yaml"))
    body_lines = [f"# Config files ({len(files)} config files)", ""]
    body_lines += [f"- `{f.name}`" for f in files]
    return _make_unit(
        "unit-fact-config-index",
        "Config files — the config/ tree index",
        [SourceRef(type="code", path="config/", commit=commit)],
        "\n".join(body_lines),
        ["fact", "operator"],
        why="The config index is computed from the live YAML files under `config/`.",
        claims=[{"probe": "config.files", "pattern": "{value} config files"}],
    )


def derive_dockerfile_index(commit: str) -> KnowledgeUnit:
    """Compute the live Dockerfile index."""
    files = sorted(_REPO_ROOT.glob("Dockerfile*"))
    body_lines = [f"# Dockerfiles ({len(files)} Dockerfiles)", ""]
    body_lines += [f"- `{f.name}`" for f in files]
    return _make_unit(
        "unit-fact-dockerfile-index",
        "Dockerfiles — the image-build index",
        [SourceRef(type="code", path=f.name, commit=commit) for f in files]
        or [SourceRef(type="code", path="Dockerfile.pipeline", commit=commit)],
        "\n".join(body_lines),
        ["fact", "operator"],
        why="The image index is computed from the live root-level `Dockerfile*` files.",
        claims=[{"probe": "dockerfiles", "pattern": "{value} Dockerfiles"}],
    )


def derive_env_reference(commit: str) -> KnowledgeUnit:
    """Compute the current environment-variable name index."""
    env_path = _REPO_ROOT / ".env.example"
    names = re.findall(r"^#?\s*([A-Z][A-Z0-9_]{2,})=", env_path.read_text(), re.MULTILINE)
    body_lines = [f"# Environment variables ({len(names)} env vars)", ""]
    body_lines += [f"- `{name}`" for name in names]
    return _make_unit(
        "unit-fact-env-reference",
        "Environment variables — the .env.example index",
        [SourceRef(type="code", path=".env.example", commit=commit)],
        "\n".join(body_lines),
        ["fact", "operator"],
        why="Environment variable names are read from the live `.env.example` file.",
        claims=[{"probe": "env.vars", "pattern": "{value} env vars"}],
    )


def derive_launch_commands(commit: str) -> KnowledgeUnit:
    """Compute the current launch.sh subcommand index."""
    launch = (_REPO_ROOT / "launch.sh").read_text()
    commands = sorted(set(re.findall(r"^\s+([a-z][a-z0-9-]+)\)", launch, re.MULTILINE)))
    body_lines = [f"# Operator commands ({len(commands)} subcommands)", ""]
    body_lines += [f"- `{command}`" for command in commands]
    return _make_unit(
        "unit-fact-launch-commands",
        "Operator commands — the launch.sh surface",
        [
            SourceRef(type="code", path="launch.sh", commit=commit),
            SourceRef(type="code", path="scripts/lib/services.sh", commit=commit),
            SourceRef(type="code", path="scripts/lib/util.sh", commit=commit),
        ],
        "\n".join(body_lines),
        ["fact", "operator"],
        why="The command index is computed from the live `launch.sh` usage cases.",
        claims=[{"probe": "launch.commands", "pattern": "{value} subcommands"}],
    )


_DERIVERS = (
    derive_persona_roster,
    derive_workspace_roster,
    derive_security_variants,
    derive_model_bindings,
    derive_mcp_fleet,
    derive_module_states,
    derive_model_catalog,
    derive_tool_authorizations,
    derive_tool_registry,
    derive_media_memory_budget,
    derive_doc_migration_coverage,
    derive_capability_rollup,
    derive_config_index,
    derive_dockerfile_index,
    derive_env_reference,
    derive_launch_commands,
)

_DERIVERS_BY_ID: dict[str, Callable[[str], KnowledgeUnit]] = {
    "unit-fact-persona-roster": derive_persona_roster,
    "unit-fact-workspace-roster": derive_workspace_roster,
    "unit-fact-security-variants": derive_security_variants,
    "unit-fact-model-bindings": derive_model_bindings,
    "unit-fact-mcp-fleet": derive_mcp_fleet,
    "unit-fact-module-states": derive_module_states,
    "unit-fact-model-catalog": derive_model_catalog,
    "unit-fact-tool-registry": derive_tool_registry,
    "unit-fact-tool-authorizations": derive_tool_authorizations,
    "unit-fact-media-memory-budget": derive_media_memory_budget,
    "unit-fact-doc-migration-coverage": derive_doc_migration_coverage,
    "unit-fact-config-index": derive_config_index,
    "unit-fact-dockerfile-index": derive_dockerfile_index,
    "unit-fact-env-reference": derive_env_reference,
    "unit-fact-launch-commands": derive_launch_commands,
    "unit-readme-capability-rollup": derive_capability_rollup,
}


def derive_facts(commit: str | None = None) -> list[KnowledgeUnit]:
    """Derive current facts in memory without writing the canonical store."""
    commit = commit or _get_current_commit()
    return [deriver(commit) for deriver in _DERIVERS]


def computed_fact_unit(unit_id: str) -> KnowledgeUnit | None:
    """Return one live fact unit by ID, or None for an authored unit ID."""
    deriver = _DERIVERS_BY_ID.get(unit_id)
    return deriver(_get_current_commit()) if deriver else None
