"""Crash-safe incremental JSON result persistence for bench runs.

Extracted byte-for-byte from tests/benchmarks/bench_tps.py.
"""

import json
import os
from datetime import UTC, datetime

from .config import OLLAMA_URL, PIPELINE_URL, RESULTS_DIR


def _init_output(
    output_path: str, args, hw: dict, ollama_cfg, workspaces_cfg, personas_cfg
) -> dict:
    """Initialize or load the output file. Returns the output dict."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if os.path.exists(output_path):
        try:
            with open(output_path) as f:
                existing = json.load(f)
            if existing.get("results"):
                print(
                    f"  Resuming from {len(existing['results'])} existing results in {output_path}"
                )
                return existing
        except Exception:
            pass
    output = {
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": args.mode,
        "order": args.order,
        "cooldown_s": args.cooldown,
        "runs_per_model": args.runs,
        "spec_decoding": args.spec_decoding_tag or "unspecified",
        "kv_quant_tag": args.kv_quant_tag or "unspecified",
        "total_wall_time_s": 0,
        "hardware": hw,
        "config_summary": {
            "ollama_models_configured": len(ollama_cfg),
            "workspaces_configured": len(workspaces_cfg),
            "personas_configured": len(personas_cfg),
        },
        "backends": {
            "ollama": {"url": OLLAMA_URL},
            "pipeline": {"url": PIPELINE_URL},
        },
        "results": [],
    }
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    return output


def _append_result(output_path: str, result: dict) -> None:
    """Append a single result to the output JSON file (crash-safe)."""
    try:
        with open(output_path) as f:
            data = json.load(f)
        data["results"].append(result)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"    ⚠️  Failed to save result: {e}")


def _result_already_done(output_path: str, match_key: str, match_value: str) -> bool:
    """Check if a result for this model/workspace/persona already exists."""
    try:
        with open(output_path) as f:
            data = json.load(f)
        return any(
            r.get(match_key) == match_value and r.get("runs_success", 0) > 0
            for r in data.get("results", [])
        )
    except Exception:
        return False
