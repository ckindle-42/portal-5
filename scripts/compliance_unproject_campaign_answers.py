#!/usr/bin/env python3
"""Remove the answers an acceptance campaign projected into the corpus.

TASK_COMPLIANCE_PROVE_CIP_007_V1 §P5, rung 0. `compliance_ask` projects every
answer into the corpus as a `derived` source and proposes candidate links from
it — correct product behaviour, and fatal to a repeated measurement: the next
reading of the same question receives its predecessor's answer through
`compliance_links`. Measured on three live Part 2.4 readings, run 1's answer
appeared inside run 2's links payload, run 2's prompt grew by 105 tokens, and
run 2 PASSED a case run 1 failed — at temperature 0.0, where the model cannot be
the variable.

The instrument now asks for `store=False`, so this is a one-off repair of the
runs made before that: it returns the store to the state the case expectations
were derived against, so a re-run measures the fix rather than the wreckage.

The selector is `prompt_version <> ''`, which is exact and self-describing: that
column arrived with the campaign (migration 16), so every answer carrying one is
a campaign answer and every answer predating it is not. A timestamp guess would
be neither.

Nothing is deleted without `--apply`, and the caller is expected to have a
backup: `sqlite3` `.backup` on the live file, or
`uv run python -c "import sqlite3; ..."`. Receipts in `reading_runs` are KEPT —
they are not in any population, and a failed reading is the record most worth
having.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from portal.modules.compliance.core.repository import Repository

    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    args = parser.parse_args()

    repo = Repository()
    try:
        answers = [
            str(row[0])
            for row in repo._conn.execute(
                "SELECT answer_id FROM conversation_answers WHERE prompt_version <> ''"
            ).fetchall()
        ]
        if not answers:
            print("no campaign-projected answers found")
            return 0
        placeholders = ",".join("?" * len(answers))
        logical = [f"answer/{a}" for a in answers]
        lp = ",".join("?" * len(logical))
        revisions = [
            str(row[0])
            for row in repo._conn.execute(
                f"SELECT revision_id FROM document_revisions WHERE logical_id IN ({lp})", logical
            ).fetchall()
        ]
        rp = ",".join("?" * len(revisions)) if revisions else "''"
        sections = (
            [
                str(row[0])
                for row in repo._conn.execute(
                    f"SELECT section_id FROM source_sections WHERE revision_id IN ({rp})",
                    revisions,
                ).fetchall()
            ]
            if revisions
            else []
        )
        print(
            f"campaign answers: {len(answers)}\n"
            f"  projected documents: {len(logical)}\n"
            f"  revisions: {len(revisions)}\n"
            f"  sections: {len(sections)}"
        )
        if not args.apply:
            print("\ndry run — pass --apply to delete (back the store up first)")
            return 0

        sp = ",".join("?" * len(sections)) if sections else "''"
        # Every table with a foreign key onto what is being removed, in
        # dependency order. The first attempt deleted spans, requirement_sections
        # and sections and then hit `FOREIGN KEY constraint failed` on the
        # revisions: `document_texts` holds the projected answer's text and
        # `source_table_cells` its cells, and neither was in the list. The whole
        # delete is ONE transaction, so that failure rolled back cleanly rather
        # than half-removing a document — the fix is to name every referent, not
        # to relax the constraint.
        with repo._lock, repo._conn:
            if sections:
                for table, column in (
                    ("source_spans", "section_id"),
                    ("source_table_cells", "section_id"),
                    ("requirement_sections", "section_id"),
                    ("operator_notes", "section_id"),
                ):
                    repo._conn.execute(f"DELETE FROM {table} WHERE {column} IN ({sp})", sections)
                repo._conn.execute(
                    f"DELETE FROM source_sections WHERE section_id IN ({sp})", sections
                )
            if revisions:
                for table, column in (
                    ("document_texts", "revision_id"),
                    ("authority_assertions", "revision_id"),
                    ("internal_controls", "revision_id"),
                    ("evidence_artifacts", "revision_id"),
                    ("requirement_sections", "revision_id"),
                    ("operator_notes", "revision_id"),
                ):
                    repo._conn.execute(f"DELETE FROM {table} WHERE {column} IN ({rp})", revisions)
                repo._conn.execute(
                    f"DELETE FROM document_revisions WHERE revision_id IN ({rp})", revisions
                )
            repo._conn.execute(f"DELETE FROM source_documents WHERE logical_id IN ({lp})", logical)
            repo._conn.execute(
                f"DELETE FROM answer_citations WHERE answer_id IN ({placeholders})", answers
            )
            repo._conn.execute(
                f"DELETE FROM conversation_answers WHERE answer_id IN ({placeholders})", answers
            )
        print(f"\ndeleted {len(answers)} projected answer(s); reading_runs receipts kept")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
