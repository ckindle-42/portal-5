"""CLI orchestration.

Model-major loop: for each workspace, evict prior model, then run all
problems × both arms serially. Emits the matrix markdown + appends one
provenance ledger entry per run.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from portal.platform.inference.router.validation import _resolve_sampling_values
from portal.platform.wiki.provenance_ledger import append_entry
from tests.benchmarks.bench_repair.checkpoint import (
    append_samples,
    cell_done,
    checkpoint_path,
    load_checkpoint,
    samples_for_cell,
)
from tests.benchmarks.bench_repair.config import (
    ARM_ONESHOT,
    ARM_REPAIR,
    ONESHOT_N,
    REPAIR_N,
    TARGETS,
)
from tests.benchmarks.bench_repair.corpus import compute_gsha, load_corpus
from tests.benchmarks.bench_repair.report import render_matrix
from tests.benchmarks.bench_repair.runner import (
    SampleResult,
    evict_all,
    run_one_shot,
    run_repair,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"


def _omlx_alias_group(model_hint: str) -> str | None:
    backends = yaml.safe_load((REPO_ROOT / "config" / "backends.yaml").read_text())
    for backend in backends.get("backends", []):
        if backend.get("type") == "omlx" and model_hint in (backend.get("aliases") or {}):
            return backend.get("group", "?")
    return None


def _resolve_workspace(workspace: str) -> dict | None:
    d = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    ws = d.get("workspaces", {}).get(workspace)
    if not ws:
        print(
            f"WARNING: workspace not found in portal.yaml, skipping: {workspace}", file=sys.stderr
        )
        return None
    hint = ws.get("model_hint")
    if not hint:
        print(f"WARNING: workspace {workspace} has no model_hint, skipping", file=sys.stderr)
        return None
    omlx_group = _omlx_alias_group(hint)
    if omlx_group:
        print(
            f"NOTE: {workspace}'s model ({hint}) is oMLX-eligible in production "
            f"(group={omlx_group}, priority 10) — this harness is Ollama-only.",
            file=sys.stderr,
        )
    return {
        "model_hint": hint,
        "sampling": _resolve_sampling_values(ws),
        "think": ws.get("think"),
        "omlx_group": omlx_group,
    }


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Portal 5 repair-loop coding bench")
    ap.add_argument(
        "--models",
        default="",
        help="Comma-separated bench workspace slugs (default: 10 curated targets)",
    )
    ap.add_argument(
        "--problems",
        default="",
        help="Comma-separated problem IDs to include (default: all in corpus)",
    )
    ap.add_argument(
        "--output",
        default="",
        help=f"Output markdown path (default: {RESULTS_DIR}/BENCH_REPAIR_<UTC>.md)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan and exit without calling any model",
    )
    ap.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore/discard any existing checkpoint for this gsha and start over",
    )
    return ap.parse_args()


def _print_plan(
    workspaces: list[str],
    resolved: dict[str, dict],
    corpus: list[dict],
    gsha: str,
    ollama_version: str,
) -> None:
    print(f"bench_repair — gsha={gsha}")
    print(f"  workspaces ({len(workspaces)}):")
    for w in workspaces:
        r = resolved[w]
        think_note = f" think={r['think']}" if r["think"] is not None else ""
        print(f"    {w:32}  {r['model_hint']}{think_note}")
    print(f"  problems: {len(corpus)}  arms: one-shot(n=5) + repair(n=2)")
    print(f"  total samples: {len(workspaces) * len(corpus) * (5 + 2)}")
    print(f"  ollama_version: {ollama_version}")


def _run_cell(
    samples: list[SampleResult],
    *,
    ckpt_path: Path,
    gsha: str,
    ws: str,
    hint: str,
    sampling: dict,
    think: bool | None,
    prob: dict,
    arm: str,
    n: int,
    run_fn,
    label: str,
) -> list[SampleResult]:
    """Reuse checkpointed samples for this (ws, problem, arm) cell, else run + persist it."""
    if cell_done(samples, ws, prob["id"], arm, n):
        cell = samples_for_cell(samples, ws, prob["id"], arm)
        print(f"  {label}: skip (checkpointed)", end="", flush=True)
        return cell
    print(f"  {label}...", end="", flush=True)
    cell = run_fn(ws, hint, prob, sampling=sampling, think=think)
    samples.extend(cell)
    append_samples(ckpt_path, gsha, cell)
    return cell


def _run_all_workspaces(
    workspaces: list[str],
    resolved: dict[str, dict],
    corpus: list[dict],
    *,
    ckpt_path: Path,
    gsha: str,
) -> list[SampleResult]:
    samples: list[SampleResult] = load_checkpoint(ckpt_path)
    if samples:
        print(f"Resuming: {len(samples)} sample(s) already checkpointed at {ckpt_path}", flush=True)
    for mi, ws in enumerate(workspaces, 1):
        r = resolved[ws]
        hint = r["model_hint"]
        print(f"\n[{mi}/{len(workspaces)}] {ws}  ({hint})", flush=True)
        evict_all()  # kick prior residents
        t_ws_start = time.monotonic()
        for pi, prob in enumerate(corpus, 1):
            print(f"  [{pi}/{len(corpus)}] {prob['id']}", flush=True)
            os_samples = _run_cell(
                samples,
                ckpt_path=ckpt_path,
                gsha=gsha,
                ws=ws,
                hint=hint,
                sampling=r["sampling"],
                think=r["think"],
                prob=prob,
                arm=ARM_ONESHOT,
                n=ONESHOT_N,
                run_fn=run_one_shot,
                label="one-shot",
            )
            print(
                f" {sum(1 for s in os_samples if s.passed)}/{len(os_samples)}", end="", flush=True
            )
            rp_samples = _run_cell(
                samples,
                ckpt_path=ckpt_path,
                gsha=gsha,
                ws=ws,
                hint=hint,
                sampling=r["sampling"],
                think=r["think"],
                prob=prob,
                arm=ARM_REPAIR,
                n=REPAIR_N,
                run_fn=run_repair,
                label="repair",
            )
            print(f" {sum(1 for s in rp_samples if s.passed)}/{len(rp_samples)}", flush=True)
        print(f"  ── {ws} elapsed {(time.monotonic() - t_ws_start) / 60:.1f}m", flush=True)
    return samples


def _finalize_results(
    samples: list[SampleResult],
    *,
    gsha: str,
    breakdown: dict,
    corpus: list[dict],
    workspaces: list[str],
    output: str,
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = (
        Path(output)
        if output
        else (RESULTS_DIR / f"BENCH_REPAIR_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.md")
    )
    md = render_matrix(samples, gsha=gsha, breakdown=breakdown, corpus_size=len(corpus))
    out_path.write_text(md)
    print(f"Wrote {out_path}")

    append_entry(
        episode_id=f"bench_repair_{gsha}_{int(time.time())}",
        scenario=gsha,
        capability_verdict=f"corpus={len(corpus)}  models={len(workspaces)}  samples={len(samples)}",
        evidence_refs=[str(out_path.resolve().relative_to(REPO_ROOT))],
        event="bench_repair_run",
    )
    print("Appended provenance ledger entry")
    return out_path


def main() -> int:
    args = _parse_args()

    requested = [w.strip() for w in args.models.split(",") if w.strip()] or list(TARGETS)
    corpus = load_corpus()
    if args.problems:
        wanted = {p.strip() for p in args.problems.split(",")}
        corpus = [p for p in corpus if p["id"] in wanted]
    if not corpus:
        print("ERROR: no problems selected", file=sys.stderr)
        return 2

    gsha, breakdown = compute_gsha(corpus)
    resolved = {w: r for w in requested if (r := _resolve_workspace(w)) is not None}
    skipped = [w for w in requested if w not in resolved]
    if skipped:
        print(
            f"Skipped {len(skipped)} unresolvable workspace(s): {', '.join(skipped)}",
            file=sys.stderr,
        )
    workspaces = [w for w in requested if w in resolved]
    if not workspaces:
        print("ERROR: no requested workspace resolved against portal.yaml", file=sys.stderr)
        return 2
    _print_plan(workspaces, resolved, corpus, gsha, breakdown["ollama_version"])

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ckpt_path = checkpoint_path(RESULTS_DIR, gsha)
    if args.fresh and ckpt_path.exists():
        ckpt_path.unlink()
        print(f"--fresh: discarded checkpoint {ckpt_path}")

    if args.dry_run:
        print("(dry-run — no chat calls)")
        return 0

    t_run_start = time.monotonic()
    samples = _run_all_workspaces(workspaces, resolved, corpus, ckpt_path=ckpt_path, gsha=gsha)
    total_elapsed = time.monotonic() - t_run_start
    print(f"\nTotal elapsed: {total_elapsed / 60:.1f}m over {len(samples)} samples")

    _finalize_results(
        samples,
        gsha=gsha,
        breakdown=breakdown,
        corpus=corpus,
        workspaces=workspaces,
        output=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
