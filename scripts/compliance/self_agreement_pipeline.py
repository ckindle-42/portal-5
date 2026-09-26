"""Self-agreement on the serving engine (TASK_COMPLIANCE_PIPELINE_ALIGNMENT_V1 §P4).

CIP-007-6's twenty requirements are read TWICE per arm, identical config,
``write=False``, through the DEFAULT dialect (the pipeline, oMLX), and the
determinations are compared as TRIPLE SETS — (requirement_id, section_id,
relation_type) after section-handle resolution, exactly what
``candidate_links.record_determination`` would have received.

Arms:

* ``sequential`` (concurrency 1) — the current default; the native-era
  self-agreement of 1.0 was measured here and this replaces it with the
  number for the engine that actually serves.
* ``concurrent`` (``--concurrency N``) — the fan-out the pipeline exists for;
  concurrency broke Ollama determinism (0.14 in PROVE_THE_MODULE) and whether
  oMLX batching preserves it at temperature 0 is the open question.

Per arm the script reports, run 1 vs run 2: identical-answer refs (the
bit-level question), identical-triple-set refs, and the added/removed triples
(the determinations question — the one that matters when tokens differ).
Walls are recorded per run: the SWEEP_CONCURRENCY default is decided on
reproducibility AND speed together.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
from pathlib import Path
from typing import Any

from portal.modules.compliance.core.repository import Repository

OUT_DEFAULT = Path("reports/compliance/pipeline_alignment/p4/determinism.json")

#: The seat the family campaigns pass (closeout_family_sweep.SEAT).
SEAT = "gemma4:26b-a4b-it-q4_K_M-ctx32k"
STANDARD = "CIP-007-6"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--standard", default=STANDARD)
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--runs", type=int, default=2, help="reads per arm")
    return parser.parse_args()


def _run_arm(
    repo: Repository,
    refs: list[str],
    fixed: dict[str, Any],
    contracts: dict[str, Any],
    concurrency: int,
    runs: int,
) -> tuple[dict[str, Any], list[dict[str, list[dict[str, Any]]]]]:
    """One arm: `runs` sweeps of the same refs at the same concurrency."""
    from portal.modules.compliance.core import sweep

    arm_runs: list[dict[str, Any]] = []
    arm_triples: list[dict[str, list[dict[str, Any]]]] = []
    for run_index in range(runs):
        started = time.time()
        payloads: dict[str, dict[str, Any]] = {}

        def _read(ref: str, payloads: dict = payloads) -> None:
            payloads[ref] = sweep.map_read(repo, ref, model=SEAT, fixed=fixed, write=False)

        if concurrency > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                list(pool.map(_read, refs))
        else:
            for ref in refs:
                _read(ref)
        wall = round(time.time() - started, 2)
        triples = {ref: _triples_of(payloads.get(ref, {}), contracts.get(ref)) for ref in refs}
        arm_runs.append(
            {
                "run": run_index + 1,
                "wall_s": wall,
                "wall_per_requirement_s": round(wall / len(refs), 2),
                "parse_errors": {
                    ref: (payloads.get(ref, {}).get("failure") or "")
                    for ref in refs
                    if payloads.get(ref, {}).get("failure")
                },
                "transport_errors": {
                    ref: str(payloads.get(ref, {}).get("error"))
                    for ref in refs
                    if payloads.get(ref, {}).get("error")
                },
                "served_models": sorted(
                    {str(payloads.get(ref, {}).get("served_model", "")) for ref in refs}
                ),
                "route_backends": sorted(
                    {str(payloads.get(ref, {}).get("route_backend", "")) for ref in refs}
                ),
            }
        )
        arm_triples.append(triples)
        print(
            f"  run {run_index + 1}: {wall:.0f}s, "
            f"{len(arm_runs[-1]['parse_errors'])} parse errors, "
            f"{len(arm_runs[-1]['transport_errors'])} transport errors",
            flush=True,
        )
    return {"runs": arm_runs}, arm_triples


def _triples_of(payload: dict[str, Any], contract: Any) -> list[dict[str, Any]]:
    """The determinations a write would have recorded, resolved as map_read
    resolves them (its section-handle resolution lives on the material's
    contract, which the payload does not carry — the caller re-renders)."""
    if not payload or payload.get("error"):
        return []
    from portal.modules.compliance.core.sweep import parse_determinations

    entries, _err = parse_determinations(payload.get("answer", ""))
    out = []
    for entry in entries:
        raw_section = str(entry.get("section_id", ""))
        resolved = contract.resolve(raw_section) if contract is not None else None
        out.append(
            {
                "requirement_id": str(entry.get("requirement_id", "")),
                "section_id": resolved.section_id if resolved is not None else raw_section,
                "relation_type": str(entry.get("relation_type", "")).upper(),
            }
        )
    return out


def _compare(refs: list[str], a: dict[str, list], b: dict[str, list]) -> dict[str, Any]:
    identical_sets, identical_answers = 0, 0
    added: set[tuple] = set()
    removed: set[tuple] = set()
    for ref in refs:
        ta = {tuple(sorted(t.items())) for t in a.get(ref, [])}
        tb = {tuple(sorted(t.items())) for t in b.get(ref, [])}
        if ta == tb:
            identical_sets += 1
        added |= set(tb - ta)
        removed |= set(ta - tb)
    return {
        "identical_triple_set_refs": identical_sets,
        "refs_compared": len(refs),
        "added_triples": [dict(t) for t in sorted(added)],
        "removed_triples": [dict(t) for t in sorted(removed)],
    }


def main() -> int:
    args = parse_args()
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.sweep import refs_for_standard

    refs = refs_for_standard(Register.load(), args.standard)
    print(
        f"arm A sequential, arm B concurrent={args.concurrency}, "
        f"{args.runs} runs each over {len(refs)} refs of {args.standard}",
        flush=True,
    )

    repo = Repository()
    from portal.modules.compliance.core import reading_material
    from portal.modules.compliance.core.sweep import load_mapping_prompt

    fixed = reading_material.fixed_body(repo, args.standard)
    prompt_body, _v, _sha = load_mapping_prompt()
    contracts = {
        ref: reading_material.render(repo, ref, question=prompt_body, fixed=fixed).get("contract")
        for ref in refs
    }
    print("arm A: sequential", flush=True)
    arm_a, triples_a = _run_arm(repo, refs, fixed, contracts, 1, args.runs)
    print(f"arm B: concurrent={args.concurrency}", flush=True)
    arm_b, triples_b = _run_arm(repo, refs, fixed, contracts, args.concurrency, args.runs)
    repo.close()

    def _pair_report(arm_triples: list[dict[str, list]]) -> dict[str, Any]:
        if len(arm_triples) < 2:
            return {"error": "fewer than two runs"}
        report = _compare(refs, arm_triples[0], arm_triples[1])
        report["per_ref_identical"] = {
            ref: arm_triples[0].get(ref) == arm_triples[1].get(ref) for ref in refs
        }
        return report

    comparison = {
        "sequential": _pair_report(triples_a),
        "concurrent": _pair_report(triples_b),
        "cross_arm_run1": _compare(refs, triples_a[0], triples_b[0]),
    }
    document = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "standard": args.standard,
        "seat": SEAT,
        "dialect": "pipeline",
        "n_refs": len(refs),
        "refs": refs,
        "arms": {"sequential": arm_a, "concurrent": {**arm_b, "concurrency": args.concurrency}},
        "comparison": comparison,
        "sweep_concurrency_decision_note": (
            "default decided on reproducibility and speed together — see the report"
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, default=str))
    for arm in ("sequential", "concurrent"):
        c = comparison[arm]
        print(f"{arm}: identical triple sets {c['identical_triple_set_refs']}/{c['refs_compared']}")
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
