"""One-off driver for the agentic blue eval sweep (arms x models x scenarios).

Not part of the CLI surface -- run directly: python3 -m tests.benchmarks.bench_security._sweep_driver
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from tests.benchmarks.bench_security.agentic_blue_eval import run_eval

MODELS = ["granite4.1:8b-ctx8k", "gpt-oss:20b", "huihui_ai/qwen3.5-abliterated:9b"]
SCENARIOS = ["kerberoast_to_da", "asrep_to_lateral", "meta3_ftp_backdoor"]
ARMS = ["raw", "tools", "harness"]

OUT_PATH = Path("/tmp/agentic_blue_sweep.json")


def main() -> None:
    results: list[dict] = []
    if OUT_PATH.exists():
        results = json.loads(OUT_PATH.read_text())
    done = {(r["scenario"], r["model"]) for r in results}

    total = len(MODELS) * len(SCENARIOS)
    i = 0
    for scenario in SCENARIOS:
        for model in MODELS:
            i += 1
            if (scenario, model) in done:
                print(f"[{i}/{total}] SKIP (already done) {scenario} x {model}")
                continue
            print(f"[{i}/{total}] RUNNING {scenario} x {model} ...", flush=True)
            t0 = time.monotonic()
            result = run_eval(scenario, model=model, arms=ARMS)
            result["_wall_s"] = round(time.monotonic() - t0, 1)
            results.append(result)
            OUT_PATH.write_text(json.dumps(results, indent=2))
            print(f"[{i}/{total}] DONE {scenario} x {model} in {result['_wall_s']}s", flush=True)

    print(f"Sweep complete: {len(results)} results written to {OUT_PATH}")


if __name__ == "__main__":
    main()
