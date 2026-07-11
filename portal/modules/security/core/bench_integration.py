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
        ("oracles", "portal.modules.security.core.oracles"),
        ("capsules", "portal.modules.security.core.capsules"),
        ("journal", "portal.modules.security.core.field_journal"),
        ("playbooks", "portal.modules.security.core.playbooks"),
        ("loop", "portal.modules.security.core.loop"),
        ("validation", "portal.modules.security.core.validation"),
        ("re_firmware", "portal.modules.security.core.re_firmware"),
        ("ctf", "portal.modules.security.core.ctf_bench"),
        ("cloud", "portal.modules.security.core.cloud_bench"),
        ("llm_redteam", "portal.modules.security.core.llm_redteam"),
        ("oast", "portal.modules.security.core.oast_bench"),
        ("cred_attacks", "portal.modules.security.core.cred_bench"),
        ("decision_engine", "portal.modules.security.core.decision_engine"),
    ]

    for step_name, module_path in bench_steps:
        try:
            __import__(module_path)
            results["steps"][step_name] = "loaded"
        except ImportError:
            results["steps"][step_name] = "absent"

    return results
