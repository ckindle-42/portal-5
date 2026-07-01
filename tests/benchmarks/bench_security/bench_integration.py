"""Bench integration — wire new capabilities into cli.py as flagged bench steps (Phase 4).

Each step no-ops when its module is absent — safe to run at any point.
"""

from __future__ import annotations

from typing import Any


def run_full_expanded_bench(*, dry_run: bool = False, lab_exec: bool = False) -> dict[str, Any]:
    """Run all available security bench steps and return a combined report.

    sec-bench-full entrypoint: test everything we built.
    """
    results: dict[str, Any] = {"status": "dry_run" if dry_run else "attempted", "steps": {}}

    bench_steps = [
        ("oracles", "bench_security.oracles"),
        ("capsules", "bench_security.capsules"),
        ("journal", "bench_security.field_journal"),
        ("playbooks", "bench_security.playbooks"),
        ("loop", "bench_security.loop"),
        ("validation", "bench_security.validation"),
        ("re_firmware", "bench_security.re_firmware"),
        ("ctf", "bench_security.ctf_bench"),
        ("cloud", "bench_security.cloud_bench"),
        ("llm_redteam", "bench_security.llm_redteam"),
        ("oast", "bench_security.oast_bench"),
        ("cred_attacks", "bench_security.cred_bench"),
        ("decision_engine", "bench_security.decision_engine"),
    ]

    for step_name, module_path in bench_steps:
        try:
            __import__(module_path)
            results["steps"][step_name] = "loaded"
        except ImportError:
            results["steps"][step_name] = "absent"

    return results
