#!/usr/bin/env python3
"""SPLASH_SWEEP_ACCELERATION_V1 P3 - four-arm sweep throughput measurement.

The question is NOT "is splash faster than ollama". It is "does putting the
sweep on splash, concurrently, beat what we run today" - and those are two
changes at once. Four arms separate them:

    A  ollama-gemma4   sequential   the incumbent; re-measured, never cited
    B  splash-Qwen     sequential   engine effect alone
    C  splash-Qwen     concurrent   the proposal
    D  ollama-gemma4   concurrent   THE CONTROL

Arm D is the one that makes the others mean anything. Splash's bake-off
advantage was measured under concurrency; if Ollama also gains from
concurrency then C-over-A is partly a concurrency result wearing an engine's
name. Without D the attribution cannot be made, and a promotion decision on an
unattributed number is the "wrong instrument" failure this module has paid for
repeatedly.

Every row records the dialect name and the endpoint that served it, so no
measurement can be filed under an engine that did not produce it.

write=False throughout: this measures the READING, it does not admit
determinations. Quality comparison happens on what each arm WOULD write.

Usage:
    uv run python scripts/compliance/bench_sweep_engines.py \
        --standard CIP-007-6 --arms A,B,C,D \
        --ollama-model gemma4:26b-a4b-it-q4_K_M-ctx32k \
        --splash-model incoai/Qwen3.6-35B-A3B-Splash \
        --concurrency 4 \
        --out reports/compliance/splash_sweep/p3/arms.json
"""

from __future__ import annotations

import argparse
import concurrent.futures as _fut
import datetime as _dt
import hashlib
import json
import pathlib
import sys
import time
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import sweep as _sweep  # noqa: E402
from portal.modules.compliance.core.cip_register import Register  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402

ARMS: dict[str, dict[str, Any]] = {
    "A": {
        "dialect": "ollama-native",
        "concurrent": False,
        "label": "ollama sequential (incumbent)",
    },
    "B": {"dialect": "openai-compat", "concurrent": False, "label": "splash sequential"},
    "C": {"dialect": "openai-compat", "concurrent": True, "label": "splash concurrent (proposal)"},
    "D": {"dialect": "ollama-native", "concurrent": True, "label": "ollama concurrent (control)"},
}


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


