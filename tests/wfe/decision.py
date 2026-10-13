"""The decision rule (cause C4). Specified in docs/WFE_ROOT_CAUSES_20261013.md,
"Decision rule"; pinned by tests/wfe/tests/test_wfe_decision.py."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from math import comb

from tests.wfe.schema import MODEL_QUALITY_OUTCOMES, Outcome

DECISION_FLOOR = 30
ALPHA = 0.05
MAX_EXCLUDED_FRAC = 0.10
SCREEN_MIN_TASKS = 8
SCREEN_DROP_MARGIN = 3

BETTER, WORSE, NOT_SEPARATED, NO_DECISION = "BETTER", "WORSE", "NOT_SEPARATED", "NO_DECISION"
DROP, ADVANCE, MISSING = "DROP", "ADVANCE", "MISSING"
ELIGIBLE, INELIGIBLE, NOT_VETTABLE = "ELIGIBLE", "INELIGIBLE", "NOT_VETTABLE"
CONFIRMED = {BETTER, WORSE, NOT_SEPARATED, NO_DECISION}

_GRADEABLE = {o.value for o in MODEL_QUALITY_OUTCOMES}


@dataclass
class Cell:
    verdict: str
    reason: str = ""
    n: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    p: float | None = None
    excluded: dict = field(default_factory=dict)


def key(row: dict) -> tuple[str, str]:
    return row["suite"], row["task_id"]


def task_scores(rows: list[dict], repeats: int) -> tuple[dict, dict]:
    """{(suite, task): pass fraction} over stored zero-based repeats; {(suite, task): reason} otherwise."""
    by = defaultdict(list)
    for r in rows:
        by[key(r)].append(r)
    want = set(range(repeats))
    scores, excluded = {}, {}
    for k, rs in by.items():
        reps = [r["repeat"] for r in rs]
        bad = sorted({r["outcome"] for r in rs if r["outcome"] not in _GRADEABLE})
        if bad:
            excluded[k] = f"ungradeable: {','.join(bad)}"
        elif sorted(reps) != sorted(want):
            excluded[k] = f"repeats {sorted(reps)} of {sorted(want)}"
        else:
            scores[k] = sum(r["outcome"] == Outcome.PASS.value for r in rs) / repeats
    return scores, excluded


def pair(
    inc_rows: list[dict], cand_rows: list[dict], expected: set, repeats: int
) -> tuple[dict, dict]:
    """Paired scores over expected tasks both arms completed; why every other one is excluded."""
    unexpected = sorted({key(r) for r in [*inc_rows, *cand_rows]} - set(expected))
    if unexpected:
        raise ValueError(f"rows for tasks outside the expected set: {unexpected[:5]}")
    si, ei = task_scores(inc_rows, repeats)
    sc, ec = task_scores(cand_rows, repeats)
    excluded = {}
    for k in expected:
        if k in si and k in sc:
            continue
        why = [
            f"incumbent {ei.get(k, 'missing')}" if k not in si else "",
            f"candidate {ec.get(k, 'missing')}" if k not in sc else "",
        ]
        excluded[k] = "; ".join(w for w in why if w)
    return {k: (si[k], sc[k]) for k in expected if k in si and k in sc}, excluded


def sign_test_p(wins: int, losses: int) -> float:
    """Exact two-sided sign test; ties already dropped."""
    n = wins + losses
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(wins, losses) + 1)) / 2**n)


def _counts(pairs: dict) -> tuple[int, int, int]:
    d = [c - i for i, c in pairs.values()]
    return sum(x > 0 for x in d), sum(x < 0 for x in d), sum(x == 0 for x in d)


def confirm(
    inc_rows: list[dict],
    cand_rows: list[dict],
    expected: set,
    repeats: int = 3,
    arguable: set | frozenset = frozenset(),
) -> Cell:
    """The confirm-tier verdict for one (candidate, workspace) cell."""
    pairs, excluded = pair(inc_rows, cand_rows, expected, repeats)
    if not expected or len(excluded) / len(expected) > MAX_EXCLUDED_FRAC:
        return Cell(
            NO_DECISION,
            f"excluded {len(excluded)}/{len(expected)} tasks",
            len(pairs),
            excluded=excluded,
        )
    if len(pairs) < DECISION_FLOOR:
        return Cell(
            NO_DECISION,
            f"floor: {len(pairs)} < {DECISION_FLOOR} compared tasks",
            len(pairs),
            excluded=excluded,
        )
    w, lo, t = _counts(pairs)
    p = sign_test_p(w, lo)
    if p >= ALPHA:
        return Cell(NOT_SEPARATED, f"sign test p={p:.3f}", len(pairs), w, lo, t, p, excluded)
    lead = w > lo
    worst = {
        k: ((1.0, 0.0) if lead else (0.0, 1.0)) if k in arguable else v for k, v in pairs.items()
    }
    w2, l2, _ = _counts(worst)
    p2 = sign_test_p(w2, l2)
    if p2 >= ALPHA or (w2 > l2) != lead:
        return Cell(
            NO_DECISION,
            f"arguable-sensitive: worst case p={p2:.3f}",
            len(pairs),
            w,
            lo,
            t,
            p,
            excluded,
        )
    return Cell(
        BETTER if lead else WORSE,
        f"sign test p={p:.4f}; worst case p={p2:.4f}",
        len(pairs),
        w,
        lo,
        t,
        p,
        excluded,
    )


def screen(inc_rows: list[dict], cand_rows: list[dict], screen_expected: set) -> Cell:
    """The screen-tier outcome for one cell, from repeat 0 of the screen tasks."""
    pick = [r for r in inc_rows if key(r) in screen_expected and r["repeat"] == 0]
    cand = [r for r in cand_rows if key(r) in screen_expected and r["repeat"] == 0]
    pairs, excluded = pair(pick, cand, screen_expected, 1)
    w, lo, t = _counts(pairs)
    note = f"lost {lo}, won {w} of {len(pairs)} compared screen tasks"
    if len(pairs) < SCREEN_MIN_TASKS:
        return Cell(ADVANCE, f"{note}: too few to drop", len(pairs), w, lo, t, excluded=excluded)
    verdict = DROP if lo - w >= SCREEN_DROP_MARGIN else ADVANCE
    return Cell(verdict, note, len(pairs), w, lo, t, excluded=excluded)


_ELIGIBILITY = (
    (
        lambda f: f.get("family_vettable") is False and f.get("has_capability") is False,
        INELIGIBLE,
        "verified: lacks the family's capability",
    ),
    (
        lambda f: f.get("family_vettable") is False,
        NOT_VETTABLE,
        "the harness cannot measure this family",
    ),
    (
        lambda f: not f.get("in_catalog"),
        MISSING,
        "not in the backends.yaml catalog: intake incomplete",
    ),
    (lambda f: not f.get("available"), MISSING, "not installed or not restorable now"),
    (
        lambda f: not f.get("family_has_suite"),
        MISSING,
        "the workspace's family has no suite at the floor",
    ),
    (
        lambda f: (
            f.get("needs_tools") and f.get("supports_tools") is False and f.get("tools_verified")
        ),
        INELIGIBLE,
        "verified: no tool support",
    ),
    (
        lambda f: (
            f.get("needs_tools") and not (f.get("supports_tools") and f.get("tools_verified"))
        ),
        MISSING,
        "tool support unverified",
    ),
    (
        lambda f: f.get("model_ctx") is None or not f.get("ctx_verified"),
        MISSING,
        "context window unverified",
    ),
    (
        lambda f: f["model_ctx"] < (f.get("workspace_ctx") or 0),
        INELIGIBLE,
        "verified context below the workspace's",
    ),
    (lambda f: f.get("memory_fits") is None, MISSING, "memory footprint unknown"),
    (
        lambda f: f.get("memory_fits") is False,
        INELIGIBLE,
        "verified: does not fit host memory beside pinned services",
    ),
)


def eligibility(f: dict) -> tuple[str, str]:
    """A cell's eligibility from recorded facts (None = unknown, never INELIGIBLE); first match wins."""
    for test, state, reason in _ELIGIBILITY:
        if test(f):
            return state, reason
    return ELIGIBLE, ""


