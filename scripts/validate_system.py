#!/usr/bin/env python3
"""Portal 5 system validation — fast smoke check before launching the full
acceptance / UAT / bench passes.

Run from repo root:
    python3 scripts/validate_system.py
    python3 scripts/validate_system.py --verbose
    python3 scripts/validate_system.py --skip-pytest    # skip the unit run
    python3 scripts/validate_system.py --skip-lifespan  # skip lifespan
    python3 scripts/validate_system.py --json           # machine-readable

Exit codes:
    0   — all checks passed
    1   — one or more checks failed (see output for which)
    2   — script setup error (missing deps, wrong cwd)

This script does NOT require a live Ollama / Open WebUI / Docker stack.
It validates:

    A. Python import surface — every public package imports cleanly
    B. Pipeline assembly — FastAPI app instantiates, all 9 routes present
    C. Config round-trip — portal.yaml loads via PortalConfig
    D. Rule 6 cross-check — workspaces ↔ backends.yaml ↔ WORKSPACES dict
    E. Hint validator — _validate_workspace_hints returns 0 errors
    F. Lifespan startup — async context manager enters + exits cleanly
    G. CLI introspection — portal --help, config show, models list, validate
    H. Unit test suite — pytest tests/unit -q (excluding env-only files)
    I. Shim contract — historical router_pipe imports all resolve
    Y. Self-index integrity — read-only signal aggregation, deterministic ranking
    Z. CI parity — bench imports without PYTHONPATH, conftest lab defaults, ci_local.sh
    AA. Live exec integrity — vulhub->host dispatch, DISPATCH_NOT_RUN guard
    AB. Stage 2 propose integrity — bounded proposals, proof-gated promotion,
        no hollow flag-flip, no writes without operator --apply

Designed to run in under 60 seconds on the M4 Pro Mac Mini. Use this as
the gate before kicking off the full long-running suites:

    python3 scripts/validate_system.py && \
    python3 tests/portal5_acceptance_v6.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# ── Setup ─────────────────────────────────────────────────────────────────────
# Bootstrap the repo root onto sys.path so the scripts.validation package can be
# imported (the package's own _shared.py REPO_ROOT is the same value).
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.validation import all_checks  # noqa: E402
from scripts.validation.blue_orchestration import (  # noqa: E402, F401
    check_barrier_tools_gate,
    check_benign_alert_fatigue,
    check_blue_orchestration_axis,
    check_budget_backward_compat,
    check_budget_starve_reaches_expert,
    check_challenge_reality,
    check_council_agreement_gate,
    check_council_bench_semantics,
    check_council_participation_floor,
    check_fleet_health_reality,
    check_mentor_discipline,
    check_model_inventory_reality,
    check_multichain_consolidation_gate,
    check_notify_scoreboard_semantics,
    check_perception_lab_scope,
    check_recall_attribution_boundary,
    check_recall_metric,
    check_single_council_quorum,
    check_subtechnique_discriminator_gate,
    check_trajectory_scoring_honesty,
)
from scripts.validation.config import check_config_loads, check_rule_6  # noqa: E402, F401
from scripts.validation.inference import (  # noqa: E402, F401
    check_cli_introspection,
    check_hint_validator,
    check_imports,
    check_lifespan,
    check_pipeline_assembles,
    check_unit_tests,
)
from scripts.validation.lab import (  # noqa: E402, F401
    check_lab_setup_readiness,
    check_lab_target_catalog,
)
from scripts.validation.personas import (  # noqa: E402, F401
    check_alias_ratchet,
    check_eval_workspace_config_hygiene,
    check_mcp_module_tag,
    check_persona_intent,
    check_persona_module_tag,
    check_persona_prompt_uniqueness,
    check_routing_regression,
    check_workspace_module_tag,
)
from scripts.validation.platform import check_agent_core  # noqa: E402, F401
from scripts.validation.security_bench import (  # noqa: E402, F401
    check_ability_port,
    check_bench_parallel_dispatch_safety,
    check_bench_security_catalog,
    check_bench_supervisor_integrity,
    check_candidate_eval_integrity,
    check_capability_graph,
    check_capability_index,
    check_ci_parity,
    check_coverage_expansion_integrity,
    check_drift_gate,
    check_goal_decide_dryrun,
    check_kali_rescore_integrity,
    check_labexec_coverage,
    check_live_exec_integrity,
    check_loop_dry_run,
    check_no_undefined_names,
    check_oracle_registry_consistency,
    check_persona_workspace_resolution,
    check_playbook_validation,
    check_rbp_evidence_grounding,
    check_scenario_oracle_matrix,
    check_self_index_integrity,
    check_shim_contract,
    check_stage2_propose_integrity,
    check_telemetry_contracts,
    check_triage_layer2_integrity,
    check_uat_catalog_no_stale_refs,
    check_valid_workspaces_resolve,
)
from scripts.validation.telemetry import check_complexity_census  # noqa: E402, F401
from scripts.validation.wiki import (  # noqa: E402, F401
    check_archive_reachability,
    check_spine_code_coverage,
    check_spine_drift,
    check_wiki_core,
    check_wiki_facts_current,
)


# ── Result tracking ───────────────────────────────────────────────────────────
@dataclass
class CheckResult:
    name: str
    status: str  # "PASS" | "FAIL" | "SKIP" | "WARN"
    detail: str = ""
    elapsed_ms: int = 0
    sub_results: list[dict] = field(default_factory=list)


class Validator:
    def __init__(self, *, verbose: bool = False, emit_json: bool = False):
        self.verbose = verbose
        self.emit_json = emit_json
        self.results: list[CheckResult] = []
        self.started_at = time.time()

    def run(self, name: str, fn: Callable[[], tuple[str, str, list[dict]]]) -> CheckResult:
        """Run a single check. fn returns (status, detail, sub_results)."""
        t0 = time.time()
        try:
            if self.emit_json:
                # In --json mode the only output must be the JSON document. Some
                # checks (lab-setup readiness, detector self-tests) print to
                # stdout directly; capture and discard it so the emitted JSON is
                # parseable.
                import contextlib
                import io

                with contextlib.redirect_stdout(io.StringIO()):
                    status, detail, sub = fn()
            else:
                status, detail, sub = fn()
        except Exception as e:
            status, detail, sub = "FAIL", f"{type(e).__name__}: {e}", []
        elapsed_ms = int((time.time() - t0) * 1000)
        r = CheckResult(
            name=name, status=status, detail=detail, elapsed_ms=elapsed_ms, sub_results=sub
        )
        self.results.append(r)
        if not self.emit_json:
            self._emit(r)
        return r

    def _emit(self, r: CheckResult) -> None:
        icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "○", "WARN": "!"}[r.status]
        timing = f"({r.elapsed_ms:>4d}ms)"
        line = f"  {icon} {r.name:<32s} {timing}"
        if r.detail and (self.verbose or r.status != "PASS"):
            line += f"  — {r.detail}"
        print(line, file=sys.stderr if r.status == "FAIL" else sys.stdout)
        if self.verbose and r.sub_results:
            for sub in r.sub_results:
                sub_icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "○", "WARN": "!"}.get(
                    sub.get("status", ""), "·"
                )
                print(f"      {sub_icon} {sub.get('name', '?')}: {sub.get('detail', '')}")

    def summary(self) -> int:
        passes = sum(1 for r in self.results if r.status == "PASS")
        fails = sum(1 for r in self.results if r.status == "FAIL")
        warns = sum(1 for r in self.results if r.status == "WARN")
        skips = sum(1 for r in self.results if r.status == "SKIP")
        total_ms = int((time.time() - self.started_at) * 1000)

        if self.emit_json:
            print(
                json.dumps(
                    {
                        "elapsed_ms": total_ms,
                        "passes": passes,
                        "fails": fails,
                        "warns": warns,
                        "skips": skips,
                        "results": [
                            {
                                "name": r.name,
                                "status": r.status,
                                "detail": r.detail,
                                "elapsed_ms": r.elapsed_ms,
                                "sub_results": r.sub_results,
                            }
                            for r in self.results
                        ],
                    },
                    indent=2,
                )
            )
        else:
            print()
            print(
                f"  {passes} pass · {fails} fail · {warns} warn · {skips} skip"
                f"  ({total_ms}ms total)"
            )
            if fails:
                print(
                    "  ⚠  System validation FAILED — fix the above before running"
                    " acceptance / UAT / bench suites.",
                    file=sys.stderr,
                )
            else:
                print("  ✓ System validation passed — ready for full test suites.")

        return 1 if fails else 0


# ── Main ──────────────────────────────────────────────────────────────────────
# The registry owns the check inventory and its canonical order. F/G/H (lifespan,
# CLI introspection, unit-test suite) are the three checks gated by --skip-* flags;
# they are registered like every other check and wrapped here based on argv so the
# --json output is byte-identical to the pre-registry harness.


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Portal 5 system validation — pre-flight check before "
        "running the full acceptance / UAT / bench suites.",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Print sub-check details")
    parser.add_argument(
        "--skip-pytest",
        action="store_true",
        help="Skip the pytest tests/unit invocation (saves ~15s)",
    )
    parser.add_argument(
        "--skip-lifespan", action="store_true", help="Skip the lifespan check (saves ~5s)"
    )
    parser.add_argument(
        "--skip-cli", action="store_true", help="Skip CLI subprocess checks (saves ~10s)"
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable output"
    )
    args = parser.parse_args()

    v = Validator(verbose=args.verbose, emit_json=args.json)

    if not args.json:
        print(f"Portal 5 system validation — {REPO_ROOT}")
        print()

    skip = {
        "lifespan": args.skip_lifespan,
        "cli": args.skip_cli,
        "unit_tests": args.skip_pytest,
    }
    skip_detail = {
        "lifespan": "--skip-lifespan",
        "cli": "--skip-cli",
        "unit_tests": "--skip-pytest",
    }
    for slug, label, fn in all_checks():
        if skip.get(slug):
            v.run(label, lambda d=skip_detail[slug]: ("SKIP", d, []))
        else:
            v.run(label, fn)

    return v.summary()


if __name__ == "__main__":
    sys.exit(main())
