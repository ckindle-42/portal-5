"""Adaptive UAT — space introspection (TASK_UAT_ADAPTIVE_OVERHAUL_V1, Phase 1).

Reads the live capability contracts of every *testable space* directly from the
config source-of-truth at HEAD:

    config/portal.yaml            workspace defs (module, description, tools,
                                  system prompts, model_hint, web search)
    config/personas/*.yaml        persona defs (system_prompt, category,
                                  workspace_model, tools_allow, tags)
    config/modules.generated.yaml enabled/disabled module state (M7 toggles)

The output is a list of ``SpaceContract`` — the normalized, module-gated view
the generator and rubric layers consume. This layer is deterministic and does
NO inference: it only parses what each space *declares it does*, which is the
substrate the challenge generator adapts to.
"""

from __future__ import annotations

import glob
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Repo root: tests/uat/adaptive/introspect.py -> parents[3]
_ROOT = Path(__file__).resolve().parents[3]
_PORTAL_YAML = _ROOT / "config" / "portal.yaml"
_PERSONA_DIR = _ROOT / "config" / "personas"
_MODULES_YAML = _ROOT / "config" / "modules.generated.yaml"

# Header patterns models are asked to emit — used to derive an output contract
# from a system prompt so the `format` challenge dimension can check fidelity.
_HEADER_RE = re.compile(r"^\s{0,4}#{1,4}\s+([A-Z][^\n]{2,60})$", re.MULTILINE)
_REQUIRED_SECTION_RE = re.compile(
    r"(?:REQUIRED STRUCTURE|use these exact headers|required sections?)",
    re.IGNORECASE,
)

# Refusal-posture heuristics from the space's own declared identity.
_UNCENSORED_MARKERS = (
    "uncensored",
    "abliterated",
    "no disclaimers",
    "do not add disclaimers",
    "without content-policy",
    "no refusals",
    "fully abliterated",
)


@dataclass
class SpaceContract:
    """Normalized, testable description of one workspace or persona."""

    space_id: str
    kind: str  # "workspace" | "persona"
    name: str
    module: str
    model_hint: str
    purpose: str  # description — what the space claims to do
    directives: str  # system prompt text (may be empty)
    tools: list[str] = field(default_factory=list)
    web_search: bool = False
    enabled: bool = True  # module gate
    memory: bool = False  # declares memory/continuity intent
    output_sections: list[str] = field(default_factory=list)  # declared headers
    strict_format: bool = False  # system prompt demands an exact structure
    refusal_posture: str = "standard"  # "uncensored" | "standard"
    category: str = ""
    tier: str = "ollama"  # workspace_tier for cascade ordering
    model_slug: str = ""  # the OWUI model id the runner selects to reach this space
    owui_addressable: bool = True  # best-guess: is this selectable in OWUI?
    design_refs: list[str] = field(default_factory=list)  # design docs to review

    def to_dict(self) -> dict:
        return {
            "space_id": self.space_id,
            "kind": self.kind,
            "name": self.name,
            "module": self.module,
            "model_hint": self.model_hint,
            "purpose": self.purpose,
            "directives": self.directives,
            "tools": list(self.tools),
            "web_search": self.web_search,
            "enabled": self.enabled,
            "memory": self.memory,
            "output_sections": list(self.output_sections),
            "strict_format": self.strict_format,
            "refusal_posture": self.refusal_posture,
            "category": self.category,
            "tier": self.tier,
            "model_slug": self.model_slug,
            "owui_addressable": self.owui_addressable,
            "design_refs": list(self.design_refs),
        }


def _load_enabled_modules() -> dict[str, bool]:
    """Return {module_name: enabled} from modules.generated.yaml.

    Missing file (fresh clone before first sync-config) -> empty dict, which
    callers treat as 'all modules enabled' so introspection never hard-fails.
    """
    if not _MODULES_YAML.exists():
        return {}
    doc = yaml.safe_load(_MODULES_YAML.read_text()) or {}
    mods = doc.get("modules", {}) or {}
    return {name: bool(v.get("enabled", True)) for name, v in mods.items()}


def _derive_output_sections(directives: str) -> tuple[list[str], bool]:
    """Extract declared output headers and whether the format is strict."""
    if not directives:
        return [], False
    sections = [h.strip() for h in _HEADER_RE.findall(directives)]
    # De-dup preserving order, cap the list so it stays a checkable contract.
    seen: set[str] = set()
    ordered: list[str] = []
    for s in sections:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(s)
    strict = bool(_REQUIRED_SECTION_RE.search(directives)) and len(ordered) >= 2
    return ordered[:12], strict


def _derive_refusal_posture(*texts: str) -> str:
    blob = " ".join(t for t in texts if t).lower()
    for marker in _UNCENSORED_MARKERS:
        if marker in blob:
            return "uncensored"
    return "standard"


def _declares_memory(directives: str, tools: list[str]) -> bool:
    if any(t in {"remember", "recall", "forget", "list_memories"} for t in tools):
        return True
    d = (directives or "").lower()
    return ("memory tool" in d) or ("across conversations" in d) or ("continuity" in d)


# Directories scanned for design intent the agent reviews before authoring a
# test. Kept cheap: a filename/token match, not a content index.
_DESIGN_DIRS = ("coding_task", "docs", "portal_wiki/canonical")


