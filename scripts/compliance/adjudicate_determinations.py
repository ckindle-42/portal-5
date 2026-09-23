#!/usr/bin/env python3
"""TASK_COMPLIANCE_PROVE_THE_MODULE_V1 P1 - extract every reading-derived edge
for adjudication by the coding agent, and fold judged verdicts back into the
module's first real precision number.

Two-step because the judge is the agent reading, not a script:

  --extract  walks every relationship_assertions row whose derivation
             contains "reading" (status='machine_determined' -> DETERMINED,
             corroborated rows with derivation 'reading' or
             'projection_rerank|reading' -> CORROBORATED) and writes each
             one's requirement text, section text, relation, and cited
             sentence(s) to --out as a judgeable unit. Writes nothing to the
             store.

  --fold     reads --verdicts (a JSON list of
             {assertion_id, verdict, quote, wrong_relation?} produced by the
             agent reading --out) and computes precision overall and per
             standard, writing the final receipt to --out.

Verdict values: SUPPORTED | UNSUPPORTED | WRONG_RELATION.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _standard_of(ref: str) -> str:
    return str(ref).split(" ")[0]


def _carry_for(unit: dict[str, Any], prior: dict[str, Any] | None) -> dict[str, Any] | None:
    """A prior verdict carries to this unit only when the claim it judged is
    unchanged: the same assertion (requirement, section, relation) and either
    the identical cited-sentence set, or a SUPPORTED verdict whose sentences are
    all still cited — a sentence added by corroboration cannot un-support a
    relation the old sentence already supported, while it CAN support one that
    was judged unsupported, so those are re-read. Everything else is judged
    fresh."""
    if prior is None:
        return None
    before = {str(x) for x in prior.get("cited_sentences") or []}
    now = {str(x) for x in unit.get("cited_sentences") or []}
    same = before == now
    widened_supported = prior.get("verdict") == "SUPPORTED" and before <= now
    if not (same or widened_supported):
        return None
    return {
        "verdict": prior.get("verdict"),
        "quote": prior.get("quote", ""),
        "wrong_relation": prior.get("wrong_relation_should_be"),
        "rule": "identical_sentences" if same else "supported_sentences_still_cited",
    }


def _extract(
    derivation_filter: str,
    out: pathlib.Path,
    *,
    only: set[str] | None = None,
    carry_from: dict[str, dict[str, Any]] | None = None,
) -> None:
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.repository import Repository
    from portal.modules.compliance.core.section_index import parent_section_id, resolve_sections

    reg = Register.load()
    req_text = {n.id: n.verbatim_text for n in reg.nodes}

    def _requirement_text_for(ref: str) -> tuple[str, bool]:
        """Exact register hit, else a synthesized concat of the Part-granular
        children under this requirement-level ref (the register has no
        requirement-level node for some standards — Parts only). ``synthesized``
        is carried through to the adjudication unit so the agent judging it
        knows the text was assembled, not a single verbatim node."""
        if ref in req_text and req_text[ref]:
            return req_text[ref], False
        # "CIP-003-8 Attachment 1 Section 5" -> "CIP-003-8 Attachment 1 Part 5"
        alt = ref.replace(" Section ", " Part ")
        if alt in req_text and req_text[alt]:
            return req_text[alt], False
        prefix = (alt if alt != ref else ref) + " Part "
        children = sorted(
            (n for n in reg.nodes if n.id.startswith(prefix) and n.verbatim_text),
            key=lambda n: n.id,
        )
        if children:
            return "\n".join(f"[{n.id}] {n.verbatim_text}" for n in children), True
        return "", False

    repo = Repository()
    try:
        rows = repo._conn.execute(
            """SELECT assertion_id, relation_type, src_ref, dst_ref, status,
                      derivation, citations_json
               FROM relationship_assertions
               WHERE valid_to IS NULL
                 AND (
                   (status = 'machine_determined' AND derivation LIKE '%reading%')
                   OR (status != 'machine_determined' AND
                       (derivation = 'reading' OR derivation = 'projection_rerank|reading'))
                 )
               ORDER BY src_ref, dst_ref""",
        ).fetchall()

        section_ids = sorted({parent_section_id(str(r["dst_ref"])) for r in rows})
        sections = resolve_sections(repo, section_ids)

        units: list[dict[str, Any]] = []
        for r in rows:
            if only is not None and str(r["assertion_id"]) not in only:
                continue
            src_ref = str(r["src_ref"])
            dst_ref = str(r["dst_ref"])
            citations = json.loads(r["citations_json"] or "[]")
            sentences = [c.get("sentence", "") for c in citations if c.get("sentence")]
            sec = sections.get(parent_section_id(dst_ref)) or {}
            rtext, synth = _requirement_text_for(src_ref)
            units.append(
                {
                    "assertion_id": r["assertion_id"],
                    "standard": _standard_of(src_ref),
                    "derivation_kind": "DETERMINED"
                    if r["status"] == "machine_determined"
                    else "CORROBORATED",
                    "status": r["status"],
                    "relation_type": r["relation_type"],
                    "requirement_id": src_ref,
                    "requirement_text": rtext,
                    "requirement_text_synthesized": synth,
                    "section_id": dst_ref,
                    "section_text": sec.get("text", ""),
                    "cited_sentences": sentences,
                    "n_citations": len(citations),
                }
            )
            if carry_from is not None:
                carried = _carry_for(units[-1], carry_from.get(str(r["assertion_id"])))
                if carried is not None:
                    units[-1]["carried"] = carried
    finally:
        repo.close()

    out.parent.mkdir(parents=True, exist_ok=True)
    n_carried = sum(1 for u in units if "carried" in u)
    out.write_text(
        json.dumps(
            {"n_units": len(units), "n_carried": n_carried, "units": units}, indent=2, default=str
        )
    )
    print(f"WROTE {out}  ({len(units)} units, {len(units) - n_carried} to adjudicate fresh)")
    missing_req = sum(1 for u in units if not u["requirement_text"])
    missing_sec = sum(1 for u in units if not u["section_text"])
    if missing_req or missing_sec:
        print(
            f"  WARN: {missing_req} units missing requirement text, {missing_sec} missing section text"
        )


def _fold(units_path: pathlib.Path, verdicts_path: pathlib.Path, out: pathlib.Path) -> None:
    units = {u["assertion_id"]: u for u in json.loads(units_path.read_text())["units"]}
    verdicts = json.loads(verdicts_path.read_text())
    if isinstance(verdicts, dict):
        verdicts = verdicts.get("verdicts", verdicts)

    rows: list[dict[str, Any]] = []
    seen = set()
    # a fresh verdict always wins; a carried one fills only what was not re-judged
    fresh_ids = {v["assertion_id"] for v in verdicts}
    verdicts = list(verdicts) + [
        {"assertion_id": aid, **u["carried"], "_carried": True}
        for aid, u in units.items()
        if "carried" in u and aid not in fresh_ids
    ]
    for v in verdicts:
        aid = v["assertion_id"]
        seen.add(aid)
        u = units.get(aid)
        if u is None:
            continue
        rows.append(
            {
                **u,
                "verdict": v["verdict"],
                "quote": v.get("quote", ""),
                "wrong_relation_should_be": v.get("wrong_relation"),
                "verdict_source": "carried" if v.get("_carried") else "fresh",
            }
        )

    missing = [aid for aid in units if aid not in seen]

    per_standard: dict[str, dict[str, int]] = {}
    for r in rows:
        s = per_standard.setdefault(
            r["standard"], {"n": 0, "supported": 0, "wrong_relation": 0, "unsupported": 0}
        )
        s["n"] += 1
        if r["verdict"] == "SUPPORTED":
            s["supported"] += 1
        elif r["verdict"] == "WRONG_RELATION":
            s["wrong_relation"] += 1
        else:
            s["unsupported"] += 1

    per_standard_list = []
    for standard, s in sorted(per_standard.items()):
        precision = round(s["supported"] / s["n"], 4) if s["n"] else None
        per_standard_list.append({"standard": standard, "precision": precision, **s})

    n_total = len(rows)
    n_supported = sum(1 for r in rows if r["verdict"] == "SUPPORTED")
    precision = round(n_supported / n_total, 4) if n_total else None

    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "n_total": n_total,
        "n_carried": sum(1 for r in rows if r.get("verdict_source") == "carried"),
        "n_missing_verdict": len(missing),
        "missing_assertion_ids": missing,
        "precision": precision,
        "supported": n_supported,
        "wrong_relation": sum(1 for r in rows if r["verdict"] == "WRONG_RELATION"),
        "unsupported": sum(1 for r in rows if r["verdict"] == "UNSUPPORTED"),
        "per_standard": per_standard_list,
        "rows": rows,
        "method": (
            "Each edge adjudicated by the coding agent reading the requirement text, "
            "the operator section text, and the cited sentence, against the question: "
            "is this relation supported by the cited sentence, read against the "
            "requirement? This replaces agreement()'s n=11 as the module's quality "
            "number."
        ),
        "verdict": "RECORDED",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"WROTE {out}")
    print(f"adjudicated {n_total}  precision={precision}")
    for s in sorted(
        per_standard_list, key=lambda x: x["precision"] if x["precision"] is not None else -1
    ):
        print(
            f"  {s['standard']:16s} n={s['n']:3d} supported={s['supported']:3d} "
            f"wrong_relation={s['wrong_relation']:3d} unsupported={s['unsupported']:3d} "
            f"precision={s['precision']}"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--derivation", default="machine_determined")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--extract", action="store_true", help="write judgeable units to --out")
    ap.add_argument(
        "--fold", action="store_true", help="fold --verdicts into the final receipt at --out"
    )
    ap.add_argument(
        "--units",
        type=pathlib.Path,
        help="units file for --fold (default: --out's *_units.json sibling)",
    )
    ap.add_argument("--verdicts", type=pathlib.Path, help="agent verdicts JSON for --fold")
    ap.add_argument(
        "--assertions",
        type=pathlib.Path,
        help="--extract only these assertions: a sweep_edge_set.py receipt "
        "(affirmed_assertion_ids) or a JSON list of ids",
    )
    ap.add_argument(
        "--carry",
        type=pathlib.Path,
        help="--extract: a prior adjudication receipt whose verdicts carry to unchanged claims",
    )
    args = ap.parse_args()

    if args.fold:
        units_path = args.units or args.out.with_name(args.out.stem + "_units.json")
        if not args.verdicts:
            print("FAIL: --fold requires --verdicts", file=sys.stderr)
            return 3
        _fold(units_path, args.verdicts, args.out)
        return 0

    # default / --extract: write units next to --out
    units_out = args.out.with_name(args.out.stem + "_units.json")
    only: set[str] | None = None
    if args.assertions:
        loaded = json.loads(args.assertions.read_text())
        only = set(loaded["affirmed_assertion_ids"] if isinstance(loaded, dict) else loaded)
    carry_from = None
    if args.carry:
        carry_from = {r["assertion_id"]: r for r in json.loads(args.carry.read_text())["rows"]}
    _extract(args.derivation, units_out, only=only, carry_from=carry_from)
    return 0


if __name__ == "__main__":
    sys.exit(main())
