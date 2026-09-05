"""Q08 (intentional strictness) and Q09 (unused flexibility) — P5/T2.

Design §9: "Are internal rules more restrictive, and is that intentional?"
and "Where does regulation permit flexibility we do not use?" Both reuse
``constraints.py``'s comparator direction and ``tiers.py``'s quantity
extraction; neither requires the (unpopulated) canonical obligation-atom
tables to answer at the text-span level this task's real corpus supports.

Both functions are pure text-in/dict-out — no I/O, no DB — so a caller
(the MCP tool) supplies the governing register text and an internal
document span, and owns looking up any recorded intentionality decision.
"""

from __future__ import annotations

import re

from portal.modules.compliance.core.constraints import (
    Quantity,
    compare_constraint,
    infer_constraint_kind,
)
from portal.modules.compliance.core.tiers import _quant_claims

_ALTERNATIVE_RE = re.compile(
    r"[^.]*\b(?:may|alternatively|at (?:its|their|the (?:responsible entity|entity)'s) discretion|"
    r"or, in the alternative,)\b[^.]*\.",
    re.I,
)


def assess_intentionality(governing_text: str, internal_text: str) -> dict:
    """Compare every quantitative claim in ``internal_text`` against the
    matching-kind claim in ``governing_text``. Direction-aware via
    ``compare_constraint`` (F05/P5.3) — a shorter internal max_interval is
    stricter, a longer internal min_retention is stricter, never the
    reverse. Returns one comparison per internal claim whose ``(unit,
    qualifier)`` matches a governing claim; claims with no matching unit
    are reported as ``no_comparable_governing_claim``, never silently
    dropped. Intentionality itself (whether a stricter internal rule was a
    deliberate business decision) is NOT determined here — this function
    has no access to ``policy_decisions``; the caller attaches that."""
    governing_claims = _quant_claims(governing_text)
    internal_claims = _quant_claims(internal_text)
    comparisons: list[dict] = []
    for value, unit, qualifier, verbatim in internal_claims:
        kind = infer_constraint_kind(verbatim) or infer_constraint_kind(internal_text)
        internal_q = Quantity(value=value, unit=unit, qualifier=qualifier)
        match = next(
            (
                g
                for g in governing_claims
                if Quantity(value=g[0], unit=g[1], qualifier=g[2]).key == internal_q.key
            ),
            None,
        )
        if match is None:
            comparisons.append(
                {
                    "internal_claim": verbatim,
                    "result": "no_comparable_governing_claim",
                    "reason": f"no governing claim shares unit/qualifier {internal_q.key}",
                }
            )
            continue
        if kind is None:
            comparisons.append(
                {
                    "internal_claim": verbatim,
                    "governing_claim": match[3],
                    "result": "kind_undetermined",
                    "reason": "no max_interval/min_retention cue found near either claim — "
                    "cannot pick a comparator direction without guessing",
                }
            )
            continue
        governing_q = Quantity(value=match[0], unit=match[1], qualifier=match[2])
        result, reason = compare_constraint(kind, governing_q, internal_q)
        comparisons.append(
            {
                "internal_claim": verbatim,
                "governing_claim": match[3],
                "kind": kind,
                "result": result,
                "reason": reason,
            }
        )
    return {
        "governing_claims": [c[3] for c in governing_claims],
        "internal_claims": [c[3] for c in internal_claims],
        "comparisons": comparisons,
    }


def find_flexibility(governing_text: str) -> dict:
    """Sourced-alternative detection (Q09) — cue-word only, NOT semantic
    obligation modeling. Finds sentences in ``governing_text`` carrying an
    explicit permissive-alternative marker ("may", "alternatively", "at
    its discretion") and returns them verbatim as candidate flexibility.
    Never produces a recommendation to relax a control — that judgment is
    explicitly left to the caller/SME (design anti-shortcut list)."""
    matches = [m.group(0).strip() for m in _ALTERNATIVE_RE.finditer(governing_text)]
    return {
        "candidate_alternatives": matches,
        "note": "cue-word detection only — each candidate is a verbatim sourced sentence, "
        "not a recommendation; confirm applicability and any conditions before considering "
        "adoption, and never treat a forbidden/conditional alternative as unconditional",
    }
