"""Semantic CIP-007 revision comparison (END_TO_END Phase 10 / slice P4).

A revision delta is a change in OBLIGATIONS, not in rows. This module pairs
revision-specific duties across two store revisions by semantic duty
correspondence (``duty_lineage``'s normalized-text similarity — part numbers
are never the identity rule), then classifies each paired delta with the
obligation taxonomy (quantity, scope, recordkeeping, evidence, rewording,
editorial). Added and removed duties are first-class rows. Every row carries
the verbatim before/after clause text so the delta is inspectable — this is
not a raw register diff repeated under an ``interpreted_delta`` key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from portal.modules.compliance.core.duty_lineage import normalize_duty_text, similarity

#: obligation-level taxonomy (operations.diff's vocabulary, store-side)
NO_REVIEW_WORK = {"EDITORIAL_ONLY"}
QUANTITY_RE = re.compile(
    r"(?<![\d.])(\d+)(?![\d.])\)?\s+((?:calendar|business)\s+)?(day|month|year|hour)s?\b", re.I
)


@dataclass
class DutyRow:
    node_id: str
    requirement: str
    part: str
    clauses: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(self.clauses).strip()


def _duty_rows(repo: Any, revision_id: str) -> dict[str, DutyRow]:
    rows = repo._conn.execute(
        """SELECT rn.node_id, rn.requirement, rn.part,
                  COALESCE(oa.clause_text, '') AS clause
           FROM requirement_nodes rn
           LEFT JOIN obligation_atoms oa ON oa.node_id = rn.node_id
           WHERE rn.standard_revision_id = ?
           ORDER BY rn.node_id, oa.atom_id""",
        (revision_id,),
    ).fetchall()
    duties: dict[str, DutyRow] = {}
    for node_id, requirement, part, clause in rows:
        duty = duties.setdefault(node_id, DutyRow(node_id, requirement, part))
        if clause:
            duty.clauses.append(clause)
    return duties


def _revision_ids(repo: Any, family: str, version: str) -> list[str]:
    """The store's requirement-node revision identities for one standard
    version (nodes carry the identity; standard_revisions schemes vary)."""
    prefix = f"{family}-{version} "
    return [
        row[0]
        for row in repo._conn.execute(
            "SELECT DISTINCT standard_revision_id FROM requirement_nodes WHERE node_id LIKE ?",
            (prefix + "%",),
        ).fetchall()
    ]


def _quantities(text: str) -> list[str]:
    return [
        f"{m.group(1)} {m.group(2) or ''}{m.group(3).lower()}".replace("  ", " ")
        for m in QUANTITY_RE.finditer(text)
    ]


def classify_delta(before_text: str, after_text: str) -> tuple[str, dict[str, Any]]:
    """Obligation-taxonomy classification of one paired duty's delta."""
    bq, aq = _quantities(before_text), _quantities(after_text)
    detail: dict[str, Any] = {}
    if bq != aq:
        detail["quantity_before"] = bq
        detail["quantity_after"] = aq
        tightened = (
            _min_days(bq) is not None
            and _min_days(aq) is not None
            and _min_days(aq) < _min_days(bq)
        )
        return ("QUANTITY_TIGHTENED" if tightened else "QUANTITY_CHANGED"), detail
    low_b, low_a = before_text.lower(), after_text.lower()
    if any(
        k in low_a for k in ("applicable system", "high impact", "medium impact", "low impact")
    ) != any(
        k in low_b for k in ("applicable system", "high impact", "medium impact", "low impact")
    ):
        return "SCOPE_CHANGE", detail
    if any(k in low_a for k in ("retain", "retention", "record")) != any(
        k in low_b for k in ("retain", "retention", "record")
    ):
        return "RECORDKEEPING_CHANGE", detail
    if "evidence" in low_a or "measure" in low_a:
        return "EVIDENCE_CHANGE", detail
    norm_b, norm_a = normalize_duty_text(before_text), normalize_duty_text(after_text)
    if norm_b == norm_a:
        return "EDITORIAL_ONLY", detail
    detail["similarity"] = round(similarity(before_text, after_text), 3)
    return "REWORDING", detail


def _min_days(quantities: list[str]) -> int | None:
    days = [int(q.split()[0]) for q in quantities if q.split()[-1] == "day"]
    return min(days) if days else None


def semantic_diff(
    repo: Any,
    *,
    family: str = "CIP-007",
    version_before: str = "6",
    version_after: str = "7.1",
) -> dict[str, Any]:
    """The semantic obligation delta between two revisions of one family."""
    before_duties: dict[str, DutyRow] = {}
    after_duties: dict[str, DutyRow] = {}
    for rid in _revision_ids(repo, family, version_before):
        before_duties.update(_duty_rows(repo, rid))
    for rid in _revision_ids(repo, family, version_after):
        after_duties.update(_duty_rows(repo, rid))

    pairs = [
        (similarity(a.text, b.text), a_id, b_id)
        for a_id, a in before_duties.items()
        for b_id, b in after_duties.items()
    ]
    pairs.sort(key=lambda x: (-x[0], x[1], x[2]))
    used_a: set[str] = set()
    used_b: set[str] = set()
    matched: list[tuple[str, str]] = []
    for score, a_id, b_id in pairs:
        if score < 0.75 or a_id in used_a or b_id in used_b:
            continue
        used_a.add(a_id)
        used_b.add(b_id)
        matched.append((a_id, b_id))

    rows: list[dict[str, Any]] = []
    for a_id, b_id in sorted(matched):
        before_text, after_text = before_duties[a_id].text, after_duties[b_id].text
        delta_type, detail = classify_delta(before_text, after_text)
        rows.append(
            {
                "duty_before": a_id,
                "duty_after": b_id,
                "relation": "PAIRED",
                "delta_type": delta_type,
                "detail": detail,
                "text_before": before_text,
                "text_after": after_text,
                "creates_review_work": delta_type not in NO_REVIEW_WORK,
            }
        )
    for a_id in sorted(set(before_duties) - used_a):
        rows.append(
            {
                "duty_before": a_id,
                "duty_after": "",
                "relation": "REMOVED",
                "delta_type": "OBLIGATION_REMOVED",
                "detail": {},
                "text_before": before_duties[a_id].text,
                "text_after": "",
                "creates_review_work": True,
            }
        )
    for b_id in sorted(set(after_duties) - used_b):
        rows.append(
            {
                "duty_before": "",
                "duty_after": b_id,
                "relation": "ADDED",
                "delta_type": "OBLIGATION_ADDED",
                "detail": {},
                "text_before": "",
                "text_after": after_duties[b_id].text,
                "creates_review_work": True,
            }
        )
    return {
        "family": family,
        "version_before": version_before,
        "version_after": version_after,
        "rows": rows,
        "census": {
            "paired": len(matched),
            "added": len(after_duties) - len(used_b),
            "removed": len(before_duties) - len(used_a),
            "creating_review_work": sum(1 for r in rows if r["creates_review_work"]),
        },
    }
