"""Authored-unit quality gate — what stops 625/625 from being a number about nothing.

Taking authored coverage from 117/625 to 625/625 means 508 new units. The risk is
not that the work is impossible; a model can read a module and explain it. The risk
is that 508 plausible-sounding units land, the percentage reads 100, and nobody can
tell which of them say anything true. That is the same failure this project already
paid for twice: ~940 units citing the docs they themselves fed, and 567 doc blocks
certified "current" by comparing a copy with its own source.

So coverage is redefined here. A surface is covered when a unit cites it *and* that
unit passes every check below. A unit that fails is not coverage — the gate is the
definition, not a review step afterwards.

Four checks, chosen because each is mechanical and each catches a distinct way to
fake authorship:

  grounding    Every backticked identifier attributed to the cited source must
               actually exist in it. Catches hallucinated function and class names,
               which is the dominant failure when a model summarises code it only
               partly read.
  substance    Prose outside code spans must clear a word floor, and must not be a
               restatement of the API surface the AST already yields for free. A
               unit that lists symbols is a projection, not an explanation.
  distinctness No unit's prose may closely duplicate another's. Template filler
               ("This module provides functionality for X") is invisible one unit at
               a time and obvious across 500.
  structure    A `## Why` section with real content. The one thing a derived
               projection can never supply is the reason the code is shaped this
               way, so it is required explicitly rather than hoped for.

Calibration discipline: these thresholds were tuned against the 117 units that were
already hand-authored before this gate existed. A gate that rejects known-good work
is wrong and must be fixed before it is used to judge new work — validate the
instrument, then measure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Tuned against the pre-existing authored corpus. See `calibrate()`.
MIN_PROSE_WORDS = 40
MIN_WHY_WORDS = 25
MAX_API_OVERLAP = 0.70
MAX_PROSE_SIMILARITY = 0.80
MIN_GROUNDED_RATIO = 0.80

_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_WHY_RE = re.compile(r"^##+\s*Why\b(.*?)(?=^##+\s|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE)
# 3-char floor: single letters in prose ("step `D`") are not symbol claims, and the
# repo identifier universe is built with the same floor, so shorter spans could
# never be grounded even when legitimate.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{2,}$")


@dataclass
class QualityIssue:
    """One reason a unit does not count as coverage."""

    unit_id: str
    check: str
    detail: str

    def __str__(self) -> str:
        return f"{self.unit_id} [{self.check}]: {self.detail}"


@dataclass
class QualityReport:
    passing: tuple[str, ...] = ()
    issues: tuple[QualityIssue, ...] = ()
    by_check: dict[str, int] = field(default_factory=dict)


def prose_of(body: str) -> str:
    """Body text with fenced blocks and inline code spans removed."""
    text = _FENCE_RE.sub(" ", body)
    return _CODE_SPAN_RE.sub(" ", text)


def prose_words(body: str) -> list[str]:
    return list(re.findall(r"[A-Za-z][A-Za-z'-]+", prose_of(body)))


def why_section(body: str) -> str:
    m = _WHY_RE.search(body)
    return m.group(1).strip() if m else ""


_EXTERNAL_OK = re.compile(
    r"^(?:T\d{4}(?:\.\d{3})?"  # MITRE ATT&CK technique ids
    r"|__\w+__"  # dunders
    r"|[A-Z][A-Z0-9_]{2,}"  # env vars and SHOUTY constants defined elsewhere
    r")$"
)

AUTHORED_TAG = "authored-v1"
VERIFIED_TAG = "verified-v1"

_UNIVERSE: set[str] | None = None


def repo_identifiers(repo_root: Path | None = None) -> set[str]:
    """Every identifier defined anywhere in the repo's Python, plus module stems.

    Grounding is checked against the whole repo rather than only the cited file.
    A unit legitimately names a symbol it interacts with but does not define —
    `render_all_generated_blocks` in a design unit citing a markdown source, for
    instance. Scoping the universe to cited files rejected 59 of 70 hand-authored
    units on first calibration, all of them correct. The check that survives is
    the one that matters: an identifier appearing *nowhere* in the repo is
    invented, and that is the failure mode a model summarising code actually has.
    """
    global _UNIVERSE
    if _UNIVERSE is not None:
        return _UNIVERSE
    root = repo_root or _REPO_ROOT
    names: set[str] = set()
    for path in root.rglob("*.py"):
        # Check parts relative to `root`, not the absolute path — otherwise a
        # dot-prefixed ancestor (e.g. `.claude/worktrees/...`) zeroes the
        # whole universe silently.
        rel_parts = path.relative_to(root).parts
        if any(p.startswith(".") or p == "__pycache__" for p in rel_parts):
            continue
        names.add(path.stem)
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        names.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", src))
    for pattern in ("*.yaml", "*.yml", "*.json", "*.toml", "*.sh"):
        for path in root.rglob(pattern):
            rel_parts = path.relative_to(root).parts
            if any(p.startswith(".") or p == "node_modules" for p in rel_parts):
                continue
            try:
                names.update(
                    re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", path.read_text(errors="replace"))
                )
            except OSError:
                continue
    _UNIVERSE = names
    return names


def reset_universe() -> None:
    """Drop the cached identifier universe (tests, or after generating code)."""
    global _UNIVERSE
    _UNIVERSE = None


def _cited_code_paths(unit) -> list[str]:
    out = []
    for src in unit.sources:
        raw = (src.path or "").split("#", 1)[0].strip()
        if raw.endswith(".py") and not raw.startswith(("http://", "https://", "/")):
            out.append(raw)
    return out


def check_grounding(unit, repo_root: Path | None = None) -> QualityIssue | None:
    """Backticked identifiers must exist somewhere in the repo, or look external."""
    spans = [x.strip() for x in _CODE_SPAN_RE.findall(_FENCE_RE.sub(" ", unit.body))]
    idents = [x for x in spans if _IDENT_RE.match(x)]
    if not idents:
        return None
    known = repo_identifiers(repo_root)
    unknown = [x for x in idents if x not in known and not _EXTERNAL_OK.match(x)]
    grounded = 1.0 - len(unknown) / len(idents)
    if grounded < MIN_GROUNDED_RATIO:
        return QualityIssue(
            unit.id,
            "grounding",
            f"{len(unknown)}/{len(idents)} backticked identifiers appear nowhere in the "
            f"repo ({grounded:.0%} grounded) — likely invented: "
            f"{', '.join(sorted(set(unknown))[:6])}",
        )
    return None


def check_substance(unit, repo_root: Path | None = None) -> QualityIssue | None:
    """Prose floor, plus proof the unit says more than the AST already does.

    The word floor applies to every live unit. The tag distinction was retired in
    TASK_WIKI_ZERO_DEBT_V1: after the legacy corpus was re-grounded against code,
    there is no ungrounded prose left to exempt, so the floor is universal. The
    API-overlap ceiling applies to every unit regardless, because restating a
    projection is never adequate.
    """
    words = prose_words(unit.body)
    if len(words) < MIN_PROSE_WORDS:
        return QualityIssue(
            unit.id, "substance", f"{len(words)} prose words, floor is {MIN_PROSE_WORDS}"
        )
    paths = _cited_code_paths(unit)
    if len(paths) != 1:
        return None
    try:
        from portal.platform.wiki.adapters.seed_api import derive_body

        derived = derive_body(paths[0], repo_root)
    except Exception:  # noqa: BLE001 — derivation is an optional comparison, not a gate
        return None
    dwords = {w.lower() for w in prose_words(derived)}
    if not dwords:
        return None
    uwords = [w.lower() for w in words]
    if not uwords:
        return None
    overlap = sum(1 for w in uwords if w in dwords) / len(uwords)
    if overlap > MAX_API_OVERLAP:
        return QualityIssue(
            unit.id,
            "substance",
            f"{overlap:.0%} of prose overlaps the derived API projection "
            f"(ceiling {MAX_API_OVERLAP:.0%}) — restates the surface instead of explaining it",
        )
    return None


def check_structure(unit) -> QualityIssue | None:
    """A `## Why` section with real content — the part no projection can supply.

    Applies to every live unit. The tag distinction was retired in
    TASK_WIKI_ZERO_DEBT_V1: the re-grounded corpus adopted the `## Why` convention
    throughout, so there is no legacy prose left to exempt from it.
    """
    why = why_section(unit.body)
    if not why:
        return QualityIssue(unit.id, "structure", "no `## Why` section")
    n = len(prose_words(why))
    if n < MIN_WHY_WORDS:
        return QualityIssue(
            unit.id, "structure", f"`## Why` has {n} prose words, floor is {MIN_WHY_WORDS}"
        )
    return None


_QUANTITY_RE = re.compile(
    r"\b\d[\d,]*\s+(?:workspaces|personas|MCP servers|servers|backends|techniques|"
    r"checks|units|tools|models|scenarios|ports)\b",
    re.IGNORECASE,
)


def check_claim_binding(unit) -> QualityIssue | None:
    """A stated live quantity must be bound to a probe, not typed once and forgotten.

    This is the "grounded in facts" requirement made mechanical. `BS` already
    evaluates declared claims against live probes; what it cannot do is notice a
    figure that was never declared. README said 60 benchmark workspaces against a
    live 65 for exactly that reason. A unit that states a countable platform
    figure and declares no claim for it is not grounded — it is a number that
    will be wrong later with nothing to catch it.

    Applies to every live unit. The legacy-corpus exemption was retired in
    TASK_WIKI_ZERO_DEBT_V1 once the re-grounded store bound or reworded every
    figure.
    """
    prose = _FENCE_RE.sub(" ", unit.body)
    hits = [m.group(0).strip() for m in _QUANTITY_RE.finditer(prose)]
    if not hits:
        return None
    if not (unit.claims or []):
        return QualityIssue(
            unit.id,
            "claim-binding",
            f"states live quantity {hits[0]!r} with no `claims:` entry — bind it to a probe "
            f"or reword to avoid a figure that cannot be checked",
        )
    return None


def _shingles(words: list[str], k: int = 5) -> set[str]:
    lowered = [w.lower() for w in words]
    return {" ".join(lowered[i : i + k]) for i in range(max(0, len(lowered) - k + 1))}


def check_distinctness(units) -> list[QualityIssue]:
    """Flag near-duplicate prose across units — template filler at scale."""
    prepared = []
    for unit in units:
        sh = _shingles(prose_words(unit.body))
        if len(sh) >= 10:
            prepared.append((unit.id, sh))
    issues: list[QualityIssue] = []
    seen: list[tuple[str, set[str]]] = []
    for uid, sh in prepared:
        for other_id, other in seen:
            inter = len(sh & other)
            if inter / min(len(sh), len(other)) > MAX_PROSE_SIMILARITY:
                issues.append(
                    QualityIssue(
                        uid,
                        "distinctness",
                        f"prose is {inter / min(len(sh), len(other)):.0%} shared with "
                        f"{other_id} — template filler, not authorship",
                    )
                )
                break
        else:
            seen.append((uid, sh))
    return issues


def assess(units, repo_root: Path | None = None) -> QualityReport:
    """Run every check. A unit with no issues is coverage; one with issues is not."""
    root = repo_root or _REPO_ROOT
    issues: list[QualityIssue] = []
    for unit in units:
        for probe in (
            lambda u: check_grounding(u, root),
            lambda u: check_substance(u, root),
            lambda u: check_structure(u),
            lambda u: check_claim_binding(u),
        ):
            issue = probe(unit)
            if issue is not None:
                issues.append(issue)
    issues.extend(check_distinctness(units))

    failed = {i.unit_id for i in issues}
    by_check: dict[str, int] = {}
    for i in issues:
        by_check[i.check] = by_check.get(i.check, 0) + 1
    return QualityReport(
        passing=tuple(sorted(u.id for u in units if u.id not in failed)),
        issues=tuple(issues),
        by_check=by_check,
    )


def calibrate(repo_root: Path | None = None) -> dict:
    """Run the gate against the pre-existing authored corpus.

    The instrument is validated before it is trusted: if this reports a high
    rejection rate on units that were hand-written by an operator, the thresholds
    are wrong, not the units. Used by the gate's own test and by the authoring
    task's Phase 1.
    """
    from portal.platform.wiki.store import load_all

    root = repo_root or _REPO_ROOT
    # Machine-seeded families. Technique signatures are ids like
    # `unit-T1021.002-signature`, seeded by seed_security — not authorship.
    machine = ("unit-fact-", "unit-code-", "unit-api-")
    seeded = re.compile(r"^unit-T\d{4}(?:\.\d{3})?-signature$")
    authored = [
        u
        for u in load_all()
        if not u.id.startswith(machine)
        and not seeded.match(u.id)
        and _cited_code_paths(u)
        and "derived" not in (u.tags or [])
    ]
    report = assess(authored, root)
    return {
        "authored_units_examined": len(authored),
        "passing": len(report.passing),
        "failing": len(authored) - len(report.passing),
        "pass_rate": round(100.0 * len(report.passing) / len(authored), 1) if authored else 0.0,
        "by_check": report.by_check,
        "sample_issues": [str(i) for i in report.issues[:12]],
    }
