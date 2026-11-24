"""Drift lock for docs/FEATURE_QAT_TRACEABILITY_MATRIX.md (lane/audit-feature-traceability-matrix).

Re-parses the live repo (portal.yaml, personas, every @mcp.tool definition) and the
matrix doc, then asserts: zero untracked tools, zero phantom persona bindings, and
no new phantom tool references beyond the locked known-issues set. Offline by design.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX = REPO_ROOT / "docs" / "FEATURE_QAT_TRACEABILITY_MATRIX.md"
PORTAL_YAML = REPO_ROOT / "config" / "portal.yaml"
PERSONA_DIR = REPO_ROOT / "config" / "personas"

# Pre-existing phantom native reference: granted in auto-coding / auto-daily::fast and the
# browser manifest, but only a REST dispatch branch exists (browser_mcp.py:555), no @mcp.tool.
# Fix lane: Lane B (audit fixes/purges) — see matrix §11 F1. Remove from this set once fixed.
KNOWN_PHANTOM_REFS = frozenset({"browser_get_markdown"})
# Tools defined by the external unifi-network-mcp package, relayed by the :8949 stdio bridge.
EXTERNAL_TOOL_PREFIXES = ("unifi_",)

_DEF_RE = re.compile(r"\s*(async\s+)?def\s+(\w+)")
_TOOL_RE = re.compile(r"\s*@mcp\.tool\b")


def _tool_definitions() -> list[tuple[str, Path, int]]:
    """Every @mcp.tool definition under portal/, portal_wiki/ and scripts/mlx-transcribe.py."""
    files = sorted(
        p for root in ("portal", "portal_wiki") for p in (REPO_ROOT / root).rglob("*.py")
    )
    files.append(REPO_ROOT / "scripts" / "mlx-transcribe.py")
    out: list[tuple[str, Path, int]] = []
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            if not _TOOL_RE.match(lines[i]):
                i += 1
                continue
            depth, j, saw_paren = 0, i, False
            while j < len(lines):
                depth += lines[j].count("(") - lines[j].count(")")
                saw_paren = saw_paren or "(" in lines[j]
                if saw_paren and depth <= 0:
                    break
                j += 1
            k = j + 1
            while k < len(lines) and not _DEF_RE.match(lines[k]):
                k += 1
            match = _DEF_RE.match(lines[k]) if k < len(lines) else None
            if match:
                out.append((match.group(2), path, i + 1))
            i = k + 1
    return out


def _workspaces() -> dict:
    data = yaml.safe_load(PORTAL_YAML.read_text(encoding="utf-8")) or {}
    return data.get("workspaces") or {}


def _persona_files() -> list[Path]:
    return sorted(PERSONA_DIR.glob("*.yaml"))


def _referenced_tool_names(workspaces: dict) -> set[str]:
    refs: set[str] = set()
    for cfg in workspaces.values():
        refs.update(str(t) for t in (cfg.get("tools") or []))
        for variant in (cfg.get("variants") or {}).values():
            refs.update(str(t) for t in ((variant or {}).get("tools") or []))
    for path in _persona_files():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        refs.update(str(t) for t in (data.get("tools_allow") or []))
    return refs


def _matrix_text() -> str:
    return MATRIX.read_text(encoding="utf-8")


def _executive_count(text: str, metric: str) -> int:
    match = re.search(rf"^\| {re.escape(metric)}[^|]*\| (\d+) \|", text, re.M)
    assert match, f"executive summary row for {metric!r} missing from the matrix"
    return int(match.group(1))


def test_every_native_tool_is_tracked_in_the_matrix() -> None:
    text = _matrix_text()
    missing = [
        f"{name} ({path.relative_to(REPO_ROOT)}:{line})"
        for name, path, line in _tool_definitions()
        if not re.search(rf"\b{re.escape(name)}\b", text)
    ]
    assert not missing, f"tools defined but absent from the matrix: {missing}"


def test_known_phantom_refs_are_documented() -> None:
    text = _matrix_text()
    for name in KNOWN_PHANTOM_REFS:
        assert re.search(rf"\b{re.escape(name)}\b", text), f"{name} must stay documented"


def test_persona_workspace_models_and_variants_resolve() -> None:
    workspaces = _workspaces()
    broken: list[str] = []
    for path in _persona_files():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        model = data.get("workspace_model")
        if not isinstance(model, str) or model not in workspaces:
            broken.append(f"{path.name}: workspace_model={model!r}")
            continue
        variant = data.get("variant")
        if variant and variant not in (workspaces[model].get("variants") or {}):
            broken.append(f"{path.name}: variant={variant!r} not in {model}")
    assert not broken, f"phantom persona bindings: {broken}"


def test_no_new_phantom_tool_references() -> None:
    refs = _referenced_tool_names(_workspaces())
    defined = {name for name, _path, _line in _tool_definitions()}
    external = {n for n in refs if n.startswith(EXTERNAL_TOOL_PREFIXES)}
    phantom = refs - defined - external - KNOWN_PHANTOM_REFS
    assert not phantom, (
        f"workspace/persona tool refs with no native definition: {sorted(phantom)} — "
        "add the tool, fix the reference, or (for a verified pre-existing issue only) "
        "extend KNOWN_PHANTOM_REFS with a fix-lane pointer"
    )


def test_matrix_executive_counts_match_the_repo() -> None:
    text = _matrix_text()
    workspaces = _workspaces()
    assert _executive_count(text, "workspaces") == len(workspaces)
    assert _executive_count(text, "variants") == sum(
        len(cfg.get("variants") or {}) for cfg in workspaces.values()
    )
    assert _executive_count(text, "personas") == len(_persona_files())
    section = text.split("## 6. MCP Tools", 1)[1].split("## 7. External", 1)[0]
    tool_rows = re.findall(r"^\| `(\w+)` \| `[^`]+:\d+` \|", section, re.M)
    assert _executive_count(text, "total_tools (tracked tool rows)") == len(tool_rows)
    native = {name for name, _path, _line in _tool_definitions()}
    assert native <= set(tool_rows), (
        f"native defs missing from §6 tables: {native - set(tool_rows)}"
    )
