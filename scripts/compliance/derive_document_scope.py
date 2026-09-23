#!/usr/bin/env python3
"""CITE_AND_SCOPE_V1 §P2 — read every operator document ONCE and store what it
states it serves.

One bounded question per document against the document's own opening and scope
material: which NERC CIP standards does this document state it serves, on what
quoted words? Every claim is validated mechanically (the folded quote must be
in the folded document) before it is stored; only evidence-backed claims ever
reach ``build_links``' scope use. The seat is the workspace-bound reading seat;
the store row carries the model, the read size and the raw answer.

    uv run python scripts/compliance/derive_document_scope.py \
        --out reports/compliance/cite_and_scope/p2/document_scope.json

Idempotent: documents already carrying a scope row are skipped unless --force.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import document_scope  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from portal.modules.compliance.core.runtime_config import reading_seat  # noqa: E402

SYSTEM = (
    "You read the opening pages of one operational document from an electric "
    "utility's compliance corpus. Answer one question about it: which NERC CIP "
    "standards does this document STATE that it serves or implements? Decide "
    "only from the text given. Every standard you name MUST come with a quote — "
    "the document's own exact words that say so, copied verbatim. Name EVERY "
    "standard the document states it serves, not only the one in its header: "
    "an umbrella policy whose own table of contents or section headings devote "
    "a section to a standard — e.g. '3.1 Personnel and Training (CIP-004)' — "
    "serves that standard too, and that heading is the quote. A standard named "
    "only as a cross-reference ('see the CIP-003 policy') is not served. If the text "
    "names no standard at all, say so: set states_scope false, leave serves "
    "empty, and give a one-line topic label for what the document is about. Do "
    "not guess a standard from vocabulary or subject matter — a physical "
    "security plan does not serve CIP-002 merely because it mentions control "
    "centers. Answer as JSON."
)

SCHEMA_HINT = (
    '{"states_scope": true|false, "about": "one-line topic", '
    '"serves": [{"standard": "CIP-0XX", "quote": "exact words from the document"}]}'
)


def _ask_seat(model: str, material: str) -> dict:
    from portal.modules.compliance.core.reading_transport import chat

    result = chat(
        model,
        system=f"{SYSTEM}\nSchema: {SCHEMA_HINT}",
        user=material,
        fmt="json",
        num_ctx=32768,
        temperature=0.0,
        timeout=900,
    )
    content = str(result.content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        content = content.split("\n", 1)[1] if "\n" in content else content
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {"_parse_error": content[:2000]}
    return parsed if isinstance(parsed, dict) else {"_parse_error": content[:2000]}


def _read_one(repo: Repository, model: str, logical_id: str, i: int, n: int) -> dict:
    """One document: read, validate, store. Returns the receipt row."""
    material = document_scope.reading_material_for(repo, logical_id)
    if "error" in material:
        print(f"[{i}/{n}] ERROR {logical_id}: {material['error']}")
        return {"logical_id": logical_id, "error": material["error"]}
    answer = _ask_seat(model, material["text"])
    if "_parse_error" in answer:
        print(f"[{i}/{n}] PARSE-ERROR {logical_id}")
        return {"logical_id": logical_id, "error": answer["_parse_error"]}
    claims = document_scope.validate_claims(answer.get("serves") or [], material["text"])
    about = str(answer.get("about", "")).strip()
    states = bool(answer.get("states_scope"))
    document_scope.store_scope(
        repo,
        logical_id=logical_id,
        claims=claims,
        about=about,
        states_scope=states,
        model=model,
        read_chars=material["read_chars"],
        raw=answer,
    )
    valid = sorted({c["standard"] for c in claims if c["quote_valid"]})
    print(f"[{i}/{n}] {logical_id[:58]:58s} scope={states!s:5s} serves={','.join(valid) or '-'}")
    return {
        "logical_id": logical_id,
        "about": about,
        "states_scope": states,
        "claims": claims,
        "families_served": valid,
        "read_chars": material["read_chars"],
        "full_chars": material["full_chars"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="debug: first N documents only")
    args = ap.parse_args()

    repo = Repository()
    model = reading_seat()
    docs = [
        str(r["logical_id"])
        for r in repo._conn.execute(
            """SELECT DISTINCT d.logical_id FROM source_documents d
               JOIN document_revisions r ON r.logical_id = d.logical_id
               JOIN source_sections s ON s.revision_id = r.revision_id
               WHERE d.jurisdiction IN ('internal','operator_note')
               ORDER BY d.logical_id"""
        ).fetchall()
    ]
    already = {
        str(r["logical_id"]) for r in repo._conn.execute("SELECT logical_id FROM document_scope")
    }
    todo = [d for d in docs if args.force or d not in already]
    if args.limit:
        todo = todo[: args.limit]
    print(
        f"{len(docs)} operator documents, {len(already)} scoped, {len(todo)} to read; seat={model}"
    )

    rows: list[dict] = []
    try:
        for i, logical_id in enumerate(todo, 1):
            rows.append(_read_one(repo, model, logical_id, i, len(todo)))
    finally:
        repo.close()

    stored_rows = []
    repo = Repository()
    try:
        for logical_id in docs:
            row = document_scope.scope_row(repo, logical_id)
            if row is not None:
                stored_rows.append(
                    {
                        "logical_id": row["logical_id"],
                        "about": row["about"],
                        "states_scope": row["states_scope"],
                        "claims": row["claims"],
                        "families_served": sorted(document_scope.families_for(row)),
                        "model": row["model"],
                        "read_chars": row["read_chars"],
                        "derived_at": row["derived_at"],
                    }
                )
    finally:
        repo.close()

    n_scope = sum(1 for r in stored_rows if r["states_scope"])
    n_invalid = sum(1 for r in stored_rows for c in r["claims"] if not c["quote_valid"])
    family_hist: dict[str, int] = {}
    for r in stored_rows:
        for f in r["families_served"]:
            family_hist[f] = family_hist.get(f, 0) + 1
    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "seat_model": model,
        "n_operator_documents": len(docs),
        "n_scoped": len(stored_rows),
        "n_stating_scope": n_scope,
        "n_claims_with_invalid_quote": n_invalid,
        "family_histogram": dict(sorted(family_hist.items())),
        "read_budget_chars": document_scope.READING_CHAR_BUDGET,
        "method": (
            "One seat read per document against its own opening and scope "
            "material (head + scope/purpose/applicability headings beyond the "
            "head). Every standard claim carries its quoted evidence and was "
            "validated by folded containment in the document text before "
            "storage; claims with invalid quotes are recorded and excluded "
            "from the scope build_links uses. families_served is "
            "evidence-backed only."
        ),
        "documents": stored_rows,
        "errors": [r for r in rows if "error" in r],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"WROTE {args.out}")
    print(
        f"scoped {len(stored_rows)}/{len(docs)}; state a scope: {n_scope}; "
        f"invalid-quote claims: {n_invalid}"
    )
    print("family histogram:", json.dumps(dict(sorted(family_hist.items()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
