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

``recompute`` (CLI) re-derives integrity for every transcript under one or
more run dirs at a given ``--min-quote-words`` - after the P6.0 calibration,
every run's diagnostics are recomputed with the calibrated value. Output is
local only.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

MIN_QUOTE_WORDS = 4
#: the persona's literal example tokens (both sides): copying one is never a
#: citation. ``R-a1b2c3`` survived P1's scrub of the operator-side example and
#: B0 measured it copied into answers.
_PLACEHOLDER = re.compile(r"\b(?:[OR]-xxxxxx|[OR]-a1b2c3)\b", re.I)

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


def integrity(
    store: Any, answer: str, *, min_quote_words: int = MIN_QUOTE_WORDS, question: str = ""
) -> dict:
    """Claim-line citation integrity of ``answer`` against ``store``."""

    answer = str(answer or "")
    quote_records: list[dict] = []
    token_records: list[dict] = []
    fabricated: list[str] = []
    sides: set[str] = set()
    lines: list[dict] = []
    for raw_line in answer.splitlines():
        measured = _measure_line(store, raw_line, min_quote_words, _question_fold(question))
        if measured is None:
            continue
        quote_records.extend(measured["quotes"])
        if not measured["citing"]:
            continue
        token_records.extend(measured["tokens"])
        fabricated.extend(measured["fabricated"])
        sides.update(measured["sides"])
        lines.append(measured)
    _forgive_mistyped(lines)
    ungrounded = [line["claim"] for line in lines if not line["grounded"]]
    return {
        "quotes": quote_records,
        "tokens": token_records,
        "fabricated_tokens": sorted(set(fabricated)),
        "placeholder_tokens": sorted({t for t in fabricated if _PLACEHOLDER.fullmatch(t)}),
        "sides_evidenced": sorted(sides),
        "ungrounded_lines": ungrounded,
        "n_claims": len(lines),
        "lines": lines,
        "grounded": bool(lines) and not ungrounded,
    }


def _token_record(store: Any, token: str) -> dict:
    entry = resolve_token(store, token)
    if entry is None:
        return {"token": token, "resolved": False}
    return {"token": token, "resolved": True, "section_id": entry.get("section_id")}


def _question_fold(question: str) -> str:
    from portal.modules.compliance.core.citation_by_quote import _fold

    return _fold(question) if question.strip() else ""


def _is_question_quote(quote: str, question_fold: str) -> bool:
    """A span that restates the user's own question cites nothing in the store."""
    from portal.modules.compliance.core.citation_by_quote import _fold

    folded = _fold(quote)
    return bool(question_fold and folded and folded in question_fold)


def _quote_record(store: Any, quote: str, min_quote_words: int, question_fold: str = "") -> dict:
    from portal.modules.compliance.core.citation_by_quote import resolve_quote

    if _is_question_quote(quote, question_fold):
        return {"quote": quote, "status": "question_quote", "sections": []}
    if len(quote.split()) < min_quote_words:
        return {"quote": quote, "status": "not_evidence", "sections": []}
    hits = resolve_quote(store, quote)
    return {"quote": quote, "status": "resolved" if hits else "unresolved", "sections": hits or []}


def _forgive_mistyped(lines: list[dict]) -> None:
    """A line whose only support is an id that is a small-edit copy of an id
    that DID resolve elsewhere in the answer restates present support, so it
    stays grounded (the token itself stays reported as fabricated, as typed).
    Moved from ``ask_conversational._grounding`` so all three harnesses apply
    the same rule."""
    from portal.modules.compliance.core.answer_contract import _mistyped_variant_of

    resolving = [t["token"] for line in lines for t in line["tokens"] if t["resolved"]]
    for line in lines:
        if not line["grounded"]:
            unresolved = [t["token"] for t in line["tokens"] if not t["resolved"]]
            line["grounded"] = any(_mistyped_variant_of(raw, resolving) for raw in unresolved)


