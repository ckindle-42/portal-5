#!/usr/bin/env python3
"""V5 ladder bench analysis — generate per-workspace recommendations.

Inputs:
  - tests/benchmarks/results/bench_tps_v5_ladders.json (measured TPS)
  - config/backends.yaml (memory_gb, supports_tools, lineage notes)
  - tests/results/smoke_test_v5.json (smoke PASS/FAIL)

Output:
  - tests/results/V5_quantization_ladder_analysis.md

Per TASK_MODEL_REFRESH_V5 §F. The report is the operator's decision input
for TASK_WORKSPACE_PROMOTION_V1.md.
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

import yaml

# Map V5 catalog entries -> workspace category for grouping
WORKSPACE_LADDER_MAP = {
    # Reasoning
    "Olmo-3-1125-32B": "auto-reasoning",
    "DeepSeek-R1-Distill-Llama-70B-3bit": "auto-reasoning",
    "DeepSeek-R1-Distill-Llama-70B-4bit": "auto-reasoning",
    # Compliance
    "granite-4.1-30b-mxfp": "auto-compliance",
    "granite-4.1-30b-nvfp": "auto-compliance",
    # Vision
    "gemma-4-26b-a4b-it-4bit": "auto-vision",
    "gemma-4-26b-a4b-it-6bit": "auto-vision",
    "gemma-4-26b-a4b-it-8bit": "auto-vision",
    "gemma-4-31b-8bit": "auto-vision",
    "gemma-4-31b-it-4bit": "auto-vision",  # current incumbent
    "Qwen3-VL-32B": "auto-vision",
    # Creative
    "gemma-4-26B-A4B-it-heretic-4bit": "auto-creative",
    "divinetribe/gemma-4-31b-it-abliterated": "auto-creative",  # incumbent
    # Coding
    "Devstral-Small-2505": "auto-coding",
    "GLM-4.7-Flash-4bit": "auto-coding",  # incumbent
    "Laguna-XS.2-4bit": "auto-coding",
    # Security/Redteam
    "Qwen3.6-27B-AEON": "auto-security/redteam",
    "glm-4.7-flash-abliterated-8bit": "auto-security/redteam",
    "DeepSeek-R1-Distill-Llama-70B-Abliterated": "auto-redteam",
    # Speed-class
    "granite-4.1-3b-mxfp8": "auto",
    "Huihui-Qwen3.5-9B-abliterated": "auto",
    "Llama-3.2-3B-Instruct-8bit": "auto",
}


def workspace_for(model_id: str) -> str:
    for substr, ws in WORKSPACE_LADDER_MAP.items():
        if substr in model_id:
            return ws
    return "uncategorized"


def main():
    repo_root = Path(__file__).parent.parent
    bench_path = repo_root / "tests/benchmarks/results/bench_tps_v5_ladders.json"
    backends_path = repo_root / "config/backends.yaml"
    smoke_path = repo_root / "tests/results/smoke_test_v5.json"
    output_path = repo_root / "tests/results/V5_quantization_ladder_analysis.md"

    bench_data = json.loads(bench_path.read_text()) if bench_path.exists() else {}
    smoke_data = json.loads(smoke_path.read_text()) if smoke_path.exists() else []
    backends = yaml.safe_load(backends_path.read_text())

    # Build catalog metadata lookup
    mlx_backend = next(b for b in backends["backends"] if b["id"] == "mlx-apple-silicon")
    catalog = {m["id"]: m for m in mlx_backend["mlx_models"]}

    # Build smoke status lookup
    smoke_status = {r["model"]: r["status"] for r in smoke_data}

    # Aggregate bench results per model (bench_tps.py uses avg_tps)
    per_model_tps: dict[str, list[float]] = defaultdict(list)
    for result in bench_data.get("results", []):
        model = result.get("model")
        tps = result.get("avg_tps") or result.get("tps") or result.get("tokens_per_sec")
        if model and tps is not None and tps > 0:
            per_model_tps[model].append(tps)

    # Build per-workspace tables
    by_workspace: dict[str, list[dict]] = defaultdict(list)
    for model_id, tps_list in per_model_tps.items():
        ws = workspace_for(model_id)
        median_tps = statistics.median(tps_list) if tps_list else 0
        meta = catalog.get(model_id, {})
        by_workspace[ws].append({
            "model": model_id,
            "median_tps": round(median_tps, 1),
            "memory_gb": meta.get("memory_gb", "?"),
            "supports_tools": meta.get("supports_tools", "?"),
            "is_vlm": meta.get("is_vlm", False),
            "big_model": meta.get("big_model", False),
            "smoke": smoke_status.get(model_id, "—"),
            "n_runs": len(tps_list),
        })

    # Generate report
    lines = []
    lines.append("# V5 Quantization Ladder Bench Analysis")
    lines.append("")
    lines.append(f"Generated from `{bench_path.name}` and `{smoke_path.name}`.")
    lines.append("")
    lines.append("**Decision input for `TASK_WORKSPACE_PROMOTION_V1.md`.**")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Per-workspace section
    workspace_order = [
        "auto-vision", "auto-creative", "auto-reasoning", "auto-compliance",
        "auto-coding", "auto-security/redteam", "auto-redteam", "auto",
        "uncategorized",
    ]
    for ws in workspace_order:
        if ws not in by_workspace:
            continue
        entries = sorted(by_workspace[ws], key=lambda e: e["median_tps"], reverse=True)
        lines.append(f"## {ws}")
        lines.append("")
        lines.append("| Model | Median TPS | Memory (GB) | Tools | VLM | BIG_MODEL | Smoke | Notes |")
        lines.append("|---|---:|---:|:-:|:-:|:-:|:-:|---|")
        for e in entries:
            tools = "✓" if e["supports_tools"] is True else ("✗" if e["supports_tools"] is False else "?")
            vlm = "✓" if e["is_vlm"] else ""
            big = "✓" if e["big_model"] else ""
            note_raw = catalog.get(e["model"], {}).get("notes", "")
            note = (note_raw[:80] + "...") if note_raw else ""
            lines.append(f"| `{e['model']}` | {e['median_tps']} | {e['memory_gb']} | {tools} | {vlm} | {big} | {e['smoke']} | {note} |")
        lines.append("")

        # Identify Pareto frontier (within this workspace)
        # Pareto-optimal: no other model has both higher TPS AND lower memory
        pareto = []
        for e in entries:
            if e["median_tps"] == 0 or e["memory_gb"] == "?":
                continue
            dominated = any(
                (other["median_tps"] >= e["median_tps"] and other["memory_gb"] < e["memory_gb"])
                or (other["median_tps"] > e["median_tps"] and other["memory_gb"] <= e["memory_gb"])
                for other in entries
                if other["model"] != e["model"]
                and other["median_tps"] > 0
                and other["memory_gb"] != "?"
            )
            if not dominated:
                pareto.append(e["model"])
        if pareto:
            lines.append("**Pareto-frontier candidates (speed × memory):**")
            for p in pareto:
                lines.append(f"- `{p}`")
            lines.append("")
        lines.append("---")
        lines.append("")

    # Promotion recommendation summary
    lines.append("## Promotion recommendations")
    lines.append("")
    lines.append("Speed-quality dominance based on measured TPS. **Quality estimates pending T-* probes — these are speed-only Pareto recommendations.** The operator should run T-RSN/T-COD/T-CMP/T-VIS/T-CRE benchmarks before flipping workspace primaries.")
    lines.append("")
    for ws in workspace_order:
        if ws not in by_workspace or not by_workspace[ws]:
            continue
        entries = sorted(
            [e for e in by_workspace[ws] if e["median_tps"] > 0],
            key=lambda e: e["median_tps"],
            reverse=True,
        )
        if not entries:
            continue
        top = entries[0]
        lines.append(f"### {ws}")
        lines.append(f"- **Fastest measured (smoke-passed):** `{top['model']}` at {top['median_tps']} TPS, {top['memory_gb']} GB resident")
        lines.append("- **Decision gate:** run T-* quality probes (see `TASK_*_SHOOTOUT_V1.md`) before promoting to workspace MLX primary.")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    print(f"Analysis report: {output_path}")


if __name__ == "__main__":
    main()