def _sha256(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _refs(standard: str) -> list[str]:
    reg = Register.load()
    return sorted({n.id for n in reg.nodes if n.id.split(" ")[0] == standard})


def _triples(cell: dict[str, Any], contract: Any = None) -> set[tuple[str, str, str]]:
    """The (requirement, section, relation) set a cell WOULD write.

    ``map_read``'s own write=True path resolves a model-named citation handle
    (``[O3]``) to its real section_id via the answer's contract before it
    ever reaches ``record_determination`` (sweep.py, guarded by ``if
    write:``) — write=False never runs that branch, so this helper used to
    take the raw ``section_id`` field verbatim. A model citing by handle
    (routine since reading_material stopped printing the raw id beside the
    handle) produced a triple keyed on "O3", not the section it actually
    named — invisible in cell counts (n_determinations was always right) but
    silently corrupting every cross-arm/cross-run SET comparison this
    receipt makes (jaccard, precision-by-pairing) for as long as any model in
    the comparison used handles. Resolving through ``contract`` here matches
    what a write=True run would actually admit.
    """
    out: set[tuple[str, str, str]] = set()
    entries, _err = _sweep.parse_determinations(cell.get("answer", "") or "")
    for e in entries or []:
        req = str(e.get("requirement_id", "")).strip()
        raw_sec = str(e.get("section_id", "")).strip()
        rel = str(e.get("relation_type", "")).strip().upper()
        sec = raw_sec
        if contract is not None and raw_sec:
            found = contract.resolve(raw_sec)
            if found is not None:
                sec = found.section_id
        if req and sec and rel:
            out.add((req, sec, rel))
    return out


def _contract_for(repo: Any, ref: str) -> Any:
    """The same contract ``map_read`` builds internally, rebuilt here so
    write=False cells can resolve a citation handle the same way a write=True
    run would. Errors resolve to None: an unresolvable ref means every raw
    token in that cell's triples stays unresolved, which is a real "the
    model named something unrecognisable" fact, not a bug to swallow."""
    from portal.modules.compliance.core import reading_material

    try:
        standard = ref.split(" ")[0]
        fixed = reading_material.fixed_body(repo, standard)
        material = reading_material.render(repo, ref, fixed=fixed if "error" not in fixed else None)
        return material.get("contract")
    except Exception:  # noqa: BLE001 - contract build failure degrades to unresolved, not a crash
        return None


def _one(
    repo: Any,
    ref: str,
    model: str,
    dialect_name: str,
    num_ctx: int,
    timeout: int,
    answer_budget: int,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        cell = _sweep.map_read(
            repo,
            ref,
            model=model,
            dialect=dialect_name,
            num_ctx=num_ctx,
            answer_budget=answer_budget,
            timeout=timeout,
            write=False,
        )
    except Exception as exc:  # noqa: BLE001 - a failed cell is a recorded cell
        return {
            "ref": ref,
            "error": f"{type(exc).__name__}: {exc}",
            "wall_s": round(time.monotonic() - started, 2),
        }
    wall = round(time.monotonic() - started, 2)
    contract = _contract_for(repo, ref)
    triples = _triples(cell, contract)
    return {
        "ref": ref,
        "wall_s": wall,
        "dialect": cell.get("dialect", dialect_name),
        "endpoint": cell.get("endpoint", ""),
        "context_source": cell.get("context_source", ""),
        # map_read catches a transport failure internally and returns an
        # {"error": ...} dict rather than raising — that dict has none of the
        # keys below, so every accessor here defaults quietly and the cell
        # used to be counted as "ok" with null metrics. Surfacing cell's own
        # error is what makes _run_arm's `ok` filter and the receipt's
        # `unaccounted` list actually see the failure and why.
        "error": cell.get("error", ""),
        "prompt_eval_count": (cell.get("latency") or {}).get("prompt_eval_count"),
        "eval_count": (cell.get("latency") or {}).get("eval_count"),
        "prompt_eval_duration_s": (cell.get("latency") or {}).get("prompt_eval_duration_s"),
        "n_determinations": len(triples),
        "triples": sorted(triples),
        "failed": bool(cell.get("failed")),
        "failure": cell.get("failure", ""),
        "verification": cell.get("verification"),
    }


def _run_arm(
    arm: str,
    refs: list[str],
    model: str,
    concurrency: int,
    num_ctx: int,
    timeout: int,
    answer_budget: int,
) -> dict[str, Any]:
    spec = ARMS[arm]
    repo = Repository()
    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    try:
        if spec["concurrent"]:
            # Each worker gets its own Repository: sqlite connections are not
            # shared across threads, and a shared one here would corrupt the
            # measurement with lock contention that has nothing to do with the
            # engine under test.
            def _task(ref: str) -> dict[str, Any]:
                r = Repository()
                try:
                    return _one(r, ref, model, spec["dialect"], num_ctx, timeout, answer_budget)
                finally:
                    r.close()

            with _fut.ThreadPoolExecutor(max_workers=concurrency) as pool:
                rows = list(pool.map(_task, refs))
        else:
            rows = [
                _one(repo, ref, model, spec["dialect"], num_ctx, timeout, answer_budget)
                for ref in refs
            ]
    finally:
        repo.close()
    wall = round(time.monotonic() - started, 2)

    ok = [r for r in rows if not r.get("error") and not r.get("failed")]
    endpoints = sorted({r.get("endpoint", "") for r in rows if r.get("endpoint")})
    # An unearned measurement is an error, not a value: a cell that COMPLETED
    # (no transport error, no parse failure) but reports no prompt-token count
    # was not measured, even though it looks like a normal row. Recording it
    # as 0 is how a receipt asserts a measurement that never happened.
    unaccounted = sorted(r["ref"] for r in ok if r.get("prompt_eval_count") is None)
    return {
        "arm": arm,
        "label": spec["label"],
        "dialect": spec["dialect"],
        "concurrent": spec["concurrent"],
        "concurrency": concurrency if spec["concurrent"] else 1,
        "model": model,
        "endpoints_observed": endpoints,
        "n_refs": len(refs),
        "n_ok": len(ok),
        "n_error": sum(1 for r in rows if r.get("error")),
        "n_parse_failed": sum(1 for r in rows if r.get("failed")),
        "unaccounted": unaccounted,
        "total_wall_s": wall,
        "per_ref_wall_s": round(wall / len(refs), 2) if refs else None,
        "mean_cell_wall_s": (round(sum(r["wall_s"] for r in ok) / len(ok), 2) if ok else None),
        "determinations_total": sum(r.get("n_determinations", 0) for r in ok),
        "rows": rows,
    }


def _jaccard(a: set[Any], b: set[Any]) -> float | None:
    if not a and not b:
        return None
    return round(len(a & b) / len(a | b), 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--standard", default="CIP-007-6")
    ap.add_argument("--arms", default="A,B,C,D")
    ap.add_argument("--ollama-model", required=True)
    ap.add_argument("--splash-model", required=True)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--num-ctx", type=int, default=32768)
    ap.add_argument("--answer-budget", type=int, default=3072)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    refs = _refs(args.standard)
    if not refs:
        print(f"FAIL: no register nodes for {args.standard}", file=sys.stderr)
        return 3

    wanted = [a.strip().upper() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in wanted if a not in ARMS]
    if unknown:
        print(f"FAIL: unknown arms {unknown}; known {sorted(ARMS)}", file=sys.stderr)
        return 3

    results: dict[str, Any] = {}
    for arm in wanted:
        model = args.splash_model if ARMS[arm]["dialect"] == "openai-compat" else args.ollama_model
        print(f"== arm {arm}: {ARMS[arm]['label']} ({model}) ==")
        results[arm] = _run_arm(
            arm, refs, model, args.concurrency, args.num_ctx, args.timeout, args.answer_budget
        )
        r = results[arm]
        print(
            f"   {r['n_ok']}/{r['n_refs']} ok, {r['total_wall_s']}s "
            f"({r['per_ref_wall_s']}s/ref), {r['determinations_total']} determinations"
        )
        # Endpoint integrity: an arm whose rows came from the wrong endpoint is
        # a mislabeled measurement, and mislabeled measurements are how this
        # decision goes wrong. Say it loudly, keep the data, refuse to score it.
        if len(r["endpoints_observed"]) > 1:
            print(f"   WARN: arm {arm} saw multiple endpoints: {r['endpoints_observed']}")

    # Quality comparison against arm A's reading, when A ran
    comparison: dict[str, Any] = {}
    if "A" in results:
        base_triples = {tuple(t) for row in results["A"]["rows"] for t in row.get("triples", [])}
        for arm, res in results.items():
            if arm == "A":
                continue
            arm_triples = {tuple(t) for row in res["rows"] for t in row.get("triples", [])}
            comparison[arm] = {
                "jaccard_vs_A": _jaccard(base_triples, arm_triples),
                "n_triples": len(arm_triples),
                "n_triples_A": len(base_triples),
                "only_in_arm": sorted(arm_triples - base_triples)[:50],
                "only_in_A": sorted(base_triples - arm_triples)[:50],
                "speedup_vs_A": (
                    round(results["A"]["total_wall_s"] / res["total_wall_s"], 3)
                    if res["total_wall_s"]
                    else None
                ),
            }

    receipt = {
        "run_id": _now(),
        "script_sha256": _sha256(pathlib.Path(__file__)),
        "standard": args.standard,
        "n_refs": len(refs),
        "concurrency": args.concurrency,
        "num_ctx_requested": args.num_ctx,
        "answer_budget": args.answer_budget,
        "arms": results,
        "comparison_vs_A": comparison,
        "attribution_note": (
            "speedup_vs_A for arm C mixes the engine change and the concurrency "
            "change. Arm D isolates concurrency on the incumbent engine and arm B "
            "isolates the engine at concurrency 1. The engine's own contribution "
            "is C/D, not C/A."
        ),
        "verdict": "RECORDED",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"\nWROTE {args.out}")
    if "C" in results and "D" in results and results["D"]["total_wall_s"]:
        print(
            f"engine-attributable speedup C/D: "
            f"{results['C']['total_wall_s'] and round(results['D']['total_wall_s'] / results['C']['total_wall_s'], 3)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
