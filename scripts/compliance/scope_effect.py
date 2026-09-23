#!/usr/bin/env python3
"""CITE_AND_SCOPE_V1 §P2 — measure how document scope changes the population,
before committing the family sweep to one mechanism.

Three measurements, in increasing cost:

1. MECHANICAL (no model): every adjudicated determination from the baseline
   (p6/adjudication_v2.json) re-checked against the scope table — is the
   section's document one that STATES it serves the requirement's family?
   Partitioned by verdict, this is the precision/recall trade every scope
   mechanism would buy, computed exactly on the edges that were adjudicated.

2. LIVE FILTER vs LIVE PRIOR vs OFF (retrieval re-run, two standards): the
   full ``build_links`` for CIP-002-5.1a (the worst case, 0.3103) and
   CIP-007-6 (the family's largest healthy set) under each mode. The proposed
   pair sets are compared against OFF and, where a pair carries a baseline
   verdict, against that verdict — contaminating pairs dropped, supported
   pairs kept is the win condition.

Writes p2/scope_effect.json and prints the comparison.

    uv run python scripts/compliance/scope_effect.py
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import candidate_links, document_scope  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from portal.modules.compliance.core.section_index import resolve_sections  # noqa: E402

FAMILY = re.compile(r"(CIP-\d+)")


def _verdict_pairs(adj_path: pathlib.Path) -> dict[tuple[str, str], str]:
    adj = json.loads(adj_path.read_text())
    out: dict[tuple[str, str], str] = {}
    for r in adj["rows"]:
        out[(str(r["requirement_id"]), str(r["section_id"]))] = str(r["verdict"])
    return out


def _mechanical(
    repo: Repository, scope: dict[str, set[str]], verdicts: dict[tuple[str, str], str]
) -> tuple[dict[str, dict[str, int]], list[dict]]:
    """Every adjudicated pair against the scope table — no model, exact."""
    mechanical: dict[str, dict[str, int]] = {}
    detail: list[dict] = []
    for (req, section_id), verdict in verdicts.items():
        family_m = FAMILY.match(req)
        if not family_m:
            continue
        family = family_m.group(1)
        entry = resolve_sections(repo, [section_id]).get(section_id)
        doc_file = str((entry or {}).get("alias_path") or (entry or {}).get("logical_id") or "")
        served = scope.get(doc_file)
        state = (
            "document_serves_family"
            if served and family in served
            else ("document_has_other_scope" if served is not None else "document_unscoped")
        )
        per = mechanical.setdefault(state, {})
        per[verdict] = per.get(verdict, 0) + 1
        detail.append(
            {
                "requirement": req,
                "section_id": section_id,
                "verdict": verdict,
                "document": doc_file,
                "scope_state": state,
            }
        )
    return mechanical, detail


def _run_live_arms(
    repo: Repository,
    scope: dict[str, set[str]],
    verdicts: dict[tuple[str, str], str],
    standards: list[str],
) -> dict[str, dict]:
    live: dict[str, dict] = {}
    for standard in standards:
        family = FAMILY.match(standard).group(1)  # type: ignore[union-attr]
        arms: dict[str, set[tuple[str, str]]] = {}
        arm_stats: dict[str, dict] = {}
        for mode in ("off", "filter", "prior"):
            links = candidate_links.build_links(repo, standard, scope=scope, scope_mode=mode)
            arms[mode] = {(link.ref, c.section_id) for link in links for c in link.proposed}
            excluded = [
                {
                    "requirement": link.ref,
                    "section_id": c.section_id,
                    "document": c.document,
                    "score": round(c.score, 4),
                }
                for link in links
                for c in link.excluded_by_scope
            ]
            boosted = sum(1 for link in links for c in link.proposed if c.scope_boosted)
            arm_stats[mode] = {
                "n_proposed": sum(len(link.proposed) for link in links),
                "n_requirements": len(links),
                "n_excluded_by_scope": len(excluded),
                "n_boosted_proposed": boosted,
                "excluded_sample": excluded[:40],
            }
            print(
                f"{standard} {mode:6s} proposed={arm_stats[mode]['n_proposed']:4d} "
                f"excluded={arm_stats[mode]['n_excluded_by_scope']:3d} "
                f"boosted={boosted}"
            )
        cross: dict[str, dict[str, int]] = {}
        pair_changes: list[dict] = []
        for mode in ("filter", "prior"):
            counts: dict[str, dict[str, int]] = {}
            for change, pair_set in (
                ("added", arms[mode] - arms["off"]),
                ("removed", arms["off"] - arms[mode]),
            ):
                v = {"SUPPORTED": 0, "UNSUPPORTED": 0, "WRONG_RELATION": 0, "unadjudicated": 0}
                for pair in pair_set:
                    verdict = verdicts.get(pair)
                    v[verdict if verdict in v else "unadjudicated"] += 1
                    pair_changes.append(
                        {
                            "arm": mode,
                            "change": change,
                            "requirement": pair[0],
                            "section_id": pair[1],
                            "baseline_verdict": verdict or "",
                        }
                    )
                counts[change] = v
                print(f"  {mode}: {change}={sum(v.values())} {v}")
            cross[mode] = counts
        live[standard] = {
            "family": family,
            "arm_stats": arm_stats,
            "cross_vs_off": cross,
            "pair_changes": pair_changes,
        }
    return live


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--adj",
        type=pathlib.Path,
        default=REPO_ROOT / "reports/compliance/load_and_converse/p6/adjudication_v2.json",
    )
    ap.add_argument(
        "--out",
        type=pathlib.Path,
        default=REPO_ROOT / "reports/compliance/cite_and_scope/p2/scope_effect.json",
    )
    ap.add_argument("--standards", default="CIP-002-5.1a,CIP-007-6")
    args = ap.parse_args()

    repo = Repository()
    scope = document_scope.scope_map(repo)
    verdicts = _verdict_pairs(args.adj)
    standards = [s.strip() for s in args.standards.split(",") if s.strip()]

    mechanical, mechanical_detail = _mechanical(repo, scope, verdicts)
    live = _run_live_arms(repo, scope, verdicts, standards)

    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "n_scoped_documents": len({k for k in scope if "/" in k}),
        "mechanical_state_counts": {state: dict(counts) for state, counts in mechanical.items()},
        "mechanical_detail": mechanical_detail,
        "live": live,
        "method": (
            "Mechanical: every baseline-adjudicated (requirement, section) pair "
            "against document_scope — evidence-backed families only. Live: "
            "build_links per mode on the named standards; pair sets differenced "
            "against OFF and cross-referenced with baseline verdicts where a "
            "pair was adjudicated. SCOPE_PRIOR was fixed at "
            f"{candidate_links.SCOPE_PRIOR} before any live mode ran."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
