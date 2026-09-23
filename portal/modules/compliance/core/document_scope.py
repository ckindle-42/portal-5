"""What each operator document is FOR, read once and stored (CITE_AND_SCOPE_V1 P2).

``build_links`` scoped a requirement's population by similarity alone —
``kb_id`` and a score threshold, nothing else — and similarity cannot
distinguish *mentions this asset class* from *implements this requirement*.
CIP-002 was the worst case structurally: categorization has no disambiguating
verb, only the asset nouns every document uses when naming assets, so its
adjudication ran 0.31 against a family at 0.81 while genuine CIP-014 physical
security and CIP-006 plan material filled its population.

The signal that separates them is what each document states it serves. It is a
readable fact over the operator corpus, once per document, with the quoted
words it rests on — so any scope row can be checked by reading the document,
and nothing here is a rule someone wrote about filenames (the layer/tier
sidecar's approach, which no population consumer ever read).

This module owns the STORE side: the reading material for one document, the
quote-evidence validation, the row write, and the lookup ``build_links``
uses. The seat call lives in the driving script.
"""

from __future__ import annotations

import json
import re
from typing import Any

from portal.modules.compliance.core.candidate_links import (
    _norm_for_verbatim as _fold,
)

__all__ = [
    "READING_CHAR_BUDGET",
    "families_for",
    "normalize_family",
    "reading_material_for",
    "scope_map",
    "scope_row",
    "store_scope",
]

#: Characters of the document handed to the reading seat: the opening (title
#: page, purpose, scope sections) carries the scope statement when there is
#: one; a document whose scope lives deeper is read as silent rather than
#: fed whole.
READING_CHAR_BUDGET = 9000

#: Section headings worth including from beyond the opening window.
_SCOPE_HEADING = re.compile(r"\b(scope|purpose|applicab|applies to|references?)\b", re.I)

_FAMILY = re.compile(r"\bCIP[- ]?(\d{2,3})\b", re.I)


def normalize_family(text: str) -> str | None:
    """``"CIP-002-5.1a"`` / ``"CIP 002"`` / ``"CIP-002"`` → ``"CIP-002"``.

    Scope is stated at family granularity in these documents; the population's
    requirement refs are versioned (``CIP-002-5.1a R1 Part 1.2``) and match by
    family prefix. Anything not naming a CIP standard returns None.
    """
    m = _FAMILY.search(str(text or ""))
    return f"CIP-{m.group(1)}" if m else None


def reading_material_for(
    repo: Any, logical_id: str, *, char_budget: int = READING_CHAR_BUDGET
) -> dict[str, Any]:
    """The document's own opening and scope material, as the seat will read it.

    The revision read is the one carrying the most sections (deterministic
    when several revisions exist). The opening window is the head of the
    document; any section whose heading names scope/purpose/applicability is
    appended beyond it, so a scope block buried past the budget still rides.
    """
    rows = repo._conn.execute(
        """SELECT r.revision_id, r.alias_path, COUNT(s.section_id) AS n
           FROM document_revisions r LEFT JOIN source_sections s ON s.revision_id = r.revision_id
           WHERE r.logical_id = ? GROUP BY r.revision_id ORDER BY n DESC, r.revision_id""",
        (logical_id,),
    ).fetchall()
    if not rows:
        return {"error": f"no revision for {logical_id!r}"}
    revision_id = str(rows[0]["revision_id"])
    full = repo.get_document_text(revision_id) or ""
    head = full[:char_budget]
    extra: list[str] = []
    if len(full) > char_budget:
        scope_rows = repo._conn.execute(
            """SELECT s.char_start, s.char_end, s.heading_path, s.title FROM source_sections s
               WHERE s.revision_id = ? AND s.char_start >= ? AND s.char_start >= 0
               ORDER BY s.ordinal""",
            (revision_id, char_budget),
        ).fetchall()
        budget_left = 3000
        for row in scope_rows:
            heading = f"{row['heading_path'] or ''} {row['title'] or ''}"
            if not _SCOPE_HEADING.search(heading):
                continue
            piece = full[int(row["char_start"]) : int(row["char_end"])].strip()
            if piece and piece not in extra:
                extra.append(piece)
                budget_left -= len(piece)
            if budget_left <= 0:
                break
    text = head + ("\n\n".join(extra) if extra else "")
    return {
        "logical_id": logical_id,
        "revision_id": revision_id,
        "text": text,
        "full_chars": len(full),
        "read_chars": len(text),
        "headings_sampled": len(extra),
    }


