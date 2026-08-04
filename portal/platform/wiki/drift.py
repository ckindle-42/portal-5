"""Drift census — measure the distance between code and the docs the spine feeds.

Three gates guard the spine:

  AW  every `WIKI:GENERATED` block equals its unit's body        (copy vs source)
  BR  every code surface is cited by a gate-passing unit         (existence, not truth)
  BS  every claim holds, every pin resolves, no dead doc refs    (absolute, no baseline)

This module measures BS in three axes that are all exact rather than heuristic:

  claims      declared assertions evaluated against live probes (see claims.py)
  pins        `last_generated_commit` resolvable, and cited sources unchanged since
  path refs   repo-relative paths named in Tier-1 docs that no longer exist

Axis 2 deliberately reports rather than fails on prose. `maintain.check_staleness`
decided that "advancing HEAD alone does not make an authored canonical unit stale"
— defensible for a *why* unit explaining a design rationale, wrong for a *what*
unit describing an interface. The census keeps both visible, and since
TASK_WIKI_ZERO_DEBT_V1 deleted the drift baseline, every finding is a hard fail
with nothing to tolerate.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

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


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False, timeout=30
    )


# ── Axis 2: pin health ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class PinHealth:
    """Per-unit provenance-pin status. Every tuple holds sorted unit ids."""

    fresh: tuple[str, ...] = ()
    stale: tuple[str, ...] = ()
    phantom: tuple[str, ...] = ()
    unpinned: tuple[str, ...] = ()
    stale_detail: dict[str, int] = field(default_factory=dict)
    authored_stale: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.fresh) + len(self.stale) + len(self.phantom) + len(self.unpinned)


def _local_source_paths(unit) -> list[str]:
    out = []
    for src in unit.sources:
        raw = (src.path or "").split("#", 1)[0].strip()
        if not raw or raw.startswith(("http://", "https://", "/")):
            continue
        out.append(raw)
    return out


def pin_health(repo_root: Path | None = None, units=None) -> PinHealth:
    """Classify every unit that cites a repo-local path.

    phantom  — `last_generated_commit` does not resolve to a commit in this clone.
               The pin is not merely old, it is unverifiable: nothing can ever be
               diffed against it, so the field is decoration.
    stale    — pin resolves and at least one cited path has a commit in pin..HEAD.
    unpinned — cites repo paths but records no pin at all.
    """
    root = repo_root or _REPO_ROOT
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()

    fresh: list[str] = []
    stale: list[str] = []
    phantom: list[str] = []
    unpinned: list[str] = []
    authored_stale: list[str] = []
    detail: dict[str, int] = {}
    rev_ok: dict[str, bool] = {}

    for unit in units:
        paths = _local_source_paths(unit)
        if not paths:
            continue
        pin = (unit.last_generated_commit or "").strip()
        if not pin:
            unpinned.append(unit.id)
            continue
        if pin not in rev_ok:
            rev_ok[pin] = _git(root, "cat-file", "-e", f"{pin}^{{commit}}").returncode == 0
        if not rev_ok[pin]:
            phantom.append(unit.id)
            continue
        out = _git(root, "log", "--oneline", f"{pin}..HEAD", "--", *paths).stdout.strip()
        if out:
            # Authored-v1 units carry the enforceable staleness contract: their
            # cited source moving is a FAIL, not a report. They are tracked
            # separately so BS can hard-fail on them while legacy units keep the
            # report-only doctrine and their baseline entry.
            if "authored-v1" in (unit.tags or []):
                authored_stale.append(unit.id)
            stale.append(unit.id)
            detail[unit.id] = len(out.splitlines())
        else:
            fresh.append(unit.id)

    return PinHealth(
        fresh=tuple(sorted(fresh)),
        stale=tuple(sorted(stale)),
        phantom=tuple(sorted(phantom)),
        unpinned=tuple(sorted(unpinned)),
        stale_detail=detail,
        authored_stale=tuple(sorted(authored_stale)),
    )


# ── Axis 3: doc path references ──────────────────────────────────────────────


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


def broken_path_refs(repo_root: Path | None = None) -> tuple[str, ...]:
    """Repo-relative paths named in Tier-1 docs that do not exist.

    Returned as `"<doc>::<path>"` so the ratchet baseline can pin an individual
    reference rather than a whole doc — a doc may legitimately gain a new broken
    reference while an old one is still being worked off.

    A few prose fragments survive the truncation filter (`tests/acceptance/s`
    from a sentence that trails off). They are deliberately left in rather than
    chased with more pattern-matching: the baseline absorbs them at zero cost,
    and every additional heuristic here is a place for a real broken reference
    to hide.
    """
    from portal.platform.wiki.render import TIER1_DOCS

    root = repo_root or _REPO_ROOT
    model_ids = _served_model_ids(root)
    broken: set[str] = set()
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
            broken.add(f"{rel}::{cand}")
    return tuple(sorted(broken))


# ── Census (the human-facing report) ─────────────────────────────────────────

_NUMERIC_CLAIM_RE = re.compile(
    r"\b\d[\d,]*\s+(?:workspaces?|personas?|MCP servers?|servers?|checks?|models?|units?|"
    r"backends?|variants?|scenarios?|techniques?|tools?|ports?)\b",
    re.IGNORECASE,
)


def undeclared_numeric_claims(units=None) -> dict[str, list[str]]:
    """Units whose body states a countable quantity but declare no claim.

    Visible debt, never a hard gate: the pattern is a heuristic and a fuzzy
    signal promoted to a failure is exactly the kind of measurement error this
    project has paid to unlearn. Use it to pick the next units to instrument.
    """
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()
    out: dict[str, list[str]] = {}
    for unit in units:
        if getattr(unit, "claims", None):
            continue
        hits = [m.group(0).strip() for m in _NUMERIC_CLAIM_RE.finditer(unit.body)]
        if hits:
            out[unit.id] = sorted(set(hits))
    return out


def census(repo_root: Path | None = None) -> dict:
    """Full drift census. Read-only; writes nothing."""
    from portal.platform.wiki.claims import claim_count, evaluate_claims, probe_all
    from portal.platform.wiki.render import render_report
    from portal.platform.wiki.store import load_all

    root = repo_root or _REPO_ROOT
    units = load_all()
    pins = pin_health(root, units)
    refs = broken_path_refs(root)
    violations = evaluate_claims(units, root)
    undeclared = undeclared_numeric_claims(units)
    blocks = render_report(root)

    return {
        "units_total": len(units),
        "probes": probe_all(root),
        "claims_declared": claim_count(units),
        "claim_violations": [str(v) for v in violations],
        "undeclared_numeric_units": len(undeclared),
        "undeclared_numeric_sample": dict(sorted(undeclared.items())[:10]),
        "pins": {
            "fresh": len(pins.fresh),
            "stale": len(pins.stale),
            "phantom": len(pins.phantom),
            "unpinned": len(pins.unpinned),
            "total": pins.total,
            "stalest": sorted(pins.stale_detail.items(), key=lambda kv: -kv[1])[:10],
        },
        "broken_path_refs": list(refs),
        "generated_blocks": blocks["blocks_total"],
    }