def dispose(
    cells: dict[str, str], intended: set[str], lineage_unique: bool = False
) -> tuple[str, str]:
    """One disposition per model from its per-workspace cell states; first match wins."""
    if not intended:
        return NO_DECISION, "no intended workspace recorded at intake"
    bad_intent = sorted(w for w in intended if cells.get(w) in (INELIGIBLE, None))
    if bad_intent:
        return (
            NO_DECISION,
            f"intended workspace(s) ineligible or absent: {bad_intent}; fix the queue",
        )
    live = {w: s for w, s in cells.items() if s != INELIGIBLE}
    better = sorted(w for w, s in live.items() if s == BETTER)
    if any(live[w] == BETTER for w in intended):
        return (
            "FOLD",
            f"BETTER in {sorted(set(better) & intended)}; also in {sorted(set(better) - intended)}",
        )
    unconfirmed = sorted(w for w in intended if live[w] not in CONFIRMED)
    if unconfirmed:
        return NO_DECISION, f"intended workspace(s) not confirmed: {unconfirmed}"
    if better:
        return "PURPOSE", f"BETTER only outside its intended lane: {better}"
    for state, why in (
        (MISSING, "evidence incomplete"),
        (ADVANCE, "advanced, not confirmed"),
        (NO_DECISION, "inconclusive"),
        (NOT_VETTABLE, "unmeasured capability"),
    ):
        hit = sorted(w for w, s in live.items() if s == state)
        if hit:
            return NO_DECISION, f"{why}: {hit}"
    tied = sorted(w for w, s in live.items() if s == NOT_SEPARATED)
    if tied:
        if lineage_unique:
            return "RETAIN_DIVERSITY", f"not separated in {tied}; only member of its lineage"
        return "REDUNDANT", f"not separated in {tied}; no gain shown anywhere"
    if all(s in (WORSE, DROP) for s in live.values()) and all(live[w] == WORSE for w in intended):
        return "REMOVE", "WORSE in every intended workspace; WORSE or dropped everywhere else"
    return NO_DECISION, "no rule matched"
