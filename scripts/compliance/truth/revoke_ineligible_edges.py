#!/usr/bin/env python3
"""DATA_TRUTH DD2 — revoke live edges whose endpoints are never eligible.

TOC, furniture and heading-fragment sections were excluded from the index in
D2/D3; Amendment 1 removes them from the edge graph too. The rule is the
integrity check's own ``_ineligible_reason`` (single source of the eligibility
rule); this tool applies it to every LIVE assertion (``status`` not in
``revoked``/``rejected``) and marks each hit ``revoked`` with the reason and
the offending refs recorded in the rationale.

Dry run by default; ``--apply`` writes. The store is backed up (L8) before an
apply. The similarity-proposed edges are NOT read-verified here (Amendment 1:
they stay as proposals) — this pass is purely mechanical endpoint eligibility.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_integrity as di  # noqa: E402 - scripts/ truth module


def find_ineligible(conn: sqlite3.Connection, full: dict[str, str]) -> list[dict]:
    edges = conn.execute(
        "select assertion_id, relation_type, src_ref, dst_ref, derivation, rationale"
        " from relationship_assertions where status not in ('revoked','rejected')"
    ).fetchall()
    hits: list[dict] = []
    for edge in edges:
        reasons = {}
        for side in ("src_ref", "dst_ref"):
            why = di._ineligible_reason(conn, full, str(edge[side]))
            if why:
                reasons[side] = f"{edge[side]} ({why})"
        if reasons:
            hits.append(
                {
                    "assertion_id": str(edge["assertion_id"]),
                    "relation_type": str(edge["relation_type"]),
                    "derivation": str(edge["derivation"] or ""),
                    "reasons": reasons,
                    "rationale": str(edge["rationale"] or ""),
                }
            )
    return hits


def backup_store() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = Path.home() / "portal5-backups" / f"compliance_store-pre-dd2-revoke-{stamp}.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(di._store_path())
    target = sqlite3.connect(str(dest))
    source.backup(target)
    target.close()
    source.close()
    return dest


def apply_revocations(store_path: str, hits: list[dict]) -> int:
    stamp = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(store_path)
    try:
        with conn:
            for hit in hits:
                offending = ", ".join(
                    f"{side}={ref}" for side, ref in sorted(hit["reasons"].items())
                )
                conn.execute(
                    "update relationship_assertions set status='revoked',"
                    " review_state='revoked', decided_at=?, rationale=? where assertion_id=?",
                    (
                        stamp,
                        f"{hit['rationale']} | revoked DD2: ineligible endpoint(s) {offending}",
                        hit["assertion_id"],
                    ),
                )
    finally:
        conn.close()
    return len(hits)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write the revocations (default: dry run)"
    )
    parser.add_argument("--out", type=Path, default=None, help="write the receipt JSON here")
    args = parser.parse_args()

    conn = di._connect()
    try:
        full = di._full_texts(conn)
        hits = find_ineligible(conn, full)
    finally:
        conn.close()
    receipt: dict = {
        "tool": "revoke_ineligible_edges",
        "mode": "apply" if args.apply else "dry_run",
        "live_edges_revoked": len(hits),
        "by_derivation": dict(Counter(hit["derivation"] for hit in hits)),
        "by_reason": dict(
            Counter(
                reason.split("(")[-1].rstrip(")")
                for hit in hits
                for reason in hit["reasons"].values()
            )
        ),
    }
    if args.apply and hits:
        receipt["backup"] = str(backup_store())
        receipt["revoked"] = apply_revocations(di._store_path(), hits)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({**receipt, "hits": hits}, indent=1), encoding="utf-8")
    print(json.dumps(receipt, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