def _measure_line(
    store: Any, raw_line: str, min_quote_words: int, question_fold: str = ""
) -> dict | None:
    """One line's integrity, or None when it carries no token and no quote.

    A line whose only quoted spans are under ``min_quote_words`` and which
    carries no token is NOT a citing line (``citing: False``): its spans are
    reported as ``not_evidence`` but it is neither a claim nor ungrounded — a
    scare-quoted term ("stricter", "need to know") cites nothing, so it cannot
    fail to ground. B0 measured 9 lines failed on exactly that. A span that
    restates the user's question (``question``) is ``question_quote`` and
    likewise cites nothing."""
    from portal.modules.compliance.core.answer_contract import SECTION_ID_PATTERN
    from portal.modules.compliance.core.citation_by_quote import quoted_spans

    stripped = raw_line.strip()
    if not stripped:
        return None
    tokens_here = re.findall(rf"\b{SECTION_ID_PATTERN}\b", stripped, re.I)
    tokens_here += re.findall(r"\b[OR]-[0-9a-f]{6}\b", stripped, re.I)
    tokens_here += _PLACEHOLDER.findall(stripped)  # the placeholder always counts as fabricated
    tokens_here = list(dict.fromkeys(tokens_here))
    quotes_here = quoted_spans(stripped)
    if not tokens_here and not quotes_here:
        return None
    if not tokens_here and all(
        len(q.split()) < min_quote_words or _is_question_quote(q, question_fold)
        for q in quotes_here
    ):
        return {
            "claim": stripped,
            "citing": False,
            "quotes": [
                _quote_record(store, q, min_quote_words, question_fold) for q in quotes_here
            ],
        }

    tokens = [_token_record(store, token) for token in tokens_here]
    line_quotes = [
        _quote_record(store, quote, min_quote_words, question_fold) for quote in quotes_here
    ]
    line_ids = [str(t["section_id"]) for t in tokens if t["resolved"]]
    line_ids += [sid for q in line_quotes for sid in q["sections"]]
    line_sides = {side for sid in line_ids if (side := _section_side(store, sid))}
    resolved_tokens = [t["token"] for t in tokens if t["resolved"]]
    fabricated = [t["token"] for t in tokens if not t["resolved"]]

    grounded = bool(line_ids)
    return {
        "claim": stripped,
        "citing": True,
        "resolved_tokens": sorted(set(resolved_tokens)),
        "quotes": line_quotes,
        "tokens": tokens,
        "fabricated": fabricated,
        "section_ids": sorted(set(line_ids)),
        "sides": sorted(line_sides),
        "grounded": grounded,
    }


def recompute(store: Any, run_dirs: list[pathlib.Path], min_quote_words: int) -> list[dict]:
    """Integrity for every ``transcripts/*.json`` answer under ``run_dirs``."""
    rows: list[dict] = []
    for run_dir in run_dirs:
        for transcript in sorted((run_dir / "transcripts").glob("*.json")):
            try:
                data = json.loads(transcript.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            result = integrity(
                store, str(data.get("answer") or ""), min_quote_words=min_quote_words
            )
            result.pop("lines", None)
            rows.append({"run_dir": str(run_dir), "transcript": transcript.name, **result})
    return rows


def main(argv: list[str] | None = None) -> int:
    from scripts.compliance.truth import _local

    ap = argparse.ArgumentParser(description="Recompute citation integrity over run dirs.")
    ap.add_argument("run_dirs", nargs="+", type=pathlib.Path)
    ap.add_argument("--min-quote-words", type=int, default=MIN_QUOTE_WORDS)
    ap.add_argument("--out", type=pathlib.Path, required=True, help="a .jsonl file (local only)")
    args = ap.parse_args(argv)
    refused = _local.refusal(args.out, "recomputed integrity")
    if refused:
        print(refused, file=sys.stderr)
        return 2
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    try:
        rows = recompute(repo, args.run_dirs, args.min_quote_words)
    finally:
        repo.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"WROTE {args.out} ({len(rows)} transcripts, min_quote_words={args.min_quote_words})")
    return 0


if __name__ == "__main__":
    if __package__ in (None, ""):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
    raise SystemExit(main())
