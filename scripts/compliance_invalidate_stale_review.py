#!/usr/bin/env python3
"""Retire review items whose evidence no longer exists in the KB.

The review queue is derived from a KB but holds no dependency on it, so a
re-ingest leaves stale judgment requests behind. Measured after
`operator_corpus` was rebuilt under real docling chunking (2026-09-12): 812
`low_confidence_extraction` and 133 `applicability_scope` items cited chunk ids
that no longer resolve — 945 of 1107.

The `applicability_scope` ones are the dangerous half: their evidence is a
POSITIONAL index (`"chunk 14"`), and the KB went 6009 fixed slices -> 2636
docling chunks, so they do not dangle, they resolve to DIFFERENT TEXT. A
reviewer opening one reads an unrelated passage with no signal anything is
wrong.

These are retired through the ordinary `decide()` path, not deleted: the prior
row flips to SUPERSEDED and a REJECTED row is chained to it, so the audit trail
shows they were invalidated rather than judged. `decided_by` records why.

    uv run python scripts/compliance_invalidate_stale_review.py [--kb-id X] [--apply]

Default is a dry run. Nothing is written without --apply.
"""

from __future__ import annotations

import argparse
from collections import Counter

# Kinds whose evidence `section` is a chunk-level reference. `document_tier`
# cites "title/filename" and `mapping_proposal` a section label — both are
# document-level and survive a re-chunk, so neither is touched here.
CHUNK_SCOPED_KINDS = {"low_confidence_extraction", "applicability_scope"}
DECIDED_BY = "system:stale-evidence-after-reingest"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb-id", default="operator_corpus")
    ap.add_argument("--apply", action="store_true", help="write; default is a dry run")
    a = ap.parse_args()

    from portal.modules.compliance.core import review_queue as rq
    from portal.platform.retrieval import store

    tbl = store.text_table(a.kb_id, create=False, prefix="compliance_")
    live = set(tbl.to_pandas()["chunk_id"].astype(str))
    print(f"{a.kb_id}: {len(live)} live chunks")

    items = rq.open_items()
    stale, kept = [], Counter()
    for it in items:
        if it.kind not in CHUNK_SCOPED_KINDS:
            kept[f"{it.kind} (not chunk-scoped)"] += 1
            continue
        sec = str((it.evidence or [{}])[0].get("section") or "")
        if sec in live:
            kept[f"{it.kind} (evidence still live)"] += 1
        else:
            stale.append(it)

    print(f"\nOPEN items: {len(items)}")
    print(f"stale (chunk evidence gone): {len(stale)}")
    for k, n in Counter(i.kind for i in stale).most_common():
        print(f"   {n:5} {k}")
    for k, n in kept.most_common():
        print(f"   {n:5} KEPT — {k}")

    if not a.apply:
        print("\ndry run — nothing written. Re-run with --apply.")
        return

    done, failed = 0, 0
    for it in stale:
        try:
            rq.decide(it.id, "REJECTED", DECIDED_BY)
            done += 1
        except Exception as exc:  # noqa: BLE001 - report and continue; partial is fine
            failed += 1
            print(f"   ! {it.id}: {exc}")
    print(f"\nretired {done} item(s); {failed} failed")
    print(f"OPEN now: {len(rq.open_items())}")


if __name__ == "__main__":
    main()