def validate_claims(claims: list[dict[str, Any]], document_text: str) -> list[dict[str, Any]]:
    """Each claimed standard keeps its quote and gains ``quote_valid`` — is the
    folded quote a substring of the folded document? An invalid quote is
    RECORDED, never silently dropped and never repaired onto nearby words;
    only evidence-backed claims enter the scope ``build_links`` uses."""
    folded_doc = _fold(document_text)
    out: list[dict[str, Any]] = []
    for claim in claims:
        family = normalize_family(str(claim.get("standard", "")))
        quote = str(claim.get("quote", "")).strip()
        valid = bool(family) and bool(quote) and _fold(quote) in folded_doc
        out.append(
            {
                "standard": family or str(claim.get("standard", "")),
                "stated_as": str(claim.get("standard", "")),
                "quote": quote,
                "quote_valid": valid,
            }
        )
    return out


def store_scope(
    repo: Any,
    *,
    logical_id: str,
    claims: list[dict[str, Any]],
    about: str,
    states_scope: bool,
    model: str,
    read_chars: int,
    raw: dict[str, Any],
) -> None:
    """One document's scope, upserted — evidence included, raw answer kept."""
    from portal.modules.compliance.core.temporal import now_iso

    with repo._lock, repo._conn:
        repo._conn.execute(
            """INSERT INTO document_scope(logical_id, standards_json, about, states_scope,
                                          model, read_chars, derived_at, raw_json)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(logical_id) DO UPDATE SET
                   standards_json = excluded.standards_json,
                   about = excluded.about,
                   states_scope = excluded.states_scope,
                   model = excluded.model,
                   read_chars = excluded.read_chars,
                   derived_at = excluded.derived_at,
                   raw_json = excluded.raw_json""",
            (
                logical_id,
                json.dumps(claims),
                str(about or ""),
                1 if states_scope else 0,
                str(model or ""),
                int(read_chars),
                now_iso(),
                json.dumps(raw, default=str),
            ),
        )


def scope_row(repo: Any, logical_id: str) -> dict[str, Any] | None:
    row = repo._conn.execute(
        "SELECT logical_id, standards_json, about, states_scope, model, read_chars, derived_at"
        " FROM document_scope WHERE logical_id = ?",
        (logical_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "logical_id": str(row["logical_id"]),
        "claims": json.loads(row["standards_json"]),
        "about": str(row["about"]),
        "states_scope": bool(row["states_scope"]),
        "model": str(row["model"]),
        "read_chars": int(row["read_chars"]),
        "derived_at": str(row["derived_at"]),
    }


def families_for(row: dict[str, Any] | None) -> set[str]:
    """The evidence-backed families a document serves. Claims whose quote
    failed validation are excluded here — they are visible in the row, but a
    scope constraint is only ever as strong as its quoted evidence."""
    if row is None:
        return set()
    return {
        str(c["standard"])
        for c in row.get("claims", [])
        if c.get("quote_valid") and c.get("standard")
    }


def scope_map(repo: Any) -> dict[str, set[str]]:
    """``document file -> served families`` for every scoped document, keyed by
    logical_id AND alias_path — the projection's ``source_file`` is the alias
    when one exists, and the join must survive both spellings."""
    out: dict[str, set[str]] = {}
    for row in repo._conn.execute(
        """SELECT s.logical_id, r.alias_path FROM document_scope s
           LEFT JOIN document_revisions r ON r.logical_id = s.logical_id"""
    ).fetchall():
        families = families_for(scope_row(repo, str(row["logical_id"])))
        out[str(row["logical_id"])] = families
        alias = str(row["alias_path"] or "")
        if alias:
            out[alias] = families
    return out
