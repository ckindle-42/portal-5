#!/usr/bin/env python3
"""One citation-integrity diagnostic for all three compliance harnesses.

P5 (READING_TRUTH_V1). ``integrity`` works claim-line by claim-line over an
answer against the store:

* **quotes** — double-quoted spans resolved by containment over the whole
  store (``citation_by_quote.resolve_quote``); a span shorter than
  ``min_quote_words`` is ``not_evidence`` (a scare quote or fragment proves
  nothing);
* **tokens** — section identifiers resolved by the one resolver
  (``_resolve_token``, moved unchanged from ``ask_conversational``): full id,
  ``cite_as`` token, unique prefix;
* **fabricated_tokens** — tokens that resolve to nothing; the persona's
  placeholder always counts as fabricated;
* **sides_evidenced** — the store's jurisdiction values mapped to sides as
  the conversational judge maps them (internal/operator_note → operator,
  US → regulatory); a bare address that resolves still evidences its side,
  but an unresolved one evidences nothing;
* **ungrounded_lines**, **n_claims**.

The three harnesses (``ask_conversational._judge``,
``ask_product_questions._ask_one``, ``compliance_acceptance.check_workspace_cell``)
derive their citation booleans from this one result — parity is asserted by
test — and every receipt says ``verdict_basis: "mechanical"``: these are
citation-integrity checks, never correctness verdicts.
"""

from __future__ import annotations

import re
from typing import Any

MIN_QUOTE_WORDS = 4
_PLACEHOLDER = re.compile(r"\b[OR]-xxxxxx\b", re.I)

__all__ = ["integrity", "MIN_QUOTE_WORDS", "resolve_token"]


def resolve_token(store: Any, raw: str) -> dict | None:
    """Full id → ``cite_as`` token → unique prefix. Ambiguous or absent
    resolves to None — never a guess, never a near neighbour. (Moved
    unchanged from ``ask_conversational._resolve_token``.)"""
    from portal.modules.compliance.core.section_index import parent_section_id, resolve_sections

    parent = parent_section_id(raw)
    full = raw.split("#")[0].lower()
    resolved = parent_section_id(full)
    got = resolve_sections(store, [resolved])
    if got:
        return got.get(resolved)
    if re.fullmatch(r"[OR]-[0-9a-f]{6}", raw or "", re.I) is not None:
        from portal.modules.compliance.core.addressing import resolve_cite_as

        return resolve_cite_as(store, raw)
    stem, _, hex_prefix = full.partition("-")
    if stem.lower() in ("csection", "isection") and len(hex_prefix) >= 6 and hex_prefix.isalnum():
        rows = store._conn.execute(
            "SELECT section_id FROM source_sections WHERE section_id LIKE ?",
            (f"{stem.lower()}-{hex_prefix.lower()}%",),
        ).fetchall()
        if len(rows) == 1:
            got = resolve_sections(store, [str(rows[0][0])])
            return got.get(str(rows[0][0]))
    return None


def _side_of(jurisdiction: str) -> str:
    jur = (jurisdiction or "").strip()
    if jur in ("internal", "operator_note"):
        return "operator"
    if jur == "US":
        return "regulatory"
    return jur or "unknown"


def _section_side(store: Any, section_id: str) -> str | None:
    row = store._conn.execute(
        """SELECT d.jurisdiction FROM source_sections s
           JOIN document_revisions r ON s.revision_id = r.revision_id
           JOIN source_documents d ON d.logical_id = r.logical_id
           WHERE s.section_id = ?""",
        (section_id,),
    ).fetchall()
    return _side_of(str(row[0][0])) if row else None


def integrity(store: Any, answer: str, *, min_quote_words: int = MIN_QUOTE_WORDS) -> dict:
    """Claim-line citation integrity of ``answer`` against ``store``."""

    answer = str(answer or "")
    quote_records: list[dict] = []
    token_records: list[dict] = []
    fabricated: list[str] = []
    sides: set[str] = set()
    ungrounded: list[str] = []
    lines: list[dict] = []
    for raw_line in answer.splitlines():
        measured = _measure_line(store, raw_line, min_quote_words)
        if measured is None:
            continue
        quote_records.extend(measured["quotes"])
        token_records.extend(measured["tokens"])
        fabricated.extend(measured["fabricated"])
        sides.update(measured["sides"])
        if not measured["grounded"]:
            ungrounded.append(measured["claim"])
        lines.append(measured)
    return {
        "quotes": quote_records,
        "tokens": token_records,
        "fabricated_tokens": sorted(set(fabricated)),
        "sides_evidenced": sorted(sides),
        "ungrounded_lines": ungrounded,
        "n_claims": len(lines),
        "lines": lines,
        "grounded": bool(lines) and not ungrounded,
    }


def _measure_line(store: Any, raw_line: str, min_quote_words: int) -> dict | None:
    """One citing line's integrity, or None when the line cites nothing."""
    from portal.modules.compliance.core.answer_contract import SECTION_ID_PATTERN
    from portal.modules.compliance.core.citation_by_quote import quoted_spans, resolve_quote

    stripped = raw_line.strip()
    if not stripped:
        return None
    tokens_here = re.findall(rf"\b{SECTION_ID_PATTERN}\b", stripped, re.I)
    tokens_here += re.findall(r"\b[OR]-[0-9a-f]{6}\b", stripped, re.I)
    tokens_here += _PLACEHOLDER.findall(stripped)  # the placeholder always counts as fabricated
    quotes_here = quoted_spans(stripped)
    if not tokens_here and not quotes_here:
        return None

    line_ids: list[str] = []
    line_sides: set[str] = set()
    resolved_tokens: list[str] = []
    tokens: list[dict] = []
    fabricated: list[str] = []
    for token in tokens_here:
        entry = resolve_token(store, token)
        if entry is not None:
            resolved_tokens.append(token)
            line_ids.append(str(entry.get("section_id")))
            side = _section_side(store, str(entry.get("section_id")))
            if side:
                line_sides.add(side)
            tokens.append({"token": token, "resolved": True, "section_id": entry.get("section_id")})
        else:
            fabricated.append(token)
            tokens.append({"token": token, "resolved": False})

    line_quotes: list[dict] = []
    for quote in quotes_here:
        if len(quote.split()) < min_quote_words:
            line_quotes.append({"quote": quote, "status": "not_evidence", "sections": []})
            continue
        hits = resolve_quote(store, quote)
        if hits:
            line_quotes.append({"quote": quote, "status": "resolved", "sections": hits})
            line_ids.extend(hits)
            for sid in hits:
                side = _section_side(store, sid)
                if side:
                    line_sides.add(side)
        else:
            line_quotes.append({"quote": quote, "status": "unresolved", "sections": []})

    grounded = bool(line_ids)
    return {
        "claim": stripped,
        "resolved_tokens": sorted(set(resolved_tokens)),
        "quotes": line_quotes,
        "tokens": tokens,
        "fabricated": fabricated,
        "section_ids": sorted(set(line_ids)),
        "sides": sorted(line_sides),
        "grounded": grounded,
    }
