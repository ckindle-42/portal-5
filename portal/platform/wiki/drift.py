"""Drift census — measure the distance between code and the docs the spine feeds.

Two gates guard the spine:

  BR  every code surface is cited by a gate-passing unit  (existence, not truth)
  BS  every claim holds, no dead doc refs                 (absolute, no baseline)

This module measures BS in two axes that are both exact rather than heuristic:

  claims      declared assertions evaluated against live probes (see claims.py)
  path refs   repo-relative paths named in Tier-1 docs that no longer exist

P0 (A1) deleted the third axis this module used to carry — per-unit
`last_generated_commit` pin health. 461 of ~720 units were pinned to a SHA
absent from all history; the field forced a two-commit re-pin dance on every
fact edit while adding no truth-checking of its own (a pin resolving to a
real commit says nothing about whether the body is still correct — `claims`
is what does that). There is no pin axis to restore; `claims` is the
anti-drift core (A2) and `broken_path_refs` is the cheap, exact axis kept
alongside it (A3).
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from portal.platform.wiki.schema import KnowledgeUnit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PENDING_TRIAGE_RE = re.compile(r"^\s*-\s+`([^`]+)`\s+\|\s+pending\s+\|", re.MULTILINE)

# Top-level directories whose names, followed by a slash, denote a repo path in
# prose. Anything else (bare words, URLs, absolute paths, model ids like
# `portal/auto-coding` served over HTTP) is not a filesystem claim.
_PATH_ROOTS = (
    "portal",
    "portal_wiki",
    "portal_mcp",
    "portal_channels",
    "scripts",
    "config",
    "tests",
    "docs",
    "deploy",
    "coding_task",
    "playbooks",
    "prompts",
    "imports",
)
_PATH_RE = re.compile(
    r"(?<![\w/.\-])((?:" + "|".join(_PATH_ROOTS) + r")/[A-Za-z0-9_./\-]*[A-Za-z0-9_\-])"
)
# A path claim must look like a file or a directory that exists in the tree — a
# fragment ending mid-word (`tests/benchmarks/results/persona_matrix_`) is a
# prose ellipsis, not a broken reference, and is skipped rather than reported.
_LOOKS_TRUNCATED = re.compile(r"[_\-.]$")


def _git(root: Path, *args: str, input: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        input=input,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


# ── Axis 2 (formerly): doc path references ──────────────────────────────────
# The pin-health axis that used to live here (`PinHealth`/`pin_health`) was
# deleted whole by P0 A1 — see module docstring.


def _served_model_ids(root: Path) -> frozenset[str]:
    """`portal/<workspace-or-persona>` is an OpenAI-style served model id, not a
    filesystem path. Suppressing these is an exact rule, not a heuristic: the
    second segment is checked against the live workspace and persona rosters, so
    a genuinely dead `portal/...` *directory* reference is still reported."""
    from portal.platform.wiki.claims import _workspace_names

    names = set(_workspace_names(root))
    names.update(p.stem for p in (root / "config" / "personas").glob("*.yaml"))
    # Personas are also referenced by slug with separators stripped.
    names.update(n.replace("-", "").replace("_", "") for n in list(names))
    return frozenset(f"portal/{n}" for n in names)


def _gitignored_paths(root: Path, candidates: list[str]) -> frozenset[str]:
    """Of `candidates`, the subset `git` itself says is intentionally untracked.

    A path a doc cites can be legitimately absent from *any* checkout — a
    gitignored scratch file (`coding_task/*.md`) or a directory a harness
    writes at runtime (`results/candidates/`). `.gitignore` is the authoritative
    answer to "should this exist here", so ask git rather than guessing with
    more regex: a hand-maintained allowlist drifts the moment a path is renamed,
    `git check-ignore` never does.

    `_PATH_RE` never captures a trailing `/` (its final char class excludes it),
    so a doc's `foo/bar/` reference reaches here as `foo/bar`. For a directory-
    only `.gitignore` pattern (`foo/bar/`), `git check-ignore` only matches a
    slash-less query reliably when that path happens to already exist on disk
    as a directory — true in a checkout that has run the harness, false in a
    fresh clone (exactly where this check must be trustworthy). Querying both
    the bare candidate and its `/`-suffixed form sidesteps that disk-state
    dependency entirely.
    """
    if not candidates:
        return frozenset()
    queries = [q for cand in candidates for q in (cand, f"{cand}/")]
    out = _git(root, "check-ignore", "--stdin", input="\n".join(queries))
    hit = set(out.stdout.splitlines())
    return frozenset(cand for cand in candidates if cand in hit or f"{cand}/" in hit)


def broken_path_refs(repo_root: Path | None = None) -> tuple[str, ...]:
    """Repo-relative paths named in Tier-1 docs that do not exist and are not
    gitignored (a gitignored path existing in no checkout is not drift — see
    `_gitignored_paths`).

    Returned as `"<doc>::<path>"` rather than one entry per doc — a doc may
    carry several independent broken references at once.

    A few prose fragments survive the truncation filter (`tests/acceptance/s`
    from a sentence that trails off). They are deliberately left in rather than
    chased with more pattern-matching: every additional heuristic here is a
    place for a real broken reference to hide.
    """
    from portal.platform.wiki.render import TIER1_DOCS

    root = repo_root or _REPO_ROOT
    model_ids = _served_model_ids(root)
    per_doc_missing: dict[str, set[str]] = {}
    for rel in TIER1_DOCS:
        doc = root / rel
        if not doc.exists():
            continue
        for match in _PATH_RE.finditer(doc.read_text(encoding="utf-8")):
            cand = match.group(1)
            if _LOOKS_TRUNCATED.search(cand) or cand in model_ids:
                continue
            if (root / cand).exists():
                continue
            per_doc_missing.setdefault(rel, set()).add(cand)

    all_missing = sorted({c for cands in per_doc_missing.values() for c in cands})
    ignored = _gitignored_paths(root, all_missing)

    broken: set[str] = set()
    for rel, cands in per_doc_missing.items():
        for cand in cands:
            if cand not in ignored:
                broken.add(f"{rel}::{cand}")
    return tuple(sorted(broken))


# ── Census (the human-facing report) ─────────────────────────────────────────

# Computed families whose figures come from live sources. A `unit-fact-*`
# body's counts are derived for each wiki query, and a
# technique signature's Event IDs come from the MITRE mapping — neither is a
# hand-typed figure that could quietly go stale.
_DERIVED_FAMILY_RE = re.compile(
    r"^(?:unit-fact-|unit-readme-capability-rollup$|unit-T\d{4}(?:\.\d{3})?-signature$)"
)

# Fenced blocks hold captured terminal output and config excerpts. A figure inside
# one is a transcript of something that already happened, not a claim about now —
# `0 backends` in a log excerpt was one of the original false alarms.
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

# Plural noun required, and the number may not be preceded by a digit, dot, or "Portal ".
_NUMERIC_CLAIM_RE = re.compile(
    r"(?<![\d.])(?<!Portal\s)\b\d[\d,]*\s+(?:workspaces|personas|MCP servers|servers|checks|"
    r"models|backends|variants|scenarios|techniques|tools|ports|modules)\b",
    re.IGNORECASE,
)

# Hardcoded module enable-state restatements in authored titles/prose.
_MODULE_STATE_RE = re.compile(
    r"modules\.[a-z_]+\.enabled(?::\s*(?:true|false)|`?\s+is\s+(?:true|false|on|off)\b)"
    r"|\b(?:ships?|shipped)\s+(?:enabled|disabled|on|off)\b"
    r"|\bmodule\s+(?:is\s+)?(?:default\s+(?:on|off)|off\s+by\s+default|on\s+by\s+default|"
    r"enabled\s+by\s+default|disabled\s+by\s+default|off|on|enabled\s+in\s+the\s+repo)\b"
    r"|\b(?:module|eval|music|video|image|orchestration|security_redteam|security-redteam)\b"
    r"[^.\n]{0,45}\b(?:is\s+(?:now\s+)?(?:enabled|disabled|on|off)\b|"
    r"(?:enabled|disabled|off)\s+by\s+default\b)"
    r"|\((?:off\s+by\s+default|disabled\s+by\s+default|enabled\s+in\s+repo|"
    r"module\s+off(?:\s+by\s+default)?)\)",
    re.IGNORECASE,
)


def undeclared_numeric_claims(
    units: Sequence[KnowledgeUnit] | None = None,
) -> dict[str, list[str]]:
    """Units whose body states a countable quantity but declare no claim."""
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()
    out: dict[str, list[str]] = {}
    for unit in units:
        if getattr(unit, "claims", None) or _DERIVED_FAMILY_RE.match(unit.id):
            continue
        hits = [
            m.group(0).strip() for m in _NUMERIC_CLAIM_RE.finditer(_FENCE_RE.sub(" ", unit.body))
        ]
        if hits:
            out[unit.id] = sorted(set(hits))
    return out


_CONDITIONAL_PREFIX_RE = re.compile(r"\b(?:when|while|if)\s+(?:the\s+)?`?$", re.IGNORECASE)


def _is_conditional_state(text: str, start: int) -> bool:
    """True when a state phrase sits inside a conditional `when/while/if` clause."""
    prefix = text[max(0, start - 24) : start]
    return bool(_CONDITIONAL_PREFIX_RE.search(prefix))


def volatile_prose_violations(
    units: Sequence[KnowledgeUnit] | None = None,
) -> dict[str, list[str]]:
    """Authored units whose title or prose hardcodes volatile counts or module enable state."""
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()
    out: dict[str, list[str]] = {}
    for unit in units:
        if unit.historical or _DERIVED_FAMILY_RE.match(unit.id):
            continue
        body_no_fence = _FENCE_RE.sub(" ", unit.body)
        counts = sorted({m.group(0).strip() for m in _NUMERIC_CLAIM_RE.finditer(body_no_fence)})
        full = f"{unit.title}\n{body_no_fence}"
        states = sorted(
            {
                m.group(0).strip()
                for m in _MODULE_STATE_RE.finditer(full)
                if not _is_conditional_state(full, m.start())
            }
        )
        msgs = [
            f"hardcoded count {c!r} — reference `unit-fact-*` instead" for c in counts
        ] + [
            f"hardcoded module enable state {s!r} — reference `unit-fact-module-states` instead"
            for s in states
        ]
        if msgs:
            out[unit.id] = msgs
    return out


def claim_coverage_gaps(units: Sequence[KnowledgeUnit], repo_root: Path | None = None) -> list[str]:
    """Units still marked pending in CLAIMS_TRIAGE.md (empty claims are valid for narrative/how-to units)."""
    root = repo_root or _REPO_ROOT
    triage = root / "docs" / "wiki" / "CLAIMS_TRIAGE.md"
    pending = (
        set(_PENDING_TRIAGE_RE.findall(triage.read_text(encoding="utf-8")))
        if triage.exists()
        else set()
    )
    return sorted(unit.id for unit in units if not unit.historical and unit.id in pending)


def census(repo_root: Path | None = None) -> dict[str, Any]:
    """Full drift census. Read-only; writes nothing."""
    from portal.platform.wiki.claims import (
        authored_claim_violations,
        claim_count,
        evaluate_claims,
        probe_all,
    )
    from portal.platform.wiki.render import render_report
    from portal.platform.wiki.store import load_all

    root = repo_root or _REPO_ROOT
    units = load_all()
    refs = broken_path_refs(root)
    violations = authored_claim_violations(units) + evaluate_claims(units, root)
    undeclared = undeclared_numeric_claims(units)
    volatile_prose = volatile_prose_violations(units)
    blocks = render_report(root)

    return {
        "units_total": len(units),
        "probes": probe_all(root),
        "claims_declared": claim_count(units),
        "claim_violations": [str(v) for v in violations],
        "volatile_prose_units": len(volatile_prose),
        "volatile_prose_sample": dict(sorted(volatile_prose.items())[:10]),
        "undeclared_numeric_units": len(undeclared),
        "undeclared_numeric_sample": dict(sorted(undeclared.items())[:10]),
        "broken_path_refs": list(refs),
        "generated_blocks": blocks["blocks_total"],
    }
