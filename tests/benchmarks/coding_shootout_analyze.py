#!/usr/bin/env python3
"""Portal 5 — Coding Shootout V2 Analyzer.

Reads a JSON file produced by tests/portal5_persona_matrix.py for the
auto-coding-bench workspace, and emits a per-shape × per-model
capability matrix. No verdict — the matrix is the deliverable. See
TASK_CODING_SHOOTOUT_V2.md §A6.

The matrix's rows are models; columns are persona shapes (REPL, Audit,
Composite, Ship-It). Each cell is the per-shape assertion-pass-rate for
that (model, shape). An "Overall" column averages over candidate-eligible
shapes (reference-only models are excluded from the Overall ranking per
§A5).

A V1 reconciliation row shows Laguna's V1 pass-rate (under bench-laguna's
Creative Coder framing) alongside Laguna's V2 per-shape pass-rates. The
gap is the finding.

Usage:
    python3 tests/benchmarks/coding_shootout_analyze.py \
        --input  tests/benchmarks/results/coding_shootout_v2_<UTC>.json \
        --output tests/benchmarks/results/coding_shootout_v2_<UTC>.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

INCUMBENT_MODEL_ID = "laguna-xs.2:q4_K_M"

# Memory hardcoded — same rationale as V1 analyzer.
MODEL_MEMORY_GB = {
    "laguna-xs.2:Q4_K_M": 19,
    "glm-4.7-flash:Q4_K_M": 15,
    "qwen3-coder:30b-a3b-q4_K_M": 19,
    "devstral-small-2": 15,
    # V9 candidates (TASK_V9_EVAL_EXTENDED)
    "hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M": 7,
    "hf.co/Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf": 19,
    "qwen3-coder-next": 46,
    "hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M": 46,
    # V4 fast-lane / reasoning probes (TASK_CODING_CAPABILITY_PROBE_V2)
    "lfm2.5:8b": 5,
    "granite4.1:8b": 5,
    "granite4.1:30b": 17,
    "hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL": 5,
    "hf.co/mradermacher/Josiefied-DeepSeek-R1-0528-Qwen3-8B-abliterated-v1-GGUF:Q4_K_M": 5,
    "hf.co/ijohn07/harness-1-Q4_K_M-GGUF:Q4_K_M": 12,
}

# V1's verdict reconciliation — Laguna's pass-rate under bench-laguna's
# Creative Coder framing. Drawn from TASK_CODING_SHOOTOUT_V1 results.
V1_LAGUNA_PASS_RATE = 0.939

SHAPE_ORDER = ("REPL", "Audit", "Composite", "Ship-It")


def _persona_shape_map_from_results(report: dict) -> dict[str, str]:
    """Best-effort recovery of persona→shape mapping.

    The matrix JSON does NOT carry the registry's persona_shapes dict, so
    we reconstruct it by reading WORKSPACE_REGISTRY at analyze-time. This
    couples the analyzer to the live registry, but that's intentional —
    the shapes are a labeling convention, not data.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from tests.portal5_persona_matrix import WORKSPACE_REGISTRY
    except Exception as exc:
        print(
            f"WARNING: could not import WORKSPACE_REGISTRY ({exc}); shape labels will be 'Unknown'",
            file=sys.stderr,
        )
        return {}
    entry = WORKSPACE_REGISTRY.get("auto-coding-bench", {})
    return dict(entry.get("persona_shapes", {}))


