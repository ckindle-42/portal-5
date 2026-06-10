#!/usr/bin/env python3
"""Dashboard generator for the positional recall benchmark.

Reads recall result JSON(s) and writes config/grafana/dashboards/portal5_recall.json
with text panels showing per-model position-bucket pass-rates, lost-in-middle deltas,
and per-function detail.

Mirrors scripts/update_grafana_benchmarks.py in style: HTML text panels, color scale,
stable panel IDs for idempotent regeneration (A6).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_PATH = REPO_ROOT / "config" / "grafana" / "dashboards" / "portal5_recall.json"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"


def _color_for_rate(rate: float) -> str:
    """Green→red color scale for pass-rates."""
    if rate >= 0.8:
        return "#73BF69"
    elif rate >= 0.5:
        return "#FFD700"
    return "#F2495C"


def _load_results(input_path: str | None = None) -> list[dict[str, Any]]:
    """Load recall results from file or latest recall_all_*.json."""
    if input_path:
        try:
            data = json.loads(Path(input_path).read_text())
        except (json.JSONDecodeError, OSError):
            print(f"No valid JSON at {input_path} — treating as no data", file=sys.stderr)
            return []
        if "models" in data:
            return data["models"]
        if isinstance(data, dict) and "model" in data:
            return [data]
        return []

    # Find latest
    results = sorted(RESULTS_DIR.glob("recall_all_*.json"), reverse=True)
    if not results:
        results = sorted(RESULTS_DIR.glob("recall_*.json"), reverse=True)
    if not results:
        print("No recall result files found", file=sys.stderr)
        return []

    print(f"Loading: {results[0].name}", file=sys.stderr)
    data = json.loads(results[0].read_text())
    if "models" in data:
        return data["models"]
    if isinstance(data, dict) and "model" in data:
        return [data]
    return []


def _build_summary_panel(models: list[dict[str, Any]]) -> str:
    if not models:
        return "<div style='text-align:center;color:#888;padding:20px'>No recall results yet. Run bench_positional_recall.py --all-longctx.</div>"

    n = len(models)
    mean_overall = sum(m["overall"]["pass_rate"] for m in models) / n if n else 0
    worst_lim = max(m["lost_in_middle_delta"] for m in models) if n else 0
    best_model = max(models, key=lambda m: m["overall"]["pass_rate"])
    worst_model = max(models, key=lambda m: m["lost_in_middle_delta"])

    config = models[0] if models else {}
    return (
        "<div style='display:flex;justify-content:space-around;align-items:center;"
        "height:100%;text-align:center;font-size:14px'>"
        f"<div><div style='font-size:28px;font-weight:bold;color:#73BF69'>{n}</div>"
        "<div style='color:#aaa'>Models Tested</div></div>"
        f"<div><div style='font-size:28px;font-weight:bold;color:#FFD700'>{mean_overall:.2f}</div>"
        "<div style='color:#aaa'>Mean Pass-Rate</div></div>"
        f"<div><div style='font-size:28px;font-weight:bold;color:#F2495C'>{worst_lim:.2f}</div>"
        "<div style='color:#aaa'>Max LIM-delta</div></div>"
        f"<div><div style='font-size:28px;font-weight:bold;color:#73BF69'>{best_model['model'].split('/')[-1][:20]}</div>"
        f"<div style='color:#aaa'>Best ({best_model['overall']['pass_rate']:.2f})</div></div>"
        f"<div><div style='font-size:28px;font-weight:bold;color:#F2CC0C'>{worst_model['model'].split('/')[-1][:20]}</div>"
        f"<div style='color:#aaa'>Worst LIM ({worst_model['lost_in_middle_delta']:.2f})</div></div>"
        f"<div><div style='font-size:11px;color:#888'>k={config.get('k','?')}</div>"
        f"<div style='font-size:11px;color:#888'>seed={config.get('seed','?')}</div></div>"
        "</div>"
    )


def _build_postion_table(models: list[dict[str, Any]]) -> str:
    if not models:
        return "<div style='text-align:center;color:#888;padding:20px'>No data</div>"

    rows: list[str] = []
    rows.append(
        "<tr style='background:#1f1f1f;position:sticky;top:0'>"
        "<th style='text-align:left'>Model</th>"
        "<th style='text-align:left'>max KV</th>"
        "<th style='text-align:left'>Front PR</th>"
        "<th style='text-align:left'>Mid PR</th>"
        "<th style='text-align:left'>Tail PR</th>"
        "<th style='text-align:left'>Overall</th>"
        "<th style='text-align:left'>LIM-delta</th>"
        "</tr>"
    )

    for i, m in enumerate(models):
        bg = "" if i % 2 == 0 else " style='background:#1a1a2e'"
        bb = m["by_bucket"]
        fpr = bb["front"]["pass_rate"]
        mpr = bb["middle"]["pass_rate"]
        tpr = bb["tail"]["pass_rate"]
        lim = m["lost_in_middle_delta"]
        name = m["model"].split("/")[-1]
        rows.append(
            f"<tr{bg}>"
            f"<td style='font-family:monospace;font-weight:bold'>{name[:40]}</td>"
            f"<td style='color:#888'>{m['max_kv_size']:,}</td>"
            f"<td><span style='color:{_color_for_rate(fpr)};font-weight:bold'>{fpr:.2f}</span>"
            f" ({bb['front']['mean_recall']:.2f})</td>"
            f"<td><span style='color:{_color_for_rate(mpr)};font-weight:bold'>{mpr:.2f}</span>"
            f" ({bb['middle']['mean_recall']:.2f})</td>"
            f"<td><span style='color:{_color_for_rate(tpr)};font-weight:bold'>{tpr:.2f}</span>"
            f" ({bb['tail']['mean_recall']:.2f})</td>"
            f"<td><span style='color:{_color_for_rate(m['overall']['pass_rate'])};font-weight:bold'>"
            f"{m['overall']['pass_rate']:.2f}</span></td>"
            f"<td><span style='color:{_color_for_rate(1-lims/1.0) if (lims := abs(lim)) < 1 else '#F2495C'};"
            f"font-weight:bold'>{lim:+.2f}</span></td>"
            f"</tr>"
        )

    return (
        "<div style='overflow:auto;max-height:500px'>"
        f"<table style='width:100%;border-collapse:collapse;font-size:11px'>"
        f"{''.join(rows)}</table></div>"
    )


def _build_methodology_panel(models: list[dict[str, Any]]) -> str:
    m = models[0] if models else {}
    return (
        "<div style='font-size:11px;color:#888;padding:4px 8px;line-height:1.5'>"
        "<b>Method:</b> LCS line-alignment verbatim recall under long context, "
        "adapted from github.com/alexziskind1/codeneedle (Alex Ziskind). "
        "Each model is tested at its configured max_kv_size. Functions are sampled "
        f"from real Portal 5 source files, stratified by position bucket."
        f"&nbsp; &nbsp; <b>k={m.get('k','?')}</b> &nbsp; <b>n_lines={m.get('n_lines','?')}</b> "
        f"&nbsp; <b>pass_threshold={m.get('pass_threshold','?')}</b>"
        "<br><b>Complements</b> bench_kv_long_context.py (physical survival) "
        "by measuring <i>usefulness</i> at the ceiling. "
        "Evidence for future max_kv_size decisions — no ceilings changed by this bench."
        "</div>"
    )


def regenerate(input_path: str | None = None) -> None:
    models = _load_results(input_path)

    skeleton = json.loads(DASHBOARD_PATH.read_text())

    content_by_id = {
        1: _build_summary_panel(models),
        2: _build_methodology_panel(models),
        10: _build_postion_table(models),
    }

    for panel in skeleton["panels"]:
        pid = panel.get("id")
        if pid in content_by_id:
            panel["options"]["content"] = content_by_id[pid]

    DASHBOARD_PATH.write_text(json.dumps(skeleton, indent=2, ensure_ascii=False))
    print(f"Dashboard regenerated: {DASHBOARD_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate the positional recall Grafana dashboard")
    parser.add_argument("--input", help="Path to recall result JSON (default: latest recall_all_*.json)")
    args = parser.parse_args()
    regenerate(args.input)


if __name__ == "__main__":
    main()
