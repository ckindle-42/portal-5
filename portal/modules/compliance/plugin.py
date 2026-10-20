"""Compliance module hooks for wiki claim probes."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from portal.platform.wiki.claims import _load_portal_yaml


def wiki_probes() -> dict[str, Callable[[Path], Any]]:
    return {
        "compliance.cite_and_scope": _probe_compliance_cite_and_scope,
        "compliance.register": _probe_compliance_register,
        "compliance.completeness": _probe_compliance_completeness,
        "compliance.change_types": _probe_compliance_change_types,
        "compliance.workspace_tools": _probe_compliance_workspace_tools,
        "compliance.capture.unit_kinds": _probe_compliance_capture_unit_kinds,
        "compliance.store.tables": _probe_compliance_store_tables,
        "compliance.served_window.tag_window": _probe_compliance_served_window_tag,
    }


def _probe_compliance_cite_and_scope(root: Path) -> list[str]:
    """Facts the cite-and-scope units rest on (CITE_AND_SCOPE_V1), derived
    from the module sources — never from live state."""
    import re as _re

    out: list[str] = []
    p = root / "portal" / "modules" / "compliance" / "core" / "citation_by_quote.py"
    if p.is_file():
        src = p.read_text(encoding="utf-8")
        out += [f"quote-min-part-chars={m}" for m in _re.findall(r"_MIN_PART_CHARS = (\d+)", src)]
    p = root / "portal" / "modules" / "compliance" / "core" / "document_scope.py"
    if p.is_file():
        src = p.read_text(encoding="utf-8")
        out += [
            f"scope-read-budget-chars={m}" for m in _re.findall(r"READING_CHAR_BUDGET = (\d+)", src)
        ]
        out += ["family-normal-form=CIP-NNN"] if "_FAMILY = re.compile" in src else []
    return sorted(out)


def _probe_compliance_register(root: Path) -> list[str]:
    """The NERC CIP standards carried in the bitemporal register (T3). A nominal
    ``modules.enabled contains: compliance`` probe passed while the register was
    a 27-entry paraphrased map on superseded versions; this lists the actual
    standard ids in the built register JSON."""
    import json as _json

    p = root / "portal" / "modules" / "compliance" / "data" / "nerc_cip_register.json"
    if not p.is_file():
        return []
    try:
        d = _json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted({n.get("standard", "") for n in d.get("nodes", []) if n.get("standard")})


def _probe_compliance_completeness(root: Path) -> list[str]:
    """Register **completeness**, not just presence (TASK_CIP_REGISTER_COMPLETENESS_V1).
    Binds the wiki claim to the document-derived completeness metric: a
    regression that drops Parts, or reverts to an extractor-supplied
    denominator, flips one of these tokens and fails the drift census."""
    import json as _json

    p = root / "portal" / "modules" / "compliance" / "data" / "nerc_cip_register.json"
    if not p.is_file():
        return []
    try:
        rep = _json.loads(p.read_text(encoding="utf-8")).get("extraction_report", {})
    except (OSError, ValueError):
        return []
    comp = rep.get("completeness", {})
    srcs = comp.get("denominator_source_by_standard", {})
    self_derived = any("extractor" in v for v in srcs.values())
    return sorted(
        [
            f"incomplete_standards:{len(comp.get('incomplete_standards', ['?']))}",
            f"completeness_holes:{comp.get('n_missing', -1)}",
            f"denominator_self_derived:{self_derived}",
            f"fidelity_failed:{rep.get('fidelity', {}).get('n_fidelity_failed', -1)}",
        ]
    )


def _probe_compliance_change_types(root: Path) -> list[str]:
    """The typed change vocabulary of the register-diff engine (T4). Binds the
    wiki claim to ``register_diff.CHANGE_TYPES`` so renaming or deleting the
    module fails the census rather than leaving a stale doc."""
    p = root / "portal" / "modules" / "compliance" / "core" / "register_diff.py"
    if not p.is_file():
        return []
    try:
        t = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    m = re.search(r"CHANGE_TYPES\s*=\s*\(([^)]*)\)", t, re.S)
    if not m:
        return []
    return sorted(re.findall(r'"([A-Z_]+)"', m.group(1)))


def _probe_compliance_workspace_tools(root: Path) -> list[str]:
    """TASK_COMPLIANCE_ENGINE_LANDING_V1 P7: a tool that is registered but
    unreachable from the persona is an engine that does not exist — six prior
    tasks improved correctness while this stayed broken and no test caught it,
    because every test called the library directly. Cross-checks THREE
    independent sources of truth for every compliance-specific name in the
    ``auto-compliance`` workspace's ``tools:`` list: it must also appear in the
    MCP's discovery manifest (what a model sees exists) AND in
    ``compliance_mcp._DISPATCH`` (what a POST actually reaches) — a probe that
    passes while the engine is unroutable is the exact failure this task fixes.
    """
    portal_yaml = root / "config" / "portal.yaml"
    manifest_json = root / "config" / "inference" / "tools_manifest_compliance_mcp.json"
    mcp_py = root / "portal" / "modules" / "compliance" / "tools" / "compliance_mcp.py"
    if not (portal_yaml.is_file() and manifest_json.is_file() and mcp_py.is_file()):
        return ["source_missing"]

    y = portal_yaml.read_text(encoding="utf-8")
    m = re.search(r"(?m)^  auto-compliance:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)", y, re.S)
    if not m:
        return ["workspace_missing"]
    tm = re.search(r"(?ms)^    tools:\n((?:    - .*\n)+)", m.group(1))
    workspace_tools = set(re.findall(r"^    - (\S+)", tm.group(1), re.M)) if tm else set()
    compliance_names = {t for t in workspace_tools if t.startswith(("compliance_", "nerc_cip"))}

    manifest = {
        f["function"]["name"] for f in json.loads(manifest_json.read_text(encoding="utf-8"))
    }
    dispatch_block = re.search(
        # tolerate an optional `: dict[str, Callable[..., Any]]` annotation
        # between the name and the `=` (mypy-strict style)
        r"_DISPATCH\s*(?::\s*[^=\n]+)?=\s*\{(.*?)\n\}",
        mcp_py.read_text(encoding="utf-8"),
        re.S,
    )
    dispatch = (
        set(re.findall(r'"([a-z_0-9]+)":', dispatch_block.group(1))) if dispatch_block else set()
    )

    unreachable = sorted(
        name for name in compliance_names if name not in manifest or name not in dispatch
    )
    return (
        [f"unreachable:{n}" for n in unreachable]
        if unreachable
        else [f"all_reachable:{len(compliance_names)}"]
    )


def _probe_compliance_capture_unit_kinds(root: Path) -> list[str]:
    """The positional unit kinds a faithful capture may emit
    (BILATERAL_CORPUS_V1 P1). Read from the module constant, so a new kind
    added in code shows up here rather than in prose."""
    import re as _re

    p = root / "portal" / "modules" / "compliance" / "core" / "capture.py"
    if not p.is_file():
        return []
    m = _re.search(r"^UNIT_KINDS = \(([^)]*)\)", p.read_text(encoding="utf-8"), _re.M)
    return sorted(_re.findall(r'"([a-z_]+)"', m.group(1))) if m else []


def _probe_compliance_store_tables(root: Path) -> list[str]:
    """Tables the compliance store's migrations create. Derived from the DDL,
    never from a live database file."""
    import re as _re

    p = root / "portal" / "modules" / "compliance" / "core" / "migrations" / "schema.py"
    if not p.is_file():
        return []
    return sorted(set(_re.findall(r"CREATE TABLE (\w+)", p.read_text(encoding="utf-8"))))


def _probe_compliance_served_window_tag(root: Path) -> int | None:
    """The window compliance-reading's bound tag declares (DATA_TRUTH F8), read
    from the live ``model_hint`` through the module's own parser — a rebinding
    or a change in tag shape shows up here."""
    from portal.modules.compliance.core.served_window import tag_window

    workspaces = _load_portal_yaml(root).get("workspaces") or {}
    hint = str((workspaces.get("compliance-reading") or {}).get("model_hint") or "")
    return tag_window(hint) if hint else None