def _reference_models() -> set[str]:
    """Return the set of model IDs flagged as reference-only."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from tests.portal5_persona_matrix import WORKSPACE_REGISTRY
    except Exception:
        return set()
    entry = WORKSPACE_REGISTRY.get("auto-coding-bench", {})
    return set(entry.get("models_reference_only", ()))


def summarize_per_model_per_shape(
    report: dict,
    persona_shapes: dict[str, str],
) -> dict[str, dict[str, dict]]:
    """Aggregate matrix cells into per-(model, shape) stats.

    Returns: {
        model_id: {
            shape_name: {n_assertions, n_passed, pass_rate, n_scenarios, tps_samples},
            ...,
            "_overall": {...same keys, aggregated across non-empty shapes},
        }
    }
    """
    out: dict[str, dict[str, dict]] = {}
    for cell in report.get("cells", []):
        model = cell.get("model") or cell.get("model_id") or ""
        persona = cell.get("persona") or ""
        if not model or not persona:
            continue
        shape = persona_shapes.get(persona, "Unknown")
        m_entry = out.setdefault(model, {})
        s_entry = m_entry.setdefault(
            shape,
            {"n_assertions": 0, "n_passed": 0, "n_scenarios": 0, "tps_samples": []},
        )
        for sc in cell.get("scenarios", []):
            s_entry["n_scenarios"] += 1
            for a in sc.get("results", sc.get("assertions", [])):
                s_entry["n_assertions"] += 1
                if a.get("passed"):
                    s_entry["n_passed"] += 1
            tps = sc.get("tps")
            if isinstance(tps, (int, float)) and tps > 0:
                s_entry["tps_samples"].append(float(tps))

    # Compute pass_rates and overall rollup
    for model, shapes in out.items():
        overall = {"n_assertions": 0, "n_passed": 0, "n_scenarios": 0, "tps_samples": []}
        for shape, s in shapes.items():
            if shape == "_overall":
                continue
            s["pass_rate"] = (s["n_passed"] / s["n_assertions"]) if s["n_assertions"] else 0.0
            s["tps_median"] = statistics.median(s["tps_samples"]) if s["tps_samples"] else 0.0
            overall["n_assertions"] += s["n_assertions"]
            overall["n_passed"] += s["n_passed"]
            overall["n_scenarios"] += s["n_scenarios"]
            overall["tps_samples"].extend(s["tps_samples"])
        overall["pass_rate"] = (
            (overall["n_passed"] / overall["n_assertions"]) if overall["n_assertions"] else 0.0
        )
        overall["tps_median"] = (
            statistics.median(overall["tps_samples"]) if overall["tps_samples"] else 0.0
        )
        shapes["_overall"] = overall
    return out


def render_markdown(
    per_model: dict,
    sources: list[Path],
    reference: set[str],
    report_cells: list[dict] | None = None,
) -> str:
    lines: list[str] = []
    lines.append("# Coding Shootout V2 — Capability Matrix")
    lines.append("")
    source_names = ", ".join(p.name for p in sources)
    lines.append(f"**Source matrix run(s)**: `{source_names}`")
    lines.append("")
    lines.append("This matrix shows per-shape assertion-pass-rate for each model.")
    lines.append("No single-winner verdict — the matrix is the deliverable.")
    lines.append("See TASK_CODING_SHOOTOUT_V2.md §A6.")
    lines.append("")

    # Sort models: candidates by overall pass-rate desc, then reference models last.
    candidates = [m for m in per_model if m not in reference]
    references = [m for m in per_model if m in reference]
    candidates.sort(key=lambda m: -per_model[m]["_overall"]["pass_rate"])
    model_order = candidates + references

    lines.append("## Per-Shape Pass Rate")
    lines.append("")
    header = "| Model | " + " | ".join(SHAPE_ORDER) + " | Overall* | TPS (median) | Memory |"
    sep = "|---" * (len(SHAPE_ORDER) + 4) + "|"
    lines.append(header)
    lines.append(sep)
    for model in model_order:
        shapes = per_model[model]
        cells = []
        for shape in SHAPE_ORDER:
            s = shapes.get(shape)
            if s and s["n_assertions"]:
                cells.append(f"{s['pass_rate'] * 100:.1f}%")
            else:
                cells.append("—")
        overall = shapes["_overall"]
        flag = " (REF)" if model in reference else ""
        marker = " ◀ incumbent" if model == INCUMBENT_MODEL_ID else ""
        mem = MODEL_MEMORY_GB.get(model, "?")
        lines.append(
            f"| `{model}`{flag}{marker} | "
            + " | ".join(cells)
            + f" | {overall['pass_rate'] * 100:.1f}% | {overall['tps_median']:.1f} | {mem} GB |"
        )
    lines.append("")
    lines.append(
        "*Overall = aggregate across all shapes. Reference models are NOT in candidate ranking."
    )
    lines.append("")

    # V1 reconciliation
    laguna = per_model.get(INCUMBENT_MODEL_ID, {}).get("_overall", {})
    laguna_v2 = laguna.get("pass_rate", 0.0) * 100
    delta = (laguna.get("pass_rate", 0.0) - V1_LAGUNA_PASS_RATE) * 100
    lines.append("## V1 Reconciliation")
    lines.append("")
    lines.append(
        f"- Laguna under V1 (bench-laguna Creative Coder framing): "
        f"**{V1_LAGUNA_PASS_RATE * 100:.1f}%**"
    )
    lines.append(
        f"- Laguna under V2 (15 production personas across 4 shapes): **{laguna_v2:.1f}%**"
    )
    sign = "+" if delta >= 0 else ""
    lines.append(f"- Delta: **{sign}{delta:.1f} pp**")
    lines.append("")
    lines.append(
        "If the delta is sharply negative, V1's verdict (INCONCLUSIVE) was correct "
        "for V1's question (single-system-prompt control) but uninformative for "
        "production load. V2's per-shape decomposition is the right input to the "
        "next design conversation."
    )
    lines.append("")

    # Per-cell breakdown — useful for spot-checking and for the design conversation
    lines.append("## Per-Cell Detail")
    lines.append("")
    lines.append(
        "Drill-down per (model, persona, scenario). Each row's status reflects all "
        "assertions for that cell."
    )
    lines.append("")
    lines.append("| Model | Persona | Scenario | Pass | Total | Status |")
    lines.append("|---|---|---|---|---|---|")
    cells = (
        report_cells if report_cells is not None else source_cells(sources[0]) if sources else []
    )
    for cell in cells:
        model = cell.get("model", "?")
        persona = cell.get("persona", "?")
        for sc in cell.get("scenarios", []):
            results = sc.get("results", sc.get("assertions", []))
            n_pass = sum(1 for a in results if a.get("passed"))
            n_total = len(results)
            status = "PASS" if n_pass == n_total else "FAIL" if n_pass == 0 else "WARN"
            marker = {"PASS": "✓", "FAIL": "✗", "WARN": "~"}[status]
            lines.append(
                f"| `{model.split('/')[-1]}` | {persona} | "
                f"{sc.get('id', '?')} | {n_pass} | {n_total} | {marker} {status} |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Next Step")
    lines.append("")
    lines.append(
        "This matrix is INPUT to a workspace-decomposition design conversation, not "
        "a repin recommendation. Read the per-shape columns; identify whether one "
        "model dominates every shape (→ simple repin candidate) or whether different "
        "models win different shapes (→ workspace decomposition needed)."
    )
    lines.append("")
    lines.append(
        "The successor task (workspace decomposition or repin) is not generated by this script."
    )
    return "\n".join(lines) + "\n"


def source_cells(source_path: Path):
    """Re-load source JSON for per-cell detail (small overhead, keeps render pure)."""
    return json.load(source_path.open()).get("cells", [])


def _merge_reports(inputs: list[Path]) -> dict:
    """Merge multiple result JSONs. Cell identity is (model, persona, scenario_id).
    Later inputs win — they replace any earlier cell with the same identity.
    """
    merged_cells: dict[tuple[str, str, str], dict] = {}
    base_meta: dict = {}
    for p in inputs:
        r = json.load(p.open())
        if not base_meta:
            base_meta = {k: v for k, v in r.items() if k != "cells"}
        for cell in r.get("cells", []):
            model = cell.get("model", "")
            persona = cell.get("persona", "")
            scenarios = cell.get("scenarios", [])
            for sc in scenarios:
                key = (model, persona, sc.get("id", ""))
                merged_cells[key] = {
                    **{k: v for k, v in cell.items() if k != "scenarios"},
                    "scenarios": [sc],
                }
    # Re-aggregate scenarios back into per-(model, persona) cells
    by_mp: dict[tuple[str, str], dict] = {}
    for (model, persona, _), cell in merged_cells.items():
        mp = (model, persona)
        if mp not in by_mp:
            by_mp[mp] = {**cell, "scenarios": list(cell["scenarios"])}
        else:
            by_mp[mp]["scenarios"].extend(cell["scenarios"])
    return {**base_meta, "cells": list(by_mp.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # --input may be passed multiple times. Later inputs override earlier
    # ones for the same (model, persona, scenario) cell. Used by
    # TASK_V2_SCENARIO_FIXES_V1.md to apply fix-run cells on top of the
    # original V2 results without rewriting the original JSON.
    ap.add_argument("--input", required=True, type=Path, action="append")
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args(argv)

    for p in args.input:
        if not p.exists():
            print(f"input not found: {p}", file=sys.stderr)
            return 2

    report = _merge_reports(args.input)
    persona_shapes = _persona_shape_map_from_results(report)
    reference = _reference_models()
    per_model = summarize_per_model_per_shape(report, persona_shapes)
    if not per_model:
        print("no per-model data extracted — check matrix JSON shape", file=sys.stderr)
        return 3

    md = render_markdown(per_model, args.input, reference, report.get("cells"))
    args.output.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