def _find_design_refs(space_id: str, module: str, category: str) -> list[str]:
    """Return repo-relative design docs whose name references this space/module.

    The executing agent reads these to confirm *what the space was designed to
    do* before authoring an intended-use challenge — the review step Chris
    requires. Best-effort; an empty list just means the agent falls back to the
    system prompt + description already in the contract.
    """
    tokens = {t for t in (space_id.split(":")[-1], module, category) if t and len(t) >= 3}
    refs: list[str] = []
    for d in _DESIGN_DIRS:
        base = _ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            stem = path.stem.lower()
            if any(tok.lower() in stem for tok in tokens):
                refs.append(str(path.relative_to(_ROOT)))
    return sorted(set(refs))[:6]


def _workspace_directives(wdef: dict) -> str:
    """Concatenate every system-prompt-bearing field on a workspace def."""
    parts = [
        wdef.get("system_prompt") or "",
        wdef.get("owui_system_prompt") or "",
        wdef.get("system_prompt_append") or "",
    ]
    return "\n\n".join(p for p in parts if p).strip()


def load_workspace_contracts(enabled: dict[str, bool]) -> list[SpaceContract]:
    doc = yaml.safe_load(_PORTAL_YAML.read_text()) or {}
    out: list[SpaceContract] = []
    for slug, wdef in (doc.get("workspaces", {}) or {}).items():
        if not isinstance(wdef, dict):
            continue
        # Only user-facing spaces are UAT-relevant; eval/bench harness slots
        # are excluded (they are model benches, graded elsewhere).
        if not wdef.get("expose_to_owui", False):
            continue
        module = wdef.get("module", "general")
        directives = _workspace_directives(wdef)
        tools = list(wdef.get("tools", []) or [])
        sections, strict = _derive_output_sections(directives)
        out.append(
            SpaceContract(
                space_id=slug,
                kind="workspace",
                name=wdef.get("name", slug),
                module=module,
                model_hint=wdef.get("model_hint", ""),
                purpose=(wdef.get("description") or "").strip(),
                directives=directives,
                tools=tools,
                web_search=bool(wdef.get("enable_web_search", False)),
                enabled=enabled.get(module, True),
                memory=_declares_memory(directives, tools),
                output_sections=sections,
                strict_format=strict,
                refusal_posture=_derive_refusal_posture(directives, wdef.get("description", "")),
                category=module,
                tier=wdef.get("workspace_tier", "ollama"),
                model_slug=slug,  # workspace is addressed in OWUI by its own slug
                owui_addressable=True,  # expose_to_owui gate already applied above
                design_refs=_find_design_refs(slug, module, module),
            )
        )
    return out


def load_persona_contracts(enabled: dict[str, bool]) -> list[SpaceContract]:
    out: list[SpaceContract] = []
    for path in sorted(glob.glob(str(_PERSONA_DIR / "*.yaml"))):
        try:
            pdef = yaml.safe_load(Path(path).read_text())
        except Exception:
            continue
        if not isinstance(pdef, dict):
            continue
        category = pdef.get("category", "")
        # Benchmark personas are model-eval harness entries, not UAT spaces.
        if category in {"benchmark", "bench"}:
            continue
        module = pdef.get("module", category or "general")
        directives = (pdef.get("system_prompt") or "").strip()
        if not directives:
            continue  # nothing to challenge against
        tools = list(pdef.get("tools_allow", []) or [])
        sections, strict = _derive_output_sections(directives)
        slug = pdef.get("slug", Path(path).stem)
        # A persona is reachable in OWUI when it is exposed as a preset/model.
        # The reliable local signals are an explicit `workspace`/`ide_expose`
        # field; absent those we still emit the challenge but mark it
        # not-addressable so the runner SKIPs with a note (honest-BLOCKED) and
        # the operator sees "designed but unreachable" rather than a fake pass.
        owui_addressable = bool(pdef.get("workspace") or pdef.get("ide_expose"))
        out.append(
            SpaceContract(
                space_id=f"persona:{slug}",
                kind="persona",
                name=pdef.get("name", slug),
                module=module,
                model_hint=(pdef.get("preferred_models") or [""])[0],
                purpose=(pdef.get("description") or "").strip(),
                directives=directives,
                tools=tools,
                web_search="web_search" in tools,
                enabled=enabled.get(module, True),
                memory=_declares_memory(directives, tools),
                output_sections=sections,
                strict_format=strict,
                refusal_posture=_derive_refusal_posture(directives, pdef.get("description", "")),
                category=category,
                tier="ollama",
                model_slug=slug,  # personas are addressed in OWUI by their slug
                owui_addressable=owui_addressable,
                design_refs=_find_design_refs(slug, module, category),
            )
        )
    return out


def introspect_spaces(
    *, include_disabled: bool = False, kinds: tuple[str, ...] = ("workspace", "persona")
) -> list[SpaceContract]:
    """Return all testable space contracts, module-gated by default.

    ``include_disabled=True`` returns every space regardless of module toggle
    (useful for a full audit); the default drops spaces whose M7 module is off,
    mirroring how sync-config drops disabled-module workspaces from presets.
    """
    enabled = _load_enabled_modules()
    spaces: list[SpaceContract] = []
    if "workspace" in kinds:
        spaces.extend(load_workspace_contracts(enabled))
    if "persona" in kinds:
        spaces.extend(load_persona_contracts(enabled))
    if not include_disabled:
        spaces = [s for s in spaces if s.enabled]
    spaces.sort(key=lambda s: (s.tier, s.module, s.space_id))
    return spaces


if __name__ == "__main__":  # pragma: no cover - manual introspection dump
    import json as _json

    rows = [s.to_dict() for s in introspect_spaces()]
    print(_json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"\n{len(rows)} enabled testable spaces", flush=True)
