"""Sweep acceptance A/B: map-read a standard's requirements with ``write=False``
and score every determination by the store's own acceptance checks — the
section id resolves, it is an operator section, the sentence is verbatim in it
(the gates ``candidate_links.record_determination`` applies before writing).

Mechanical acceptance only: an accepted edge is one the store WOULD take, not
one an adjudicator has judged correct. Precision needs ``adjudicate``.

    uv run python scripts/compliance/sweep_acceptance_ab.py \\
        --out reports/.../sweep.json [--model TAG] [--standard CIP-007-6] \\
        [--prompt path/to/mapping_prompt.md] [--refs "ref1;ref2"]

``COMPLIANCE_TRANSPORT=ollama-native`` runs the same reads on the rollback
transport, which isolates engine/pipeline effects from prompt effects.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from portal.modules.compliance.core import reading_material, sweep
from portal.modules.compliance.core.candidate_links import _norm_for_verbatim
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.jurisdiction import is_operator_side
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.section_index import resolve_sections

SEAT = "gemma4:26b-a4b-it-q4_K_M-ctx32k"


def _verdict(repo: Repository, contract: Any, entry: dict[str, Any]) -> tuple[str, str, str]:
    raw = str(entry.get("section_id", ""))
    found = contract.resolve(raw) if contract is not None else None
    section_id = found.section_id if found is not None else raw
    resolved = resolve_sections(repo, [section_id]).get(section_id)
    sentence = _norm_for_verbatim(str(entry.get("sentence", "")))
    if resolved is None:
        return "unresolved", raw, section_id
    if not is_operator_side(resolved.get("jurisdiction")):
        return "not_operator", raw, section_id
    if not sentence or sentence not in _norm_for_verbatim(str(resolved.get("text", ""))):
        return "not_verbatim", raw, section_id
    return "accepted", raw, section_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", default=SEAT)
    ap.add_argument("--standard", default="CIP-007-6")
    ap.add_argument("--prompt", type=Path, default=None)
    ap.add_argument("--refs", default="", help="semicolon-separated subset")
    args = ap.parse_args()

    repo = Repository()
    refs = sweep.refs_for_standard(Register.load(), args.standard)
    only = [r for r in args.refs.split(";") if r]
    if only:
        refs = [r for r in refs if r in only]
    fixed = reading_material.fixed_body(repo, args.standard)
    prompt_body, prompt_version, _sha = sweep.load_mapping_prompt(args.prompt)

    totals: Counter[str] = Counter()
    rows = []
    for ref in refs:
        started = time.time()
        payload = sweep.map_read(
            repo, ref, model=args.model, fixed=fixed, write=False, prompt_path=args.prompt
        )
        entries, parse_error = sweep.parse_determinations(payload.get("answer", "") or "")
        contract = reading_material.render(repo, ref, question=prompt_body, fixed=fixed).get(
            "contract"
        )
        error = parse_error or payload.get("failure") or payload.get("error") or ""
        totals["parse_errors"] += bool(error)
        scored = []
        for entry in entries:
            verdict, raw, section_id = _verdict(repo, contract, entry)
            totals["entries"] += 1
            totals[verdict] += 1
            scored.append(
                {
                    "raw_section": raw,
                    "section_id": section_id,
                    "relation": entry.get("relation_type"),
                    "verdict": verdict,
                }
            )
        rows.append(
            {
                "ref": ref,
                "wall_s": round(time.time() - started, 1),
                "parse_error": str(error),
                "workspace": payload.get("workspace"),
                "served_model": payload.get("served_model"),
                "entries": scored,
            }
        )
        print(
            ref, rows[-1]["wall_s"], [f"{e['verdict'][:4]}:{e['raw_section'][:16]}" for e in scored]
        )
    repo.close()
    report = {
        "model": args.model,
        "prompt_version": prompt_version,
        "standard": args.standard,
        "totals": dict(totals),
        "rows": rows,
    }
    args.out.write_text(json.dumps(report, indent=1))
    print("TOTALS", dict(totals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
